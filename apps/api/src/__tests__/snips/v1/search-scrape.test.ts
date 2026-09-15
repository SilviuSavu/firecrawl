import { describeIf, HAS_PROXY, HAS_SEARCH, scrapeTimeout, TEST_PRODUCTION } from "../lib";
import { search, searchRaw, idmux, Identity } from "./lib";

let identity: Identity;

beforeAll(async () => {
  identity = await idmux({
    name: "search-scrape",
    concurrency: 100,
    credits: 1000000,
  });
}, 10000);






describeIf(TEST_PRODUCTION || HAS_SEARCH || HAS_PROXY)("Search scrapeOptions pipeline", () => {
  it.concurrent(
    "scrapes markdown server-side for top results",
    async () => {
      const res = await search(
        {
          query: "firecrawl",
          limit: 3,
          scrapeOptions: {
            formats: ["markdown"],
            onlyMainContent: true,
            fastMode: true,
          },
          timeout: scrapeTimeout,
        },
        identity,
      );

      expect(res.length).toBeGreaterThan(0);
      expect(res.length).toBeLessThanOrEqual(3);

      
      
      for (const doc of res) {
        expect(doc.markdown).toBeDefined();
        expect(typeof doc.markdown).toBe("string");
        expect((doc.markdown ?? "").trim().length).toBeGreaterThan(100);
        expect(doc.url).toBeTruthy();
      }
    },
    scrapeTimeout + 30000,
  );

  it.concurrent(
    "returns multiple requested formats together",
    async () => {
      const res = await search(
        {
          query: "firecrawl",
          limit: 3,
          scrapeOptions: {
            formats: ["markdown", "links"],
            onlyMainContent: true,
          },
          timeout: scrapeTimeout,
        },
        identity,
      );

      expect(res.length).toBeGreaterThan(0);

      
      const withBoth = res.filter(
        d => typeof d.markdown === "string" && Array.isArray(d.links) && d.links.length > 0,
      );
      expect(withBoth.length).toBeGreaterThan(0);
    },
    scrapeTimeout + 30000,
  );

  it.concurrent(
    "omits markdown when scrapeOptions is absent (no-formats gate)",
    async () => {
      const res = await search(
        {
          query: "firecrawl",
          limit: 3,
        },
        identity,
      );

      expect(res.length).toBeGreaterThan(0);
      
      for (const doc of res) {
        expect(doc.markdown).toBeUndefined();
        expect(doc.url).toBeTruthy();
      }
    },
    60000,
  );

  it.concurrent(
    "rejects an invalid format name with 400",
    async () => {
      const raw = await searchRaw(
        {
          query: "firecrawl",
          limit: 1,
          scrapeOptions: {
            formats: ["bogus-format"],
          },
        } as any,
        identity,
      );

      expect(raw.statusCode).toBe(400);
      expect(raw.body.success).toBe(false);
    },
    60000,
  );
});
