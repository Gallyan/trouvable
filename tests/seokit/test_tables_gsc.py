import io
import unittest
import zipfile

from tests.support import LIB  # noqa: F401

from seokit import gsc
from seokit.tables import TableError, parse_number, read_tables_bytes


def make_xlsx(rows):
    shared = []
    sheet_rows = []

    for r, row in enumerate(rows, start=1):
        cells = []

        for c, value in enumerate(row):
            ref = f"{chr(65 + c)}{r}"

            if isinstance(value, str):
                shared.append(value)
                cells.append(f'<c r="{ref}" t="s"><v>{len(shared) - 1}</v></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')

        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml",
                         f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                         'relationships">'
                         '<sheets><sheet name="Requêtes" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels",
                         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/sharedStrings.xml",
                         f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>")
        archive.writestr("xl/worksheets/sheet1.xml",
                         f'<worksheet {ns}><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>')

    return buffer.getvalue()


class NumberTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_number("1,234"), 1234)
        self.assertEqual(parse_number("1 234"), 1234)
        self.assertAlmostEqual(parse_number("12,5 %"), 0.125)
        self.assertAlmostEqual(parse_number("3.4%"), 0.034)
        self.assertAlmostEqual(parse_number("7,9"), 7.9)
        self.assertIsNone(parse_number("abc"))


class TablesTest(unittest.TestCase):
    def test_csv_semicolon(self):
        tables = read_tables_bytes("Requête;Clics;Impressions;CTR;Position\nfoo;3;100;3 %;8,2\n".encode(), "q.csv")

        self.assertEqual(tables[0].rows[0][0], "foo")

    def test_xlsx(self):
        data = make_xlsx([["Top queries", "Clicks", "Impressions", "CTR", "Position"], ["foo", 3, 100, "3%", 8.2]])
        tables = read_tables_bytes(data, "export.xlsx")

        self.assertEqual(tables[0].name, "Requêtes")
        self.assertEqual(tables[0].rows[0], ["foo", "3", "100", "3%", "8.2"])

    def test_nul_bytes_raise_table_error(self):
        with self.assertRaises(TableError):
            read_tables_bytes(b"a,b\n\x00\x01,2\n", "bad.csv")

    def test_zip_bomb_refused(self):
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("Queries.csv", "a," * 2_000_000)

        with self.assertRaises(TableError):
            read_tables_bytes(buffer.getvalue(), "bomb.zip")


NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def sheet_xlsx(sheet_xml, sheet_entries=1):
    buffer = io.BytesIO()
    sheets = "".join(f'<sheet name="s{i}" sheetId="{i}" r:id="rId1"/>' for i in range(sheet_entries))

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml",
                         f'<workbook {NS} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                         'relationships">'
                         f'<sheets>{sheets}</sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels",
                         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return buffer.getvalue()


def cell_sheet(ref):
    return (f'<worksheet {NS}><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>h</t></is></c></row>'
            f'<row r="2"><c r="{ref}" t="inlineStr"><is><t>x</t></is></c></row></sheetData></worksheet>')


class HostileTablesTest(unittest.TestCase):
    def test_column_beyond_xfd_is_refused(self):
        for ref in ("ZZZZZZZ2", "ZZZZ2", "XFE2"):
            with self.assertRaises(TableError):
                read_tables_bytes(sheet_xlsx(cell_sheet(ref)), "export.xlsx")

        table = read_tables_bytes(sheet_xlsx(cell_sheet("XFD2")), "export.xlsx")[0]
        self.assertEqual(len(table.rows[0]), 16384)

    def test_repeated_sheet_entries_read_once(self):
        tables = read_tables_bytes(sheet_xlsx(cell_sheet("B2"), sheet_entries=50), "export.xlsx")

        self.assertEqual(len(tables), 1)

    def test_nested_workbooks_share_one_budget(self):
        from unittest import mock

        from seokit import tables as tables_mod

        inner = sheet_xlsx(cell_sheet("B2"))
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w") as archive:
            for i in range(5):
                archive.writestr(f"export{i}.xlsx", inner)

        declared = sum(info.file_size for info in zipfile.ZipFile(io.BytesIO(inner)).infolist())

        with mock.patch.object(tables_mod, "MAX_TOTAL_UNCOMPRESSED", declared * 3):
            with self.assertRaises(TableError):
                read_tables_bytes(buffer.getvalue(), "export.zip")

    def test_malformed_parts_raise_table_error(self):
        broken_xml = sheet_xlsx(f"<worksheet {NS}><sheetData><row>")
        doctype = sheet_xlsx(f'<!DOCTYPE x [<!ENTITY a "b">]><worksheet {NS}/>')
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("nested.xlsx", b"not a zip at all")

        for data in (broken_xml, doctype, buffer.getvalue()):
            with self.assertRaises(TableError):
                read_tables_bytes(data, "export.zip")


class GscDetectTest(unittest.TestCase):
    def test_english_headers(self):
        tables = read_tables_bytes(b"Top queries,Clicks,Impressions,CTR,Position\nfoo,3,100,3%,8.2\n", "Queries.csv")
        result = gsc.detect(tables[0])

        self.assertEqual(result.kind, "query")
        self.assertEqual(result.rows[0]["impressions"], 100)

    def test_unknown_language_by_content(self):
        text = "Xyz,Aaa,Bbb,Ccc,Ddd\nfoo,3,100,3 %,8.2\nbar,0,40,0 %,15.5\n"
        result = gsc.detect(read_tables_bytes(text.encode(), "q.csv")[0])

        self.assertEqual(result.columns, {"ctr": "Ccc", "position": "Ddd", "clicks": "Aaa", "impressions": "Bbb"})
        self.assertEqual(result.kind, "query-or-other")

    def test_pages_by_content(self):
        text = "Xyz,Aaa,Bbb,Ccc,Ddd\nhttps://x.test/a,3,100,3%,8.2\n"
        result = gsc.detect(read_tables_bytes(text.encode(), "p.csv")[0])

        self.assertEqual(result.kind, "page")


if __name__ == "__main__":
    unittest.main()
