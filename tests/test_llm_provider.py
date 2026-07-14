from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from modules.llm_provider import (
    ArticleLLMService,
    LLMProviderError,
    LLMProviderMalformedOutput,
    OpenAIChatJSONProvider,
    LLMSectionRewriteProvider,
    build_llm_service,
    render_writer_output,
    validate_rewrite_output,
)
from scripts.run_canary_batch import run_canary_batch


RESEARCH_PACKAGE = {
    "keyword": "Test Agent Review",
    "slug": "test-agent-review",
    "outline": {"heading_hierarchy": [{"heading": "Overview"}, {"heading": "Use cases"}]},
    "faq": {},
    "entities": {},
    "quality": {"overall_score": 80},
    "sources": {
        "verified_sources": [
            {"url": "https://docs.example.com/agent", "status": "verified"},
            {"url": "https://github.com/example/agent", "status": "verified"},
        ]
    },
}
TOPIC = {"topic": "Test Agent Review", "slug": "test-agent-review"}


class FakeJSONProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def generate_json(self, *, system: str, prompt: str, timeout_seconds: float | None = None):
        self.calls += 1
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return payload


def writer_payload() -> dict:
    return {
        "title": "Test Agent Review",
        "slug": "test-agent-review",
        "introduction": "A source-backed introduction for editors.",
        "sections": [
            {
                "heading": "Overview",
                "body": "This section cites official documentation and repository evidence.",
                "citations": ["https://docs.example.com/agent"],
                "claims": ["The tool has official documentation."],
            },
            {
                "heading": "Use cases",
                "body": "This section explains implementation fit without inventing pricing.",
                "citations": ["https://github.com/example/agent"],
                "claims": ["The repository is an implementation source."],
            },
        ],
        "conclusion": "Editors should verify final claims before approval.",
        "faq": [{"question": "Who is it for?", "answer": "Teams comparing agent tools."}],
        "citations": ["https://docs.example.com/agent", "https://github.com/example/agent"],
        "metadata": {"description": "Test review.", "language": "en"},
    }


class LLMProviderTests(unittest.TestCase):
    def test_writer_success_returns_contract_and_renders_article(self) -> None:
        service = ArticleLLMService(FakeJSONProvider([writer_payload()]))

        payload = service.write_article(topic=TOPIC, research_package=RESEARCH_PACKAGE)
        html, markdown, mapping = render_writer_output(payload, canonical_url="https://example.com/test-agent-review/")

        self.assertIn("<h1>Test Agent Review</h1>", html)
        self.assertIn('"@type": "FAQPage"', html)
        self.assertIn("https://docs.example.com/agent", html)
        self.assertIn("# Test Agent Review", markdown)
        self.assertTrue(mapping)
        self.assertEqual(service.telemetry.request_count, 1)

    def test_rewrite_success_preserves_heading_and_links(self) -> None:
        section = "<section id='overview'><h2>Overview</h2><p><a href='https://docs.example.com/agent'>Docs</a></p></section>"
        rewritten = "<section id='overview'><h2>Overview</h2><p><a href='https://docs.example.com/agent'>Docs</a> updated for clarity.</p></section>"
        service = ArticleLLMService(FakeJSONProvider([{"section_html": rewritten}]))

        result = LLMSectionRewriteProvider(service).rewrite_section(section_id="overview", section_html=section, issues=[], context={})

        self.assertEqual(result, rewritten)
        self.assertEqual(service.telemetry.request_count, 1)

    def test_timeout_or_provider_error_is_reported(self) -> None:
        service = ArticleLLMService(FakeJSONProvider([LLMProviderError("timeout")]))

        with self.assertRaises(LLMProviderError):
            service.write_article(topic=TOPIC, research_package=RESEARCH_PACKAGE)
        self.assertIn("writer:LLMProviderError", service.telemetry.errors)

    def test_openai_adapter_retries_then_parses_json(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"{\\"ok\\":true}"}}]}'

        calls = {"count": 0}

        def fake_urlopen(request, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                raise TimeoutError("temporary timeout")
            return FakeResponse()

        provider = OpenAIChatJSONProvider(api_key="test-key", model="test-model", max_retries=1)
        with patch("urllib.request.urlopen", fake_urlopen):
            result = provider.generate_json(system="system", prompt="prompt", timeout_seconds=1)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls["count"], 2)

    def test_malformed_writer_output_is_rejected(self) -> None:
        service = ArticleLLMService(FakeJSONProvider([{"title": "Bad"}]))

        with self.assertRaises(LLMProviderMalformedOutput):
            service.write_article(topic=TOPIC, research_package=RESEARCH_PACKAGE)

    def test_rewrite_validation_rejects_lost_citation(self) -> None:
        old = "<section><h2>Overview</h2><p><a href='https://docs.example.com/agent'>Docs</a></p></section>"
        new = "<section><h2>Overview</h2><p>No link.</p></section>"

        with self.assertRaises(LLMProviderMalformedOutput):
            validate_rewrite_output(old=old, new=new)

    def test_provider_unavailable_without_credentials(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            service, status = build_llm_service({"llm_provider": {"provider": "openai", "model": "fake"}}, allow_heuristic_fallback=False)

        self.assertIsNone(service)
        self.assertFalse(status["provider_available"])
        self.assertIn("OPENAI_API_KEY", status["missing_environment"])

    def test_production_mode_does_not_fallback_when_provider_missing(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            report = run_canary_batch(count=5, output_root=Path(temp_dir), batch_id="no-provider", allow_heuristic_fallback=False)

        self.assertEqual(report["selected"], 0)
        self.assertEqual(report["drafts_generated"], 0)
        self.assertFalse(report["provider_status"]["provider_available"])
        self.assertTrue(report["provider_status"]["heuristic_fallback_used"])
        self.assertFalse(report["production_recommendation"]["ready_for_5_per_day"])

    def test_test_mode_allows_fallback_for_local_orchestration(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            report = run_canary_batch(count=2, output_root=Path(temp_dir), batch_id="fallback-ok", allow_heuristic_fallback=True)

        self.assertEqual(report["selected"], 2)
        self.assertEqual(report["drafts_generated"], 2)
        self.assertTrue(report["provider_status"]["allow_heuristic_fallback"])
        self.assertEqual(report["production_review_ready"], 0)


if __name__ == "__main__":
    unittest.main()
