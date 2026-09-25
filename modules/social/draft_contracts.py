from __future__ import annotations

import html
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .content_quality import official_source_name
from .utils import PublishedArticle, now_iso

BLUESKY_CHARACTER_LIMIT = 300

SOCIAL_DRAFT_STATUSES = {
    "needs_social_review",
    "revision_requested",
    "approved_for_copy",
    "pending_manual_publish",
    "rejected",
    "writing_package_ready",
    "needs_social_draft",
    "not_recommended",
    "published_manual",
    "failed",
}

SOCIAL_STATUS_LABELS = {
    "needs_social_review": "Needs Review",
    "revision_requested": "Revision Requested",
    "approved_for_copy": "Approved for Copy",
    "pending_manual_publish": "Pending Manual Publish",
    "rejected": "Rejected",
    "writing_package_ready": "Draft",
    "needs_social_draft": "Draft",
    "not_recommended": "Not Recommended",
    "published_manual": "Published Manual",
    "failed": "Failed",
}

SOCIAL_STATUS_ALIASES = {
    "approved for copy": "approved_for_copy",
    "pending manual publish": "pending_manual_publish",
    "needs changes": "revision_requested",
    "revision requested": "revision_requested",
    "published manual": "published_manual",
    "draft": "needs_social_review",
    "needs review": "needs_social_review",
    "not recommended": "not_recommended",
}

PLATFORM_LABELS = {
    "facebook_en": "Facebook English",
    "facebook_vi": "Facebook Vietnamese",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
    "x": "X",
    "twitter": "X",
    "quora": "Quora",
    "devto": "Dev.to",
    "pinterest": "Pinterest",
    "producthunt": "Product Hunt",
    "threads": "Threads",
    "bluesky": "Bluesky",
    "medium": "Medium",
    "hashnode": "Hashnode",
    "blogger": "Blogger",
    "telegram": "Telegram",
}

VIETNAMESE_MOJIBAKE_PATTERNS = (
    "C?ng",
    "T?nh",
    "B?i",
    "??",
    "Chá»",
    "ChÃ",
    "phÃ",
    "Ä‘",
    "á»",
    "áº",
    "Ã ",
)

def _status_key(status: object) -> str:
    raw = str(status or "needs_social_review").strip()
    lowered = raw.lower().replace("-", "_").replace(" ", "_")
    if lowered in SOCIAL_DRAFT_STATUSES:
        return lowered
    return SOCIAL_STATUS_ALIASES.get(raw.lower(), "needs_social_review")

def _status_label(status: object) -> str:
    return SOCIAL_STATUS_LABELS.get(_status_key(status), str(status or "Needs Review"))

def _platform_label(platform: object) -> str:
    return PLATFORM_LABELS.get(str(platform), str(platform).replace("_", " ").title())

def has_vietnamese_mojibake(value: object) -> bool:
    text = str(value or "")
    if not text:
        return False
    return any(pattern in text for pattern in VIETNAMESE_MOJIBAKE_PATTERNS)

def vietnamese_mojibake_warning() -> str:
    return (
        "Facebook Vietnamese draft appears to contain mojibake/corrupted Vietnamese text. "
        "Regenerate or edit it before approving for copy."
    )

def _append_unique_warning(warnings: list[Any], warning: str) -> list[str]:
    normalized = [str(item) for item in warnings if str(item)]
    if warning not in normalized:
        normalized.append(warning)
    return normalized

def normalize_pinterest_final_url(value: str) -> str:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        return ""
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if hostname in {"www.pinterest.com", "pinterest.com"}:
        match = re.fullmatch(r"/pin/(\d+)", path)
        if not match:
            return ""
        return urlunsplit(("https", "www.pinterest.com", f"/pin/{match.group(1)}/", "", ""))
    if hostname == "pin.it":
        code = path.strip("/")
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,80}", code):
            return ""
        return urlunsplit(("https", "pin.it", f"/{code}", "", ""))
    return ""

def validate_pinterest_final_url(value: str) -> dict[str, Any]:
    raw = str(value or "").strip()
    normalized = normalize_pinterest_final_url(raw)
    if not raw:
        return {"valid": False, "status": "empty", "message": "Final Pinterest URL is required."}
    if not normalized:
        return {
            "valid": False,
            "status": "invalid",
            "message": "Enter a Pinterest Pin URL such as https://www.pinterest.com/pin/<numeric-id>/ or a pin.it short URL.",
        }
    hostname = (urlsplit(normalized).hostname or "").lower()
    if hostname == "pin.it":
        return {
            "valid": True,
            "status": "limited_short_url",
            "normalized_url": normalized,
            "message": "pin.it short URL accepted with limited validation. Use the full pinterest.com/pin URL when available.",
        }
    return {
        "valid": True,
        "status": "valid_pin_url",
        "normalized_url": normalized,
        "message": "Pinterest Pin URL accepted.",
    }

def _extract_prefixed_line(text: str, prefix: str) -> str:
    pattern = rf"^\s*{re.escape(prefix)}\s*(.+?)\s*$"
    match = re.search(pattern, text or "", flags=re.I | re.M)
    return match.group(1).strip() if match else ""

def _strip_pinterest_labels(text: str) -> str:
    cleaned = re.sub(r"^#\s*Pinterest pin draft\s*", "", text or "", flags=re.I).strip()
    for label in (
        "Pin title:",
        "Pin description:",
        "Destination URL:",
        "Image URL:",
        "Local image file:",
        "Suggested board:",
        "Keywords:",
        "Overlay text:",
        "CTA:",
    ):
        cleaned = re.sub(rf"^\s*{re.escape(label)}\s*.*$", "", cleaned, flags=re.I | re.M)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"^\s*(?:Source|Ngu\u1ed3n)\s*:\s*$", "", cleaned, flags=re.I | re.M)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

def _clean_pin_description(
    value: str,
    *,
    cta: str = "",
    hashtags: list[str] | None = None,
    source_name: str = "",
) -> str:
    description = _strip_pinterest_labels(value)
    # A dashboard read used to persist the derived description back to metadata.
    # On the next read URLs were stripped but the preceding CTA label survived,
    # so another CTA was appended.  Canonicalise every CTA/link block first so
    # this function is idempotent even when repairing already polluted metadata.
    description = re.sub(
        r"^\s*(?:read|open|view|continue)(?:\s+the)?(?:\s+exact)?(?:\s+full)?"
        r"(?:\s+live)?\s+(?:guide|article|review|comparison|post)\s*:\s*(?:https?://\S+)?\s*$",
        "",
        description,
        flags=re.I | re.M,
    )
    # Remove repeated hashtag-only blocks; one normalized block is appended
    # below from metadata.
    description = re.sub(r"^\s*(?:#[A-Za-z0-9_-]+\s*)+$", "", description, flags=re.M)
    if not description:
        description = "Read the full comparison on Smile AI Review Hub."
    description = re.sub(r"\b(Image URL|Destination URL|Suggested board|Keywords|Overlay text)\b.*", "", description, flags=re.I)
    description = re.sub(r"\n{3,}", "\n\n", description).strip()
    if source_name and not re.search(rf"(?:^|\n)\s*(?:Source|Ngu\u1ed3n)\s*:\s*{re.escape(source_name)}\s*$", description, re.I):
        description = f"{description}\n\nSource: {source_name}".strip()
    canonical_cta = re.sub(r"\s+", " ", cta or "").strip()
    if canonical_cta:
        description = f"{description}\n\n{canonical_cta}".strip()
    tag_text = " ".join(tag for tag in (hashtags or []) if str(tag).startswith("#"))
    if tag_text and tag_text not in description:
        description = f"{description}\n\n{tag_text}".strip()
    return description

def _pinterest_fields_from_metadata(
    *,
    metadata: dict[str, Any],
    body: str,
    title: str,
    source_url: str,
    platform_image_path: str,
) -> dict[str, Any]:
    raw = body or str(metadata.get("body") or "")
    hashtags = metadata.get("hashtags") if isinstance(metadata.get("hashtags"), list) else []
    pin_title = str(metadata.get("pin_title") or _extract_prefixed_line(raw, "Pin title:") or metadata.get("source_title") or title).strip()
    # Prefer the selected Markdown over the cached derived metadata.  The
    # Markdown is the imported source of truth; metadata is only a cache and may
    # contain output from an older, non-idempotent dashboard read.
    extracted_description = _extract_prefixed_line(raw, "Pin description:")
    pin_description_raw = str(extracted_description or raw or metadata.get("pin_description") or "")
    if not pin_description_raw:
        pin_description_raw = _strip_pinterest_labels(raw)
    destination_url = str(metadata.get("destination_url") or _extract_prefixed_line(raw, "Destination URL:") or metadata.get("source_url") or source_url).strip()
    suggested_board = str(metadata.get("suggested_board") or _extract_prefixed_line(raw, "Suggested board:") or "AI Tools Comparison").strip()
    keyword_text = metadata.get("keywords")
    if isinstance(keyword_text, list):
        keywords = [str(item).strip() for item in keyword_text if str(item).strip()]
    else:
        keywords = [
            item.strip()
            for item in str(keyword_text or _extract_prefixed_line(raw, "Keywords:") or "").split(",")
            if item.strip()
        ]
    overlay_text = str(metadata.get("overlay_text") or _extract_prefixed_line(raw, "Overlay text:") or pin_title).strip()
    alt_text = str(metadata.get("alt_text") or f"Pinterest graphic for {pin_title}.").strip()
    source_name = official_source_name(
        source_url,
        str(metadata.get("official_source_name") or metadata.get("source_name") or ""),
    )
    pin_description = _clean_pin_description(
        pin_description_raw,
        cta=str(metadata.get("CTA") or metadata.get("cta") or ""),
        hashtags=hashtags,
        source_name=source_name,
    )
    paragraphs = pin_description.split("\n\n")
    if paragraphs and paragraphs[0].strip().casefold() == pin_title.casefold():
        pin_description = "\n\n".join(paragraphs[1:]).strip()
    return {
        "pin_title": pin_title,
        "pin_description": pin_description,
        "destination_url": destination_url,
        "image_path": platform_image_path,
        "image_url": "",
        "suggested_board": suggested_board,
        "keywords": keywords,
        "alt_text": alt_text,
        "overlay_text": overlay_text,
        "hashtags": hashtags,
        "official_source_name": source_name,
    }

def _public_url(value: object) -> str:
    text = str(value or "").strip()
    return text if text.startswith(("https://", "http://")) else ""

def _plain_words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", html.unescape(value or ""))

def _word_count(value: str) -> int:
    return len(_plain_words(value))

def _sentence(value: str, *, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", html.unescape(value or "")).strip()
    if not text:
        return fallback
    parts = re.split(r"(?<=[.!?])\s+", text)
    for part in parts:
        clean = part.strip()
        if len(clean) >= 35:
            return clean
    return text

def _sentence_list(article: PublishedArticle) -> list[str]:
    candidates = [
        article.summary,
        article.description,
        *(article.key_points or []),
        *(article.headings or []),
    ]
    sentences: list[str] = []
    for candidate in candidates:
        clean = _sentence(str(candidate or ""))
        if clean and clean.lower() not in {item.lower() for item in sentences}:
            sentences.append(clean)
    return sentences

def _clean_public_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"[A-Z]:\\[^\n]+", "", text)
    text = re.sub(r"\b(?:metadata|debug|draft_path|local image file|image note|canonical url note)\b:?.*$", "", text, flags=re.I | re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def _slugify(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return clean[:80].strip("-") or "smile-ai-review-hub-guide"

def _title_case(value: str) -> str:
    small = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "nor", "of", "on", "or", "the", "to", "vs", "with"}
    proper = {"ai": "AI", "ifttt": "IFTTT", "saas": "SaaS", "seo": "SEO", "api": "API", "crm": "CRM"}
    words = re.split(r"(\s+|-)", value.strip())
    result: list[str] = []
    word_index = 0
    word_total = len([part for part in words if part and not part.isspace() and part != "-"])
    for part in words:
        if not part or part.isspace() or part == "-":
            result.append(part)
            continue
        raw = part.strip()
        lowered = raw.lower()
        word_index += 1
        if lowered in proper:
            result.append(proper[lowered])
        elif lowered in small and word_index not in {1, word_total}:
            result.append(lowered)
        else:
            result.append(raw[:1].upper() + raw[1:].lower())
    return "".join(result)

def _blogger_title_for_article(article: PublishedArticle) -> str:
    source = article.title.strip()
    lowered = source.lower()
    if "companies are buying ai tools" in lowered:
        return "Are AI Tools Worth It for Small Businesses?"
    if "marketing automation" in lowered:
        return "Marketing Automation Software Workflow Checklist"
    if "ifttt" in lowered:
        return "Best New AI Tools by IFTTT: Workflow Use Cases"
    title = _title_case(source)
    if len(title) > 65:
        title = title[:65].rsplit(" ", 1)[0].strip()
    while title.split() and title.split()[-1].lower() in {"in", "for", "and", "or", "to", "of", "with"}:
        title = " ".join(title.split()[:-1])
    return title

def _blogger_search_description(article: PublishedArticle, title: str) -> str:
    lowered = f"{article.title} {article.description}".lower()
    if "companies are buying ai tools" in lowered:
        return "Evaluate AI tools for small businesses with practical checks for workflow fit, pricing, integrations, adoption risks, governance, and real-world use."
    if "ifttt" in lowered:
        return "Evaluate new AI tools for IFTTT workflows with practical checks for pricing, automation limits, integrations, risks, setup effort, and real-world use."
    if "marketing automation" in lowered:
        return "Compare marketing automation software with workflow criteria for pricing, integrations, campaign handoffs, reporting, buyer risk, and practical team fit."
    subject = title.replace("  ", " ")
    description = f"Evaluate {subject} with practical checks for workflow fit, pricing, integrations, risks, and real-world use."
    if len(description) < 130:
        description = f"Evaluate {subject} with practical checks for workflow fit, pricing, integrations, risks, source evidence, and buyer readiness."
    if len(description) > 160:
        description = f"Evaluate {subject} with practical checks for workflow fit, pricing, integrations, risk, source evidence, and buyer readiness."
    if len(description) > 160:
        description = f"Evaluate {subject} with checks for workflow fit, pricing, integrations, risk, source evidence, and buyer readiness."
    return description

def _blogger_permalink_slug(article: PublishedArticle, title: str) -> str:
    lowered = f"{article.article_id} {article.title}".lower()
    if "ifttt" in lowered:
        return "new-ai-tools-by-ifttt-workflows-use-cases-2026"
    if "marketing automation" in lowered:
        return "marketing-automation-software-workflow-checklist-2026"
    return _slugify(title)[:75].strip("-")

def _looks_incomplete_sentence(value: str) -> bool:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return True
    if not re.search(r"[.!?]$", text):
        return True
    lowered = text.rstrip(".!?").lower()
    endings = (
        " to the",
        " to a",
        " to an",
        " for the",
        " for a",
        " with the",
        " with a",
        " of the",
        " of a",
        " and",
        " or",
        " to",
        " for",
        " with",
        " of",
        " the",
    )
    return lowered.endswith(endings)

def _unique(values: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        result.append(clean)
        if limit and len(result) >= limit:
            break
    return result

def _label_from_tag(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9 ]+", "", value.replace("#", " ")).strip()
    return re.sub(r"\s+", " ", label)[:40]

def _html_paragraph(value: str) -> str:
    return f"<p>{html.escape(_clean_public_text(value))}</p>"

def _html_list(items: list[str], *, ordered: bool = False) -> str:
    tag = "ol" if ordered else "ul"
    lis = "".join(f"<li>{html.escape(_clean_public_text(item))}</li>" for item in items if _clean_public_text(item))
    return f"<{tag}>{lis}</{tag}>" if lis else ""

def _html_link(url: str, label: str) -> str:
    clean_url = _public_url(url)
    if not clean_url:
        return html.escape(label)
    return f'<a href="{html.escape(clean_url, quote=True)}" rel="noopener noreferrer">{html.escape(label)}</a>'

def _dedupe_paragraphs(paragraphs: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for paragraph in paragraphs:
        clean = re.sub(r"\s+", " ", _clean_public_text(paragraph)).strip()
        if not clean:
            continue
        fingerprint = re.sub(r"[^a-z0-9]+", " ", clean.lower()).strip()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(clean)
    return result

def _duplicate_items(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        clean = re.sub(r"\s+", " ", html.unescape(value or "")).strip().lower()
        if not clean:
            continue
        if clean in seen and clean not in duplicates:
            duplicates.append(clean)
        seen.add(clean)
    return duplicates

def _extract_html_headings(html_body: str) -> list[tuple[int, str]]:
    return [
        (int(level), re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip())
        for level, text in re.findall(r"<h([1-6])[^>]*>(.*?)</h\1>", html_body or "", flags=re.I | re.S)
    ]

def _extract_html_paragraph_texts(html_body: str) -> list[str]:
    texts = re.findall(r"<p[^>]*>(.*?)</p>", html_body or "", flags=re.I | re.S)
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip() for text in texts]

def _count_links(html_body: str, *, internal: bool) -> int:
    links = re.findall(r"<a\s+[^>]*href=[\"']([^\"']+)[\"']", html_body or "", flags=re.I)
    if internal:
        return sum(1 for link in links if "smileaireviewhub.com" in link)
    return sum(1 for link in links if link.startswith(("http://", "https://")) and "smileaireviewhub.com" not in link)

def _blogger_json_ld(article: PublishedArticle, title: str, description: str, faq_items: list[dict[str, str]], image_url: str) -> dict[str, Any]:
    url = article.canonical_url or article.url
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": "https://smileaireviewhub.com/#organization",
                "name": "Smile AI Review Hub",
                "url": "https://smileaireviewhub.com/",
            },
            {
                "@type": "WebSite",
                "@id": "https://smileaireviewhub.com/#website",
                "url": "https://smileaireviewhub.com/",
                "name": "Smile AI Review Hub",
                "publisher": {"@id": "https://smileaireviewhub.com/#organization"},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://smileaireviewhub.com/"},
                    {"@type": "ListItem", "position": 2, "name": title, "item": url},
                ],
            },
            {
                "@type": "Article",
                "headline": title,
                "description": description,
                "mainEntityOfPage": url,
                "image": image_url or article.image,
                "author": {"@type": "Person", "name": "Smile AI Review Hub Editorial Team"},
                "publisher": {"@id": "https://smileaireviewhub.com/#organization"},
                "datePublished": article.publish_date or now_iso(),
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["question"],
                        "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
                    }
                    for item in faq_items
                ],
            },
        ],
    }

def _blogger_seo_metrics(html_body: str, plain_text: str, faq_items: list[dict[str, str]], *, title: str, description: str, slug: str, keyword: str) -> dict[str, Any]:
    headings = _extract_html_headings(html_body)
    word_count = _word_count(plain_text)
    checks = {
        "title_has_keyword": keyword.lower() in title.lower(),
        "description_has_keyword": keyword.lower() in description.lower(),
        "slug_has_keyword": any(part and part in slug for part in _slugify(keyword).split("-")[:2]),
        "first_paragraph_has_keyword": keyword.lower() in (plain_text.split("\n\n", 1)[0] if plain_text else "").lower(),
        "has_faq": len(faq_items) >= 3,
        "word_count_ok": 1300 <= word_count <= 2200,
        "heading_count_ok": len(headings) >= 9,
    }
    return {
        "seo_score": round(100 * sum(1 for passed in checks.values() if passed) / max(1, len(checks))),
        "estimated_reading_time_minutes": max(1, round(word_count / 220)),
        "heading_count": len(headings),
        "faq_count": len(faq_items),
        "internal_link_count": _count_links(html_body, internal=True),
        "external_link_count": _count_links(html_body, internal=False),
        "json_ld_status": "present",
        "seo_checks": checks,
    }

def _body_has_internal_text(value: str) -> bool:
    lowered = value.lower()
    return bool(
        re.search(r"[a-z]:\\", value, flags=re.I)
        or any(token in lowered for token in ("metadata.json", "source_package", "draft_path", "local image file:", "image note:", "canonical url note:"))
    )

def _clip_to_limit(text: str, limit: int = BLUESKY_CHARACTER_LIMIT) -> str:
    if len(text) <= limit:
        return text
    suffix = "..."
    return text[: max(0, limit - len(suffix))].rstrip() + suffix

def _blogger_article_fields(
    article: PublishedArticle,
    *,
    platform_image_path: str,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = existing or {}
    url = article.canonical_url or article.url
    title = _blogger_title_for_article(article)
    lowered = f"{article.title} {article.description}".lower()
    if "ifttt" in lowered:
        primary_keyword = "new AI tools by IFTTT"
    elif "marketing automation" in lowered:
        primary_keyword = "marketing automation software"
    else:
        primary_keyword = title
    seo_title = title
    permalink_slug = _blogger_permalink_slug(article, title)
    labels = _unique([_label_from_tag(tag) for tag in article.tags] + ["AI Tools", "Small Business", "Workflow Automation", "Software Review"], limit=5)
    summary = _sentence(article.summary or article.description, fallback=f"This guide explains how to evaluate {article.title} before relying on it in a real workflow.")
    key_points = _unique([item for item in (article.key_points or article.headings or []) if str(item).strip()], limit=7)
    if len(key_points) < 5:
        key_points.extend([
            "Confirm the workflow problem before comparing feature lists.",
            "Check pricing, limits, integrations, support, and export rules.",
            "Use the source article as the final reference before buying.",
        ])
    key_points = _unique(key_points, limit=7)
    checklist = _unique([
        "Define the weekly workflow you want to improve.",
        "Shortlist tools only after the workflow problem is clear.",
        "Verify pricing, plan limits, AI usage caps, admin controls, exports, and support on official pages.",
        "Run one real task before committing to a platform.",
        "Keep human review in the loop when AI output affects customers or decisions.",
    ])
    search_description = _blogger_search_description(article, title)
    intro = (
        f"{primary_keyword} should be judged by the workflow it improves, not by a feature list alone. "
        "This companion article turns the source review into a practical buyer guide for small teams that need a clearer way to compare options before committing."
    )
    disclosure = str(existing.get("disclosure") or article.affiliate_disclosure or "Some links may be affiliate links. The review remains independent editorial research.")
    faq_items = [
        {
            "question": f"What should buyers verify before choosing {primary_keyword}?",
            "answer": "Verify pricing, usage limits, integrations, data export, support expectations, and whether the product solves a real workflow problem.",
        },
        {
            "question": "Can this companion article replace the source review?",
            "answer": "No. It summarizes a practical evaluation path and links back to the Smile AI Review Hub source article for the full context and supporting details.",
        },
        {
            "question": "What if a feature or price cannot be verified?",
            "answer": "Treat the claim as unconfirmed. Check the official vendor website, pricing page, documentation, or FAQ before using it in a buying decision.",
        },
    ]
    h2_keyword = f"How to evaluate {primary_keyword}"
    sections: list[dict[str, Any]] = [
        {"level": 2, "heading": "Introduction", "paragraphs": [intro, summary]},
        {"level": 2, "heading": "Why this comparison matters", "paragraphs": [
            "Small teams often compare software after a landing page, a demo, or a recommendation. That is risky because the real cost appears later in setup work, handoffs, support gaps, and limits that were not obvious during the first review.",
            f"The better approach is to compare {primary_keyword} against the work your team already performs. If the tool does not shorten that workflow or make it easier to review, the strongest feature list may still be a poor fit.",
        ]},
        {"level": 2, "heading": "Who should read this", "paragraphs": [
            "This guide is for founders, marketers, operators, and small business teams that need a practical way to compare software before paying for a plan or moving important work into a new system.",
            "It is also useful for reviewers who want a structured checklist. The goal is not to crown a winner from one screenshot. The goal is to reduce avoidable buying mistakes.",
        ]},
        {"level": 2, "heading": h2_keyword, "paragraphs": [
            f"Start by naming the job you expect {primary_keyword} to improve. A useful test might be campaign planning, content review, lead routing, support follow-up, automation cleanup, or reporting.",
            "Then compare the tool against that job. Look at setup time, permissions, exports, integrations, review controls, reporting quality, and the amount of human checking still required.",
        ]},
        {"level": 3, "heading": "Verification methods", "paragraphs": [
            "Use the official website for feature claims. Use the official pricing page for plan limits. Use documentation or FAQ pages for setup, integration, security, export, and support details.",
            "If a claim is not visible in the source article or official documentation, do not present it as fact. Mark it as unverified and check it manually before buying.",
        ]},
        {"level": 2, "heading": "Key buying checklist", "list": checklist},
        {"level": 2, "heading": "Pricing considerations", "paragraphs": [
            "Pricing can change by billing period, region, seat count, usage tier, and feature access. A plan that looks inexpensive can become costly when AI usage, automation runs, storage, or team seats increase.",
            "Before buying, confirm what happens when usage grows. Check whether key features sit behind higher plans, whether cancellation is simple, and whether export options are available if the tool does not work out.",
        ]},
        {"level": 2, "heading": "Workflow examples", "paragraphs": [
            "A practical workflow test should use one real task. For a marketing team, that might mean planning one campaign, routing one lead list, reviewing one automation sequence, or producing one weekly report.",
            "For an operations team, the test might be handoff quality. Does the tool reduce manual copying, make errors easier to catch, or create a clearer review trail? Those are stronger signals than a polished demo.",
        ]},
        {"level": 2, "heading": "Pros", "list": [
            "A source-backed checklist keeps the evaluation tied to visible evidence.",
            "Workflow testing helps teams avoid buying tools that look strong but do not reduce real work.",
            "Separating verified claims from unverified claims improves trust and makes the final decision easier to defend.",
        ]},
        {"level": 2, "heading": "Cons", "list": [
            "A companion guide cannot confirm every current price or plan detail on its own.",
            "Some features may require hands-on testing before the real value is clear.",
            "Teams with regulated medical, legal, financial, or security workflows need specialist review before relying on any software output.",
        ]},
        {"level": 2, "heading": "Alternatives", "paragraphs": [
            "Alternatives should be compared by use case, not only by category. A simpler tool may be better if it solves one repeatable workflow with less setup and less review burden.",
            "When you compare alternatives, keep the same evaluation method. Test the same workflow, use the same pricing assumptions, and ask the same support and export questions.",
        ]},
        {"level": 2, "heading": "Common mistakes", "list": [
            "Choosing the tool with the longest feature list before defining the workflow.",
            "Trusting copied pricing notes instead of checking the official pricing page.",
            "Ignoring export rules, support limits, cancellation terms, and admin controls.",
            "Treating unverified vendor claims as facts without checking official documentation.",
        ]},
        {"level": 2, "heading": "Frequently asked questions", "faqs": faq_items},
        {"level": 2, "heading": "Final recommendation", "paragraphs": [
            f"Use {primary_keyword} only after it passes a real workflow test and after the commercial details are verified. The safest buying decision is the one your team can explain with evidence.",
        ]},
        {"level": 2, "heading": "Disclosure", "paragraphs": [disclosure]},
    ]
    html_parts = [f"<h1>{html.escape(title)}</h1>"]
    plain_chunks: list[str] = []
    for section in sections:
        level = int(section["level"])
        heading = str(section["heading"])
        html_parts.append(f"<h{level}>{html.escape(heading)}</h{level}>")
        plain_chunks.append(heading)
        if "list" in section:
            items = [str(item) for item in section["list"]]
            html_parts.append(_html_list(items))
            plain_chunks.extend([f"- {item}" for item in items])
        elif "faqs" in section:
            for faq in section["faqs"]:
                question = str(faq["question"])
                answer = str(faq["answer"])
                html_parts.append(f"<h3>{html.escape(question)}</h3>{_html_paragraph(answer)}")
                plain_chunks.extend([question, answer])
        else:
            paragraphs = _dedupe_paragraphs([str(item) for item in section.get("paragraphs", [])])
            for paragraph in paragraphs:
                html_parts.append(_html_paragraph(paragraph))
                plain_chunks.append(paragraph)
    html_body = "\n".join(html_parts)
    plain_text = _clean_public_text("\n\n".join(plain_chunks))
    if _word_count(plain_text) < 1300:
        expansion = [
            "A good review process also includes a rollback plan. Before moving a team into a new tool, write down how you would export the data, pause the workflow, or return to the previous process if the test fails.",
            "Ask who will own the tool after purchase. A product can look simple during evaluation but still require a clear owner for settings, billing, permissions, integrations, training, and quality checks.",
            "Do not treat AI output as final by default. Even useful automation should have a review step for claims, customer-facing language, sensitive data, and tasks that could affect revenue or trust.",
            "Finally, compare the cost of the tool with the cost of the current process. If a tool saves only a few minutes but adds review work, support uncertainty, or export risk, the buying case is weak.",
            "Keep the evaluation narrow enough to finish. One tested workflow with real data usually reveals more than a broad checklist that no one on the team has time to verify.",
            "Document any assumptions that came from marketing copy rather than official documentation. Those assumptions should be reviewed again before the team signs a contract or moves customer data.",
            "Look for evidence of support quality, onboarding help, and realistic documentation. A tool can have strong features but still slow the team down if setup questions are hard to answer.",
            "When possible, compare the same task in two or three tools. This keeps the evaluation fair and makes it easier to explain why one option fits the workflow better than another.",
            "For teams that rely on approvals, check whether the tool keeps a useful audit trail. A clear review history is often more valuable than another automation feature that no one can verify later.",
            "For teams that handle client work, test how easy it is to separate projects, users, and permissions. Weak account structure can create rework even when the core feature set looks promising.",
            "For teams that expect growth, ask what changes when usage doubles. Review seat pricing, automation limits, file storage, reporting access, and whether support remains available on the same plan.",
            "For teams with limited technical help, favor tools with clear documentation and simple recovery steps. A powerful system that requires constant troubleshooting may not be the best small-business choice.",
            "The final decision should be written down in plain language. Note what was verified, what remains uncertain, who approved the test, and what would trigger a switch to another option.",
            "This kind of buying record improves trust. It also helps the team avoid repeating the same evaluation when a new tool appears with similar claims a few months later.",
            "Before final approval, ask a second reviewer to repeat the key workflow and confirm the same result. A repeatable outcome is stronger evidence than one successful test performed by the person who configured the tool.",
        ]
        while _word_count(plain_text) < 1300:
            added = False
            for paragraph in expansion:
                if paragraph in plain_text:
                    continue
                html_body += "\n" + _html_paragraph(paragraph)
                plain_text += "\n\n" + paragraph
                added = True
                if _word_count(plain_text) >= 1300:
                    break
            if not added:
                break
    source_limit_note = ""
    if _word_count(plain_text) < 1300:
        source_limit_note = "Kept near the lower target because the source package is concise; no unsupported facts were added."
    html_body += (
        f'\n<p>Read the {_html_link(url, "full source review on Smile AI Review Hub")} '
        "for the complete evidence and buying notes.</p>"
    )
    plain_text += f"\n\nRead the full source review: {url}"
    image_alt_text = f"{primary_keyword} buying checklist and workflow review."
    image_caption = f"Use this companion guide to review {primary_keyword} with source-backed buying criteria."
    recommended_filename = f"{permalink_slug}-blogger-companion.png"
    json_ld = _blogger_json_ld(article, title, search_description, faq_items, article.og_image or article.image)
    html_body = f'{html_body}\n<script type="application/ld+json">{html.escape(json.dumps(json_ld, ensure_ascii=False))}</script>'
    metrics = _blogger_seo_metrics(html_body, plain_text, faq_items, title=title, description=search_description, slug=permalink_slug, keyword=primary_keyword)
    warnings = validate_blogger_metadata(
        {
            "title": title,
            "seo_title": seo_title,
            "html_body": html_body,
            "plain_text_body": plain_text,
            "search_description": search_description,
            "source_article_url": url,
            "image_path": platform_image_path,
            "disclosure": disclosure,
            "recommended_permalink_slug": permalink_slug,
            "json_ld": json_ld,
            **metrics,
        }
    )
    return {
        "title": title,
        "seo_title": seo_title,
        "h1": title,
        "html_body": html_body,
        "plain_text_body": plain_text,
        "labels": labels,
        "search_description": search_description,
        "source_article_url": url,
        "recommended_permalink_slug": permalink_slug,
        "slug": permalink_slug,
        "disclosure": disclosure,
        "image_path": platform_image_path,
        "image_alt_text": image_alt_text,
        "image_caption": image_caption,
        "recommended_image_filename": recommended_filename,
        "open_graph_title": title,
        "open_graph_description": search_description,
        "twitter_card_description": search_description,
        "json_ld": json_ld,
        "body": plain_text,
        "character_count": len(plain_text),
        "blogger_word_count": _word_count(plain_text),
        **metrics,
        "source_limit_note": source_limit_note,
        "validation_warnings": warnings,
    }

def validate_blogger_metadata(metadata: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    title = str(metadata.get("title") or "").strip()
    html_body = str(metadata.get("html_body") or "")
    plain_body = str(metadata.get("plain_text_body") or metadata.get("body") or "")
    source_url = _public_url(metadata.get("source_article_url") or metadata.get("website_url"))
    if not title:
        warnings.append("Blogger title is missing.")
    elif len(title) > 60:
        warnings.append("Blogger title should stay under 60 characters.")
    if not html_body or not plain_body:
        warnings.append("Blogger body is missing.")
    word_count = _word_count(plain_body)
    if word_count < 1300:
        warnings.append("Blogger article is below the 1300-word minimum.")
    if word_count > 2200:
        warnings.append("Blogger article is above the 2200-word maximum.")
    description = str(metadata.get("search_description") or "")
    if not description:
        warnings.append("Blogger search description is missing.")
    elif not (140 <= len(description) <= 160):
        warnings.append("Blogger search description should be 140-160 characters.")
    if description and _looks_incomplete_sentence(description):
        warnings.append("Blogger search description appears truncated or incomplete.")
    if description and _body_has_internal_text(description):
        warnings.append("Blogger search description contains internal metadata or local paths.")
    if not source_url:
        warnings.append("Source website URL is missing or invalid.")
    elif source_url not in html_body and source_url not in plain_body:
        warnings.append("Source website URL is not visible in the Blogger article.")
    image_path = Path(str(metadata.get("image_path") or ""))
    if not image_path.exists():
        warnings.append("Blogger image file is missing.")
    visible = f"{html_body}\n{plain_body}"
    if _body_has_internal_text(visible):
        warnings.append("Blogger visible body contains internal metadata or local paths.")
    for token in ("Title:", "Image note:", "Local image file:", "metadata.json"):
        if token.lower() in visible.lower():
            warnings.append(f"Blogger visible body contains raw internal label: {token}")
    if "placeholder" in visible.lower():
        warnings.append("Blogger body contains placeholder text.")
    if not str(metadata.get("disclosure") or "").strip():
        warnings.append("Affiliate disclosure is missing.")
    plain_start = re.sub(r"\s+", " ", plain_body.strip().splitlines()[0] if plain_body.strip().splitlines() else "").strip().lower()
    if title and plain_start == re.sub(r"\s+", " ", title).strip().lower():
        warnings.append("Blogger body starts with a duplicate title.")
    slug = str(metadata.get("recommended_permalink_slug") or "")
    if slug != slug.lower() or not re.fullmatch(r"[a-z0-9-]+", slug or ""):
        warnings.append("Blogger permalink slug must be lowercase hyphenated text.")
    if len(slug) > 75:
        warnings.append("Blogger permalink slug is longer than 75 characters.")
    if "best-top-10" in slug or "--" in slug:
        warnings.append("Blogger permalink slug contains redundant or malformed wording.")
    headings = _extract_html_headings(html_body)
    heading_texts = [heading for _, heading in headings]
    if _duplicate_items(heading_texts):
        warnings.append("Blogger article contains duplicate headings.")
    paragraphs = [text for text in _extract_html_paragraph_texts(html_body) if _word_count(text) >= 6]
    if _duplicate_items(paragraphs):
        warnings.append("Blogger article contains duplicate paragraphs.")
    heading_matches = list(re.finditer(r"<h([1-6])[^>]*>.*?</h\1>", html_body, flags=re.I | re.S))
    for index, match in enumerate(heading_matches):
        if int(match.group(1)) == 1:
            continue
        end = match.end()
        next_start = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(html_body)
        if index + 1 < len(heading_matches) and int(heading_matches[index + 1].group(1)) > int(match.group(1)):
            continue
        between = re.sub(r"<script.*?</script>", "", html_body[end:next_start], flags=re.I | re.S)
        if not re.sub(r"<[^>]+>", " ", between).strip():
            warnings.append("Blogger article contains a heading without content.")
            break
    if not any(level == 1 for level, _ in headings):
        warnings.append("Blogger article is missing an H1.")
    levels = [level for level, _ in headings]
    if 3 in levels and 2 not in levels:
        warnings.append("Blogger heading hierarchy skips H2 before H3.")
    faq_count = int(metadata.get("faq_count") or 0)
    if faq_count < 3:
        faq_count = len(re.findall(r'"@type"\s*:\s*"Question"', json.dumps(metadata.get("json_ld") or {})))
    if faq_count < 3:
        warnings.append("Blogger FAQ section should include at least 3 questions.")
    if not metadata.get("json_ld"):
        warnings.append("Blogger JSON-LD is missing.")
    return _unique(warnings)

def _bluesky_fields(article: PublishedArticle, *, platform_image_path: str, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    url = article.canonical_url or article.url
    hashtags = _unique([tag for tag in article.tags if str(tag).startswith("#")], limit=3)
    if not hashtags:
        hashtags = ["#AI", "#SmallBusiness"]
    key = _sentence((article.key_points or article.headings or [article.summary or article.title])[0], fallback=article.title)
    if len(key) < 45:
        key = _sentence(article.summary or article.description, fallback=f"Evaluate {article.title} by workflow fit before comparing feature lists.")
    standalone_base = f"{key}\n\nRead the guide: {url}"
    if hashtags:
        standalone_base = f"{standalone_base}\n\n{' '.join(hashtags[:3])}"
    standalone = _clip_to_limit(standalone_base)
    insight = _clip_to_limit(f"1/4 {key}", BLUESKY_CHARACTER_LIMIT)
    thread = [
        insight,
        _clip_to_limit("2/4 Start with workflow fit before comparing feature lists. Check what changes in the real weekly process.", BLUESKY_CHARACTER_LIMIT),
        _clip_to_limit("3/4 Verify pricing, integrations, exports, support, and review controls before adopting a new AI tool.", BLUESKY_CHARACTER_LIMIT),
        _clip_to_limit(f"4/4 Full source guide: {url}\n{' '.join(hashtags[:2])}", BLUESKY_CHARACTER_LIMIT),
    ]
    warnings = validate_bluesky_metadata(
        {
            "standalone_post": standalone,
            "thread_posts": thread,
            "article_url": url,
            "hashtags": hashtags,
            "image_path": platform_image_path,
        }
    )
    return {
        "standalone_post": standalone,
        "thread_posts": thread,
        "article_url": url,
        "hashtags": hashtags,
        "image_path": platform_image_path,
        "image_alt_text": f"Social card for {article.title}.",
        "character_counts": {
            "standalone_post": len(standalone),
            "thread_posts": [len(post) for post in thread],
        },
        "body": standalone,
        "character_count": len(standalone),
        "validation_warnings": warnings,
    }

def validate_bluesky_metadata(metadata: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    standalone = str(metadata.get("standalone_post") or "")
    if not standalone:
        warnings.append("Bluesky standalone post is missing.")
    if len(standalone) > BLUESKY_CHARACTER_LIMIT:
        warnings.append("Bluesky standalone post exceeds the character limit.")
    article_url = _public_url(metadata.get("article_url") or metadata.get("website_url"))
    if not article_url:
        warnings.append("Bluesky article URL is missing or invalid.")
    elif article_url not in standalone and not any(article_url in str(post) for post in metadata.get("thread_posts") or []):
        warnings.append("Bluesky article URL is missing from post text.")
    thread = metadata.get("thread_posts") or []
    if not isinstance(thread, list) or not thread:
        warnings.append("Bluesky thread posts are missing.")
    else:
        for index, post in enumerate(thread, start=1):
            if not str(post).strip():
                warnings.append(f"Bluesky thread post {index} is empty.")
            if len(str(post)) > BLUESKY_CHARACTER_LIMIT:
                warnings.append(f"Bluesky thread post {index} exceeds the character limit.")
    tags = metadata.get("hashtags") or []
    if isinstance(tags, list):
        if len(tags) != len(_unique([str(tag) for tag in tags])):
            warnings.append("Bluesky hashtags contain duplicates.")
        if len(tags) > 3:
            warnings.append("Bluesky uses too many hashtags.")
    visible = "\n".join([standalone, *[str(post) for post in thread if isinstance(thread, list)]])
    if _body_has_internal_text(visible):
        warnings.append("Bluesky text contains internal metadata or local paths.")
    if "placeholder" in visible.lower():
        warnings.append("Bluesky text contains placeholder text.")
    return _unique(warnings)
