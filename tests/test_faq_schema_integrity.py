import json
import re
import unittest
from pathlib import Path

from config import settings


JSON_LD_RE = re.compile(
    r"<script\s+type=['\"]application/ld\+json['\"]\s*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


COMPARISON_PATHS = [
    "comparisons/framer-vs-webflow",
    "comparisons/cursor-vs-windsurf",
    "comparisons/copilot-vs-cursor",
    "comparisons/make-vs-zapier",
    "comparisons/semrush-vs-ahrefs",
]


def read_page(path: str) -> str:
    return (settings.site_output_dir / path / "index.html").read_text(encoding="utf-8")


def json_ld_payloads(html: str) -> list[dict]:
    payloads: list[dict] = []
    for match in JSON_LD_RE.finditer(html):
        data = json.loads(match.group(1))
        if isinstance(data, list):
            payloads.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            payloads.append(data)
    return payloads


def faq_schemas(html: str) -> list[dict]:
    return [payload for payload in json_ld_payloads(html) if payload.get("@type") == "FAQPage"]


def faq_text(schema: dict) -> str:
    parts: list[str] = []
    for item in schema.get("mainEntity", []):
        parts.append(str(item.get("name", "")))
        answer = item.get("acceptedAnswer", {})
        if isinstance(answer, dict):
            parts.append(str(answer.get("text", "")))
    return " ".join(parts)


class FAQSchemaIntegrityTest(unittest.TestCase):
    def assert_valid_single_faq_schema(self, html: str) -> dict:
        schemas = faq_schemas(html)
        self.assertLessEqual(len(schemas), 1, "page must not render duplicate FAQPage JSON-LD")
        self.assertEqual(len(schemas), 1, "comparison page should have one FAQPage JSON-LD")
        schema = schemas[0]
        self.assertIsInstance(schema.get("mainEntity"), list)
        self.assertGreater(len(schema["mainEntity"]), 0)
        for item in schema["mainEntity"]:
            self.assertEqual(item.get("@type"), "Question")
            self.assertTrue(str(item.get("name", "")).strip())
            answer = item.get("acceptedAnswer")
            self.assertIsInstance(answer, dict)
            self.assertEqual(answer.get("@type"), "Answer")
            self.assertTrue(str(answer.get("text", "")).strip())
        return schema

    def test_comparison_pages_have_one_valid_faqpage_schema(self):
        for path in COMPARISON_PATHS:
            with self.subTest(path=path):
                self.assert_valid_single_faq_schema(read_page(path))

    def test_vietnamese_comparison_pages_have_one_valid_faqpage_schema(self):
        for path in COMPARISON_PATHS:
            vi_path = f"vi/{path}"
            with self.subTest(path=vi_path):
                self.assert_valid_single_faq_schema(read_page(vi_path))

    def test_english_faq_schema_is_not_vietnamese(self):
        forbidden = [
            "nên chọn",
            "phù hợp với ai",
            "Trang này",
            "Nên so sánh",
            "Công cụ nào",
            "có tốt hơn",
        ]
        for path in COMPARISON_PATHS:
            with self.subTest(path=path):
                text = faq_text(self.assert_valid_single_faq_schema(read_page(path)))
                for phrase in forbidden:
                    self.assertNotIn(phrase, text)

    def test_vietnamese_faq_schema_is_not_english_ui(self):
        forbidden = [
            "which tool should you choose",
            "Who should use",
            "Does this page use affiliate links",
            "How should you compare pricing",
            "Which tool is easier for beginners",
            "What should I verify before buying either tool",
            "Can I promote these tools as an affiliate",
            "Should I read individual reviews before choosing",
        ]
        for path in COMPARISON_PATHS:
            vi_path = f"vi/{path}"
            with self.subTest(path=vi_path):
                text = faq_text(self.assert_valid_single_faq_schema(read_page(vi_path)))
                for phrase in forbidden:
                    self.assertNotIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
