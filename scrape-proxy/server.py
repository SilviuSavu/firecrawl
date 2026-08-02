#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transparent Firecrawl proxy with a Firecrawl Cloud fallback for hard pages.

Sits between callers (the pi web tools via FIRECRAWL_URL=http://localhost:3003/v1)
and the self-hosted Firecrawl. For /v1/scrape it tries the LOCAL instance first;
if local fails, returns too little content, or looks like a bot-challenge page,
it retries the SAME url against Firecrawl Cloud (managed stealth proxy) and
returns whichever gave real content. Everything else (/v1/search, /v1/crawl,
GET, ...) is passed straight through to local -- search already has multi-engine
redundancy inside SearXNG, so it does not need Cloud.

Why this exists: self-hosted Firecrawl cannot use Fire Engine (Mendable-internal),
so the built-in stealthProxy retry is inert. This proxy is a self-hosted shim that
uses Firecrawl Cloud as the stealth backend, spending Cloud credits ONLY when a
local scrape actually fails.

Failure detection (matches the extension's own contract + adds challenge heuristics):
  - HTTP non-2xx, or JSON success != true, or data.markdown missing  -> hard fail
  - markdown shorter than MIN_OK_LEN                                -> suspect
  - markdown contains a challenge marker (Cloudflare/DataDome)       -> false-success
"""

import json
import os
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest

LOCAL = os.environ.get("LOCAL_FIRECRAWL_URL", "http://api:3002").rstrip("/")
CLOUD = "https://api.firecrawl.dev"
CLOUD_KEY = os.environ.get("FIRECRAWL_API_KEY", "").strip()

LOCAL_TIMEOUT = float(os.environ.get("LOCAL_TIMEOUT", "25"))
CLOUD_TIMEOUT = float(os.environ.get("CLOUD_TIMEOUT", "45"))
# Near-empty floor only as a degenerate-case backstop: real pages are almost
# always > this (example.com is ~167 chars); kept low so legitimately small
# pages don't false-positive into a Cloud call.
MIN_OK_LEN = int(os.environ.get("MIN_OK_LEN", "50"))
# Substrings that indicate the page returned is a bot-challenge interstitial,
# not real content (200 OK but useless).
CHALLENGE_MARKERS = (
    "verify you are human",
    "checking your browser",
    "just a moment",
    "attention required",
    "enable javascript and cookies to continue",
    "cf-challenge",
    "dd-block",          # datadome
    "access denied",
    "request blocked",
    "unusual traffic from your computer",
)

SCRAPE_PATHS = {"/v1/scrape", "/scrape", "/v2/scrape"}
_SSL = ssl.create_default_context()


def _request(method, url, headers, body, timeout):
    # GET must have no body (Firecrawl's /crawl/{id} status is GET-only and
    # 404s on POST); POST/PUT carry the body. Honor the original verb.
    req = urlrequest.Request(url, data=(body if body else None), headers=headers, method=method)
    with urlrequest.urlopen(req, timeout=timeout, context=_SSL) as r:
        return r.status, r.read()


def _looks_failed(raw_bytes):
    """True if a local scrape response should trigger a Cloud retry."""
    try:
        payload = json.loads(raw_bytes) if raw_bytes else None
    except ValueError:
        return True  # unparseable -> definitely failed
    if not payload or not payload.get("success"):
        return True
    md = ((payload.get("data") or {}).get("markdown") or "")
    if len(md) < MIN_OK_LEN:
        return True
    low = md.lower()
    return any(m in low for m in CHALLENGE_MARKERS)


def _hdrs_in(source_headers):
    """Forward incoming headers, dropping hop-by-hop / host."""
    skip = {"host", "content-length", "connection", "transfer-encoding"}
    return {k: v for k, v in source_headers.items() if k.lower() not in skip}


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep stderr quiet, one line per request
        path = self.path
        print(f"[proxy] {self.command} {path}", *args, flush=True)

    # ---- shared ----
    def _respond(self, status, body, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_body(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(n) if n > 0 else b""

    def _passthrough_local(self, body):
        """Forward any request to local unchanged."""
        headers = _hdrs_in(self.headers)
        try:
            status, resp = _request(self.command, LOCAL + self.path, headers, body, LOCAL_TIMEOUT)
            self._respond(status, resp)
        except Exception as e:  # local unreachable
            self._respond(502, json.dumps({"success": False, "error": f"proxy->local: {e}"}).encode())

    # ---- scrape with Cloud fallback ----
    def _scrape(self, body):
        headers = _hdrs_in(self.headers)
        local_status, local_resp = None, None
        try:
            local_status, local_resp = _request("POST", LOCAL + self.path, headers, body, LOCAL_TIMEOUT)
            if not _looks_failed(local_resp):
                self._respond(local_status, local_resp)
                return
            reason = "thin/challenge"
        except Exception as e:
            reason = f"local error: {e}"

        # Cloud fallback
        if not CLOUD_KEY:
            # No key -> return local's best effort (or 502 if local hard-failed).
            if local_resp is not None:
                self._respond(local_status, local_resp)
            else:
                self._respond(502, json.dumps({"success": False, "error": f"local failed ({reason}); no FIRECRAWL_API_KEY"}).encode())
            return
        try:
            payload = json.loads(body) if body else {}
        except ValueError:
            payload = {}
        payload.setdefault("proxy", "auto")  # let Cloud escalate to stealth if basic fails
        cheaders = {"Content-Type": "application/json", "Authorization": "Bearer " + CLOUD_KEY}
        try:
            cstatus, cresp = _request("POST", CLOUD + self.path, cheaders, json.dumps(payload).encode(), CLOUD_TIMEOUT)
            print(f"[proxy] Cloud fallback USED for {payload.get('url')[:60] if isinstance(payload.get('url'), str) else '?'} (local: {reason})", flush=True)
            self._respond(cstatus, cresp)
        except Exception as e:
            # Cloud failed too -> return local's result if we have one, else 502.
            if local_resp is not None:
                self._respond(local_status, local_resp)
            else:
                self._respond(502, json.dumps({"success": False, "error": f"local ({reason}) + cloud ({e}) both failed"}).encode())

    # ---- verbs ----
    def do_POST(self):
        body = self._read_body()
        if self.path.rstrip("/") in SCRAPE_PATHS:
            self._scrape(body)
        else:
            self._passthrough_local(body)

    def do_GET(self):
        # All non-scrape reads pass through to local (health, etc.).
        self._passthrough_local(b"")

    def do_HEAD(self):
        self._passthrough_local(b"")


if __name__ == "__main__":
    if not CLOUD_KEY:
        print("[proxy] WARNING: FIRECRAWL_API_KEY not set; Cloud fallback disabled (local-only).", flush=True)
    print(f"[proxy] listening on :3003 -> local {LOCAL} (cloud fallback {'on' if CLOUD_KEY else 'OFF'})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 3003), Proxy).serve_forever()
