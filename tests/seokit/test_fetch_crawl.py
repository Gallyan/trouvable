import tempfile
import unittest

from tests.support import LocalSite, html

from seokit import crawl, sitemap
from seokit.fetch import Fetcher

SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{base}/</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>{base}/a</loc></url>
<url><loc>{base}/orphan</loc></url>
</urlset>"""


def site_routes():
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        b"User-agent: *\nDisallow: /private\nSitemap: {base}/sitemap.xml\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"}, SITEMAP),
        "/": html('<nav><a href="/a">A</a></nav><main><p>Hi <a href="/old">old</a> '
                  '<a href="/private/x">p</a></p></main>'),
        "/a": html("<main><p>Page A</p></main>"),
        "/old": (307, {"Location": "/a"}, b""),
        "/orphan": html("<p>alone</p>"),
    }


class FetchTest(unittest.TestCase):
    def test_redirect_chain_is_recorded(self):
        with LocalSite(site_routes()) as site:
            response = Fetcher(delay=0).get(site.url("/old"))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.chain[0].status, 307)
        self.assertTrue(response.final_url.endswith("/a"))

    def test_robots_is_respected(self):
        with LocalSite(site_routes()) as site:
            response = Fetcher(delay=0).get(site.url("/private/x"))

        self.assertIsNone(response.status)
        self.assertIn("robots", response.error)

    def test_body_is_capped(self):
        routes = {"/big": (200, {"Content-Type": "text/html"}, b"x" * 5000)}

        with LocalSite(routes) as site:
            response = Fetcher(delay=0, max_bytes=1000).get(site.url("/big"))

        self.assertTrue(response.truncated)
        self.assertEqual(len(response.body), 1000)

    def test_non_http_redirect_is_refused(self):
        routes = {"/r": (302, {"Location": "file:///etc/passwd"}, b"")}

        with LocalSite(routes) as site:
            response = Fetcher(delay=0).get(site.url("/r"))

        self.assertIsNone(response.status)
        self.assertIn("non-http", response.error)
        self.assertEqual(response.body, b"")

    def test_non_http_start_url_is_refused(self):
        response = Fetcher(delay=0).get("file:///etc/passwd")

        self.assertIsNone(response.status)
        self.assertEqual(response.body, b"")

    def test_public_to_private_redirect_is_refused(self):
        from unittest import mock

        from seokit import fetch

        hops = iter([
            fetch.Response("http://public.test/", "http://public.test/", 302, {"location": "http://10.0.0.1/admin"}),
        ])

        with mock.patch.object(fetch.Fetcher, "_single", lambda self, url: next(hops)), \
                mock.patch.object(fetch, "_is_private_host", lambda url: "10.0.0.1" in url):
            response = Fetcher(delay=0, respect_robots=False).get("http://public.test/")

        self.assertIsNone(response.status)
        self.assertIn("private", response.error)

    def test_private_target_refused_after_public_start(self):
        from unittest import mock

        from seokit import fetch

        fetcher = Fetcher(delay=0, respect_robots=False)

        with mock.patch.object(fetch, "_is_private_host", lambda url: "127.0.0.1" in url), \
                mock.patch.object(fetch.Fetcher, "_single",
                                  lambda self, url: fetch.Response(url, url, 200, {}, b"ok")):
            first = fetcher.get("http://public.test/")
            second = fetcher.get("http://127.0.0.1/admin")

        self.assertEqual(first.status, 200)
        self.assertIsNone(second.status)
        self.assertIn("private", second.error)

    def test_dns_rebinding_to_private_address_is_refused_at_connect(self):
        import socket
        from unittest import mock

        from seokit import fetch

        real_getaddrinfo = socket.getaddrinfo

        def rebinding(host, *args, **kwargs):
            if host == "rebind.test":
                return real_getaddrinfo("127.0.0.1", *args, **kwargs)

            return real_getaddrinfo(host, *args, **kwargs)

        with LocalSite({"/": html("<p>internal</p>")}) as site:
            port = site.server.server_address[1]

            with mock.patch.object(fetch, "_is_private_host", lambda url: False), \
                    mock.patch.object(socket, "getaddrinfo", rebinding):
                response = Fetcher(delay=0, respect_robots=False).get(f"http://rebind.test:{port}/")

        self.assertIsNone(response.status)
        self.assertEqual(response.body, b"")
        self.assertIn("private", response.error)

    def test_private_dns_answer_does_not_open_the_guard(self):
        import socket
        from unittest import mock

        from seokit import fetch

        real_getaddrinfo = socket.getaddrinfo

        with LocalSite({"/internal": html("<p>internal</p>")}) as inner:
            port = inner.server.server_address[1]

            def mixed(host, *args, **kwargs):
                if host == "site.test":
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 80)),
                            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 80))]

                return real_getaddrinfo(host, *args, **kwargs)

            hops = iter([fetch.Response("http://site.test/", "http://site.test/", 302,
                                        {"location": f"http://127.0.0.1:{port}/internal"})])

            with mock.patch.object(socket, "getaddrinfo", mixed), \
                    mock.patch.object(fetch.Fetcher, "_single", lambda self, url: next(hops)):
                fetcher = Fetcher(delay=0, respect_robots=False)
                response = fetcher.get("http://site.test/")

        self.assertFalse(fetcher.allow_private)
        self.assertIsNone(response.status)
        self.assertIn("private", response.error)
        self.assertEqual(inner.hits, [])

    def test_literal_local_target_still_latches(self):
        from seokit.fetch import _is_local_target

        self.assertTrue(_is_local_target("http://127.0.0.1:8000/"))
        self.assertTrue(_is_local_target("http://localhost/"))
        self.assertTrue(_is_local_target("http://[::1]/"))
        self.assertFalse(_is_local_target("http://example.com/"))

    def test_scripts_refuse_private_unless_flag(self):
        import argparse

        from seokit.fetch import add_fetch_arguments, fetcher_from_args

        parser = argparse.ArgumentParser()
        add_fetch_arguments(parser)

        self.assertIs(fetcher_from_args(parser.parse_args([])).allow_private, False)
        self.assertIs(fetcher_from_args(parser.parse_args(["--allow-private"])).allow_private, True)

        with LocalSite({"/admin": html("<p>secret</p>")}) as site:
            response = fetcher_from_args(parser.parse_args(["--delay", "0"])).get(site.url("/admin"))

        self.assertIsNone(response.status)
        self.assertIn("--allow-private", response.error)
        self.assertEqual(site.hits, [])

    def test_non_global_ranges_are_blocked(self):
        from seokit.fetch import _blocked_address

        for ip in ("100.64.0.1", "100.100.100.200", "100.127.255.254", "::ffff:100.100.100.200",
                   "169.254.169.254", "10.0.0.1", "127.0.0.1", "::ffff:127.0.0.1", "fd00::1", "192.0.2.1"):
            self.assertTrue(_blocked_address(ip), ip)

        for ip in ("93.184.215.14", "8.8.8.8", "2606:4700::1111"):
            self.assertFalse(_blocked_address(ip), ip)

    def test_network_error_does_not_raise(self):
        response = Fetcher(delay=0, timeout=2).get("http://127.0.0.1:9/")

        self.assertIsNone(response.status)
        self.assertTrue(response.error)


class SitemapTest(unittest.TestCase):
    def test_doctype_is_refused(self):
        with self.assertRaises(ValueError):
            sitemap.parse_sitemap_bytes(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><urlset/>')

    def test_doctype_in_utf16_is_refused(self):
        doc = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE urlset [<!ENTITY e0 "AAAAAAAAAA">'
               '<!ENTITY e1 "&e0;&e0;&e0;&e0;&e0;">]><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
               '<url><loc>&e1;</loc></url></urlset>')

        for data in (doc.encode("utf-16"), doc.encode("utf-16-le"), doc.encode("utf-32")):
            with self.assertRaises(ValueError):
                sitemap.parse_sitemap_bytes(data)

    def test_declared_wide_encoding_is_refused(self):
        with self.assertRaises(ValueError):
            sitemap.parse_sitemap_bytes(b'<?xml version="1.0" encoding="UTF-7"?><urlset/>')

        kind, urls, _ = sitemap.parse_sitemap_bytes(
            '<?xml version="1.0" encoding="ISO-8859-1"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://example.test/é</loc></url></urlset>'.encode("latin-1"))
        self.assertEqual(kind, "urlset")
        self.assertEqual(len(urls), 1)

    def test_index_and_alternates(self):
        data = (b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                b'xmlns:xhtml="http://www.w3.org/1999/xhtml"><url><loc>https://x.test/</loc>'
                b'<xhtml:link rel="alternate" hreflang="fr" href="https://x.test/fr/"/></url></urlset>')
        kind, urls, _ = sitemap.parse_sitemap_bytes(data)

        self.assertEqual(kind, "urlset")
        self.assertEqual(urls[0].alternates, [("fr", "https://x.test/fr/")])


class SitemapFetchCapTest(unittest.TestCase):
    def index(self, count):
        children = "".join(f"<sitemap><loc>{{base}}/c-{i}.xml</loc></sitemap>" for i in range(count))

        return f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{children}</sitemapindex>'.encode()

    def test_failing_children_count_against_the_cap(self):
        routes = {"/robots.txt": (404, {}, b""),
                  "/index.xml": (200, {"Content-Type": "application/xml"}, self.index(300))}

        with LocalSite(routes) as site:
            result = sitemap.load(Fetcher(delay=0), [site.url("/index.xml")])

        fetched = [path for path, _ in site.hits if path.startswith("/c-")]
        self.assertLessEqual(len(fetched), sitemap.MAX_SITEMAP_FILES)
        self.assertTrue(any("cap of" in error for error in result.errors))


class CrawlTest(unittest.TestCase):
    def test_crawl_directory(self):
        with LocalSite(site_routes()) as site, tempfile.TemporaryDirectory() as out:
            result = crawl.crawl(site.url("/"), Fetcher(delay=0), out, max_pages=20)
            meta, records = crawl.load_crawl(out)

        by_url = {r["url"]: r for r in records}
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(by_url[site.url("/a")]["depth"], 1)
        self.assertIsNone(by_url[site.url("/orphan")]["depth"])
        self.assertTrue(by_url[site.url("/orphan")]["in_sitemap"])
        self.assertEqual(by_url[site.url("/old")]["chain"][0]["status"], 307)
        self.assertIn("Disallow", meta["robots_txt"])

    def test_stops_on_403(self):
        routes = {"/": (403, {"Content-Type": "text/html"}, b"no")}

        with LocalSite(routes) as site, tempfile.TemporaryDirectory() as out:
            result = crawl.crawl(site.url("/"), Fetcher(delay=0), out, use_sitemap=False)

        self.assertIn("403", result.stop_reason)
        self.assertEqual(result.pages, 1)


if __name__ == "__main__":
    unittest.main()
