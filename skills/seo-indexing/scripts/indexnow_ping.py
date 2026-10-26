#!/usr/bin/env python3
"""Prepare, and only on request send, an IndexNow submission for the user's own URLs.

Default is a dry run: it prints the host, key file URL, URL count, the first URLs, the
exact request that would be sent and a confirmation code (a hash of that request), and makes
no network call at all. --send needs --confirm with that code, so what is sent is exactly
what the user saw. It first checks (GET) that the key file is served on the host with the
key as content, then POSTs the URL list once and prints the HTTP status and body, as data.

Usage:
    python3 scripts/indexnow_ping.py --key <key> --urls urls.txt                              # dry run
    python3 scripts/indexnow_ping.py --key <key> --urls urls.txt --send --confirm <code>      # after the user agreed

Network: none in dry run. With --send: one GET of the key file (seokit.fetch), one POST to
the endpoint (urllib, no redirect followed). The only script of the skill that sends a POST.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

from seokit.fetch import DEFAULT_USER_AGENT, Fetcher, add_private_argument, guarded_opener
from seokit.report import emit_json, today, untrusted

# Read on https://www.indexnow.org/faq and /documentation on 2026-10-16, re-read 2026-10-24.
# Verify before use.
DEFAULT_ENDPOINT = "https://api.indexnow.org/indexnow"
ENDPOINT_READ_ON = "2026-10-24"
MAX_URLS_PER_POST = 10_000
KEY_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")
URL_RE = re.compile(r"^https?://", re.I)
PREVIEW = 10

EXIT_BY_STATUS = {200: 0, 202: 0, 400: 2, 422: 2, 403: 3, 429: 3}


class InputError(Exception):
    pass


def read_key(args: argparse.Namespace) -> str:
    """The user's IndexNow key from --key or --key-file; InputError when missing or malformed."""
    key = args.key

    if args.key_file:
        if not os.path.isfile(args.key_file):
            raise InputError(f"key file not found: {args.key_file}")

        with open(args.key_file, encoding="utf-8", errors="replace") as handle:
            key = handle.read(200).strip()

    if not key:
        raise InputError("give the user's own key with --key or --key-file")

    if not KEY_RE.match(key):
        raise InputError("key must be 8 to 128 characters among a-z, A-Z, 0-9 and '-' (IndexNow documentation)")

    return key


def read_urls(path: str) -> List[str]:
    """Distinct http(s) URLs of the file, in order; reading stops one past the per-POST cap.

    Raises InputError when a URL holds control characters or when the file has no URL."""
    if not os.path.isfile(path):
        raise InputError(f"URL file not found: {path}")

    urls: List[str] = []
    seen = set()

    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            value = line.strip()

            if URL_RE.match(value) and untrusted(value, len(value)) != value:
                raise InputError(f"{path}: a URL holds control or bidi characters; clean the list first")

            if URL_RE.match(value) and value not in seen:
                seen.add(value)
                urls.append(value)

            if len(urls) > MAX_URLS_PER_POST:
                break

    if not urls:
        raise InputError(f"no http(s) URL in {path}")

    return urls


def resolve_host(urls: List[str], host: Optional[str]) -> str:
    """The one host of the URLs (or --host, which every URL must match); InputError otherwise."""
    hosts = sorted({(urllib.parse.urlsplit(u).hostname or "") for u in urls})

    if host:
        host = host.lower().strip()
        off_host = [u for u in urls if (urllib.parse.urlsplit(u).hostname or "") != host]

        if off_host:
            raise InputError(f"{len(off_host)} URL(s) not on {host}, refused (first: {untrusted(off_host[0], 200)})")

        return host

    if len(hosts) != 1:
        raise InputError(f"URLs span several hosts ({', '.join(untrusted(h, 80) or '' for h in hosts[:5])}): "
                         "submit one host at a time with --host")

    return hosts[0]


def resolve_key_location(key: str, host: str, urls: List[str], location: Optional[str]) -> str:
    """Key file URL: /<key>.txt on the URLs' origin, or --key-location on the same host."""
    first = urllib.parse.urlsplit(urls[0])

    if not location:
        return f"{first.scheme}://{first.netloc}/{key}.txt"

    parts = urllib.parse.urlsplit(location)

    if parts.hostname != host:
        raise InputError("--key-location must be on the same host as the URLs")

    directory = parts.path.rsplit("/", 1)[0] + "/"
    outside = [u for u in urls if not (urllib.parse.urlsplit(u).path or "/").startswith(directory)]

    if outside:
        raise InputError(f"{len(outside)} URL(s) outside the key file's directory {directory}, refused "
                         "(a key file only covers URLs under its own directory)")

    return location


def build_request(endpoint: str, host: str, key: str, key_location: str, urls: List[str]) -> dict:
    return {
        "method": "POST",
        "url": endpoint,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": {"host": host, "key": key, "keyLocation": key_location, "urlList": urls},
    }


def confirmation_code(request: dict) -> str:
    """Short hash of the exact request: the dry run shows it, --send must repeat it."""
    canonical = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def check_key_file(fetcher: Fetcher, key_location: str, key: str) -> dict:
    """Fetch the key file and say whether it serves exactly the key, on the same host."""
    response = fetcher.get(key_location)
    served = response.text().strip() if response.ok else ""
    moved = (urllib.parse.urlsplit(response.final_url or key_location).hostname
             != urllib.parse.urlsplit(key_location).hostname)

    if moved:
        served = ""

    return {
        "url": key_location,
        "status": response.status,
        "error": untrusted(response.error, 200),
        "content_matches_key": bool(served) and served == key,
        "redirected_to_other_host": moved,
        "content_quoted": untrusted(served, 140) if served and served != key else None,
    }


def post(request: dict, timeout: float, user_agent: str, allow_private: bool = False) -> dict:
    """Send the IndexNow POST; return the status and the quoted answer (first 20 kB read)."""
    data = json.dumps(request["body"]).encode("utf-8")
    headers = dict(request["headers"])
    headers["User-Agent"] = user_agent
    outgoing = urllib.request.Request(request["url"], data=data, headers=headers, method="POST")
    # Same restricted opener as every GET: no proxy from the environment, no redirect,
    # private and local addresses refused unless the user passed --allow-private.
    opener = guarded_opener(allow_private)

    try:
        handle = opener.open(outgoing, timeout=timeout)
    except urllib.error.HTTPError as error:
        handle = error
    except (urllib.error.URLError, OSError, ValueError) as error:
        return {"status": None, "error": untrusted(str(getattr(error, "reason", error)), 200)}

    try:
        body = handle.read(20_000)
    finally:
        handle.close()

    return {"status": handle.code, "body_quoted": untrusted(body.decode("utf-8", errors="replace"), 1000)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="IndexNow submission for the user's own URLs. Dry run by default (no network); "
                    "nothing is sent without --send.")
    parser.add_argument("--key", help="the user's own IndexNow key")
    parser.add_argument("--key-file", help="read the key from this local file instead of --key")
    parser.add_argument("--key-location", help="URL of the key file when not at /<key>.txt on the host")
    parser.add_argument("--host", help="host of the URLs (default: derived from the URL file, one host only)")
    parser.add_argument("--urls", required=True, help="file with one URL per line")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                        help=f"default {DEFAULT_ENDPOINT}, read on indexnow.org on {ENDPOINT_READ_ON}: "
                             "verify on indexnow.org before sending")
    parser.add_argument("--send", action="store_true",
                        help="actually send; only after the user saw the dry run and agreed")
    parser.add_argument("--confirm", help="confirmation code printed by the dry run, required with --send")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    add_private_argument(parser)

    return parser


def prepare(args: argparse.Namespace) -> dict:
    """Check the key, URLs, endpoint and host, and build the request shown by the dry run."""
    key = read_key(args)
    urls = read_urls(args.urls)

    if len(urls) > MAX_URLS_PER_POST:
        raise InputError(f"more than {MAX_URLS_PER_POST} URLs: IndexNow accepts up to {MAX_URLS_PER_POST} per POST, "
                         "split the file")

    scheme = urllib.parse.urlsplit(args.endpoint).scheme.lower()

    if scheme != "https" and not (scheme == "http" and args.allow_private):
        raise InputError("--endpoint must be an https URL")

    host = resolve_host(urls, args.host)
    key_location = resolve_key_location(key, host, urls, args.key_location)

    return {
        "key": key,
        "host": host,
        "key_location": key_location,
        "urls": urls,
        "request": build_request(args.endpoint, host, key, key_location, urls),
    }


def main(argv: Optional[List[str]] = None) -> int:
    """Print the dry run, or send it when --send repeats its confirmation code and the key file checks out."""
    args = build_parser().parse_args(argv)

    try:
        plan = prepare(args)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    output = {
        "generated_on": today(),
        "tool": "indexnow_ping.py",
        "mode": "send" if args.send else "dry-run",
        "endpoint": args.endpoint,
        "endpoint_note": (f"default read on indexnow.org on {ENDPOINT_READ_ON}; verify the endpoint and the "
                          "participating engines on indexnow.org and date the reading"
                          if args.endpoint == DEFAULT_ENDPOINT
                          else "non-default endpoint: confirm this host with the user before --send"),
        "host": plan["host"],
        "key_location": plan["key_location"],
        "url_count": len(plan["urls"]),
        "first_urls": [untrusted(u, 300) for u in plan["urls"][:PREVIEW]],
        "request": plan["request"],
        "confirmation": confirmation_code(plan["request"]),
        "sent": False,
        "not_covered": "Google: not an IndexNow participant when this script was written; re-check on indexnow.org",
    }

    if not args.send:
        output["next_step"] = ("show this dry run to the user; send only after explicit agreement, with "
                               f"--send --confirm {output['confirmation']}")
        emit_json(output)

        return 0

    if args.confirm != output["confirmation"]:
        output["refused"] = ("--confirm does not match this request: run the dry run, show it to the user, "
                             "then send with the code it prints. Nothing sent")
        emit_json(output)

        return 2

    fetcher = Fetcher(user_agent=args.user_agent, timeout=args.timeout, delay=0.0, allow_private=args.allow_private)
    key_check = check_key_file(fetcher, plan["key_location"], plan["key"])
    output["key_file_check"] = key_check

    if key_check["status"] in (401, 403, 429):
        output["refused"] = "key file answered with a blocking status: nothing sent"
        emit_json(output)

        return 3

    if not key_check["content_matches_key"]:
        output["refused"] = "key file is not served on the host with the key as content: nothing sent"
        emit_json(output)

        return 2

    print(f"POST {len(plan['urls'])} URL(s) to {args.endpoint}", file=sys.stderr)
    output["response"] = post(plan["request"], args.timeout, args.user_agent, args.allow_private)
    output["sent"] = True
    status = output["response"].get("status")

    emit_json(output)

    return EXIT_BY_STATUS.get(status, 1)


if __name__ == "__main__":
    sys.exit(main())
