#!/usr/bin/env python3
"""
zimtitles benchmark: measure the (candidates, final) Pareto frontier.

candidates = pool size fed to the reranker (default 12)
final      = kept after rerank (default 8)

Runs a grid of (candidates, final) over a query set drawn from the local ZIM
library. Outputs latency and reranker-score-at-rank for each combination.

Usage:
  python3 zimtitles_bench.py                          # default grid
  python3 zimtitles_bench.py --queries 30 --candidates 12,20,30,50 --finals 8,12,16
  python3 zimtitles_bench.py --reranker-url http://localhost:8101/rerank

Set endpoints via env: ZIMTITLES_URL, KIWIX_URL, RERANKER_URL
"""

import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from statistics import median


# ---------------------------------------------------------------------------
# Defaults (overridable via env)
# ---------------------------------------------------------------------------
TITLES_URL  = os.environ.get("ZIMTITLES_URL",  "http://100.125.208.86:7777")
KIWIX_URL   = os.environ.get("KIWIX_URL",     "http://100.125.208.86:8181")
RERANK_URL  = os.environ.get("RERANKER_URL",  
    "http://host.docker.internal:8101/rerank")


def _post(url, payload, timeout=15.0):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get(url, timeout=15.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------------------
# Stage 1 — fetch candidate titles
# ---------------------------------------------------------------------------
def stage_titles(query: str, limit: int):
    t0 = time.monotonic()
    url = f"{TITLES_URL}/search?q={urllib.parse.quote(query)}&limit={limit}"
    data = _get(url)
    elapsed = (time.monotonic() - t0) * 1000
    return data.get("results", []), elapsed


# ---------------------------------------------------------------------------
# Stage 2 — rerank
# ---------------------------------------------------------------------------
def stage_rerank(query: str, titles: list[dict], top_k: int):
    if not titles:
        return [], 0.0
    docs = [t["title"] for t in titles]
    t0 = time.monotonic()
    res = _post(RERANK_URL,
                {"query": query, "documents": docs, "top_k": top_k})
    elapsed = (time.monotonic() - t0) * 1000
    return res.get("results", []), elapsed


# ---------------------------------------------------------------------------
# Stage 3 — path resolution + snippet fetch (parallel)
# ---------------------------------------------------------------------------
def _resolve_path(book: str, title: str):
    book = book.replace(".zim", "")
    try:
        u = f"{KIWIX_URL}/suggest?content={urllib.parse.quote(book)}&term={urllib.parse.quote(title)}"
        with urllib.request.urlopen(u, timeout=5.0) as r:
            for s in json.loads(r.read()):
                if s.get("kind") == "path" and s.get("path"):
                    return s["path"]
    except Exception:
        pass
    return None


def _fetch_snippet(book: str, path: str | None):
    if not path:
        return None
    book = book.replace(".zim", "")
    try:
        u = f"{KIWIX_URL}/content/{urllib.parse.quote(book)}/{urllib.parse.quote(path)}"
        req = urllib.request.Request(u, headers={"Range": "bytes=0-32767"})
        with urllib.request.urlopen(req, timeout=5.0) as r:
            body = r.read(32768).decode("utf-8", errors="ignore")
        for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S):
            t = re.sub(r"<[^>]+>", " ", p)
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) > 60:
                return t[:300]
    except Exception:
        pass
    return None


def stage_snippets(top: list[dict]):
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(len(top), 1)) as ex:
        paths = list(ex.map(
            lambda t: _resolve_path(t["book"].replace(".zim", ""), t["title"]),
            top))
        snippets = list(ex.map(
            lambda tp: _fetch_snippet(tp[0]["book"].replace(".zim", ""), tp[1]),
            zip(top, paths)))
    elapsed = (time.monotonic() - t0) * 1000
    return paths, snippets, elapsed


# ---------------------------------------------------------------------------
# Single (query, candidates, final) run
# ---------------------------------------------------------------------------
def run_one(query: str, candidates: int, final: int):
    t_start = time.monotonic()

    titles, t_titles_ms = stage_titles(query, candidates)
    if not titles:
        return {
            "query": query, "candidates": candidates, "final": final,
            "n_titles": 0, "skipped": "no_titles",
            "t_total_ms": (time.monotonic() - t_start) * 1000,
        }

    # Rerank: get top_k = final (or less if pool is small)
    reranked_rows, t_rerank_ms = stage_rerank(
        query, titles, min(final, len(titles)))

    # Reorder titles per reranker; fallback to original order on failure
    reranked = []
    for r in reranked_rows:
        idx = r.get("index")
        if idx is not None and idx < len(titles):
            reranked.append(titles[idx])
    if not reranked:
        reranked = titles[:final]

    top = reranked[:final]

    # Snippets
    paths, snippets, t_snippets_ms = stage_snippets(top)

    # Quality proxy: reranker scores
    score_at = {}
    for r in reversed(reranked_rows):
        score_at[len(reranked_rows) - len(score_at)] = r.get("score", 0.0)
    # Simpler — scores at rank (1-indexed)
    scores = {}
    for r in reranked_rows:
        idx = r.get("index")
        rank = reranked.index(titles[idx]) + 1 if idx is not None and idx < len(titles) else None
        if rank:
            scores[rank] = r.get("score", 0.0)

    return {
        "query": query,
        "candidates": candidates,
        "final": final,
        "n_titles": len(titles),
        "n_reranked": len(reranked),
        "n_paths": sum(1 for p in paths if p),
        "n_snippets": sum(1 for s in snippets if s),
        "t_titles_ms": round(t_titles_ms, 1),
        "t_rerank_ms": round(t_rerank_ms, 1),
        "t_snippets_ms": round(t_snippets_ms, 1),
        "t_total_ms": round((time.monotonic() - t_start) * 1000, 1),
        "scores": {str(k): round(v, 4) for k, v in scores.items()},
    }


# ---------------------------------------------------------------------------
# Query set builder
# ---------------------------------------------------------------------------
SEEDS = [
    "rust async", "python decorator", "kubernetes pod", "docker compose",
    "react hooks", "git rebase", "linux kernel module", "javascript promise",
    "golang context", "typescript generic", "rust borrow", "python async",
    "http status code", "redis pubsub", "kafka consumer", "postgres index",
    "graphql resolver", "wasm runtime", "vllm scheduler", "neural network",
    "transformer attention", "regular expression", "sql join", "oauth flow",
    "jwt token", "elasticsearch query", "rabbitmq exchange", "make rule",
    "cmake target", "verifier timeout",
]

def build_queries(n: int):
    queries = []
    for q in SEEDS:
        if len(queries) >= n:
            break
        try:
            titles, _ = stage_titles(q, 3)
            if titles:
                queries.append(q)
        except Exception:
            pass
    return queries


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def summarize(results: list[dict]):
    cells = {}
    for r in results:
        if r.get("skipped"):
            continue
        k = (r["candidates"], r["final"])
        cells.setdefault(k, []).append(r)

    print()
    print("─── Pareto frontier ───")
    print(f"{'c':>5} {'f':>5} {'n':>5} {'med':>8} {'p95':>8} {'max':>8} "
          f"{'rerank':>8} {'snip':>8} {'path':>8} {'snip%':>8}")
    for (c, f), runs in sorted(cells.items()):
        totals = [r["t_total_ms"] for r in runs]
        rerank = [r["t_rerank_ms"] for r in runs]
        snips  = [r["t_snippets_ms"] for r in runs]
        n_path = [r["n_paths"] / max(r["n_reranked"], 1) for r in runs]
        n_snip = [r["n_snippets"] / max(r["n_reranked"], 1) for r in runs]
        p95 = sorted(totals)[int(0.95 * len(totals))]
        print(f"{c:>5d} {f:>5d} {len(runs):>5d} "
              f"{median(totals):>7.0f}ms {p95:>7.0f}ms {max(totals):>7.0f}ms "
              f"{median(rerank):>7.1f}ms {median(snips):>7.0f}ms "
              f"{median(n_path)*100:>7.0f}% {median(n_snip)*100:>7.0f}%")
    return cells


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="zimtitles benchmark")
    p.add_argument("--queries", type=int, default=20,
                   help="max queries to test (def 20)")
    p.add_argument("--candidates", default="12,20,30,50",
                   help="comma-sep candidate pool sizes (def 12,20,30,50)")
    p.add_argument("--finals", default="8,12,16",
                   help="comma-sep final kept counts (def 8,12,16)")
    p.add_argument("--out", default="zimtitles_bench_results.json",
                   help="json output path (def zimtitles_bench_results.json)")
    args = p.parse_args()

    cs = [int(x) for x in args.candidates.split(",")]
    fs = [int(x) for x in args.finals.split(",")]

    print(f"titles:  {TITLES_URL}")
    print(f"kiwix:   {KIWIX_URL}")
    print(f"rerank:  {RERANK_URL}")
    print(f"grid:    {len(cs)} candidates × {len(fs)} finals = {len(cs)*len(fs)}")
    print()

    queries = build_queries(args.queries)
    print(f"queries: {len(queries)} (from seed list)")
    if not queries:
        print("WARNING: no queries hit — is zimtitles reachable?")

    total = len(queries) * len(cs) * len(fs)
    print(f"runs:    {total}")
    print()

    results = []
    t0 = time.monotonic()
    for i, q in enumerate(queries):
        for c in cs:
            for f in fs:
                if f < c:  # only meaningful combos
                    r = run_one(q, c, f)
                    results.append(r)
        if (i + 1) % 10 == 0 or i == len(queries) - 1:
            print(f"  {i+1}/{len(queries)}  "
                  f"{(time.monotonic()-t0):.0f}s")

    cells = summarize(results)

    meta = {
        "titles_url": TITLES_URL,
        "kiwix_url": KIWIX_URL,
        "reranker_url": RERANK_URL,
        "queries": queries,
        "grid_candidates": cs,
        "grid_finals": fs,
        "n_results": len(results),
        "elapsed_s": round(time.monotonic() - t0, 1),
    }
    with open(args.out, "w") as fh:
        json.dump({"meta": meta, "results": results}, fh, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
