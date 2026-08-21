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

### Mac Mini (`100.125.208.86` — Mac-mini-von-Savu.local)

| Service | Port | Launch | Persistence |
|---------|------|--------|-------------|
| zimtitles title server | :7777 | launchd `local.kiwix.zimtitles` | `~/Library/LaunchAgents/local.kiwix.zimtitles.plist` |
| kiwix-serve (main library) | :8181 | launchd `local.kiwix.serve8181` | `~/Library/LaunchAgents/local.kiwix.serve8181.plist` |
| kiwix-serve (english search) | :8182 | launchd `local.kiwix.serve8182` | `~/Library/LaunchAgents/local.kiwix.serve8182.plist` |

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

## Changes made (this session)

All committed as `5c2ce8608`:

1. **settings.yml**: Removed 666 per-book kiwix engine entries (file 10,022→124 lines). Replaced by single `zimtitles` engine (above).
2. **zimtitles.py**: 
   - `candidates`: 12 → 30 (wider reranker pool)
   - `final`: 8 → 12 (more results per query)
   - `weight`: 1.5 → 0.6 (data-driven from benchmarks)
   - `reranker_url`: fixed from dead IP `100.125.208.86:8101` → live `host.docker.internal:8101`
3. **MLX reranker launchd**: Created `local.mlx.reranker` plist for auto-start on boot.

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

### zimtitles server (Mac Mini) is down
```bash
ssh savusilviu@100.125.208.86
launchctl start local.kiwix.zimtitles
```

### kiwix-serve (Mac Mini) is down
```bash
ssh savusilviu@100.125.208.86
launchctl start local.kiwix.serve8181
```

### Firecrawl API is down
```bash
cd ~/projects/firecrawl
docker compose up -d api
```
