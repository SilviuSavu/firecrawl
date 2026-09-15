"""
Example demonstrating pagination functionality in Firecrawl v2 SDK.

This example shows how to use the new pagination features for both crawl and batch scrape operations.
"""

from firecrawl import Firecrawl
from firecrawl.v2.types import PaginationConfig


firecrawl = Firecrawl(api_key="your-api-key")



print("=== Example 1: Simple crawl (default) ===")
crawl_result = firecrawl.crawl("https://example.com", limit=100)
print(f"Total documents fetched: {len(crawl_result.data)}")
print(f"Next URL: {crawl_result.next}")  




print("\n=== Example 2: Manual crawl with pagination control ===")
crawl_job = firecrawl.start_crawl("https://example.com", limit=100)


pagination_config = PaginationConfig(auto_paginate=False)
status = firecrawl.get_crawl_status(crawl_job.id, pagination_config=pagination_config)
print(f"Documents from first page: {len(status.data)}")
print(f"Next URL: {status.next}")  
if status.next:
    next_page = firecrawl.get_crawl_status_page(status.next)
    print(f"Documents from next page: {len(next_page.data)}")



print("\n=== Example 3: Limited pagination ===")
pagination_config = PaginationConfig(max_pages=3)
status = firecrawl.get_crawl_status(crawl_job.id, pagination_config=pagination_config)
print(f"Documents from first 3 pages: {len(status.data)}")



print("\n=== Example 4: Result-limited pagination ===")
pagination_config = PaginationConfig(max_results=50)
status = firecrawl.get_crawl_status(crawl_job.id, pagination_config=pagination_config)
print(f"Documents (max 50): {len(status.data)}")



print("\n=== Example 5: Time-limited pagination ===")
pagination_config = PaginationConfig(max_wait_time=30)
status = firecrawl.get_crawl_status(crawl_job.id, pagination_config=pagination_config)
print(f"Documents fetched within 30 seconds: {len(status.data)}")



print("\n=== Example 6: Combined limits ===")
pagination_config = PaginationConfig(
    max_pages=5,        
    max_results=100,    
    max_wait_time=60    
)
status = firecrawl.get_crawl_status(crawl_job.id, pagination_config=pagination_config)
print(f"Documents with combined limits: {len(status.data)}")



print("\n=== Example 7: Simple batch scrape (default) ===")
urls = ["https://example1.com", "https://example2.com", "https://example3.com"]
batch_result = firecrawl.batch_scrape(urls)
print(f"Batch scrape documents: {len(batch_result.data)}")




print("\n=== Example 8: Manual batch scrape with pagination control ===")
batch_job = firecrawl.start_batch_scrape(urls)
status = firecrawl.get_batch_scrape_status(batch_job.id, pagination_config=PaginationConfig(auto_paginate=False))
print(f"Batch scrape documents: {len(status.data)}")
print(f"Next URL: {status.next}")
if status.next:
    next_page = firecrawl.get_batch_scrape_status_page(status.next)
    print(f"Batch scrape next page documents: {len(next_page.data)}")


print("\n=== Example 9: Async pagination ===")
import asyncio
from firecrawl import AsyncFirecrawl

async def async_example():
    async_client = AsyncFirecrawl(api_key="your-api-key")
    
    
    crawl_result = await async_client.crawl("https://example.com", limit=50)
    print(f"Async crawl documents: {len(crawl_result.data)}")
    
    
    crawl_job = await async_client.start_crawl("https://example.com", limit=50)
    pagination_config = PaginationConfig(max_pages=2)
    status = await async_client.get_crawl_status(
        crawl_job.id, 
        pagination_config=pagination_config
    )
    print(f"Async crawl with pagination: {len(status.data)}")
    if status.next:
        next_page = await async_client.get_crawl_status_page(status.next)
        print(f"Async crawl next page documents: {len(next_page.data)}")



