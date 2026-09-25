from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


RULE_ID = "PUBLIC_HTML_INTERNAL_WORKFLOW_MARKER"
SEVERITY = "BLOCKER"
WEBSITE_ADVANCED_RULE_ID = "WEBSITE_ADVANCED_EDITORIAL_CONTRACT"


@dataclass(frozen=True)
class PublicOutputRule:
    matcher_name: str
    pattern: str
    matched_marker: str
    fix_instruction: str
    flags: int = re.IGNORECASE

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": RULE_ID,
            "severity": SEVERITY,
            "matcher_name": self.matcher_name,
            "pattern": self.pattern,
            "matched_marker": self.matched_marker,
            "case_sensitive": not bool(self.flags & re.IGNORECASE),
            "fix_instruction": self.fix_instruction,
        }


PUBLIC_OUTPUT_RULES = (
    PublicOutputRule(
        "workflow_state_token",
        (
            r"(?<![A-Za-z0-9_])(?:needs_human_review|human_approved|"
            r"ready_for_publish|approved_for_publish|blocked_research|"
            r"article_ready)(?![A-Za-z0-9_])"
        ),
        "internal workflow state token",
        "Remove the internal state token from public content; keep approval state only in private workflow files.",
    ),
    PublicOutputRule(
        "serialized_workflow_key",
        (
            r"[\"'](?:workflow_state|approval_state|publish_gate_state|"
            r"deployment_state|internal_task_id)[\"']\s*:"
        ),
        "serialized internal workflow key",
        "Remove serialized workflow state from public HTML or metadata.",
    ),
    PublicOutputRule(
        "internal_repository_path",
        (
            r"(?<![A-Za-z0-9_])(?:CURRENT_TASK\.md|"
            r"data[/\\](?:editorial_queue|production_article_drafts)[/\\])"
        ),
        "internal repository path",
        "Remove the repository path and replace it with reader-facing wording.",
    ),
    PublicOutputRule(
        "internal_debug_section",
        (
            r"(?<![A-Za-z0-9_])(?:affiliate placeholder fields|"
            r"research package snapshot|content planning snapshot|debug text)"
            r"(?![A-Za-z0-9_])"
        ),
        "internal debug section",
        "Remove the internal/debug section from the public article.",
    ),
    PublicOutputRule(
        "template_placeholder",
        r"\{\{[^{}\r\n]{1,200}\}\}",
        "unresolved template placeholder",
        "Replace the complete placeholder with final reader-facing content or a safe official URL.",
        flags=0,
    ),
    PublicOutputRule(
        "publication_hygiene_internal_token",
        (
            r"(?<![A-Za-z0-9_])(?:HUMAN_REVIEW_REQUIRED|"
            r"DUPLICATE_RISK_REMEDIATION|OBSERVATION_START|"
            r"LEGACY_APPROVAL_UNBOUND)(?![A-Za-z0-9_])"
        ),
        "internal publication metadata token",
        "Remove the internal publication token from reader-facing content; retain it only in private sidecar or review metadata.",
    ),
    PublicOutputRule(
        "publication_hygiene_internal_key",
        (
            r"(?<![A-Za-z0-9_])(?:canonical_task_id|legacy_task_id|"
            r"revision_id|approved_content_hash)(?![A-Za-z0-9_])"
        ),
        "internal publication metadata key",
        "Remove the internal identifier/hash key from public content; retain it only in private sidecar metadata.",
    ),
    PublicOutputRule(
        "publication_hygiene_metadata_label",
        r"(?<![A-Za-z0-9_])(?:Revision\s+reason|Review\s+status)\s*:",
        "internal publication metadata label",
        "Remove the internal metadata label from the public article body and keep the value in its private review package.",
    ),
)

INTERNAL_COMMENT_RE = re.compile(
    r"<!--(?P<body>.*?(?:internal[-_ ]only|workflow_state|approval_state|"
    r"publish_gate_state|deployment_state|CURRENT_TASK\.md|"
    r"data[/\\](?:editorial_queue|production_article_drafts)[/\\]).*?)-->",
    re.IGNORECASE | re.DOTALL,
)


class PublicOutputValidationError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        first = errors[0] if errors else {}
        marker = first.get("matched_marker") or "unknown marker"
        file = first.get("file") or "unknown file"
        line = first.get("line") or 0
        super().__init__(
            f"Public output contains an internal workflow marker: "
            f"{marker!r} in {file} at line {line}."
        )


class WebsiteEditorialValidationError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        details = "; ".join(str(row.get("message") or "") for row in errors)
        super().__init__(f"WEBSITE_ADVANCED editorial contract failed: {details}")


class _EditorialHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._current_heading = ""
        self._current_heading_level = 0
        self._heading_parts: list[str] = []
        self.text_parts: list[str] = []
        self.h2: list[str] = []
        self.h3: list[str] = []
        self.h3_parents: list[str] = []
        self._latest_h2 = ""
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "nav", "footer"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if lowered in {"h2", "h3"}:
            self._current_heading = lowered
            self._current_heading_level = int(lowered[1])
            self._heading_parts = []
        if lowered == "a":
            href = next((value or "" for key, value in attrs if key.casefold() == "href"), "")
            if href.strip():
                self.links.append(href.strip())

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "nav", "footer"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if lowered == self._current_heading:
            heading = " ".join(self._heading_parts).strip()
            if self._current_heading_level == 2:
                self.h2.append(heading)
                self._latest_h2 = heading
            elif self._current_heading_level == 3:
                self.h3.append(heading)
                self.h3_parents.append(self._latest_h2)
            self._current_heading = ""
            self._current_heading_level = 0
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        self.text_parts.append(text)
        if self._current_heading:
            self._heading_parts.append(text)


def validate_website_advanced_html(
    *,
    task_id: str,
    slug: str,
    html: str,
    article_spec: dict[str, Any] | None,
    website_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    spec = article_spec if isinstance(article_spec, dict) else {}
    contract = website_contract if isinstance(website_contract, dict) else {}
    parser = _EditorialHTMLParser()
    parser.feed(html)
    visible_text = " ".join(parser.text_parts)
    words = re.findall(r"[A-Za-z0-9']+", visible_text)
    headings = [re.sub(r"\s+", " ", value).strip().casefold() for value in parser.h2]

    target_length = spec.get("target_length") if isinstance(spec.get("target_length"), dict) else {}
    editorial_words = (
        contract.get("editorial_word_count")
        if isinstance(contract.get("editorial_word_count"), dict)
        else {}
    )
    minimum_words = int(target_length.get("minimum_words") or editorial_words.get("minimum") or 1600)
    maximum_words = int(target_length.get("maximum_words") or editorial_words.get("maximum") or 2600)

    structure = contract.get("structure") if isinstance(contract.get("structure"), dict) else {}
    h2_range = structure.get("h2_range") if isinstance(structure.get("h2_range"), list) else []
    section_order = spec.get("section_order") if isinstance(spec.get("section_order"), list) else []
    minimum_h2 = max(int(h2_range[0] if h2_range else 8), len(section_order))

    faq_spec = spec.get("faq_requirements") if isinstance(spec.get("faq_requirements"), dict) else {}
    faq_range = structure.get("faq_questions") if isinstance(structure.get("faq_questions"), list) else []
    minimum_faq = int(
        faq_spec.get("minimum_questions")
        or len(faq_spec.get("questions") or [])
        or (faq_range[0] if faq_range else 1)
    )

    canonical_match = re.search(
        r"<link\b[^>]*rel=['\"]canonical['\"][^>]*href=['\"]([^'\"]+)",
        html,
        flags=re.IGNORECASE,
    )
    canonical_host = urlparse(canonical_match.group(1)).netloc.casefold() if canonical_match else ""
    internal_links: set[str] = set()
    citations: set[str] = set()
    for href in parser.links:
        parsed = urlparse(href)
        if href.startswith("/") and not href.startswith("//"):
            internal_links.add(href)
        elif parsed.scheme in {"http", "https"}:
            if canonical_host and parsed.netloc.casefold() == canonical_host:
                internal_links.add(href)
            else:
                citations.add(href)

    required_internal_links = spec.get("required_internal_links")
    minimum_internal_links = (
        len(required_internal_links)
        if isinstance(required_internal_links, list) and required_internal_links
        else 1
    )

    section_patterns = {
        "pricing": ("pricing", "price", "cost"),
        "security": ("security", "privacy", "compliance"),
        "integrations": ("integration", "integrations", "connectors"),
        "comparison": ("comparison", "compare", "alternatives", "versus", " vs "),
    }
    section_presence = {
        section: any(any(marker in f" {heading} " for marker in markers) for heading in headings)
        for section, markers in section_patterns.items()
    }
    faq_present = any("faq" in heading or "frequently asked" in heading for heading in headings)
    faq_question_count = sum(
        1
        for parent in parser.h3_parents
        if "faq" in parent.casefold() or "frequently asked" in parent.casefold()
    )
    lowered_text = visible_text.casefold()
    affiliate_disclosure_present = (
        "affiliate disclosure" in lowered_text and "commission" in lowered_text
    )
    placeholder_patterns = (
        r"\{\{[^{}]+\}\}",
        r"\[(?:placeholder|insert [^\]]+)\]",
        r"\b(?:coming soon|lorem ipsum|tbd|todo)\b",
    )
    placeholder_found = any(re.search(pattern, visible_text, flags=re.IGNORECASE) for pattern in placeholder_patterns)
    h2_blocks = re.split(r"(?i)<h2\b[^>]*>", html)
    empty_sections = 0
    for block in h2_blocks[1:]:
        body = re.split(r"(?i)</h2>", block, maxsplit=1)
        if len(body) != 2:
            empty_sections += 1
            continue
        section_body = re.split(r"(?i)<h2\b", body[1], maxsplit=1)[0]
        section_words = re.findall(
            r"[A-Za-z0-9']+",
            re.sub(r"<[^>]+>", " ", section_body),
        )
        if len(section_words) < 20:
            empty_sections += 1
    tables = re.findall(r"(?is)<table\b[^>]*>(.*?)</table>", html)
    nonempty_tables = [
        table
        for table in tables
        if len(re.findall(r"(?is)<t[dh]\b[^>]*>\s*(?!</t[dh]>).+?</t[dh]>", table)) >= 2
    ]
    cta_present = bool(
        re.search(
            r"(?is)<a\b[^>]*>[^<]*(?:try|visit|check|read|compare|explore|learn|get started|view)[^<]*</a>",
            html,
        )
    )
    json_ld_present = bool(
        re.search(
            r"<script\b[^>]*type=['\"]application/ld\+json['\"]",
            html,
            flags=re.IGNORECASE,
        )
    )
    schema_policy = contract.get("schema_policy") if isinstance(contract.get("schema_policy"), dict) else {}
    json_ld_required = bool(schema_policy.get("json_ld_required", True))
    paragraphs = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip().casefold()
        for value in re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", html)
    ]
    comparable_paragraphs = [value for value in paragraphs if len(value.split()) >= 20]
    duplicate_count = len(comparable_paragraphs) - len(set(comparable_paragraphs))
    duplicate_risk = round(
        (duplicate_count / max(1, len(comparable_paragraphs))) * 100,
        2,
    )

    errors: list[dict[str, Any]] = []

    def require(condition: bool, requirement: str, message: str) -> None:
        if not condition:
            errors.append(
                {
                    "task_id": task_id,
                    "slug": slug,
                    "rule_id": WEBSITE_ADVANCED_RULE_ID,
                    "severity": SEVERITY,
                    "requirement": requirement,
                    "message": message,
                }
            )

    require(
        len(words) >= minimum_words,
        "minimum_word_count",
        f"word count {len(words)} is below ARTICLE_SPEC minimum {minimum_words}",
    )
    require(
        len(words) <= maximum_words,
        "maximum_word_count",
        f"word count {len(words)} exceeds ARTICLE_SPEC maximum {maximum_words}",
    )
    require(
        len(parser.h2) >= minimum_h2,
        "minimum_h2_count",
        f"H2 count {len(parser.h2)} is below minimum {minimum_h2}",
    )
    require(faq_present, "faq", "FAQ section is missing")
    require(
        faq_question_count >= minimum_faq,
        "faq",
        f"FAQ question count {faq_question_count} is below ARTICLE_SPEC minimum {minimum_faq}",
    )
    for section, present in section_presence.items():
        require(present, f"{section}_section", f"{section} section is missing")
    require(
        affiliate_disclosure_present,
        "affiliate_disclosure",
        "affiliate disclosure with commission language is missing",
    )
    require(
        len(internal_links) >= minimum_internal_links,
        "internal_links",
        f"internal link count {len(internal_links)} is below ARTICLE_SPEC minimum {minimum_internal_links}",
    )
    require(
        len(citations) >= 2,
        "citations",
        f"external citation count {len(citations)} is below minimum 2",
    )
    require(cta_present, "cta", "reader-facing CTA link is missing")
    require(
        not json_ld_required or json_ld_present,
        "json_ld",
        "required JSON-LD is missing",
    )
    require(not placeholder_found, "placeholders", "placeholder or coming-soon text is present")
    require(empty_sections == 0, "empty_sections", f"{empty_sections} H2 section(s) are empty or insubstantial")
    require(bool(nonempty_tables), "comparison_table", "comparison table is missing or empty")
    maximum_duplicate_risk = float(
        (
            contract.get("preflight_quality")
            if isinstance(contract.get("preflight_quality"), dict)
            else {}
        ).get("maximum_duplicate_risk", 35)
    )
    require(
        duplicate_risk <= maximum_duplicate_risk,
        "duplicate_risk",
        f"duplicate risk {duplicate_risk} exceeds maximum {maximum_duplicate_risk}",
    )

    hard_check_count = 18
    passed_hard_checks = hard_check_count - len(
        {row["requirement"] for row in errors}
    )
    coverage = round(max(0, passed_hard_checks) / hard_check_count * 100, 2)
    predicted_ai_score = round(max(0, min(100, coverage * 0.8 + (100 - duplicate_risk) * 0.2)), 2)
    minimum_score = float(
        (
            contract.get("preflight_quality")
            if isinstance(contract.get("preflight_quality"), dict)
            else {}
        ).get("minimum_predicted_ai_score", 70)
    )
    require(
        predicted_ai_score >= minimum_score,
        "predicted_ai_score",
        f"predicted AI score {predicted_ai_score} is below minimum {minimum_score}",
    )

    return {
        "status": "PASS" if not errors else "FAIL",
        "task_id": task_id,
        "slug": slug,
        "metrics": {
            "word_count": len(words),
            "minimum_word_count": minimum_words,
            "maximum_word_count": maximum_words,
            "h2_count": len(parser.h2),
            "minimum_h2_count": minimum_h2,
            "faq_question_count": faq_question_count,
            "minimum_faq_questions": minimum_faq,
            "internal_link_count": len(internal_links),
            "minimum_internal_links": minimum_internal_links,
            "citation_count": len(citations),
            "duplicate_risk": duplicate_risk,
            "coverage": coverage,
            "predicted_ai_score": predicted_ai_score,
            "cta_present": cta_present,
            "json_ld_present": json_ld_present,
            "placeholder_found": placeholder_found,
            "empty_section_count": empty_sections,
            "nonempty_table_count": len(nonempty_tables),
            "affiliate_disclosure_present": affiliate_disclosure_present,
            **{f"{name}_section_present": present for name, present in section_presence.items()},
            "faq_section_present": faq_present,
        },
        "errors": errors,
    }


def assert_website_advanced_html(
    *,
    task_id: str,
    slug: str,
    html: str,
    article_spec: dict[str, Any] | None,
    website_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    report = validate_website_advanced_html(
        task_id=task_id,
        slug=slug,
        html=html,
        article_spec=article_spec,
        website_contract=website_contract,
    )
    if report["errors"]:
        raise WebsiteEditorialValidationError(report["errors"])
    return report


def public_output_validation_contract() -> dict[str, Any]:
    return {
        "schema_version": "public_output_validation_v1",
        "rule_id": RULE_ID,
        "scan_policy": {
            "html": ["visible_text", "attribute", "comment", "json_ld"],
            "markdown": ["visible_text"],
            "metadata": ["metadata"],
            "validation_report": [],
            "case_sensitive_default": False,
            "raw_substring_scan": False,
        },
        "rules": [rule.as_dict() for rule in PUBLIC_OUTPUT_RULES],
        "comment_rule": {
            "rule_id": RULE_ID,
            "severity": SEVERITY,
            "matcher_name": "internal_html_comment",
            "pattern": INTERNAL_COMMENT_RE.pattern,
            "matched_marker": "internal-only HTML comment",
            "case_sensitive": False,
            "fix_instruction": "Remove the internal comment from public HTML.",
        },
        "explicitly_allowed_public_words": [
            "workflow",
            "review",
            "editorial",
            "approval",
            "validation",
            "internal",
            "scheduled",
            "not yet live",
            "research package",
            "supplied package",
            "source package",
            "blueprint",
            "claim",
            "draft",
        ],
        "valid_examples": [
            "Our editorial review covers a practical workflow.",
            "Internal collaboration features can help a small team.",
            '<script type="application/ld+json">{"@type":"Article"}</script>',
            "This article was prepared from the supplied research package.",
        ],
        "invalid_examples": [
            '{"approval_state":"needs_human_review"}',
            "<!-- internal-only workflow_state=ARTICLE_READY -->",
            "See data/editorial_queue/2026-07-27/topics.json.",
            "Buy now at {{AFFILIATE_LINK}}.",
        ],
    }


def validate_public_output_files(
    *,
    task_id: str,
    slug: str,
    files: dict[str, tuple[str, str]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for file, (text, declared_type) in files.items():
        if declared_type == "html":
            errors.extend(_scan_html(task_id, slug, file, text))
        elif declared_type == "metadata":
            errors.extend(_scan_text(task_id, slug, file, text, "metadata"))
        else:
            errors.extend(_scan_text(task_id, slug, file, text, "visible_text"))
    return _deduplicate(errors)


def assert_public_output_files(
    *,
    task_id: str,
    slug: str,
    files: dict[str, tuple[str, str]],
) -> None:
    errors = validate_public_output_files(task_id=task_id, slug=slug, files=files)
    if errors:
        raise PublicOutputValidationError(errors)


def _scan_html(task_id: str, slug: str, file: str, text: str) -> list[dict[str, Any]]:
    errors = _scan_text(task_id, slug, file, text, "visible_text", classify_html=True)
    for match in INTERNAL_COMMENT_RE.finditer(text):
        errors.append(
            _error(
                task_id=task_id,
                slug=slug,
                file=file,
                text=text,
                start=match.start(),
                end=match.end(),
                matcher_name="internal_html_comment",
                marker=match.group(0),
                location_type="comment",
                fix_instruction="Remove the internal comment from public HTML.",
            )
        )
    return errors


def _scan_text(
    task_id: str,
    slug: str,
    file: str,
    text: str,
    location_type: str,
    *,
    classify_html: bool = False,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for rule in PUBLIC_OUTPUT_RULES:
        for match in rule.compiled().finditer(text):
            actual_location = (
                _classify_html_location(text, match.start())
                if classify_html
                else location_type
            )
            errors.append(
                _error(
                    task_id=task_id,
                    slug=slug,
                    file=file,
                    text=text,
                    start=match.start(),
                    end=match.end(),
                    matcher_name=rule.matcher_name,
                    marker=match.group(0),
                    location_type=actual_location,
                    fix_instruction=rule.fix_instruction,
                )
            )
    return errors


def _classify_html_location(text: str, offset: int) -> str:
    comment_open = text.rfind("<!--", 0, offset + 1)
    comment_close = text.rfind("-->", 0, offset + 1)
    if comment_open > comment_close:
        return "comment"
    script_open = text.lower().rfind("<script", 0, offset + 1)
    script_close = text.lower().rfind("</script", 0, offset + 1)
    if script_open > script_close:
        opening_end = text.find(">", script_open)
        opening = text[script_open : opening_end + 1].lower()
        if "application/ld+json" in opening:
            return "json_ld"
    tag_open = text.rfind("<", 0, offset + 1)
    tag_close = text.rfind(">", 0, offset + 1)
    if tag_open > tag_close:
        return "attribute"
    return "visible_text"


def _error(
    *,
    task_id: str,
    slug: str,
    file: str,
    text: str,
    start: int,
    end: int,
    matcher_name: str,
    marker: str,
    location_type: str,
    fix_instruction: str,
) -> dict[str, Any]:
    line = text.count("\n", 0, start) + 1
    line_start = text.rfind("\n", 0, start) + 1
    column = start - line_start + 1
    snippet_start = max(0, start - 90)
    snippet_end = min(len(text), end + 90)
    snippet = re.sub(r"\s+", " ", text[snippet_start:snippet_end]).strip()
    return {
        "task_id": task_id,
        "slug": slug,
        "file": Path(file).as_posix(),
        "rule_id": RULE_ID,
        "severity": SEVERITY,
        "matched_marker": marker,
        "matcher_name": matcher_name,
        "line": line,
        "column": column,
        "character_offset": start,
        "snippet": snippet,
        "location_type": location_type,
        "fix_instruction": fix_instruction,
    }


def _deduplicate(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for error in errors:
        key = (
            error["file"],
            error["character_offset"],
            error["matcher_name"],
            error["matched_marker"],
        )
        unique[key] = error
    return sorted(
        unique.values(),
        key=lambda row: (row["file"], row["character_offset"], row["matcher_name"]),
    )
