"""Polite HTTP fetching: robots.txt, rate limit, size caps, redirect chain."""

from __future__ import annotations

import argparse
import contextlib
import http.client
import ipaddress
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import robots

DEFAULT_USER_AGENT = "seokit-audit/0.1 (+manual SEO review; polite crawler)"
DEFAULT_DELAY = 0.5
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 5_000_000
MAX_REDIRECTS = 10
# Wall-clock cap on one response: the socket timeout alone lets a server that drips one byte
# per interval hold a run for hours.
DEFAULT_DEADLINE = 60.0
READ_CHUNK = 65_536
BLOCKING_STATUSES = (401, 403, 429)


@dataclass
class Hop:
    """One redirect step: the URL requested, its 3xx status and its Location header."""

    url: str
    status: int
    location: Optional[str] = None


@dataclass
class Response:
    """Outcome of a GET. `status` is None when no HTTP answer came back; `error` then says why."""

    url: str
    final_url: str
    status: Optional[int]
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    truncated: bool = False
    chain: List[Hop] = field(default_factory=list)
    error: Optional[str] = None
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        """True for a 2xx status."""
        return self.status is not None and 200 <= self.status < 300

    @property
    def content_type(self) -> str:
        """Media type of the Content-Type header, lowercased, without parameters."""
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    @property
    def is_html(self) -> bool:
        """True for text/html and application/xhtml+xml."""
        return self.content_type in ("text/html", "application/xhtml+xml")

    def text(self) -> str:
        """The body decoded with its declared charset, else UTF-8 (see decode_body)."""
        return decode_body(self.body, self.headers.get("content-type", ""))

    def to_dict(self) -> dict:
        """JSON-ready summary: everything but the body, whose length is given in `bytes`."""
        return {
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "headers": self.headers,
            "truncated": self.truncated,
            "chain": [hop.__dict__ for hop in self.chain],
            "error": self.error,
            "elapsed": round(self.elapsed, 3),
            "bytes": len(self.body),
        }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Never follow: Fetcher.get follows redirects itself and re-checks every hop."""
        return None


# Shared address space (carrier-grade NAT, Tailscale, Alibaba Cloud metadata at 100.100.100.200):
# not global, yet not flagged by is_private on every Python version.
_SHARED_SPACE = ipaddress.ip_network("100.64.0.0/10")
# IPv6 forms that carry an IPv4 address in their low 32 bits: NAT64 well-known prefix
# (RFC 6052), IPv4-compatible (deprecated) and IPv4-translated (SIIT). A translator on the
# path would forward them to that IPv4 address, so it is the one to classify.
_EMBEDDED_IPV4 = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("::/96"),
    ipaddress.ip_network("::ffff:0:0:0/96"),
)
# Translation prefixes refused outright: local-use NAT64 (RFC 8215) and 6to4, whose embedded
# IPv4 sits at other offsets. Python 3.9 counts both as global, later versions do not.
_TRANSLATION_REFUSED = (
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("2002::/16"),
)

PRIVATE_REFUSED = "private or local address refused (public target; --allow-private for a local site)"


def _blocked_address(ip: str) -> bool:
    """True for every address that is not globally routable."""
    address = ipaddress.ip_address(ip.split("%", maxsplit=1)[0])

    if isinstance(address, ipaddress.IPv6Address) and any(address in net for net in _TRANSLATION_REFUSED):
        return True

    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    elif isinstance(address, ipaddress.IPv6Address) and any(address in net for net in _EMBEDDED_IPV4):
        address = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)

    if isinstance(address, ipaddress.IPv4Address) and address in _SHARED_SPACE:
        return True

    return not address.is_global or address.is_multicast


def _guarded_create_connection(private_allowed: Callable[[], bool],
                               on_connect: Optional[Callable[[socket.socket], None]] = None) -> Callable:
    """socket.create_connection that checks the address it actually connects to. Checking
    the host name beforehand is not enough: a second DNS answer (rebinding) could differ.
    on_connect receives each connected socket, so the caller can cut it at a deadline."""
    def create(address, timeout=None, source_address=None, *args, **kwargs):
        host, port = address
        error: Optional[OSError] = None

        for family, kind, proto, _, sockaddr in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
            if not private_allowed() and _blocked_address(sockaddr[0]):
                error = OSError(f"connection to private or local address {sockaddr[0]} refused (public target)")
                continue

            sock = socket.socket(family, kind, proto)

            try:
                if isinstance(timeout, (int, float)):
                    sock.settimeout(timeout)

                if source_address:
                    sock.bind(source_address)

                sock.connect(sockaddr)

                if on_connect:
                    on_connect(sock)

                return sock
            except OSError as exc:
                error = exc
                sock.close()

        raise error or OSError(f"no address found for {host}")

    return create


class _GuardedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, private_allowed: Callable[[], bool], on_connect=None) -> None:
        super().__init__()
        self._create = _guarded_create_connection(private_allowed, on_connect)

    def http_open(self, req):
        return self.do_open(self._factory(http.client.HTTPConnection), req)

    def _factory(self, connection_class):
        def build(*args, **kwargs):
            connection = connection_class(*args, **kwargs)
            connection._create_connection = self._create

            return connection

        return build


class _GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, private_allowed: Callable[[], bool], on_connect=None) -> None:
        super().__init__()
        self._create = _guarded_create_connection(private_allowed, on_connect)
        self._factory = _GuardedHTTPHandler._factory.__get__(self)

    def https_open(self, req):
        return self.do_open(self._factory(http.client.HTTPSConnection), req, context=self._context)


def _build_opener(private_allowed: Callable[[], bool], on_connect=None) -> urllib.request.OpenerDirector:
    """HTTP(S) only: no file://, ftp:// or data: handlers, no proxy, no automatic redirects.
    Every connection re-checks the resolved address against the private-address policy."""
    opener = urllib.request.OpenerDirector()

    for handler in (
        _GuardedHTTPHandler(private_allowed, on_connect),
        _GuardedHTTPSHandler(private_allowed, on_connect),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
        _NoRedirect(),
    ):
        opener.add_handler(handler)

    return opener


def guarded_opener(allow_private: bool) -> urllib.request.OpenerDirector:
    """The same restricted opener for callers that must send something other than a GET."""
    return _build_opener(lambda: allow_private)


def _is_private_host(url: str) -> bool:
    """True when the host resolves to a loopback, private, link-local or reserved address."""
    host = urllib.parse.urlsplit(url).hostname

    if not host:
        return True

    try:
        infos = socket.getaddrinfo(host.rstrip("."), None)
    except (socket.gaierror, UnicodeError):
        return False

    return any(_blocked_address(str(info[4][0])) for info in infos)


def _is_local_target(url: str) -> bool:
    """True only when the URL itself names a local host: localhost or a literal private IP.
    DNS answers never count, so a public site cannot make itself look local."""
    host = (urllib.parse.urlsplit(url).hostname or "").rstrip(".").lower()

    if host == "localhost" or host.endswith(".localhost"):
        return True

    try:
        return _blocked_address(host)
    except ValueError:
        return False


def _http_url(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)

    return parts.scheme in ("http", "https") and bool(parts.hostname)


_META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([A-Za-z0-9_\-]+)""", re.I)


def decode_body(body: bytes, content_type: str = "") -> str:
    """Decode with the charset of the Content-Type header or of a <meta> in the first 4 KB, else UTF-8.

    Never raises: undecodable bytes are replaced.
    """
    charset = None
    match = re.search(r"charset=([A-Za-z0-9_\-]+)", content_type or "", re.I)

    if match:
        charset = match.group(1)

    if not charset:
        meta = _META_CHARSET.search(body[:4096])
        charset = meta.group(1).decode("ascii", "ignore") if meta else None

    for candidate in (charset, "utf-8"):
        if not candidate:
            continue

        try:
            return body.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue

    return body.decode("utf-8", errors="replace")


def read_file_body(path: str, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    """A local HTML or text file, decoded like a response body. Refused above max_bytes, so a
    file handed to the user weighs no more than a fetched page."""
    with open(path, "rb") as handle:
        data = handle.read(max_bytes + 1)

    if len(data) > max_bytes:
        raise ValueError(f"{path}: file above {max_bytes} bytes")

    return decode_body(data)


def normalize_url(url: str) -> str:
    """Drop the fragment, lowercase scheme and host, keep path and query as-is."""
    parts = urllib.parse.urlsplit(url.strip())
    path = parts.path or "/"

    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


def same_site(url: str, other: str) -> bool:
    """True when both URLs share a host, ignoring a leading www."""
    def host(value: str) -> str:
        netloc = urllib.parse.urlsplit(value).hostname or ""

        return netloc[4:] if netloc.startswith("www.") else netloc

    return host(url) == host(other)


class Fetcher:
    """GET-only client. One instance per run: it keeps robots.txt and timing per host."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        delay: float = DEFAULT_DELAY,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        respect_robots: bool = True,
        allow_private: Optional[bool] = None,
        deadline: float = DEFAULT_DEADLINE,
    ) -> None:
        self.user_agent = user_agent
        self.delay = delay
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.respect_robots = respect_robots
        self.deadline = deadline
        # True: private and local addresses allowed (explicit --allow-private). False: always
        # refused. None (direct library use only): decided once by the first URL requested,
        # and only when that URL literally names localhost or a private IP.
        self.allow_private = allow_private
        self._private_cache: Dict[str, bool] = {}
        self._live: List[socket.socket] = []
        self._opener = _build_opener(lambda: bool(self.allow_private), self._live.append)
        self._robots: Dict[str, Optional[List[robots.Group]]] = {}
        self._robots_text: Dict[str, str] = {}
        self._last_request: Dict[str, float] = {}

    def _private(self, url: str) -> bool:
        host = urllib.parse.urlsplit(url).hostname or ""

        if host not in self._private_cache:
            self._private_cache[host] = _is_private_host(url)

        return self._private_cache[host]

    def _wait(self, host: str) -> None:
        last = self._last_request.get(host)

        if last is not None:
            pause = self.delay - (time.monotonic() - last)

            if pause > 0:
                time.sleep(pause)

        self._last_request[host] = time.monotonic()

    def _single(self, url: str) -> Response:
        host = urllib.parse.urlsplit(url).netloc
        self._wait(host)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept": "*/*"},
            method="GET",
        )
        started = time.monotonic()
        self._live.clear()
        # The socket timeout bounds one recv, not a response: a timer cuts the connection at
        # the deadline whatever phase it is in (status line, headers, body, chunk trailers).
        timer = threading.Timer(self.deadline, self._cut_live)
        timer.daemon = True
        timer.start()

        try:
            return self._exchange(url, request, started)
        finally:
            timer.cancel()
            self._live.clear()

    def _cut_live(self) -> None:
        for sock in list(self._live):
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

    def _late(self, url: str, started: float, status=None, headers=None) -> Optional[Response]:
        if time.monotonic() - started <= self.deadline:
            return None

        return Response(url, url, status, headers or {}, elapsed=time.monotonic() - started,
                        error=f"read failed: response took more than {self.deadline:g} s")

    def _exchange(self, url: str, request, started: float) -> Response:
        """One request and its body; any failure past the deadline is reported as the deadline."""
        try:
            handle = self._opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            handle = error
        except (urllib.error.URLError, socket.timeout, ConnectionError, ValueError, http.client.HTTPException,
                OSError) as error:
            reason = getattr(error, "reason", error)

            return self._late(url, started) or Response(url, url, None, error=f"{type(error).__name__}: {reason}",
                                                        elapsed=time.monotonic() - started)

        status = handle.getcode() if hasattr(handle, "getcode") else handle.code
        headers: Dict[str, str] = {}

        for name, value in handle.headers.items():
            key = name.lower()
            headers[key] = f"{headers[key]}, {value}" if key in headers else value

        try:
            body, late = self._read_body(handle, started)
        except (socket.timeout, ConnectionError, OSError, http.client.HTTPException) as error:
            return self._late(url, started, status, headers) or Response(
                url, url, status, headers, error=f"read failed: {error}", elapsed=time.monotonic() - started)
        finally:
            handle.close()

        if late:
            return Response(url, url, status, headers, error=late, elapsed=time.monotonic() - started)

        expired = self._late(url, started, status, headers)

        if expired:
            return expired

        truncated = len(body) > self.max_bytes

        return Response(url, url, status, headers, body[: self.max_bytes], truncated,
                        elapsed=time.monotonic() - started)

    def _read_body(self, handle, started: float) -> Tuple[bytes, Optional[str]]:
        """Up to max_bytes + 1 bytes, one socket read at a time, within the deadline."""
        read = getattr(handle, "read1", handle.read)
        chunks: List[bytes] = []
        size = 0

        while size <= self.max_bytes:
            if time.monotonic() - started > self.deadline:
                return b"", f"read failed: response took more than {self.deadline:g} s"

            chunk = read(min(READ_CHUNK, self.max_bytes + 1 - size))

            if not chunk:
                break

            chunks.append(chunk)
            size += len(chunk)

        return b"".join(chunks), None

    def robots_for(self, url: str) -> Optional[List[robots.Group]]:
        """robots.txt groups for the URL's origin (RFC 9309). [] when the file is absent
        (4xx: no restriction); None when it is unreachable (5xx or network error)."""
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"

        if origin in self._robots:
            return self._robots[origin]

        response = self.get(f"{origin}/robots.txt", check_robots=False)
        text = response.text() if response.status is not None else ""
        self._robots_text[origin] = text

        if response.status is not None and 200 <= response.status < 300:
            groups: Optional[List[robots.Group]] = robots.parse(text)
        elif response.status is not None and 400 <= response.status < 500:
            groups = []
        else:
            groups = None

        self._robots[origin] = groups

        return groups

    def robots_text(self, url: str) -> str:
        """Raw robots.txt of the URL's origin, fetched once; "" when it could not be read."""
        self.robots_for(url)
        parts = urllib.parse.urlsplit(url)

        return self._robots_text.get(f"{parts.scheme}://{parts.netloc}", "")

    def robots_refusal(self, url: str) -> Optional[str]:
        """Why robots.txt forbids this URL, or None when it may be fetched."""
        if not self.respect_robots:
            return None

        groups = self.robots_for(url)

        if groups is None:
            return "robots.txt unreachable (server error or network): treated as full disallow (RFC 9309)"

        if not robots.allowed(groups, robots.product_token(self.user_agent), url):
            return "blocked by robots.txt"

        return None

    def allowed(self, url: str) -> bool:
        """True when robots.txt lets this fetcher's user agent fetch the URL (always when robots are ignored)."""
        return self.robots_refusal(url) is None

    def get(self, url: str, follow: bool = True, check_robots: bool = True) -> Response:
        """GET a URL, recording every redirect hop. Never raises on HTTP or network errors."""
        if not _http_url(url):
            return Response(url, url, None, error="only http and https URLs are fetched")

        if self.allow_private is None:
            self.allow_private = _is_local_target(url)

        if not self.allow_private and self._private(url):
            return Response(url, url, None, error=PRIVATE_REFUSED)

        refusal = self.robots_refusal(url) if check_robots else None

        if refusal:
            return Response(url, url, None, error=refusal)

        chain: List[Hop] = []
        current = url
        seen = {url}

        for _ in range(MAX_REDIRECTS + 1):
            response = self._single(current)

            if response.status is None or not (300 <= response.status < 400):
                response.url = url
                response.final_url = current
                response.chain = chain

                return response

            location = response.headers.get("location")
            chain.append(Hop(current, response.status, location))

            if not follow or not location:
                response.url = url
                response.final_url = current
                response.chain = chain

                return response

            current = urllib.parse.urljoin(current, location)

            if not _http_url(current):
                return Response(url, current, None, chain=chain, error="redirect to a non-http(s) URL refused")

            if not self.allow_private and self._private(current):
                return Response(url, current, None, chain=chain,
                                error="redirect from a public host to a private or local address refused")

            if current in seen:
                return Response(url, current, response.status, response.headers,
                                chain=chain, error="redirect loop")

            seen.add(current)

            refusal = self.robots_refusal(current) if check_robots else None

            if refusal:
                return Response(url, current, None, chain=chain, error=f"redirect target refused: {refusal}")

        return Response(url, current, None, chain=chain, error=f"more than {MAX_REDIRECTS} redirects")


def add_fetch_arguments(parser: argparse.ArgumentParser) -> None:
    """Add --user-agent, --delay, --timeout, --max-bytes and --allow-private to a script's parser."""
    group = parser.add_argument_group("fetching")
    group.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    group.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                       help="seconds between requests to one host (default 0.5, about 2 req/s)")
    group.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    group.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES,
                       help="cap on bytes read per response")
    add_private_argument(group)


def add_private_argument(group) -> None:
    """Add --allow-private alone, for scripts that build their own fetching options."""
    group.add_argument("--allow-private", action="store_true",
                       help="allow loopback, private and link-local addresses (audit of a local or staging site)")


def fetcher_from_args(args: argparse.Namespace) -> Fetcher:
    """A Fetcher built from the options added by add_fetch_arguments; a negative delay counts as 0."""
    return Fetcher(
        user_agent=args.user_agent,
        delay=max(args.delay, 0.0),
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        allow_private=bool(getattr(args, "allow_private", False)),
    )
