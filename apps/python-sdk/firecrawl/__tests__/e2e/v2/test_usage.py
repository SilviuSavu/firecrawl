import os
from dotenv import load_dotenv
from firecrawl import Firecrawl

load_dotenv()


class TestUsageE2E:
    def setup_method(self):
        
        self.client = Firecrawl(api_key=os.getenv("API_KEY"), api_url=os.getenv("API_URL"))

    def test_get_concurrency(self):
        resp = self.client.get_concurrency()
        
        assert hasattr(resp, "concurrency")
        assert hasattr(resp, "max_concurrency")

    def test_get_credit_usage(self):
        resp = self.client.get_credit_usage()
        assert hasattr(resp, "remaining_credits")

    def test_get_token_usage(self):
        resp = self.client.get_token_usage()
        assert hasattr(resp, "remaining_tokens")

