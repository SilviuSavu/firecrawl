from firecrawl import V1JsonConfig, FirecrawlApp, AsyncFirecrawlApp, V1ScrapeOptions, V1JsonConfig
from pydantic import BaseModel, Field
from typing import List
import time
import os
from dotenv import load_dotenv


import nest_asyncio
import asyncio


load_dotenv()


api_key = os.getenv("TEST_API_KEY")
api_url = os.getenv("TEST_API_URL", "https://api.firecrawl.dev")

app = FirecrawlApp(api_key=api_key, api_url=api_url)


scrape_result = app.v1.scrape_url('example.com', formats=["markdown", "html"])
print(scrape_result.markdown)


urls = ['https://example.com', 'https://docs.firecrawl.dev']

batch_result = app.v1.batch_scrape_urls(urls, formats=["markdown", "html"])
print("Synchronous Batch Scrape Result:")
print(batch_result.data[0].markdown)


async_batch_result = app.v1.async_batch_scrape_urls(urls, formats=["markdown", "html"])
print("\nAsynchronous Batch Scrape Result:")
print(async_batch_result)


crawl_result = app.v1.crawl_url('firecrawl.dev', exclude_paths=['blog/*'])
print(crawl_result.data[0].markdown)


async_result = app.v1.async_crawl_url('firecrawl.dev', exclude_paths=['blog/*'])
print(async_result)

crawl_status = app.v1.check_crawl_status(async_result.id)
print(crawl_status)

attempts = 15
while attempts > 0 and crawl_status.status != 'completed':
    print(crawl_status)
    crawl_status = app.v1.check_crawl_status(async_result.id)
    attempts -= 1
    time.sleep(1)

crawl_status = app.v1.check_crawl_status(async_result.id)
print(crawl_status)



json_schema = {
  "type": "object",
  "properties": {
    "top": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "points": {"type": "number"},
          "by": {"type": "string"},
          "commentsURL": {"type": "string"}
        },
        "required": ["title", "points", "by", "commentsURL"]
      },
      "description": "Top 5 stories on Hacker News"
    }
  },
  "required": ["top"]
}

extract_config = V1JsonConfig(schema=json_schema)
llm_extraction_result = app.v1.scrape_url('https://news.ycombinator.com', formats=["json"], json_options=extract_config)

print(llm_extraction_result.json)


map_result = app.v1.map_url('https://firecrawl.dev', search="blog")
print(map_result)


class ExtractSchema(BaseModel):
    title: str
    description: str
    links: List[str]


extract_schema = ExtractSchema.schema()


extract_result = app.v1.extract(['https://firecrawl.dev'], prompt="Extract the title, description, and links from the website", schema=extract_schema)
print(extract_result)



research_result = app.v1.deep_research(
    "What are the latest developments in large language models?",
    max_urls=4
)
print("Research Results:", research_result)


llms_result = app.v1.generate_llms_text(
    "https://firecrawl.dev")
print("LLMs.txt Results:", llms_result)




import nest_asyncio
nest_asyncio.apply()


def on_document(detail):
    print("DOC", detail)

def on_error(detail):
    print("ERR", detail['error'])

def on_done(detail):
    print("DONE", detail['status'])

    
async def start_crawl_and_watch():
    
    watcher = app.crawl_url_and_watch('firecrawl.dev', { 'excludePaths': ['blog/*'], 'limit': 5 })

    
    watcher.add_event_listener("document", on_document)
    watcher.add_event_listener("error", on_error)
    watcher.add_event_listener("done", on_done)

    
    await watcher.connect()


class ExtractSchema(BaseModel):
    company_mission: str
    supports_sso: bool
    is_open_source: bool
    is_in_yc: bool

extract_config = V1JsonConfig(schema=ExtractSchema.model_json_schema())
data = app.scrape_url('https://docs.firecrawl.dev/', formats=['json'], json_options=extract_config)
print(data.json)



async_app = AsyncFirecrawlApp(api_url="https://api.firecrawl.dev")

async def example_scrape():
    
    scrape_result = await async_app.v1.scrape_url('example.com', formats=["markdown", "html"])
    print(scrape_result.markdown)

async def example_batch_scrape():
    
    urls = ['https://example.com', 'https://docs.firecrawl.dev']

    
    batch_result = await async_app.v1.batch_scrape_urls(urls, formats=["markdown", "html"])
    print("Synchronous Batch Scrape Result:")
    print(batch_result.data[0].markdown)

    
    async_batch_result = await async_app.v1.async_batch_scrape_urls(urls, formats=["markdown", "html"])
    print("\nAsynchronous Batch Scrape Result:")
    print(async_batch_result)

async def example_crawl():
    
    crawl_result = await async_app.v1.crawl_url('firecrawl.dev', exclude_paths=['blog/*'])
    print(crawl_result.data[0].markdown)

    
    async_result = await async_app.v1.async_crawl_url('firecrawl.dev', exclude_paths=['blog/*'])
    print(async_result)

    crawl_status = await async_app.v1.check_crawl_status(async_result.id)
    print(crawl_status)

    attempts = 15
    while attempts > 0 and crawl_status.status != 'completed':
        print(crawl_status)
        crawl_status = await async_app.v1.check_crawl_status(async_result.id)
        attempts -= 1
        await asyncio.sleep(1)  

    crawl_status = await async_app.v1.check_crawl_status(async_result.id)
    print(crawl_status)

async def example_llm_extraction():
    
    class ArticleSchema(BaseModel):
        title: str
        points: int 
        by: str
        commentsURL: str

    class TopArticlesSchema(BaseModel):
        top: List[ArticleSchema] = Field(..., description="Top 5 stories")

    extract_config = V1JsonConfig(schema=TopArticlesSchema.model_json_schema())

    llm_extraction_result = await async_app.v1.scrape_url('https://news.ycombinator.com', formats=["extract"], extract=extract_config)

    print(llm_extraction_result.extract)

async def example_map_and_extract():
    
    map_result = await async_app.v1.map_url('https://firecrawl.dev', search="blog")
    print(map_result)

    
    class ExtractSchema(BaseModel):
        title: str
        description: str
        links: List[str]

    
    extract_schema = ExtractSchema.schema()

    
    extract_result = await async_app.v1.extract(['https://firecrawl.dev'], prompt="Extract the title, description, and links from the website", schema=extract_schema)
    print(extract_result)

async def example_deep_research():
    
    research_result = await async_app.v1.deep_research(
        "What are the latest developments in large language models?",
        max_urls=4
    )
    print("Research Results:", research_result)

async def example_generate_llms_text():
    
    llms_result = await async_app.v1.generate_llms_text(
        "https://firecrawl.dev")
    print("LLMs.txt Results:", llms_result)


def on_document(detail):
    print("DOC", detail)

def on_error(detail):
    print("ERR", detail['error'])

def on_done(detail):
    print("DONE", detail['status'])

async def example_websocket_crawl():
    
    watcher = await async_app.v1.crawl_url_and_watch('firecrawl.dev', { 'excludePaths': ['blog/*'], 'limit': 5 })

    
    watcher.add_event_listener("document", on_document)
    watcher.add_event_listener("error", on_error)
    watcher.add_event_listener("done", on_done)

    
    await watcher.connect()

async def main():
    nest_asyncio.apply()
    
    await example_scrape()
    await example_batch_scrape()
    await example_crawl()
    await example_llm_extraction()
    await example_map_and_extract()
    await example_websocket_crawl()
    await example_deep_research()
    await example_generate_llms_text()

if __name__ == "__main__":
    asyncio.run(main())

