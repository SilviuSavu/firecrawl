#!/usr/bin/env python3
"""Search outage watchdog: catches transient search failures with attribution.

Two detectors, zero extra upstream engine load:
1. INFRA: every 60s a zimtitles-only canary (local kiwix index, free) against
   searxng directly - catches searxng container death, watchtower restarts,
   and zimtitles degradation.
2. USER-VISIBLE: tails the firecrawl api logs for the "SearXNG returned no
   results" warn (emitted with unresponsiveEngines attribution) - catches
   every real user-visible 0-result window the new api build logs.

Events append to /var/log/search-outage-watchdog.log.
"""
import json
import subprocess
import time
import urllib.request
from datetime import datetime

SEARX = "http://127.0.0.1:8888/search?q={}&format=json&engines=zimtitles"
CANARIES = ["alpha", "bravo", "charlie", "delta", "echo"]
LOG = "/var/log/search-outage-watchdog.log"
API_CONTAINER = "firecrawl-api-1"
WARN_MARKER = "SearXNG returned no results"


def log_event(kind, detail):
    line = "%s %s %s" % (datetime.now().isoformat(timespec="seconds"), kind, detail)
    with open(LOG, "a") as f:
        f.write(line + "\n")
    try:
        if sum(1 for _ in open(LOG)) > 20000:
            lines = open(LOG).readlines()[-5000:]
            open(LOG, "w").writelines(lines)
    except OSError:
        pass


def infra_canary(i):
    q = CANARIES[i % len(CANARIES)]
    t0 = time.time()
    try:
        d = json.load(urllib.request.urlopen(SEARX.format(q), timeout=20))
        n = len(d.get("results", []))
        el = time.time() - t0
        if n == 0:
            log_event("INFRA", "zimtitles canary 0 results q=%s unres=%s" % (q, [e[0] for e in d.get("unresponsive_engines", [])]))
        elif el > 10:
            log_event("INFRA", "zimtitles canary slow %.1fs q=%s" % (el, q))
    except Exception as e:
        log_event("INFRA", "zimtitles canary FAILED q=%s err=%s" % (q, e))


def tail_api():
    try:
        out = subprocess.run(
            ["docker", "logs", "--since", "35s", API_CONTAINER],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception as e:
        return
    for ln in out.splitlines():
        if WARN_MARKER in ln:
            log_event("USER-VISIBLE", ln.strip()[:500])


def main():
    log_event("BOOT", "watchdog started")
    i = 0
    last_infra = 0.0
    last_tail = 0.0
    while True:
        now = time.time()
        if now - last_infra >= 60:
            infra_canary(i)
            i += 1
            last_infra = now
        if now - last_tail >= 30:
            tail_api()
            last_tail = now
        time.sleep(1)


if __name__ == "__main__":
    main()
