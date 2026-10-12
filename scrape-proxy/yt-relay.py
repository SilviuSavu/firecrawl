#!/usr/bin/env python3
"""Tailnet-only YouTube transcript relay for the home search stack.

Home egress IPs (CGNAT) are IpBlocked by YouTube; the VPS IP is not.
GET /transcript?video_id=<id>[&lang=en,de][&format=text]
GET /transcript?url=<watch url>...
"""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from youtube_transcript_api import YouTubeTranscriptApi



class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] != "/transcript":
            self._reply(404, {"success": False, "error": "use /transcript"})
            return
        qs = parse_qs(urlparse(self.path).query)
        url = unquote(qs.get("url", [""])[0])
        vid = qs.get("video_id", [""])[0]
        if not vid and url:
            m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", url)
            if m:
                vid = m.group(1)
        if not vid:
            self._reply(400, {"success": False, "error": "provide ?url= or ?video_id="})
            return
        langs = [l.strip() for l in qs.get("lang", ["en"])[0].split(",") if l.strip()]
        try:
            fetched = YouTubeTranscriptApi().fetch(vid, languages=langs)
            rows = fetched.to_raw_data()
        except Exception as exc:
            self._reply(404, {"success": False, "error": str(exc)[:300], "video_id": vid})
            return
        text = "\n".join(r.get("text", "") for r in rows)
        if qs.get("format", ["json"])[0] == "text":
            self._reply(200, text)
        else:
            self._reply(200, {"success": True, "video_id": vid, "segments": len(rows), "text": text})

    def _reply(self, status, payload):
        body = (payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8" if isinstance(payload, str) else "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("[yt-relay]", fmt % args, flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8300), Handler).serve_forever()
