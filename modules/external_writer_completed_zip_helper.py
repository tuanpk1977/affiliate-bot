from __future__ import annotations


def completed_zip_helper_script() -> str:
    return r'''from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import sys
import zipfile
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


EXECUTABLE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".js",
    ".jse",
    ".msi",
    ".ps1",
    ".py",
    ".scr",
    ".sh",
    ".vbs",
    ".wsf",
}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_safe_relative(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        bool(path)
        and not pure.is_absolute()
        and "\\" not in path
        and all(part not in {"", ".", ".."} for part in pure.parts)
    )


def allowed(path: str, allowed_paths: list[str]) -> bool:
    if path == "completed_manifest.json":
        return True
    for pattern in allowed_paths:
        if pattern.endswith("/*"):
            prefix = pattern[:-1]
            if path.startswith(prefix):
                return True
        elif path == pattern:
            return True
    return False


def output_root_for(task_type: str, slug: str) -> str:
    lane = "website" if task_type.startswith("WEBSITE_") else "social"
    return f"{lane}/{slug}"


class EditorialParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.heading = ""
        self.heading_parts: list[str] = []
        self.text: list[str] = []
        self.h2: list[str] = []
        self.h3: list[str] = []
        self.h3_parents: list[str] = []
        self.latest_h2 = ""
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "nav", "footer"}:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in {"h2", "h3"}:
            self.heading = tag
            self.heading_parts = []
        if tag == "a":
            href = next((value or "" for key, value in attrs if key.casefold() == "href"), "")
            if href.strip():
                self.links.append(href.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "nav", "footer"}:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == self.heading:
            value = " ".join(self.heading_parts).strip()
            if tag == "h2":
                self.h2.append(value)
                self.latest_h2 = value
            else:
                self.h3.append(value)
                self.h3_parents.append(self.latest_h2)
            self.heading = ""
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.skip or not data.strip():
            return
        self.text.append(data.strip())
        if self.heading:
            self.heading_parts.append(data.strip())


def advanced_editorial_review(
    root: Path,
    slug: str,
    task_id: str,
    html: str,
    spec: dict,
    website_contract: dict,
) -> dict:
    parser = EditorialParser()
    parser.feed(html)
    text = " ".join(parser.text)
    headings = [value.casefold() for value in parser.h2]
    target = spec.get("target_length") if isinstance(spec.get("target_length"), dict) else {}
    word_contract = website_contract.get("editorial_word_count") or {}
    minimum_words = int(target.get("minimum_words") or word_contract.get("minimum") or 2200)
    maximum_words = int(target.get("maximum_words") or word_contract.get("maximum") or 2600)
    structure = website_contract.get("structure") or {}
    h2_range = structure.get("h2_range") or []
    section_order = spec.get("section_order") or []
    minimum_h2 = max(int(h2_range[0] if h2_range else 8), len(section_order))
    faq = spec.get("faq_requirements") if isinstance(spec.get("faq_requirements"), dict) else {}
    faq_range = structure.get("faq_questions") or []
    minimum_faq = int(
        faq.get("minimum_questions")
        or len(faq.get("questions") or [])
        or (faq_range[0] if faq_range else 1)
    )
    required_internal = spec.get("required_internal_links") or []
    minimum_internal = len(required_internal) if required_internal else 1
    canonical = re.search(
        r"<link\b[^>]*rel=['\"]canonical['\"][^>]*href=['\"]([^'\"]+)",
        html,
        flags=re.I,
    )
    canonical_host = urlparse(canonical.group(1)).netloc.casefold() if canonical else ""
    internal: set[str] = set()
    citations: set[str] = set()
    for href in parser.links:
        parsed = urlparse(href)
        if href.startswith("/") and not href.startswith("//"):
            internal.add(href)
        elif parsed.scheme in {"http", "https"}:
            if canonical_host and parsed.netloc.casefold() == canonical_host:
                internal.add(href)
            else:
                citations.add(href)
    checks = {
        "pricing section": ("pricing", "price", "cost"),
        "security section": ("security", "privacy", "compliance"),
        "integrations section": ("integration", "integrations", "connectors"),
        "comparison section": ("comparison", "compare", "alternatives", "versus", " vs "),
    }
    errors: list[str] = []
    words = re.findall(r"[A-Za-z0-9']+", text)
    if len(words) < minimum_words:
        errors.append(f"word count {len(words)} is below ARTICLE_SPEC minimum {minimum_words}")
    if len(words) > maximum_words:
        errors.append(f"word count {len(words)} exceeds ARTICLE_SPEC maximum {maximum_words}")
    if len(parser.h2) < minimum_h2:
        errors.append(f"H2 count {len(parser.h2)} is below minimum {minimum_h2}")
    if not any("faq" in value or "frequently asked" in value for value in headings):
        errors.append("FAQ section is missing")
    faq_questions = sum(
        1
        for parent in parser.h3_parents
        if "faq" in parent.casefold() or "frequently asked" in parent.casefold()
    )
    if faq_questions < minimum_faq:
        errors.append(f"FAQ question count {faq_questions} is below ARTICLE_SPEC minimum {minimum_faq}")
    for label, markers in checks.items():
        if not any(any(marker in f" {heading} " for marker in markers) for heading in headings):
            errors.append(f"{label} is missing")
    lowered = text.casefold()
    if "affiliate disclosure" not in lowered or "commission" not in lowered:
        errors.append("affiliate disclosure with commission language is missing")
    if len(internal) < minimum_internal:
        errors.append(f"internal link count {len(internal)} is below ARTICLE_SPEC minimum {minimum_internal}")
    if len(citations) < 2:
        errors.append(f"external citation count {len(citations)} is below minimum 2")

    placeholder_found = bool(
        re.search(
            r"\{\{[^{}]+\}\}|\[(?:placeholder|insert [^\]]+)\]|\b(?:coming soon|lorem ipsum|tbd|todo)\b",
            text,
            flags=re.I,
        )
    )
    if placeholder_found:
        errors.append("placeholder or coming-soon text is present")

    h2_blocks = re.split(r"(?i)<h2\b[^>]*>", html)
    empty_sections = 0
    for block in h2_blocks[1:]:
        body = re.split(r"(?i)</h2>", block, maxsplit=1)
        if len(body) != 2:
            empty_sections += 1
            continue
        section_body = re.split(r"(?i)<h2\b", body[1], maxsplit=1)[0]
        if len(re.findall(r"[A-Za-z0-9']+", re.sub(r"<[^>]+>", " ", section_body))) < 20:
            empty_sections += 1
    if empty_sections:
        errors.append(f"{empty_sections} H2 section(s) are empty or insubstantial")

    tables = re.findall(r"(?is)<table\b[^>]*>(.*?)</table>", html)
    nonempty_tables = [
        table
        for table in tables
        if len(re.findall(r"(?is)<t[dh]\b[^>]*>\s*(?!</t[dh]>).+?</t[dh]>", table)) >= 2
    ]
    if not nonempty_tables:
        errors.append("comparison table is missing or empty")

    cta_present = bool(
        re.search(
            r"(?is)<a\b[^>]*>[^<]*(?:try|visit|check|read|compare|explore|learn|get started|view)[^<]*</a>",
            html,
        )
    )
    if not cta_present:
        errors.append("reader-facing CTA link is missing")
    json_ld_present = bool(
        re.search(r"<script\b[^>]*type=['\"]application/ld\+json['\"]", html, flags=re.I)
    )
    if bool((website_contract.get("schema_policy") or {}).get("json_ld_required", True)) and not json_ld_present:
        errors.append("required JSON-LD is missing")

    required_artifacts = list(website_contract.get("required_research_artifacts") or [])
    research_root = root / "research" / slug
    available_names = {
        path.name.casefold()
        for path in research_root.rglob("*")
        if path.is_file()
    }
    missing_artifacts = [
        name for name in required_artifacts if name.casefold() not in available_names
    ]
    if missing_artifacts:
        errors.append("required research artifacts missing: " + ", ".join(missing_artifacts))

    validation_path = root / "website" / slug / "validation.json"
    validation = load_json(validation_path) if validation_path.is_file() else {}
    generation_attempt = int(validation.get("generation_attempt") or 0)
    if generation_attempt < 1 or generation_attempt > 3:
        errors.append("validation.json generation_attempt must be between 1 and 3")
    utilization = (
        validation.get("research_utilization")
        if isinstance(validation.get("research_utilization"), dict)
        else {}
    )
    consumed = {
        str(value).casefold()
        for value in utilization.get("artifacts", [])
        if str(value).strip()
    }
    unreported_artifacts = [
        name for name in required_artifacts if name.casefold() not in consumed
    ]
    if unreported_artifacts:
        errors.append(
            "research utilization not declared for: " + ", ".join(unreported_artifacts)
        )
    contract_payload = load_json(root / "verified_package_contract.json")
    contract_task = next(
        (
            row for row in contract_payload.get("tasks", [])
            if isinstance(row, dict) and str(row.get("task_id") or "") == task_id
        ),
        {},
    )
    minimum_claims = int(
        (contract_task.get("evidence_policy") or {}).get(
            "minimum_publishable_claims", 1
        )
    )
    fact_payload = load_json(root / "FACT_LEDGER.json")
    fact_row = next(
        (
            row for row in fact_payload.get("articles", [])
            if isinstance(row, dict) and str(row.get("task_id") or "") == task_id
        ),
        {},
    )
    valid_claim_ids = {
        str(row.get("claim_id") or "")
        for row in fact_row.get("facts", [])
        if isinstance(row, dict) and str(row.get("claim_id") or "")
    }
    used_claim_ids = {
        str(value) for value in utilization.get("used_claim_ids", []) if str(value)
    }
    invalid_claim_ids = sorted(used_claim_ids - valid_claim_ids)
    required_claim_count = min(minimum_claims, len(valid_claim_ids))
    if len(used_claim_ids & valid_claim_ids) < required_claim_count:
        errors.append(
            f"verified claim utilization {len(used_claim_ids & valid_claim_ids)} "
            f"is below required {required_claim_count}"
        )
    if invalid_claim_ids:
        errors.append("unknown used_claim_ids: " + ", ".join(invalid_claim_ids))
    declared_citations = {
        str(value) for value in utilization.get("citation_urls", []) if str(value)
    }
    if not citations.issubset(declared_citations):
        errors.append("research_utilization.citation_urls does not cover article citations")

    entity_profile = load_json(root / "ENTITY_PROFILE.json")
    entity_row = next(
        (
            row for row in entity_profile.get("articles", [])
            if isinstance(row, dict) and str(row.get("task_id") or "") == task_id
        ),
        {},
    )
    entity_names = [
        str(entity.get("official_name") or "").strip()
        for entity in entity_row.get("entities", [])
        if isinstance(entity, dict) and str(entity.get("official_name") or "").strip()
    ]
    covered_entities = [
        name for name in entity_names if name.casefold() in text.casefold()
    ]
    entity_coverage = round(
        len(covered_entities) / max(1, len(entity_names)) * 100,
        2,
    )
    if entity_names and entity_coverage < 100:
        errors.append(f"entity coverage {entity_coverage} is below 100")

    paragraphs = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip().casefold()
        for value in re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", html)
    ]
    comparable = [value for value in paragraphs if len(value.split()) >= 20]
    duplicated = len(comparable) - len(set(comparable))
    history_paragraphs: set[str] = set()
    history_root = research_root / "series_history"
    if history_root.is_dir():
        for path in history_root.rglob("article.md"):
            for paragraph in re.split(r"(?:\r?\n){2,}", path.read_text(encoding="utf-8")):
                normalized = re.sub(r"\s+", " ", paragraph).strip().casefold()
                if len(normalized.split()) >= 20:
                    history_paragraphs.add(normalized)
    website_root = root / "website"
    if website_root.is_dir():
        for path in website_root.glob("*/article.html"):
            if path.parent.name == slug:
                continue
            other_html = path.read_text(encoding="utf-8")
            for paragraph in re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", other_html):
                normalized = re.sub(
                    r"\s+",
                    " ",
                    re.sub(r"<[^>]+>", " ", paragraph),
                ).strip().casefold()
                if len(normalized.split()) >= 20:
                    history_paragraphs.add(normalized)
    duplicated += sum(1 for value in set(comparable) if value in history_paragraphs)
    duplicate_risk = round(duplicated / max(1, len(comparable)) * 100, 2)
    maximum_duplicate = float(
        (website_contract.get("preflight_quality") or {}).get("maximum_duplicate_risk", 35)
    )
    if duplicate_risk > maximum_duplicate:
        errors.append(f"duplicate risk {duplicate_risk} exceeds maximum {maximum_duplicate}")

    required_checks = 17
    coverage = round(max(0, required_checks - len(errors)) / required_checks * 100, 2)
    citation_coverage = round(min(100, len(citations) / 2 * 100), 2)
    predicted_score = round(
        max(
            0,
            min(
                100,
                coverage * 0.55
                + (100 - duplicate_risk) * 0.15
                + entity_coverage * 0.15
                + citation_coverage * 0.15,
            ),
        ),
        2,
    )
    minimum_score = float(
        (website_contract.get("preflight_quality") or {}).get(
            "minimum_predicted_ai_score", 70
        )
    )
    if predicted_score < minimum_score:
        errors.append(f"predicted AI score {predicted_score} is below minimum {minimum_score}")
    return {
        "task_id": task_id,
        "slug": slug,
        "predicted_ai_score": predicted_score,
        "word_count": len(words),
        "duplicate_risk": duplicate_risk,
        "coverage": coverage,
        "entity_coverage": entity_coverage,
        "citation_coverage": citation_coverage,
        "missing_sections": errors,
        "expected_menu_w_result": "VALIDATION_PASS" if not errors else "BLOCKED",
        "generation_attempt": generation_attempt,
        "errors": errors,
    }


def normalized_social_title(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def clean_website_title(value: object) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def normalized_website_title(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_website_title(value).casefold()).strip()


def website_title_review(root: Path, task: dict) -> tuple[str, list[str]]:
    errors: list[str] = []
    slug = str(task.get("article_slug") or task.get("slug") or "")
    article_root = root / "website" / slug
    try:
        metadata = load_json(article_root / "metadata.json")
        html = (article_root / "article.html").read_text(encoding="utf-8")
        markdown = (article_root / "article.md").read_text(encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return "", [f"website title files are missing or invalid: {exc}"]
    html_title_match = re.search(r"(?is)<title\b[^>]*>(.*?)</title>", html)
    html_h1_match = re.search(r"(?is)<h1\b[^>]*>(.*?)</h1>", html)
    markdown_h1_match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
    values = [
        clean_website_title(metadata.get("title")),
        clean_website_title(html_title_match.group(1) if html_title_match else ""),
        clean_website_title(html_h1_match.group(1) if html_h1_match else ""),
        clean_website_title(markdown_h1_match.group(1) if markdown_h1_match else ""),
    ]
    normalized = [normalized_website_title(value) for value in values]
    if not all(normalized) or len(set(normalized)) != 1:
        errors.append(
            "public title must match in metadata.title, HTML title, HTML H1, and Markdown H1"
        )
    title = values[0]
    if len(title) >= 45 and re.search(r"\b[A-Za-z]$", title):
        errors.append("title appears truncated because it ends with a single-letter fragment")
    prior = {
        normalized_website_title(value)
        for value in task.get("prior_website_titles") or []
        if normalized_website_title(value)
    }
    if normalized[0] and normalized[0] in prior:
        errors.append(f"title reuses a prior website title: {title}")
    return normalized[0], errors


def social_series_review(root: Path, task: dict, contract: dict) -> list[str]:
    errors: list[str] = []
    slug = str(task.get("article_slug") or task.get("slug") or "")
    metadata_path = root / "social" / slug / "metadata.json"
    try:
        metadata = load_json(metadata_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"social metadata is missing or invalid: {exc}"]
    series_plan = metadata.get("series_plan")
    if not isinstance(series_plan, dict):
        return ["social metadata must declare series_plan"]
    social_contract = contract.get("social_editorial_contract") or {}
    expected_schema = str(social_contract.get("schema_version") or "social_editorial_series_v1")
    if str(series_plan.get("schema_version") or "") != expected_schema:
        errors.append(f"series_plan schema_version must be {expected_schema}")
    strict_value = bool((task.get("social_value_requirements") or {}).get("enabled"))
    complementary_components = str(task.get("task_type") or "") == "SOCIAL_WEBSITE_DISTRIBUTION"
    fields = (
        ("pillar_title", "today_angle")
        if strict_value or complementary_components
        else ("pillar_title", "today_angle", "next_day_title")
    )
    for field in fields:
        if not str(series_plan.get(field) or "").strip():
            errors.append(f"series_plan.{field} is required")
    try:
        if int(series_plan.get("day_number") or 0) < 1:
            errors.append("series_plan.day_number must be a positive integer")
    except (TypeError, ValueError):
        errors.append("series_plan.day_number must be a positive integer")
    if str(series_plan.get("next_day_title") or "").strip() and normalized_social_title(series_plan.get("today_angle")) == normalized_social_title(
        series_plan.get("next_day_title")
    ):
        errors.append("series_plan.next_day_title must differ from today_angle")

    canonical = normalized_social_title(task.get("title"))
    prior = {
        normalized_social_title(value)
        for value in task.get("prior_social_titles") or []
        if normalized_social_title(value)
    }
    seen: set[str] = set()
    platforms = contract.get("social_platforms") or []
    variants = contract.get("social_variants") or ["A.md", "B.md", "C.md"]
    platform_metadata = metadata.get("platforms")
    if not isinstance(platform_metadata, dict):
        return [*errors, "social metadata.platforms must be an object"]
    for platform in platforms:
        details = platform_metadata.get(platform)
        if not isinstance(details, dict):
            errors.append(f"missing metadata for {platform}")
            continue
        variant_titles = details.get("variant_titles")
        if not isinstance(variant_titles, dict):
            errors.append(f"missing variant_titles for {platform}")
            continue
        for variant in variants:
            title = str(variant_titles.get(variant) or "").strip()
            normalized = normalized_social_title(title)
            if not normalized:
                errors.append(f"missing {platform} title for {variant}")
            elif normalized == canonical:
                errors.append(f"{platform} {variant} title repeats the canonical article title")
            elif normalized in prior:
                errors.append(f"{platform} {variant} title reuses a prior social title")
            elif normalized in seen:
                errors.append(f"duplicate social variant title: {title}")
            seen.add(normalized)
        if normalized_social_title(details.get("title")) != normalized_social_title(
            variant_titles.get("A.md")
        ):
            errors.append(f"{platform} title must match variant_titles.A.md")
        teaser = str(details.get("closing_cta") or details.get("next_day_teaser") or details.get("cta") or "").strip()
        if not teaser and not strict_value and not complementary_components:
            errors.append(f"missing closing CTA for {platform}")
            continue
        markers = (
            ("ngày mai", "đón đọc", "tiếp theo")
            if platform == "facebook_vi"
            else ("tomorrow", "next", "coming")
        )
        if not strict_value and not complementary_components and not any(marker in teaser.casefold() for marker in markers):
            errors.append(f"{platform} next_day_teaser does not lead into tomorrow's content")
        if strict_value and teaser and not task.get("scheduled_followup_exists") and re.search(
            r"\b(tomorrow|check back tomorrow|more tomorrow|stay tuned|i['\u2019]?ll (?:post|share))\b",
            teaser,
            flags=re.I,
        ):
            errors.append(f"{platform} contains an unsupported future promise")
        for variant in variants:
            draft = root / "social" / slug / platform / variant
            if draft.is_file():
                draft_text = draft.read_text(encoding="utf-8").rstrip()
                if teaser and not complementary_components and not draft_text.endswith(teaser):
                    errors.append(f"{platform} {variant} must end with the declared closing CTA")
                if strict_value:
                    public_lines = [line.strip() for line in draft_text.splitlines() if line.strip()]
                    ending = public_lines[-1] if public_lines else ""
                    if re.search(
                        r"^(?:use|check(?: out)?|learn more|try|start|read|visit|follow|click|open|save)\b",
                        ending,
                        flags=re.I,
                    ):
                        errors.append(
                            f"{platform} {variant} generic CTA ending; use an implication, decision question, observation, or source"
                        )
                    if not task.get("scheduled_followup_exists") and re.search(
                        r"\b(?:today|yesterday|tomorrow|this week|act now|breaking|game[ -]?changer)\b",
                        draft_text,
                        flags=re.I,
                    ):
                        errors.append(f"{platform} {variant} contains fake urgency or a stale relative date")
    return errors


def main() -> int:
    root = Path.cwd()
    manifest = load_json(root / "manifest.json")
    queue = load_json(root / "queue.json")
    contract_path = (
        root / "OUTPUT_CONTRACT.json"
        if (root / "OUTPUT_CONTRACT.json").is_file()
        else root / "output_contract.json"
    )
    contract = load_json(contract_path)
    tasks = queue.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        print("ERROR: queue.json must contain at least one task.", file=sys.stderr)
        return 2

    package_id = str(manifest.get("package_id") or "")
    task_type = str(manifest.get("task_type") or "")
    allowed_paths = contract.get("allowed_paths") or []
    if not isinstance(allowed_paths, list):
        print("ERROR: OUTPUT_CONTRACT.json allowed_paths must be a list.", file=sys.stderr)
        return 2

    writer_name = os.environ.get("EXTERNAL_WRITER_NAME", "ChatGPT").strip() or "ChatGPT"
    writer_type = os.environ.get("EXTERNAL_WRITER_TYPE", "external_ai").strip() or "external_ai"
    writer_version = os.environ.get("EXTERNAL_WRITER_VERSION", "web").strip() or "web"
    now = datetime.now(timezone.utc).isoformat()

    errors: list[str] = []
    item_rows: list[dict] = []
    zip_members: list[str] = []
    quality_reports: list[dict] = []
    returned_website_titles: set[str] = set()
    article_specs: dict[str, dict] = {}
    website_contract: dict = {}
    if task_type == "WEBSITE_ADVANCED":
        try:
            spec_payload = load_json(root / "ARTICLE_SPEC.json")
            website_contract = load_json(root / "website_writing_contract.json")
            article_specs = {
                str(row.get("task_id") or ""): row
                for row in spec_payload.get("articles", [])
                if isinstance(row, dict) and str(row.get("task_id") or "")
            }
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"WEBSITE_ADVANCED contract files are missing or invalid: {exc}")

    for task in tasks:
        if not isinstance(task, dict):
            errors.append("Every task must be a JSON object.")
            continue
        slug = str(task.get("article_slug") or task.get("slug") or "")
        row_task_type = str(task.get("task_type") or task_type)
        task_id = str(task.get("task_id") or "")
        revision = int(task.get("revision") or 1)
        targets = task.get("target_output_paths") or []
        if not slug or not task_id:
            errors.append("Task is missing article_slug or task_id.")
            continue
        if not isinstance(targets, list) or not targets:
            errors.append(f"{task_id}: no target_output_paths are declared.")
            continue

        files: dict[str, str] = {}
        for target in targets:
            target = str(target)
            if not is_safe_relative(target):
                errors.append(f"{task_id}: unsafe target path {target!r}.")
                continue
            if not allowed(target, allowed_paths):
                errors.append(f"{task_id}: target path is outside output_contract allowlist: {target}")
                continue
            source = root / Path(*PurePosixPath(target).parts)
            if not source.is_file():
                errors.append(f"{task_id}: missing required output {target}.")
                continue
            if source.suffix.lower() in EXECUTABLE_SUFFIXES:
                errors.append(f"{task_id}: executable output is not allowed: {target}.")
                continue
            files[target] = sha256(source)
            zip_members.append(target)

        asset_root = root / output_root_for(row_task_type, slug) / "assets"
        if asset_root.exists():
            for asset in sorted(path for path in asset_root.rglob("*") if path.is_file()):
                rel = asset.relative_to(root).as_posix()
                if not is_safe_relative(rel):
                    errors.append(f"{task_id}: unsafe asset path {rel!r}.")
                    continue
                if not allowed(rel, allowed_paths):
                    errors.append(f"{task_id}: asset path is outside output_contract allowlist: {rel}")
                    continue
                if asset.suffix.lower() in EXECUTABLE_SUFFIXES:
                    errors.append(f"{task_id}: executable asset is not allowed: {rel}.")
                    continue
                files[rel] = sha256(asset)
                zip_members.append(rel)

        if row_task_type.startswith("WEBSITE_"):
            returned_title, title_errors = website_title_review(root, task)
            for error in title_errors:
                errors.append(f"{task_id}: {error}.")
            if returned_title:
                if returned_title in returned_website_titles:
                    errors.append(f"{task_id}: duplicate website title within package.")
                returned_website_titles.add(returned_title)

        if row_task_type == "WEBSITE_ADVANCED":
            article_path = root / "website" / slug / "article.html"
            spec = article_specs.get(task_id)
            if spec is None:
                errors.append(f"{task_id}: ARTICLE_SPEC.json entry is missing.")
            elif article_path.is_file():
                quality_report = advanced_editorial_review(
                    root,
                    slug,
                    task_id,
                    article_path.read_text(encoding="utf-8"),
                    spec,
                    website_contract,
                )
                quality_reports.append(quality_report)
                for error in quality_report["errors"]:
                    errors.append(f"{task_id}: {error}.")
        elif row_task_type.startswith("SOCIAL_"):
            for error in social_series_review(root, task, contract):
                errors.append(f"{task_id}: {error}.")

        item_rows.append(
            {
                "task_id": task_id,
                "slug": slug,
                "article_slug": slug,
                "task_type": row_task_type,
                "revision": revision,
                "status": "completed_needs_review",
                "output_root": output_root_for(row_task_type, slug),
                "files": files,
            }
        )

    if errors:
        stale_zip = root / "completed_drafts.zip"
        if stale_zip.exists():
            stale_zip.unlink()
        for report in quality_reports:
            print(f"Predicted AI Score: {report['predicted_ai_score']}")
            print(f"Word count: {report['word_count']}")
            print(f"Duplicate score: {report['duplicate_risk']}")
            print(f"Coverage: {report['coverage']}")
            print(f"Missing sections: {report['missing_sections']}")
            print(f"Expected Menu W result: {report['expected_menu_w_result']}")
            if report["generation_attempt"] < 3:
                print(
                    f"Regeneration required: automatically rewrite and self-review attempt "
                    f"{report['generation_attempt'] + 1} of 3."
                )
            else:
                print("Regeneration limit reached: 3 of 3 attempts; ZIP remains blocked.")
        print("completed_drafts.zip was not created because the package is incomplete:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        retryable = bool(quality_reports) and all(
            report["generation_attempt"] < 3 for report in quality_reports
        )
        if retryable:
            (root / "generation_feedback.json").write_text(
                json.dumps(
                    {
                        "status": "REGENERATION_REQUIRED",
                        "next_attempt": max(
                            1,
                            max(report["generation_attempt"] for report in quality_reports) + 1,
                        ),
                        "maximum_attempts": 3,
                        "reports": quality_reports,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return 3
        feedback_path = root / "generation_feedback.json"
        if feedback_path.exists():
            feedback_path.unlink()
        return 1

    completed_manifest = {
        "schema_version": "universal_external_writer_return_v1",
        "package_id": package_id,
        "task_type": task_type,
        "verified_package_contract": {
            "path": "verified_package_contract.json",
            "sha256": sha256(root / "verified_package_contract.json"),
        },
        "writer": {
            "writer_type": writer_type,
            "writer_name": writer_name,
            "writer_version": writer_version,
            "generated_at": now,
        },
        "writer_type": writer_type,
        "writer_name": writer_name,
        "writer_version": writer_version,
        "generated_at": now,
        "completed_at": now,
        "approval_changed": False,
        "published": False,
        "items": item_rows,
    }

    manifest_path = root / "completed_manifest.json"
    manifest_path.write_text(
        json.dumps(completed_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    zip_path = root / "completed_drafts.zip"
    feedback_path = root / "generation_feedback.json"
    if feedback_path.exists():
        feedback_path.unlink()
    if zip_path.exists():
        zip_path.unlink()
    unique_members = [
        "completed_manifest.json",
        "verified_package_contract.json",
        *sorted(set(zip_members)),
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in unique_members:
            if not is_safe_relative(member):
                print(f"ERROR: unsafe ZIP member {member!r}.", file=sys.stderr)
                return 2
            if Path(member).suffix.lower() in EXECUTABLE_SUFFIXES:
                print(f"ERROR: executable ZIP member is not allowed: {member}", file=sys.stderr)
                return 2
            archive.write(root / Path(*PurePosixPath(member).parts), member)

    print(f"completed_drafts.zip created: {zip_path}")
    print(f"tasks: {len(item_rows)}")
    print(f"files: {len(unique_members)}")
    for report in quality_reports:
        print(f"Predicted AI Score: {report['predicted_ai_score']}")
        print(f"Word count: {report['word_count']}")
        print(f"Duplicate score: {report['duplicate_risk']}")
        print(f"Coverage: {report['coverage']}")
        print(f"Missing sections: {report['missing_sections']}")
        print(f"Expected Menu W result: {report['expected_menu_w_result']}")
    print("approval_changed: false")
    print("published: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
