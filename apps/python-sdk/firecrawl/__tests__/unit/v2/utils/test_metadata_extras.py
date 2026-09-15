import pytest

from firecrawl.v2.types import Document, DocumentMetadata
from firecrawl.v2.utils.normalize import normalize_document_input


class TestDocumentMetadataExtras:
    def test_metadata_extras_preserved_in_metadata_dict(self):
        raw = {
            "markdown": "# Hello",
            "metadata": {
                "title": "Example",
                
                "statusCode": "200",
                
                "twitter:card": "summary",
                "twitterCard": "summary_large_image",
                "theme-color": "#fff",
            },
        }

        doc = Document(**normalize_document_input(raw))
        md_dict = doc.metadata_dict
        
        assert md_dict["status_code"] == 200
        assert md_dict["title"] == "Example"
        
        assert md_dict["twitter:card"] == "summary"
        assert md_dict["twitterCard"] == "summary_large_image"
        assert md_dict["theme-color"] == "#fff"

    def test_metadata_typed_from_plain_dict_preserves_extras(self):
        
        doc = Document(
            markdown="# Hi",
            metadata={
                "ogTitle": "Hello",  
                "x-custom": "ok",
            },
        )

        md = doc.metadata_typed
        assert isinstance(md, DocumentMetadata)
        
        assert md.og_title is None
        
        extras = getattr(md, "__pydantic_extra__", {}) or {}
        assert extras == {"ogTitle": "Hello", "x-custom": "ok"}
        assert doc.metadata_dict["ogTitle"] == "Hello"
        assert doc.metadata_dict["x-custom"] == "ok"

    def test_document_model_dump_includes_metadata_extras(self):
        raw = {
            "markdown": "# Body",
            "metadata": {
                "title": "Page",
                "twitter:site": "@site",
            },
        }
        doc = Document(**normalize_document_input(raw))
        dumped = doc.model_dump(exclude_none=True)
        assert "metadata" in dumped
        assert dumped["metadata"]["title"] == "Page"
        assert dumped["metadata"]["twitter:site"] == "@site"

    def test_concurrency_fields_are_mapped(self):
        raw = {
            "markdown": "# Queue info",
            "metadata": {
                "concurrencyLimited": True,
                "concurrencyQueueDurationMs": 1234,
            },
        }
        doc = Document(**normalize_document_input(raw))
        md = doc.metadata_typed
        assert md.concurrency_limited is True
        assert md.concurrency_queue_duration_ms == 1234

    def test_unknown_list_metadata_preserved(self):
        raw = {
            "markdown": "# Body",
            "metadata": {
                "title": "Page",
                "x-list": [1, "a", 3],
            },
        }
        doc = Document(**normalize_document_input(raw))
        md = doc.metadata_dict
        assert md["x-list"] == [1, "a", 3]

    def test_metadata_typed_extras_property(self):
        md = DocumentMetadata(title="T", **{"x-foo": "bar"})
        
        assert md.extras == {"x-foo": "bar"}
