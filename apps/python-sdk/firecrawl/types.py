"""
Unified Firecrawl Types

This module provides unified access to Firecrawl types across all API versions.
Currently exports v2 types as the primary interface.
"""

from .v2.types import (
    
    BaseResponse,
    
    
    Document,
    DocumentMetadata,
    
    
    ScrapeFormats,
    ScrapeOptions,
    ScrapeRequest,
    ScrapeData,
    ScrapeResponse,
    ThreatProtectionOptions,
    
    
    CrawlRequest,
    CrawlJob,
    CrawlResponse,
    CrawlParamsRequest,
    CrawlParamsData,
    CrawlParamsResponse,
    CrawlErrorsResponse,
    ActiveCrawlsResponse,
    
    
    BatchScrapeRequest,
    BatchScrapeJob,
    BatchScrapeResponse,
    
    
    MapOptions,
    MapRequest,
    MapData,
    MapResponse,
    
    
    Source,
    SourceOption,
    Format,
    JsonFormat,
    QuestionFormat,
    HighlightsFormat,
    QueryFormat,
    FormatOption,
    SearchRequest,
    SearchResultWeb,
    SearchResultNews,
    SearchResultImages,
    SearchData,
    
    
    WaitAction,
    ScreenshotAction,
    ClickAction,
    WriteAction,
    PressAction,
    ScrollAction,
    ScrapeAction,
    ExecuteJavascriptAction,
    PDFAction,
    
    
    QueueStatusResponse,

    
    Location,
    
    
    ErrorDetails,
    ErrorResponse,
    
    
    JobStatus,
    
    
    WebhookData,
    
    
    ClientConfig,
    AgentOptions,
)

__all__ = [
    
    'BaseResponse',
    
    
    'Document',
    'DocumentMetadata',
    
    
    'ScrapeFormats',
    'ScrapeOptions',
    'ScrapeRequest',
    'ScrapeData',
    'ScrapeResponse',
    'ThreatProtectionOptions',
    
    
    'CrawlRequest',
    'CrawlJob',
    'CrawlJobData',
    'CrawlResponse',
    'CrawlParamsRequest',
    'CrawlParamsData',
    'CrawlParamsResponse',
    'CrawlErrorsResponse',
    'ActiveCrawlsResponse',
    
    
    'BatchScrapeRequest',
    'BatchScrapeJob',
    'BatchScrapeResponse',
    
    
    'MapOptions',
    'MapRequest',
    'MapData',
    'MapResponse',
    
    
    'Source',
    'SourceOption',
    'Format',
    'JsonFormat',
    'QuestionFormat',
    'HighlightsFormat',
    'QueryFormat',
    'FormatOption',
    'SearchRequest',
    'SearchResultWeb',
    'SearchResultNews',
    'SearchResultImages',
    'SearchData',
    
    
    'WaitAction',
    'ScreenshotAction',
    'ClickAction',
    'WriteAction',
    'PressAction',
    'ScrollAction',
    'ScrapeAction',
    'ExecuteJavascriptAction',
    'PDFAction',

    
    'QueueStatusResponse',
    
    
    'Location',
    
    
    'ErrorDetails',
    'ErrorResponse',
    
    
    'JobStatus',
    
    
    'WebhookData',
    
    
    'ClientConfig',
    'AgentOptions',
]  