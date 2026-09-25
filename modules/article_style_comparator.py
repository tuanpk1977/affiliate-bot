from __future__ import annotations

import re
from difflib import SequenceMatcher
from html.parser import HTMLParser
from typing import Any, Iterable


URL_RE = re.compile(r"https?://\S+", re.I)
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
SPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[a-z0-9]+")


class _ArticleBlocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self.headings: list[str] = []
        self.h1_count = 0
        self.h2_count = 0
        self.h3_count = 0
        self.table_count = 0
        self.faq_question_count = 0
        self.body_words: list[str] = []
        self._skip_depth = 0
        self._tag = ""
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "h1":
            self.h1_count += 1
        elif tag == "h2":
            self.h2_count += 1
        elif tag == "h3":
            self.h3_count += 1
        elif tag == "table":
            self.table_count += 1
        if tag in {"p", "li", "h2", "h3"}:
            self._tag = tag
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.body_words.extend(WORD_RE.findall(data.lower()))
        if self._tag:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag != self._tag:
            return
        text = SPACE_RE.sub(" ", "".join(self._buffer)).strip()
        if text:
            if tag in {"h2", "h3"}:
                self.headings.append(text)
                if text.rstrip().endswith("?"):
                    self.faq_question_count += 1
            elif len(WORD_RE.findall(text.lower())) >= 8:
                self.paragraphs.append(text)
        self._tag = ""
        self._buffer = []


def _normalize(value: str, entity_terms: Iterable[str]) -> str:
    text = URL_RE.sub(" <url> ", value.lower())
    text = NUMBER_RE.sub(" <number> ", text)
    for term in sorted({_term.lower().strip() for _term in entity_terms if _term.strip()}, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(term)}\b", " <entity> ", text, flags=re.I)
    return SPACE_RE.sub(" ", text).strip()


def compare_articles(
    reference_html: str,
    candidate_html: str,
    *,
    reference_entities: Iterable[str] = (),
    candidate_entities: Iterable[str] = (),
) -> dict[str, Any]:
    reference = _ArticleBlocks()
    candidate = _ArticleBlocks()
    reference.feed(reference_html)
    candidate.feed(candidate_html)
    reference_blocks = [_normalize(value, reference_entities) for value in reference.paragraphs]
    candidate_blocks = [_normalize(value, candidate_entities) for value in candidate.paragraphs]
    reference_set = set(reference_blocks)
    candidate_set = set(candidate_blocks)
    shared = reference_set & candidate_set
    denominator = max(1, min(len(reference_set), len(candidate_set)))
    paragraph_overlap = len(shared) / denominator

    reference_headings = [_normalize(value, reference_entities) for value in reference.headings]
    candidate_headings = [_normalize(value, candidate_entities) for value in candidate.headings]
    heading_similarity = SequenceMatcher(None, reference_headings, candidate_headings).ratio()
    sequence_similarity = SequenceMatcher(
        None,
        "\n".join(reference_blocks),
        "\n".join(candidate_blocks),
    ).ratio()
    differentiation = max(
        0.0,
        100.0 - (paragraph_overlap * 55.0 + heading_similarity * 25.0 + sequence_similarity * 20.0),
    )
    near_template_duplicate = (
        paragraph_overlap > 0.35
        or (heading_similarity >= 0.85 and sequence_similarity >= 0.82)
    )
    return {
        "schema_version": "article_style_comparison_v1",
        "reference_paragraphs": len(reference_blocks),
        "candidate_paragraphs": len(candidate_blocks),
        "shared_normalized_paragraphs": len(shared),
        "normalized_paragraph_overlap_percent": round(paragraph_overlap * 100, 2),
        "heading_sequence_similarity_percent": round(heading_similarity * 100, 2),
        "body_sequence_similarity_percent": round(sequence_similarity * 100, 2),
        "differentiation_score": round(differentiation, 2),
        "near_template_duplicate": near_template_duplicate,
        "decision": "FAIL_REWRITE" if near_template_duplicate else "PASS",
    }


def analyze_article(html: str) -> dict[str, Any]:
    parser = _ArticleBlocks()
    parser.feed(html)
    normalized_paragraphs = [SPACE_RE.sub(" ", value.lower()).strip() for value in parser.paragraphs]
    normalized_headings = [SPACE_RE.sub(" ", value.lower()).strip() for value in parser.headings]
    return {
        "word_count": len(parser.body_words),
        "paragraph_count": len(parser.paragraphs),
        "h1_count": parser.h1_count,
        "h2_count": parser.h2_count,
        "h3_count": parser.h3_count,
        "heading_count": parser.h1_count + parser.h2_count + parser.h3_count,
        "faq_question_count": parser.faq_question_count,
        "table_count": parser.table_count,
        "duplicate_paragraph_count": len(normalized_paragraphs) - len(set(normalized_paragraphs)),
        "duplicate_heading_count": len(normalized_headings) - len(set(normalized_headings)),
    }


def evaluate_website_contract(html: str, *, task_type: str) -> dict[str, Any]:
    metrics = analyze_article(html)
    advanced = task_type == "WEBSITE_ADVANCED"
    # Keep this validator aligned with the contracts shipped by Menu X.  A
    # foundation article may be broader than a focused advanced/deep-dive
    # article; the old values accidentally imposed the inverse relationship.
    minimum_words = 2200 if advanced else 1900
    maximum_words = 2600 if advanced else 3200
    checks = {
        "word_count": minimum_words <= metrics["word_count"] <= maximum_words,
        "h1": metrics["h1_count"] == 1,
        "h2": 8 <= metrics["h2_count"] <= 14,
        "h3": 3 <= metrics["h3_count"] <= 12,
        "faq": 4 <= metrics["faq_question_count"] <= 6,
        "tables": 1 <= metrics["table_count"] <= 2,
        "duplicate_paragraphs": metrics["duplicate_paragraph_count"] == 0,
        "duplicate_headings": metrics["duplicate_heading_count"] == 0,
    }
    errors: list[str] = []
    if not checks["word_count"]:
        errors.append(
            f"editorial word count {metrics['word_count']} is outside {minimum_words}-{maximum_words}"
        )
    if not checks["h1"]:
        errors.append(f"H1 count must be 1, found {metrics['h1_count']}")
    if not checks["h2"]:
        errors.append(f"H2 count must be 8-14, found {metrics['h2_count']}")
    if not checks["h3"]:
        errors.append(f"H3 count must be 3-12, found {metrics['h3_count']}")
    if not checks["faq"]:
        errors.append(
            f"FAQ question heading count must be 4-6, found {metrics['faq_question_count']}"
        )
    if not checks["tables"]:
        errors.append(f"responsive content table count must be 1-2, found {metrics['table_count']}")
    if not checks["duplicate_paragraphs"]:
        errors.append(
            f"duplicate paragraph count must be 0, found {metrics['duplicate_paragraph_count']}"
        )
    if not checks["duplicate_headings"]:
        errors.append(
            f"duplicate heading count must be 0, found {metrics['duplicate_heading_count']}"
        )
    score = round(100.0 * sum(1 for passed in checks.values() if passed) / len(checks), 2)
    return {
        "schema_version": "website_style_gate_v1",
        "task_type": task_type,
        "metrics": metrics,
        "checks": checks,
        "score": score,
        "minimum_score": 90,
        "errors": errors,
        "decision": "PASS" if not errors and score >= 90 else "FAIL_REWRITE",
    }
