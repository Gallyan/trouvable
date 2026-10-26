"""Hardening left open by the security audit of 2026-10-25: a response that drips bytes is cut
at a wall-clock deadline, and a sitemap index cannot send the run to another host."""

import io
import socket
import threading
import time
import unittest
import zipfile

from tests.support import LocalSite

from seokit import sitemap, tables
from seokit import fetch
from seokit.fetch import Fetcher


class DripServer:
    """Sends `head` then `drip` every `pause` seconds (default: a 200 whose body drips)."""

    def __init__(self, pause: float, head: bytes = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                 b"Content-Length: 1000\r\n\r\n", drip: bytes = b"x") -> None:
        self.pause = pause
        self.head = head
        self.drip = drip
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def serve(self) -> None:
        conn, _ = self.sock.accept()

        with conn:
            conn.recv(4096)
            conn.sendall(self.head)

            while not self.stop.is_set():
                try:
                    conn.sendall(self.drip)
                except OSError:
                    return

                time.sleep(self.pause)

    def __enter__(self) -> "DripServer":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop.set()
        self.sock.close()

    def url(self) -> str:
        return f"http://127.0.0.1:{self.sock.getsockname()[1]}/"


class DeadlineTest(unittest.TestCase):
    def test_dripping_body_is_cut_at_the_deadline(self):
        fetcher = Fetcher(delay=0, timeout=5, deadline=0.5, respect_robots=False, allow_private=True)

        with DripServer(pause=0.05) as server:
            started = time.monotonic()
            response = fetcher.get(server.url())

        self.assertLess(time.monotonic() - started, 3)
        self.assertIn("more than 0.5 s", response.error)
        self.assertEqual(response.body, b"")

    def test_dripping_headers_are_cut_at_the_deadline(self):
        fetcher = Fetcher(delay=0, timeout=5, deadline=0.5, respect_robots=False, allow_private=True)

        with DripServer(0.05, head=b"HTTP/1.1 200 OK\r\nX-Drip: ", drip=b"a") as server:
            started = time.monotonic()
            response = fetcher.get(server.url())

        self.assertLess(time.monotonic() - started, 3)
        self.assertIn("more than 0.5 s", response.error)

    def test_dripping_chunk_trailers_are_cut_at_the_deadline(self):
        fetcher = Fetcher(delay=0, timeout=5, deadline=0.5, respect_robots=False, allow_private=True)
        head = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Type: text/html\r\n\r\n2\r\nok\r\n0\r\n"

        with DripServer(0.05, head=head, drip=b"T: a\r\n") as server:
            started = time.monotonic()
            response = fetcher.get(server.url())

        self.assertLess(time.monotonic() - started, 3)
        self.assertIn("more than 0.5 s", response.error)

    def test_normal_body_is_read_whole(self):
        body = b"<p>" + b"a" * 200_000 + b"</p>"

        with LocalSite({"/": (200, {"Content-Type": "text/html"}, body)}) as site:
            response = Fetcher(delay=0, respect_robots=False, allow_private=True).get(site.url("/"))

        self.assertIsNone(response.error)
        self.assertEqual(response.body, body)


class EmbeddedIpv4Test(unittest.TestCase):
    def test_ipv6_forms_carrying_a_private_ipv4_are_refused(self):
        for address in ("64:ff9b::7f00:1", "64:ff9b::a9fe:a9fe", "64:ff9b::a00:1", "::127.0.0.1", "::ffff:0:7f00:1",
                        "::ffff:0:a9fe:a9fe", "::1", "::", "64:ff9b:1::7f00:1", "64:ff9b:1:7f00:1::",
                        "2002:7f00:1::1", "2002:a9fe:a9fe::1", "2002:808:808::1"):
            self.assertTrue(fetch._blocked_address(address), address)

    def test_ipv6_forms_carrying_a_public_ipv4_stay_allowed(self):
        for address in ("64:ff9b::808:808", "2001:4860:4860::8888", "8.8.8.8"):
            self.assertFalse(fetch._blocked_address(address), address)

    def test_literal_nat64_host_is_refused_before_connecting(self):
        response = Fetcher(delay=0, allow_private=False).get("http://[64:ff9b::7f00:1]:9/", check_robots=False)

        self.assertEqual(response.error, fetch.PRIVATE_REFUSED)


class SitemapHostTest(unittest.TestCase):
    def test_child_on_another_host_is_not_fetched(self):
        index = (b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                 b"<sitemap><loc>{base}/own.xml</loc></sitemap>"
                 b"<sitemap><loc>http://other.example/evil.xml</loc></sitemap></sitemapindex>")
        own = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{base}/a</loc></url></urlset>'
        routes = {
            "/robots.txt": (404, {}, b""),
            "/index.xml": (200, {"Content-Type": "application/xml"}, index),
            "/own.xml": (200, {"Content-Type": "application/xml"}, own),
        }

        with LocalSite(routes) as site:
            result = sitemap.load(Fetcher(delay=0, allow_private=True), [site.url("/index.xml")])

        self.assertEqual([entry.loc for entry in result.urls], [site.url("/a")])
        self.assertTrue(any("another host" in error for error in result.errors))


class CsvWidthTest(unittest.TestCase):
    def test_row_wider_than_a_workbook_is_refused(self):
        with self.assertRaises(tables.TableError):
            tables.read_csv_text("a,b\n" + "x," * (tables.MAX_COLUMNS + 1) + "\n")

    def test_cell_budget_truncates(self):
        original = tables.MAX_CELLS
        tables.MAX_CELLS = 10

        try:
            table = tables.read_csv_text("a,b\n" + "1,2\n" * 20)
        finally:
            tables.MAX_CELLS = original

        self.assertTrue(table.truncated)
        self.assertEqual(len(table.rows), 5)

    def test_padding_to_a_wide_header_counts_against_the_budget(self):
        original = tables.MAX_CELLS
        tables.MAX_CELLS = 1000

        try:
            header = ",".join(f"h{i}" for i in range(300))
            table = tables.read_csv_text(header + "\n" + "x\n" * 50)
        finally:
            tables.MAX_CELLS = original

        self.assertTrue(table.truncated)
        self.assertEqual(len(table.rows), 3)
        self.assertLessEqual(sum(len(record) for record in table.records()), 1000)

    def test_xlsx_padding_counts_against_the_budget(self):
        rows = '<row><c r="XFD1" t="inlineStr"><is><t>h</t></is></c></row>' + "<row><c><v>1</v></c></row>" * 50
        sheet = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                 f"<sheetData>{rows}</sheetData></worksheet>")
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("xl/worksheets/sheet1.xml", sheet)

        original = tables.MAX_CELLS
        tables.MAX_CELLS = 100_000

        try:
            with self.assertRaises(tables.TableError):
                tables.read_tables_bytes(buffer.getvalue(), "wide.xlsx")
        finally:
            tables.MAX_CELLS = original


if __name__ == "__main__":
    unittest.main()
