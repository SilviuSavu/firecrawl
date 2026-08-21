#!/usr/bin/env python3
"""
Local vs web benchmark: compare result quality across query types.
Scores every result (both engines) with the MLX reranker to get a unified
relevance score, then finds the optimal weight ratio.
"""

import json
import os
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from statistics import mean, median

SEARXNG = os.environ.get("SEARXNG_URL", "http://localhost:8888")
RERANKER = os.environ.get("RERANKER_URL",
    "http://host.docker.internal:8101/rerank")

QUERIES = {
    "reference": [
        "rust async await explained",
        "python decorator @ syntax",
        "git merge squash rebase",
        "docker compose volumes bind",
        "javascript promise chaining",
        "kafka consumer offset reset",
        "postgres transaction isolation levels",
        "typescript type vs interface vs type",
        "redis pubsub pattern usage",
        "graphql vs rest api comparison",
    ],
    "current": [
        "iPhone 16 price 2026",
        "US presidential poll 2026",
        "latest AI news this week",
        "bitcoin price today",
        "fed interest rate cut 2026",
        "Nvidia stock 2026",
        "TSMC 3nm production 2026",
        "instagram threads update 2026",
        "microsoft layoffs 2026",
        "samsung galaxy watch 2026",
    ],
    "mixed": [
        "TSMC chip manufacturing process",
        "verifier timeout testing",
        "machine learning explained simply",
        "Rust programming for beginners",
        "hashicorp terraform vs pulumi",
        "nginx reverse proxy vs load balancer",
        "renewable energy solar vs wind",
        "database design patterns examples",
        "kubernetes pod autoscaling",
        "oauth vs openid connect",
    ],
}

# Number of results to fetch per category
# searXNG default limit is ~20-50 per category
SEARCH_LIMIT = 30

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


def searx_search(query, categories=None):
    """Query searXNG and return results with engine attribution."""
    params = [
        f"q={urllib.parse.quote(query)}",
        "format=json",
        f"limit={SEARCH_LIMIT}",
    ]
    if categories:
        # searXNG categories: comma-separated, URL-encoded
        params.append(f"categories={urllib.parse.quote(categories)}")
    url = f"{SEARXNG}/search?{'&'.join(params)}"
    try:
        data = _get(url, timeout=30.0)
        return data.get("results", [])
    except Exception as e:
        print(f"  [ERR] searx search: {e}")
        return []


def extract_results(results, engine_filter=None):
    """Get result (title, url, engine) tuples, optionally filtered by engine."""
    out = []
    for r in results:
        eng = r.get("engine", "?")
        if engine_filter and eng != engine_filter:
            continue
        title = r.get("title", "")
        url = r.get("url", "")
        snippet = r.get("content", "") or r.get("snippet", "")
        if title:
            out.append({"title": title, "url": url, "engine": eng, "snippet": snippet})
    return out


def rerank_score(query, documents):
    """Score all documents against query. Returns list of (score, doc) sorted descending."""
    if not documents:
        return []
    try:
        res = _post(RERANKER, {
            "query": query,
            "documents": [d["title"] + ". " + d.get("snippet", "") for d in documents],
            "top_k": len(documents),
        })
        scored = []
        for r in res.get("results", []):
            idx = r.get("index")
            score = r.get("score", 0.0)
            if idx is not None and idx < len(documents):
                scored.append((score, documents[idx]))
        scored.sort(key=lambda x: -x[0])
        return scored
    except Exception as e:
        print(f"  [ERR] reranker: {e}")
        return []


def main():
    print("=" * 72)
    print("  Local (zimtitles) vs Web (google cse, bing, exa, bravesearch)")
    print("  Benchmark: result relevance by query type")
    print("=" * 72)
    print(f"\nQuery categories: {', '.join(f'{k} ({len(v)})' for k, v in QUERIES.items())}")
    total = sum(len(v) for v in QUERIES.values())
    print(f"Total queries: {total}")
    print()

    # For each query, collect local and web results separately
    # Local: through searXNG with categories=offline (only zimtitles)
    # Web: mixed - local (we get mixed, then diff)
    by_type = defaultdict(list)

    t0 = time.monotonic()
    done = 0
    for qtype, queries in QUERIES.items():
        for query in queries:
            done += 1
            print(f"  [{done}/{total}] {qtype:10s} {query[:40]:40s}  ", end="", flush=True)

            # Get mixed results (all engines)
            mixed_results = searx_search(query)
            if not mixed_results:
                print("no mixed results")
                continue

            # Separate into local vs web
            local_docs = extract_results(mixed_results, engine_filter="zimtitles")
            web_docs = [d for d in extract_results(mixed_results) if d["engine"] != "zimtitles"]

            # Score local results against query
            local_scored = rerank_score(query, local_docs) if local_docs else []

            # Score web results against query
            web_scored = rerank_score(query, web_docs) if web_docs else []

            # Record best scores
            best_local = local_scored[0][0] if local_scored else 0.0
            best_web = web_scored[0][0] if web_scored else 0.0
            n_local = len(local_scored)
            n_web = len(web_scored)

            # Avg of top-5 scores
            top5_local = mean([s for s, _ in local_scored[:5]]) if len(local_scored) >= 5 else (mean([s for s, _ in local_scored]) if local_scored else 0.0)
            top5_web = mean([s for s, _ in web_scored[:5]]) if len(web_scored) >= 5 else (mean([s for s, _ in web_scored]) if web_scored else 0.0)

            print(f"local: {n_local:2d} best={best_local:.4f} avg5={top5_local:.4f}  "
                  f"web: {n_web:2d} best={best_web:.4f} avg5={top5_web:.4f}", flush=True)

            by_type[qtype].append({
                "query": query,
                "n_local": n_local, "n_web": n_web,
                "best_local": best_local, "best_web": best_web,
                "mean5_local": top5_local, "mean5_web": top5_web,
                "local_scores": [s for s, _ in local_scored],
                "web_scores": [s for s, _ in web_scored],
            })

    elapsed = time.monotonic() - t0

    print()
    print("=" * 72)
    print("  RESULTS BY QUERY TYPE")
    print("=" * 72)
    for qtype in ["reference", "current", "mixed"]:
        items = by_type[qtype]
        print(f"\n─── {qtype.upper()} ({len(items)} queries) ───")
        print(f"{'query':<42s} {'n_local':>7} {'best_l':>7} {'mean5_l':>7} "
              f"{'n_web':>5} {'best_w':>7} {'mean5_w':>7} {'win':>5}")
        wins = {"local": 0, "web": 0, "tie": 0}
        for item in items:
            bl = item["best_local"]
            bw = item["best_web"]
            if bl > bw + 0.01:
                w = "local"
                wins["local"] += 1
            elif bw > bl + 0.01:
                w = "web"
                wins["web"] += 1
            else:
                w = "tie"
                wins["tie"] += 1
            print(f"{item['query']:<42s} {item['n_local']:>7d} {bl:>7.4f} {item['mean5_local']:>7.4f} "
                  f"{item['n_web']:>5d} {bw:>7.4f} {item['mean5_web']:>7.4f} {w:>5s}")

        # Aggregate
        all_best_local = [it["best_local"] for it in items if it["best_local"] > 0]
        all_best_web = [it["best_web"] for it in items if it["best_web"] > 0]
        all_mean5_local = [it["mean5_local"] for it in items if it["mean5_local"] > 0]
        all_mean5_web = [it["mean5_web"] for it in items if it["mean5_web"] > 0]
        print()
        print(f"  local avg best score: {mean(all_best_local):.4f}" if all_best_local else "  no local results")
        print(f"  web   avg best score: {mean(all_best_web):.4f}" if all_best_web else "  no web results")
        print(f"  local avg top-5 mean: {mean(all_mean5_local):.4f}" if all_mean5_local else "  -")
        print(f"  web   avg top-5 mean: {mean(all_mean5_web):.4f}" if all_mean5_web else "  -")
        print(f"  best-result wins: local={wins['local']} web={wins['web']} tie={wins['tie']}")

    # Overall summary
    print()
    print("=" * 72)
    print("  WEIGHT RECOMMENDATION")
    print("=" * 72)

    # For each query type, compute the weight at which local and web best results
    # would be equal in the merged ranking.
    # searXNG score ~= weight * (1 / (rank+1)) * ...
    # For the best result from each source, we approximate:
    #   local_score ~= weight_local * engine_score_local
    #   web_score   ~= weight_web * engine_score_web
    # At equilibrium: weight_local * best_local = weight_web * best_web
    # => weight_local / weight_web = best_web / best_local (if web has better results)
    # Currently: weight_web = 0.4 (average across engines)
    # So: weight_local = 0.4 * best_web / best_local

    print("\n  Per-query-type ideal weight for local (web weight fixed at 0.4):")
    print(f"  (based on: weight_local * best_local = weight_web * best_web)")
    print(f"  {'type':>12s}  {'n':>4}  {'avg best_local':>15} {'avg best_web':>14} {'ideal w_local':>14}")
    for qtype in ["reference", "current", "mixed"]:
        items = by_type[qtype]
        ratios = []
        for it in items:
            bl = it["best_local"]
            bw = it["best_web"]
            if bl > 0.1 and bw > 0.1:
                # What weight would make local result equal to web result?
                # w_l * bl = 0.4 * bw  =>  w_l = 0.4 * bw / bl
                ratios.append(0.4 * bw / bl)
        if ratios:
            ideal = mean(ratios)
            bl_all = mean([it["best_local"] for it in items if it["best_local"] > 0])
            bw_all = mean([it["best_web"] for it in items if it["best_web"] > 0])
            print(f"  {qtype:>12s}  {len(items):>4d}  {bl_all:>14.4f}  {bw_all:>13.4f}  {ideal:>13.2f}")
        else:
            print(f"  {qtype:>12s}  {len(items):>4d}  {'insufficient data':>29}")

    print(f"\n  ⏱  Elapsed: {elapsed:.0f}s")


if __name__ == "__main__":
    main()
