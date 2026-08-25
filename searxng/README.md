# searXNG + zimtitles — local-first hybrid search engine

This is a two-tier search engine that merges **curated offline content** (ZIM files: Wikipedia, StackOverflow, DevDocs, StackExchange, etc.) with **live web results** (Google CSE, Bing, Brave, Exa), scored by a local MLX reranker and optionally verified by HHEM.

## Architecture

```
                          ┌──────────────────────────────────────┐
                          │        prime-agent web_search       │
                          │   (websearch.py — python skill)     │
                          └──────────────┬───────────────────────┘
                                         │ POST /search
                                         ▼
                          ┌──────────────────────────────────────┐
                          │          Firecrawl API               │
                          │           localhost:3002              │
                          └──────────────┬───────────────────────┘
                                         │ POST /search
                                         ▼
                          ┌──────────────────────────────────────┐
                          │            searXNG                   │
                          │           localhost:8888              │
                          │ categories: general, it, offline     │
                          └──┬──────────────┬────────────────────┘
                             │              │
               ┌─────────────┘              └─────────────┐
               ▼                                          ▼
   ┌──────────────────────┐                  ┌──────────────────────┐
   │   web engines         │                  │   local engines      │
   │   ────────────        │                  │   ────────────       │
   │   google cse   (0.4)  │                  │   zimtitles   (0.6)  │
   │   bing         (0.4)  │                  │                      │
   │   exa          (0.4)  │                  │   ┌──────────────┐   │
   │   bravesearch  (0.4)  │                  │   │ title index  │   │
   └──────────────────────┘                  │   │ :7777 (Mini) │   │
                                             │   └──────┬───────┘   │
                                             │          │            │
                                             │   ┌──────▼───────┐   │
                                             │   │ MLX reranker │   │
                                             │   │ :8101 (host) │   │
                                             │   └──────┬───────┘   │
                                             │          │            │
                                             │   ┌──────▼───────┐   │
                                             │   │ kiwix-serve  │   │
                                             │   │ :8181 (Mini) │   │
                                             │   └──────────────┘   │
                                             └──────────────────────┘

```

## Service inventory

### Host (this MacBook)

| Service | Port | Launch | Persistence | Config |
|---------|------|--------|-------------|--------|
| Firecrawl API | :3002 | Docker compose `firecrawl-api-1` | `restart: unless-stopped` | `~/projects/firecrawl/docker-compose.yaml` |
| searXNG | :8888 | Docker compose `firecrawl-searxng-1` | `restart: unless-stopped` | `~/projects/firecrawl/searxng/settings.yml` |
| MLX reranker | :8101 | launchd `local.mlx.reranker` | launchd plist (boot + crash restart) | `~/Library/LaunchAgents/local.mlx.reranker.plist` |
|          |      |                              |                              | `~/projects/grounding-verifier-mlx/verify_mlx.py` |
| HHEM verifier | (same as reranker) | served by same process at `/verify` and `/rerank` |
| prime-agent web_search skill | n/a | `~/.prime/agent/skills/websearch/` | host filesystem | `websearch.py` |

### Mac Mini (`mac-mini-von-savu.netbird.selfhosted`, Netbird IP `100.106.64.215` — prefer the DNS name)

| Service | Port | Launch | Persistence |
|---------|------|--------|-------------|
| zimtitles title server | :7777 | LaunchDaemon `local.kiwix.zimtitles` → `~/zh-venv/start_zimtitles.sh` (venv python) | `/Library/LaunchDaemons/local.kiwix.zimtitles.plist` (KeepAlive) |
| kiwix-serve (main library) | :8181 | LaunchDaemon `local.kiwix.serve8181` → `~/.local/bin/kiwix-serve-agent.sh` (**ssh relay**, see below) | `/Library/LaunchDaemons/local.kiwix.serve8181.plist` (KeepAlive) |
| library warmup | n/a | LaunchDaemon `local.kiwix.warm8181` → `~/.local/bin/kiwix-warmup.sh 8181` (RunAtLoad) | `/Library/LaunchDaemons/local.kiwix.warm8181.plist` |
| zimtitles MCP server | stdio | on-demand: `ssh macmini ~/zh-venv/zimtitles_mcp.py` | none needed (stateless stdio) |

> **8182 (english search) is dead**: its plists are user LaunchAgents, and the mini is headless (no GUI session), so user agents never run. Everything routes through 8181 + the unified title index now.

> **All mini plists are system LaunchDaemons** (`/Library/LaunchDaemons`), owned by root, running as `savusilviu`. Restart with `sudo launchctl kickstart -k system/<label>`, not `launchctl start`.

## Pipeline flow (user query → answer)

```
query "rust async await"
    │
    ▼
prime-agent: web_search("rust async await")
    │ POST /search (Firecrawl localhost:3002)
    ▼
Firecrawl: fan-out to searXNG (localhost:8888)
    │ categories=general,it (includes both web and zimtitles)
    ▼
searXNG: parallel engine dispatch
    ├── google cse  → Bing/Google API → web results (weight 0.4)
    ├── bing        → Bing API         → web results (weight 0.4)
    ├── exa         → Exa API          → web results (weight 0.4)
    ├── bravesearch → Brave API        → web results (weight 0.4)
    └── zimtitles   → local pipeline:
                      ├── titles:7777/search?q=rust+async&limit=30
                      │     → 30 candidate titles from ZIM library
                      ├── reranker:8101/rerank
                      │     → scores all 30, keeps top 12
                      ├── kiwix:8181/suggest (resolve paths)
                      └── kiwix:8181/content (fetch 32KB snippets)
                      └── 12 results (weight 0.6)
    │
    ▼
searXNG: merge by score = weight × reranker_score
    ├── local results (weight 0.6) appear first when relevant
    ├── web results (weight 0.4) fill gaps
    └── final: 40-60 results to Firecrawl
    │
    ▼
Firecrawl: returns to prime-agent
    │
    ▼
prime-agent: presents to user with grounding verdicts
```

## Key configuration files

| File | Purpose | Last changed |
|------|---------|-------------|
| `~/projects/firecrawl/docker-compose.yaml` | Full stack definition | git history |
| `~/projects/firecrawl/searxng/settings.yml` | searXNG engine settings, categories, weights | commit `5c2ce8608` |
| `~/projects/firecrawl/searxng/zimtitles.py` | ZIM library search engine for searXNG | commit `5c2ce8608` |
| `~/projects/firecrawl/searxng/zimtitles_bench.py` | Pareto frontier benchmark harness | commit `5c2ce8608` |
| `~/projects/firecrawl/searxng/local_vs_web_bench.py` | Local vs web quality comparison | commit `5c2ce8608` |
| `~/Library/LaunchAgents/local.mlx.reranker.plist` | Auto-start MLX reranker on host boot | **new — not committed** |
| `~/.prime/agent/skills/websearch/` | prime-agent web_search skill | local |

## Engine weights (searXNG scoring)

| Engine | Weight | Ratio vs web | Role |
|--------|--------|-------------|------|
| google cse | 0.4 | 1× | web results (via Google Programmable Search) |
| bing | 0.4 | 1× | web results (HTML scrape) |
| exa | 0.4 | 1× | web results (API — needs `EXA_API_KEY`) |
| bravesearch | 0.4 | 1× | web results (API — needs `BRAVE_API_KEY`) |
| **zimtitles** | **0.6** | **1.5×** | **local library (curated ZIM content)** |

zimtitles at 0.6 gives curated content a 1.5× trust bonus over web. See benchmark data for rationale:
- `zimtitles_bench.py`: 225 runs across 5 candidate pool sizes × 3 final counts
- `local_vs_web_bench.py`: 30 queries (reference/current/mixed) scored by MLX reranker
- Conclusion: pure relevance parity = 0.43; 0.6 applies a moderate trust bonus for curated content

## Benchmark results (summary)

```
candidates = 30  (pool size for reranker)
final      = 12  (results kept after rerank)
weight     = 0.6 (1.5× trust bonus over web)

Quality by query type:
  reference: local avg best=0.9565  web avg best=0.9728  (local ≈ 98% of web)
  current:   local avg best=0.8327  web avg best=0.9451  (web dominates)
  mixed:     local avg best=0.8952  web avg best=0.9620  (web edges ahead)
```

## Special shortcuts

| Search | Behavior |
|--------|----------|
| `!offline query` | Pure ZIM library search (no web engines) |
| `!general query` | Web + local mixed (default) |
| `!zt query` | zimtitles only (via its `zt` shortcut) |

## Mac Mini internals — the 2026-08-25 rework

### Why kiwix-serve must launch through an ssh relay (TCC)

macOS **TCC "Removable Volumes" privacy** denies background daemons read access to `/Volumes/Media24TB` (the 24TB USB HDD holding all 3,260 ZIMs) — **even when running as root**. A daemon-spawned kiwix-serve logs `The library was successfully loaded` but serves an *empty* catalog (every ZIM probe denied → every book dropped). Processes spawned inside an sshd session inherit Remote Login's TCC grant and read the volume fine.

So `kiwix-serve-agent.sh` waits for the volume, then `exec`s kiwix-serve **via `ssh savusilviu@127.0.0.1`**. Requirements: Remote Login enabled + localhost pubkey auth. The relay command also raises `ulimit -n 32768`: sshd spawns children with a **256 fd soft limit**, and kiwix holds ~1 fd per open ZIM (3,259) — without the raise it hits EMFILE mid-warmup and then **caches every failed ZIM open** (permanent HTTP 500 for those books until the serve restarts).

Symptom decoder:

| Symptom | Cause | Fix |
|---|---|---|
| catalog endpoints answer but 0 entries; suggest 404s for every book | serve lost TCC access (started outside ssh relay, or relay broke) | `sudo launchctl kickstart -k system/local.kiwix.serve8181`; verify the ssh relay works: `ssh savusilviu@127.0.0.1 true` |
| some books return instant HTTP 500 on /suggest, forever | EMFILE burst → cached failed opens | restart the serve (same kickstart), confirm `ulimit -n 32768` in `kiwix-serve-agent.sh` |
| snippets are `[book] local library article` placeholders, ~20 min after mini reboot | warmup still opening books (each suggest blocks on a cold USB-HDD open) | wait for `warmup done: 3259/3259` in `~/Library/Logs/local.kiwix.warm8181.out.log` |

### Warmup (once per boot, ~20 min)

kiwix-tools 3.8.2 has **no working global warmup**: the old `/search?pattern=...` API returns 400 and opens nothing (the pre-3.8.2 one-liner warmup was silently a no-op — this went unnoticed for a long time). `kiwix-warmup.sh` instead reads the 3,259 book ids from `titles_slim.db` (internal SSD — no TCC problem) and fires one `/suggest?content=<book>` per book, 4-way concurrent (matching kiwix's thread count). First pass measured: **3,259/3,259 in ~22 min**. Books stay open for the serve's lifetime, so this cost is paid once per boot. Expect degraded zimtitles latency while it runs (USB HDD saturated).

### zimtitles service (:7777) — two-tier query planner

`~/zh-venv/zimtitles_service.py` searches a 470.5M-title FTS5 index (`titles_slim.db`, 57 GiB, internal SSD). FTS5's `ORDER BY rank` must walk the driving term's whole posting list (~70 µs/row), so a common word like "physics" (df > 50k) is a multi-minute walk — the original service simply bailed with `[]` for **every everyday query** at this corpus scale. The planner (Lucene `CommonTermsQuery` semantics) now routes:

| Query shape | Mode | Strategy | Typical latency |
|---|---|---|---|
| some term df ≤ 20,000 | `ranked` | `ORDER BY rank` over selective AND plan (as before) | 10–30 ms |
| every term df > 20,000 ("physics", "machine learning") | `sample` | plain conjunction, evaluated in 8 stratified rowid windows (120 rows each), bm25-scored inline in the SELECT (no rank iterator), sorted in-process | 150–300 ms |
| terms absent from index | — | empty | < 10 ms |

The response carries `"mode": "ranked"|"sample"` for observability. Invariants: never `ORDER BY rank` a df>20k term; `COUNT(*)` and `min/max(rowid)` on this FTS5 table are 160-second full scans (the span is derived by binary-searching point rowid lookups instead).

### Snippet extraction (engine `zimtitles.py`)

For each of the top-12 reranked results: resolve the ZIM path via `/suggest` (kind=`path`; 8 s timeout + one retry — a client timeout does not cancel the server-side lazy open, so the retry usually lands warm), then fetch the first 32 KB via HTTP Range and extract:

1. first `<p>` longer than 60 chars (encyclopedia lead), else
2. **merge consecutive short paragraphs** until > 60 chars (wiktionary definition/etymology lines are 20–40 chars each — a large share of the library; without this pass every wiktionary hit showed a placeholder), else
3. fall back to `[book] local library article` (typically infobox-heavy pages with no `<p>` in the first 32 KB).

### MCP server (alternative agent entry point)

`~/zh-venv/zimtitles_mcp.py` exposes the same library to any MCP client over stdio — zero dependencies (pure Python 3.9 stdlib; the official `mcp` SDK needs ≥ 3.10):

```json
{ "mcpServers": { "zimtitles": {
    "command": "ssh",
    "args": ["macmini", "/Users/savusilviu/zh-venv/zimtitles_mcp.py"] } } }
```

Tools: `zim_search` (titles across all books), `zim_read` (article plain text, ~10 KB truncated), `zim_catalog` (book listing from `titles_slim.db`). Read-only by construction (two GET-speaking HTTP clients). Deliberately **not** wired into pi — the SearXNG path remains the primary integration.

## Changes made (2026-08-25 session)

Commits on `main`:

- `59d100538` — replace raw Netbird IP with DNS name (`mac-mini-von-savu.netbird.selfhosted`) in settings.yml, zimtitles.py, zimtitles_bench.py; verified end-to-end.
- `a2d7e93d0` — snippet path hardening: `_resolve_path` 8 s + retry, `_lead_snippet` 3 s → 8 s (cold-ZIM opens on USB HDD exceed the old 3 s).
- `b2fc51de7` — two-pass snippet extraction (short-paragraph/wiktionary pages).
- this commit — documentation upgrade.

Mac-mini side (not in this repo): two-tier planner in `zimtitles_service.py`, ssh-relay + `ulimit -n 32768` in `kiwix-serve-agent.sh`, per-book warmup in `kiwix-warmup.sh`, LaunchDaemons `local.kiwix.warm8181` (+ zimtitles daemon reconciliation), `zimtitles_mcp.py`, library.xml absolute paths + `version="1.0"`.

Historical (commit `5c2ce8608` + follow-ups): 666 per-book kiwix engines replaced by single `zimtitles` engine; `candidates` 12 → 30, `final` 8 → 12, `weight` 1.5 → 0.6; reranker url fixed to `host.docker.internal:8101`; MLX reranker launchd on host.

## Troubleshooting

### MLX reranker (port 8101) is down
```bash
launchctl start local.mlx.reranker
tail -f ~/Library/Logs/mlx-reranker.log
```

### searXNG is down
```bash
docker restart firecrawl-searxng-1
curl http://localhost:8888/healthz
```

### zimtitles server (Mac Mini :7777) is down
```bash
ssh macmini
sudo launchctl kickstart -k system/local.kiwix.zimtitles   # it is a system LaunchDaemon
curl -s http://127.0.0.1:7777/health   # {"status":"ok","books":3259}
tail -5 ~/zh-venv/zimtitles.out
```

Do **not** start uvicorn manually — a hand-started instance squats port 7777 and the KeepAlive daemon spawn-loops against it (this caused intermittent engine timeouts once already).

### kiwix-serve (Mac Mini :8181) is down or serves an empty catalog
```bash
ssh macmini
sudo launchctl kickstart -k system/local.kiwix.serve8181
# catalog should list books within ~30s:
curl -s "http://127.0.0.1:8181/catalog/v2/entries?count=1" | grep -c "<entry>"   # 1
# if 0 entries: see the TCC/ssh-relay section above
tail -20 ~/Library/Logs/local.kiwix.serve8181.err.log
```

After any serve restart, the warmup daemon should re-fire on its own; if not: `sudo launchctl kickstart system/local.kiwix.warm8181`.

### Firecrawl API is down
```bash
cd ~/projects/firecrawl
docker compose up -d api
```
