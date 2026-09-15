"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.executeSearch = executeSearch;
const config_1 = require("../config");
const v2_1 = require("./v2");
const reranker_1 = require("./v2/reranker");
const rag_1 = require("./v2/rag");
const grounded_answer_1 = require("./v2/grounded-answer");
const persistence_1 = require("./v2/persistence");
const search_query_builder_1 = require("../lib/search-query-builder");
const scrape_1 = require("./scrape");
const highlights_1 = require("./highlights");
const highlights_shadow_1 = require("./highlights-shadow");
const tracking_1 = require("../lib/tracking");
const request_1 = require("../lib/threat-protection/request");
const scrape_billing_1 = require("../lib/scrape-billing");
async function executeSearch(options, context, logger) {
    const { query, limit, sources, categories, scrapeOptions } = options;
    
    
    
    if (scrapeOptions && config_1.config.DEEPINFRA_API_KEY) {
        const cached = await (0, persistence_1.checkAnswerCache)(query, logger);
        if (cached) {
            logger.info("Answer cache hit; skipping pipeline", { query });
            return {
                response: { answer: cached },
                totalResultsCount: 0,
                searchCredits: 0,
                scrapeCredits: 0,
                totalCredits: 0,
                shouldScrape: false,
            };
        }
    }
    const { teamId, origin, apiKeyId, flags, requestId, bypassBilling, zeroDataRetention, billing, } = context;
    
    
    const RERANK_MIN_CANDIDATES = 30;
    const num_results_buffer = Math.max(Math.floor(limit * 2), RERANK_MIN_CANDIDATES);
    
    let __last = Date.now();
    const __mark = (stage, extra = {}) => {
        const now = Date.now();
        const ms = now - __last;
        __last = now;
        logger.info(`pipeline.stage ${stage} ${ms}ms ${JSON.stringify(extra)}`);
    };
    logger.info("Searching for results");
    const searchTypes = [...new Set(sources.map((s) => s.type))];
    const { query: searchQuery, categoryMap } = (0, search_query_builder_1.buildSearchQuery)(query, categories, {
        includeDomains: options.includeDomains,
        excludeDomains: options.excludeDomains,
    });
    const searchResponse = (await (0, v2_1.search)({
        query: searchQuery,
        logger,
        advanced: false,
        num_results: num_results_buffer,
        timeout: options.timeout,
        tbs: options.tbs,
        filter: options.filter,
        lang: options.lang,
        country: options.country,
        location: options.location,
        type: searchTypes,
        enterprise: options.enterprise,
    }));
    __mark("search", { candidates: searchResponse.web?.length ?? 0 });
    // Threat protection: remove blocked results entirely — before
    // slicing/counting, before scraping, and before returning. Checks are
    // URL-level and deduped within this request; scan fees bill +2 per unique
    // scanned URL (see calculateThreatScanCredits), charged as part of the
    // search credits below.
    let threatScanCredits = 0;
    const threatPolicy = context.threatProtectionPolicy;
    if (threatPolicy && threatPolicy.mode !== "off") {
        const urlsToCheck = [
            ...(searchResponse.web ?? []).map(x => x.url),
            ...(searchResponse.news ?? []).map(x => x.url),
            ...(searchResponse.images ?? []).map(x => x.url),
        ].filter((x) => !!x);
        if (urlsToCheck.length > 0) {
            const { decisionsByUrl } = await (0, request_1.checkUrlsAgainstThreatPolicy)(urlsToCheck, threatPolicy, { teamId });
            threatScanCredits = (0, scrape_billing_1.calculateThreatScanCredits)(decisionsByUrl.values());
            const isAllowed = (url) => {
                if (!url)
                    return true;
                const decision = decisionsByUrl.get(url);
                return decision === undefined || decision.allowed;
            };
            if (searchResponse.web) {
                searchResponse.web = searchResponse.web.filter(x => isAllowed(x.url));
            }
            if (searchResponse.news) {
                searchResponse.news = searchResponse.news.filter(x => isAllowed(x.url));
            }
            if (searchResponse.images) {
                searchResponse.images = searchResponse.images.filter(x => isAllowed(x.url));
            }
        }
    }
    if (searchResponse.web && searchResponse.web.length > 0) {
        searchResponse.web = searchResponse.web.map(result => ({
            ...result,
            category: (0, search_query_builder_1.getCategoryFromUrl)(result.url, categoryMap),
        }));
        // Always-on rerank: score the full candidate pool against the query, then
        // the slice below keeps the most relevant top-`limit`. Best-effort ordering
        // -- on any reranker failure the SearXNG order is kept (see reranker.ts).
        searchResponse.web = await (0, reranker_1.rerankWebResults)(query, searchResponse.web, logger);
    }
    __mark("rerank", { web: searchResponse.web?.length ?? 0 });
    if (searchResponse.news && searchResponse.news.length > 0) {
        searchResponse.news = searchResponse.news.map(result => ({
            ...result,
            category: result.url
                ? (0, search_query_builder_1.getCategoryFromUrl)(result.url, categoryMap)
                : undefined,
        }));
    }
    let totalResultsCount = 0;
    if (searchResponse.web && searchResponse.web.length > 0) {
        if (searchResponse.web.length > limit) {
            searchResponse.web = searchResponse.web.slice(0, limit);
        }
        totalResultsCount += searchResponse.web.length;
    }
    __mark("slice", { web: searchResponse.web?.length ?? 0 });
    if (searchResponse.images && searchResponse.images.length > 0) {
        if (searchResponse.images.length > limit) {
            searchResponse.images = searchResponse.images.slice(0, limit);
        }
        totalResultsCount += searchResponse.images.length;
    }
    if (searchResponse.news && searchResponse.news.length > 0) {
        if (searchResponse.news.length > limit) {
            searchResponse.news = searchResponse.news.slice(0, limit);
        }
        totalResultsCount += searchResponse.news.length;
    }
    const isZDR = options.enterprise?.includes("zdr");
    const creditsPerTenResults = isZDR ? 10 : 2;
    // Threat protection scan fees ride on the search credits: they are part of
    // serving the search itself (every result domain is scanned before
    // filtering), so they bill against the same feature and show up in the
    // request's creditsUsed.
    const searchCredits = Math.ceil(totalResultsCount / 10) * creditsPerTenResults +
        threatScanCredits;
    let scrapeCredits = 0;
    const shouldScrape = scrapeOptions?.formats && scrapeOptions.formats.length > 0;
    let retrievalSufficient = true;
    if (shouldScrape) {
        __mark("pre_sufficiency");
        retrievalSufficient = await (0, grounded_answer_1.checkSufficiency)(query, (0, grounded_answer_1.buildSnippets)(searchResponse.web ?? []), logger);
        if (!retrievalSufficient) {
            searchResponse.answer = {
                text: "The retrieved context does not contain sufficient information to answer this query.",
                faithfulness: 0,
                grounded: false,
                reason: "insufficient_context",
            };
        }
    }
    if (shouldScrape && scrapeOptions && retrievalSufficient) {
        const itemsToScrape = (0, scrape_1.getItemsToScrape)(searchResponse, flags, {
            team_id: teamId,
            origin,
        });
        if (itemsToScrape.length > 0) {
            const scrapeOpts = {
                teamId,
                origin,
                timeout: options.timeout,
                scrapeOptions,
                bypassBilling: bypassBilling ?? false,
                apiKeyId,
                zeroDataRetention,
                requestId,
                billing,
                agentIndexOnly: context.agentIndexOnly,
                keylessReserved: context.keylessReserved,
                threatProtectionPolicy: threatPolicy ?? null,
            };
            const allDocsWithCostTracking = await (0, scrape_1.scrapeSearchResults)(itemsToScrape.map(i => i.scrapeInput), scrapeOpts, logger, flags);
            (0, scrape_1.mergeScrapedContent)(searchResponse, itemsToScrape, allDocsWithCostTracking);
            scrapeCredits = (0, scrape_1.calculateScrapeCredits)(allDocsWithCostTracking);
            __mark("scrape", { scraped: itemsToScrape.length });
            // RAG: chunk each scraped page, embed via DeepInfra bge-m3, and attach the
            // top-k passages most relevant to the query. Best-effort (see rag.ts).
            await (0, rag_1.attachRagPassages)(searchResponse, query, logger);
            __mark("rag");
            // Grounded answer: synthesize one answer to the query from the scraped
            // pages via GLM-5.2 (ZAI Coding Plan), then HHEM-verify it. Best-effort.
            await (0, grounded_answer_1.buildGroundedAnswer)(searchResponse, query, logger);
            __mark("grounded_answer");
        }
    }
    // Experimental highlights beta: replace provider snippets with index-backed
    // highlights. Gated on (1) the request opting in, (2) the team's highlightsBeta
    // flag, and (3) all required envs being present (index DB, GCS, model). Any
    // gate failing => silently keep the provider snippets.
    // Runs after scraping (mergeScrapedContent rebuilds the result objects, so
    // highlight mutations must come last to survive). Uses the user's original
    // query, not the domain-filtered upstream query.
    const shouldApplyHighlights = options.highlights &&
        flags?.highlightsBeta === true &&
        (0, highlights_1.highlightsEnvReady)();
    if (shouldApplyHighlights) {
        await (0, highlights_1.applyIndexedSearchHighlights)(searchResponse, query, logger, context.requestId);
    }
    else {
        (0, highlights_shadow_1.runSearchHighlightsShadow)({
            response: searchResponse,
            query,
            requestId: context.requestId,
            teamId,
            zeroDataRetention: zeroDataRetention === true || isZDR === true,
        });
    }
    const scrapeFormats = scrapeOptions?.formats
        ? scrapeOptions.formats.map((f) => typeof f === "string" ? f : f.type)
        : [];
    (0, tracking_1.trackSearchRequest)({
        searchId: context.jobId,
        requestId: context.requestId,
        teamId,
        query,
        origin,
        kind: billing?.endpoint ?? "search",
        apiVersion: context.apiVersion,
        lang: options.lang,
        country: options.country,
        sources: searchTypes,
        numResults: totalResultsCount,
        searchCredits,
        scrapeCredits,
        totalCredits: searchCredits + scrapeCredits,
        hasScrapeFormats: shouldScrape ?? false,
        scrapeFormats,
        isSuccessful: true,
        timeTaken: 0, // filled by caller if needed
        zeroDataRetention: zeroDataRetention ?? false,
    }).catch(err => logger.warn("Search request tracking failed", { error: err }));
    (0, tracking_1.trackSearchResults)({
        searchId: context.jobId,
        teamId,
        response: searchResponse,
        zeroDataRetention: zeroDataRetention ?? false,
        hasScrapeFormats: shouldScrape ?? false,
    }).catch(err => logger.warn("Search tracking failed", { error: err }));
    return {
        response: searchResponse,
        totalResultsCount,
        searchCredits,
        scrapeCredits,
        totalCredits: searchCredits + scrapeCredits,
        shouldScrape: shouldScrape ?? false,
    };
}
//# sourceMappingURL=execute.js.map