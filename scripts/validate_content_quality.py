from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
DATA = ROOT / "data"
PRIORITY_INDEX = DATA / "priority_pages_index.csv"
HUB_INDEX = DATA / "hub_pages_index.csv"
OUTPUT = DATA / "content_quality_report.csv"


PLACEHOLDER_PATTERNS = [
    r"yourdomain\.com",
    r"example\.com",
    r"lorem ipsum",
    r"\btodo\b",
    r"\bundefined\b",
    r"placeholder image",
    r"page not found",
    r"404 not found",
]


@dataclass
class QualityRow:
    page_type: str
    slug: str
    path: str
    word_count: int
    internal_link_count: int
    go_link_count: int
    h1: str
    meta_description: str
    section_signature: str
    max_intro_similarity: float
    max_heading_similarity: float
    similarity_reason: str
    issues: str
    warnings: str
    passed: bool


def main() -> int:
    pages = load_pages()
    if not pages:
        print("No priority or hub pages found. Run python main.py first.")
        return 1

    h1_counts = Counter(page["h1"] for page in pages if page["h1"])
    meta_counts = Counter(page["meta"] for page in pages if page["meta"])
    signature_counts = Counter(page["signature"] for page in pages if page["signature"])
    rows: list[QualityRow] = []

    for page in pages:
        issues: list[str] = []
        warnings: list[str] = []
        min_words = 900 if page["type"] == "priority" else 700
        if page["word_count"] < min_words:
            issues.append(f"word_count_below_{min_words}")
        if not page["h1"]:
            issues.append("missing_h1")
        if not page["meta"]:
            issues.append("missing_meta_description")
        if page["h1"] and h1_counts[page["h1"]] > 1:
            issues.append("duplicate_h1")
        if page["meta"] and meta_counts[page["meta"]] > 1:
            issues.append("duplicate_meta_description")
        if page["internal_links"] < 3:
            issues.append("fewer_than_3_internal_links")
        if page["type"] == "priority" and page["go_links"] < 3:
            issues.append("priority_page_fewer_than_3_go_links")
        if has_placeholder(page["html"]):
            issues.append("placeholder_text_found")
        if signature_counts[page["signature"]] > 6:
            warnings.append("many_pages_share_same_section_structure")

        intro_similarity, heading_similarity = max_similarity(page, pages)
        if intro_similarity >= 0.94:
            warnings.append("intro_too_similar_to_another_page")
        if heading_similarity >= 0.98:
            warnings.append("heading_structure_nearly_identical")
        similarity_reason = similarity_reason_for(intro_similarity, heading_similarity)

        rows.append(
            QualityRow(
                page_type=page["type"],
                slug=page["slug"],
                path=str(page["path"]),
                word_count=page["word_count"],
                internal_link_count=page["internal_links"],
                go_link_count=page["go_links"],
                h1=page["h1"],
                meta_description=page["meta"],
                section_signature=page["signature"],
                max_intro_similarity=round(intro_similarity, 3),
                max_heading_similarity=round(heading_similarity, 3),
                similarity_reason=similarity_reason,
                issues="|".join(issues) or "ok",
                warnings="|".join(warnings) or "none",
                passed=not issues,
            )
        )

    write_report(rows)
    failed = [row for row in rows if not row.passed]
    warning_count = sum(1 for row in rows if row.warnings != "none")
    intro_warning_count = sum(1 for row in rows if "intro_too_similar_to_another_page" in row.warnings)
    heading_warning_count = sum(1 for row in rows if "heading_structure_nearly_identical" in row.warnings)
    print(f"Content quality checked {len(rows)} pages")
    print(f"Passed: {len(rows) - len(failed)} | Failed: {len(failed)} | Warnings: {warning_count}")
    print(f"Warning summary: intro_too_similar={intro_warning_count} | heading_structure_nearly_identical={heading_warning_count}")
    print(f"Output: {OUTPUT}")
    if failed:
        for row in failed[:10]:
            print(f"- FAIL {row.slug}: {row.issues}")
        return 1
    return 0


def load_pages() -> list[dict]:
    pages: list[dict] = []
    for slug in priority_slugs():
        path = SITE / slug / "index.html"
        if path.exists():
            pages.append(parse_page("priority", slug, path))
    for slug in hub_slugs():
        path = SITE / ("hubs" if slug == "hubs" else f"hub/{slug}") / "index.html"
        if path.exists():
            pages.append(parse_page("hub", slug, path))
    return pages


def priority_slugs() -> list[str]:
    if not PRIORITY_INDEX.exists():
        return []
    df = pd.read_csv(PRIORITY_INDEX).fillna("")
    if "suggested_slug" not in df.columns:
        return []
    return [str(slug).strip("/") for slug in df["suggested_slug"].tolist() if str(slug).strip()]


def hub_slugs() -> list[str]:
    if not HUB_INDEX.exists():
        return []
    df = pd.read_csv(HUB_INDEX).fillna("")
    if "hub_slug" not in df.columns:
        return []
    return [str(slug).strip("/") for slug in df["hub_slug"].tolist() if str(slug).strip()]


def parse_page(page_type: str, slug: str, path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    headings = extract_headings(text)
    return {
        "type": page_type,
        "slug": slug,
        "path": path,
        "html": text,
        "h1": extract_tag_text(text, "h1"),
        "meta": extract_meta_description(text),
        "intro": first_paragraph(text),
        "headings": headings,
        "signature": " > ".join(headings[:12]),
        "word_count": word_count(text),
        "internal_links": len(internal_links(text)),
        "go_links": text.count("/go/"),
    }


def extract_tag_text(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return clean_text(match.group(1))


def extract_meta_description(text: str) -> str:
    match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', text, flags=re.IGNORECASE)
    return clean_text(match.group(1)) if match else ""


def extract_headings(text: str) -> list[str]:
    return [clean_text(match) for match in re.findall(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", text, flags=re.IGNORECASE | re.DOTALL)]


def first_paragraph(text: str) -> str:
    for match in re.findall(r"<p[^>]*>(.*?)</p>", text, flags=re.IGNORECASE | re.DOTALL):
        cleaned = clean_text(match)
        if len(cleaned) >= 80 and "Home /" not in cleaned and "Some links may be affiliate links" not in cleaned:
            return cleaned
    return ""


def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def visible_text(text: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9À-ỹ]+(?:[-'][A-Za-z0-9À-ỹ]+)?", visible_text(text)))


def internal_links(text: str) -> set[str]:
    links = set()
    for link in re.findall(r"href=['\"]([^'\"]+)['\"]", text):
        if link.startswith("/") and not link.startswith(("/assets/", "/go/", "//")):
            normalized = link.split("#")[0].split("?")[0]
            if normalized:
                links.add(normalized)
    return links


def has_placeholder(text: str) -> bool:
    lower = re.sub(r"<(script|style)\b.*?</\1>", " ", text.lower(), flags=re.IGNORECASE | re.DOTALL)
    lower = re.sub(r"<!--.*?-->", " ", lower, flags=re.DOTALL)
    return any(re.search(pattern, lower, re.IGNORECASE) for pattern in PLACEHOLDER_PATTERNS)


def max_similarity(page: dict, pages: list[dict]) -> tuple[float, float]:
    intro_scores = []
    heading_scores = []
    for other in pages:
        if other["path"] == page["path"]:
            continue
        intro_scores.append(SequenceMatcher(None, page["intro"], other["intro"]).ratio() if page["intro"] and other["intro"] else 0)
        heading_scores.append(SequenceMatcher(None, page["signature"], other["signature"]).ratio() if page["signature"] and other["signature"] else 0)
    return (max(intro_scores or [0]), max(heading_scores or [0]))


def similarity_reason_for(intro_similarity: float, heading_similarity: float) -> str:
    reasons = []
    if intro_similarity >= 0.94:
        reasons.append("opening paragraphs share similar sentence structure")
    if heading_similarity >= 0.98:
        reasons.append("section heading order/labels are nearly identical")
    if not reasons:
        return "ok"
    return "; ".join(reasons)


def write_report(rows: list[QualityRow]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(QualityRow.__dataclass_fields__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


if __name__ == "__main__":
    raise SystemExit(main())
