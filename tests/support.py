"""Test helpers: import paths and a local HTTP server. No test touches the network."""

from __future__ import annotations

import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "lib")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

if LIB not in sys.path:
    sys.path.insert(0, LIB)


def use_skill_scripts(slug: str) -> str:
    """Put skills/<slug>/scripts first on sys.path (its seokit copy included) and return it."""
    path = os.path.join(ROOT, "skills", slug, "scripts")

    if path in sys.path:
        sys.path.remove(path)

    sys.path.insert(0, path)

    for name in [m for m in sys.modules if m == "seokit" or m.startswith("seokit.")]:
        del sys.modules[name]

    return path


Route = Tuple[int, Dict[str, str], bytes]


class LocalSite:
    """Serve a dict of path -> (status, headers, body) on 127.0.0.1, in a thread.

    Unknown paths answer 404. Use as a context manager; .url(path) builds absolute URLs.
    """

    def __init__(self, routes: Dict[str, Route]) -> None:
        self.routes = routes
        self.hits = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                site.hits.append((self.path, self.headers.get("User-Agent")))
                status, headers, body = site.routes.get(self.path, (404, {"Content-Type": "text/plain"}, b"not found"))
                self.send_response(status)

                for key, value in headers.items():
                    self.send_header(key, value.replace("{base}", site.base))

                body = body.replace(b"{base}", site.base.encode())
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def url(self, path: str = "/") -> str:
        return f"{self.base}{path}"

    def __enter__(self) -> "LocalSite":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()


def html(body: str, head: str = "", lang: str = "en") -> Route:
    page = f"<!doctype html><html lang=\"{lang}\"><head>{head}</head><body>{body}</body></html>"

    return 200, {"Content-Type": "text/html; charset=utf-8"}, page.encode("utf-8")
