import { SearchV2Response, SearchResultType } from "../../lib/entities";
import { config } from "../../config";
import { fire_engine_search_v2 } from "./fireEngine-v2";
import { searxng_search } from "./searxng";
import { ddgSearch } from "./ddgsearch";
import { Logger } from "winston";

export async function search({
  query,
  logger,
  requestId,
  advanced = false,
  num_results = 5,
  tbs = undefined,
  filter = undefined,
  lang = "en",
  country = "us",
  location = undefined,
  safe = undefined,
  proxy = undefined,
  sleep_interval = 0,
  timeout = 30000,
  type = undefined,
  enterprise = undefined,
  includeDomains = undefined,
  excludeDomains = undefined,
}: {
  query: string;
  logger: Logger;
  requestId?: string;
  advanced?: boolean;
  num_results?: number;
  tbs?: string;
  filter?: string;
  lang?: string;
  country?: string;
  location?: string;
  safe?: boolean;
  proxy?: string;
  sleep_interval?: number;
  timeout?: number;
  type?: SearchResultType | SearchResultType[];
  enterprise?: ("default" | "anon" | "zdr")[];
  includeDomains?: string[];
  excludeDomains?: string[];
}): Promise<SearchV2Response> {
  try {
    if (config.FIRE_ENGINE_BETA_URL) {
      logger.info("Using fire engine search");
      const results = await fire_engine_search_v2(query, {
        requestId,
        numResults: num_results,
        tbs,
        filter,
        lang,
        country,
        location,
        safe,
        type,
        enterprise,
        includeDomains,
        excludeDomains,
      });

      return results;
    }

    // includeDomains/excludeDomains are enforced on returned URLs only on
    // the fire engine path above; the fallback providers below receive them
    // solely as the site: chain baked into the query.
    let searxngMeta:
      | { unresponsiveEngines?: string[]; provider?: string }
      | undefined;
    if (config.SEARXNG_ENDPOINT) {
      logger.info("Using searxng search");
      const results = await searxng_search(query, {
        num_results,
        tbs,
        filter,
        lang,
        country,
        location,
        type,
        timeout,
        safe,
      });
      const hasAny =
        (results.web?.length ?? 0) > 0 ||
        (results.images?.length ?? 0) > 0 ||
        (results.news?.length ?? 0) > 0;
      if (hasAny) return results;
      searxngMeta = results.meta;
    }

    logger.info("Using DuckDuckGo search");
    const ddgResults = await ddgSearch(query, num_results, {
      tbs,
      lang,
      country,
      proxy,
      timeout,
    });
    if (ddgResults.web && ddgResults.web.length > 0) {
      ddgResults.meta = {
        unresponsiveEngines: searxngMeta?.unresponsiveEngines ?? [],
        provider: "duckduckgo",
      };
      return ddgResults;
    }

    // Fallback to empty response
    return {
      meta: {
        unresponsiveEngines: searxngMeta?.unresponsiveEngines ?? [],
        provider: "duckduckgo",
      },
    };
  } catch (error) {
    logger.error(`Error in search function`, { error });
    return {};
  }
}
