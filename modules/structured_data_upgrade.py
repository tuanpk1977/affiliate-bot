from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from config import settings
from modules.indexing_policy import is_redirect_page, rel_path_for_html


BASE_URL = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
SITE_NAME = settings.site_name or "MS Smile AI Review Hub"
AUTHOR_NAME = "Nguyen Quoc Tuan"
ORG_ID = f"{BASE_URL}/#organization"
WEBSITE_ID = f"{BASE_URL}/#website"
AUTHOR_ID = f"{BASE_URL}/about-author/#person"
FAQ_SCHEMA_DISABLED_PATHS = {
    "/comparisons/framer-vs-webflow/",
    "/vi/comparisons/framer-vs-webflow/",
}
JSON_LD_PATTERN = re.compile(
    r"\s*<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>.*?</script>\s*",
    flags=re.I | re.S,
)


def apply_structured_data_upgrade(output: Path) -> dict[str, int]:
    stats = {
        "pages": 0,
        "changed": 0,
        "schemas_removed_from_excluded_pages": 0,
        "review_pages": 0,
        "comparison_pages": 0,
        "video_pages": 0,
    }
    for page in sorted(output.rglob("index.html")):
        rel_url = rel_path_for_html(page, output)
        original = page.read_text(encoding="utf-8", errors="ignore")
        existing = json_ld_payloads(original)
        without_schema = JSON_LD_PATTERN.sub("\n", original)
        stats["pages"] += 1

        if is_excluded_page(without_schema, rel_url):
            updated = without_schema
            if existing:
                stats["schemas_removed_from_excluded_pages"] += 1
        else:
            schemas, page_stats = build_page_schemas(without_schema, rel_url, existing, page)
            stats["review_pages"] += page_stats["review"]
            stats["comparison_pages"] += page_stats["comparison"]
            stats["video_pages"] += page_stats["video"]
            scripts = "\n".join(
                f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}</script>'
                for schema in schemas
            )
            updated = without_schema.replace("</head>", scripts + "\n</head>", 1)

        if updated != original:
            page.write_text(updated, encoding="utf-8")
            stats["changed"] += 1
    return stats


def build_page_schemas(
    source: str,
    rel_url: str,
    existing: list[dict[str, object]],
    page: Path,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    canonical = clean_canonical(source, rel_url)
    lang = page_language(source, rel_url)
    title = clean_text(extract(source, r"<title\b[^>]*>(.*?)</title>")) or SITE_NAME
    h1 = clean_text(extract(source, r"<h1\b[^>]*>(.*?)</h1>")) or title
    description = extract_meta(source, "description")
    image = extract_property(source, "og:image")
    page_kind = classify_page(rel_url, h1, existing)
    modified, published = schema_dates(existing, page)
    section = article_section(rel_url, page_kind)

    schemas: list[dict[str, object]] = [organization_schema(), website_schema()]
    if page_kind in {"article", "review", "comparison"}:
        schemas.append(person_schema())
        schemas.append(
            article_schema(
                canonical=canonical,
                headline=h1,
                description=description,
                image=image,
                lang=lang,
                section=section,
                published=published,
                modified=modified,
            )
        )
    if rel_url != "/":
        schemas.append(breadcrumb_schema(rel_url, h1, lang))

    if page_kind == "review":
        product_name = review_product_name(h1, lang)
        software_id = f"{canonical}#software"
        schemas.append(software_schema(product_name, canonical, description, software_id))
        schemas.append(review_schema(product_name, canonical, description, lang, software_id))
    elif page_kind == "comparison":
        tools = comparison_tools(h1, rel_url)
        if len(tools) >= 2:
            schemas.append(comparison_item_list(canonical, tools, description))
    elif page_kind == "category":
        schemas.append(collection_schema(canonical, h1, description, lang))

    faq = None if rel_url in FAQ_SCHEMA_DISABLED_PATHS else faq_schema_from_visible_details(source)
    if faq:
        schemas.append(faq)

    video = video_schema(source, canonical, h1, description, image, modified)
    if video:
        schemas.append(video)

    return schemas, {
        "review": int(page_kind == "review"),
        "comparison": int(page_kind == "comparison"),
        "video": int(video is not None),
    }


def organization_schema() -> dict[str, object]:
    social_profiles = load_social_profiles()
    schema: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": ORG_ID,
        "name": SITE_NAME,
        "url": f"{BASE_URL}/",
        "description": (
            "Independent research-focused reviews and comparisons of AI tools, SaaS, workflow "
            "automation, SEO tools, productivity software, and website builders."
        ),
        "email": settings.contact_email or "contact@smileaireviewhub.com",
        "founder": {"@id": AUTHOR_ID},
        "contactPoint": [
            {
                "@type": "ContactPoint",
                "contactType": "business inquiries",
                "email": settings.contact_email or "contact@smileaireviewhub.com",
                "url": f"{BASE_URL}/contact/",
            },
            {
                "@type": "ContactPoint",
                "contactType": "partnership requests",
                "email": settings.admin_email or "admin@smileaireviewhub.com",
                "url": f"{BASE_URL}/contact/",
            },
        ],
    }
    if social_profiles:
        schema["sameAs"] = social_profiles
    return schema


def website_schema() -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": WEBSITE_ID,
        "name": SITE_NAME,
        "url": f"{BASE_URL}/",
        "publisher": {"@id": ORG_ID},
        "inLanguage": ["en", "vi-VN"],
    }


def person_schema() -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "@id": AUTHOR_ID,
        "name": AUTHOR_NAME,
        "url": f"{BASE_URL}/about-author/",
        "jobTitle": "Founder - MS Smile AI Review Hub",
        "worksFor": {"@id": ORG_ID},
    }


def article_schema(
    canonical: str,
    headline: str,
    description: str,
    image: str,
    lang: str,
    section: str,
    published: str,
    modified: str,
) -> dict[str, object]:
    schema: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "Article",
        "@id": f"{canonical}#article",
        "headline": headline,
        "description": description,
        "url": canonical,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "inLanguage": lang,
        "articleSection": section,
        "datePublished": published,
        "dateModified": modified,
        "author": {"@id": AUTHOR_ID},
        "publisher": {"@id": ORG_ID},
    }
    if image:
        schema["image"] = image
    return schema


def software_schema(name: str, canonical: str, description: str, software_id: str) -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "@id": software_id,
        "name": name,
        "url": canonical,
        "description": description,
        "applicationCategory": "BusinessApplication",
        "operatingSystem": "Web",
    }


def review_schema(name: str, canonical: str, description: str, lang: str, software_id: str) -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "Review",
        "@id": f"{canonical}#review",
        "url": canonical,
        "name": f"{name} review",
        "reviewBody": description,
        "inLanguage": lang,
        "author": {"@id": AUTHOR_ID},
        "publisher": {"@id": ORG_ID},
        "itemReviewed": {"@id": software_id},
    }


def comparison_item_list(canonical: str, tools: list[str], description: str) -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "@id": f"{canonical}#compared-tools",
        "name": "Compared software",
        "description": description,
        "url": canonical,
        "numberOfItems": len(tools),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "item": {
                    "@type": "SoftwareApplication",
                    "@id": f"{canonical}#software-{position}",
                    "name": name,
                    "applicationCategory": "BusinessApplication",
                    "operatingSystem": "Web",
                },
            }
            for position, name in enumerate(tools, start=1)
        ],
    }


def collection_schema(canonical: str, name: str, description: str, lang: str) -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "@id": f"{canonical}#collection",
        "name": name,
        "description": description,
        "url": canonical,
        "inLanguage": lang,
        "isPartOf": {"@id": WEBSITE_ID},
    }


def breadcrumb_schema(rel_url: str, page_name: str, lang: str) -> dict[str, object]:
    parts = [part for part in rel_url.strip("/").split("/") if part]
    home_name = "Trang chủ" if lang == "vi-VN" else "Home"
    items: list[dict[str, object]] = [
        {"@type": "ListItem", "position": 1, "name": home_name, "item": f"{BASE_URL}/"}
    ]
    for position, part in enumerate(parts, start=2):
        path = "/" + "/".join(parts[: position - 1]) + "/"
        name = page_name if position == len(parts) + 1 else part.replace("-", " ").title()
        if lang == "vi-VN" and part == "vi":
            name = "Tiếng Việt"
        items.append({"@type": "ListItem", "position": position, "name": name, "item": f"{BASE_URL}{path}"})
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "@id": f"{BASE_URL}{rel_url}#breadcrumb",
        "itemListElement": items,
    }


def faq_schema_from_visible_details(source: str) -> dict[str, object] | None:
    entities: list[dict[str, object]] = []
    for details in re.findall(r"<details\b[^>]*>(.*?)</details>", source, flags=re.I | re.S):
        question = clean_text(extract(details, r"<summary\b[^>]*>(.*?)</summary>"))
        answer = clean_text(re.sub(r"<summary\b[^>]*>.*?</summary>", "", details, count=1, flags=re.I | re.S))
        if question and answer and len(question) <= 220 and len(answer) >= 20:
            entities.append(
                {
                    "@type": "Question",
                    "name": question,
                    "acceptedAnswer": {"@type": "Answer", "text": answer[:1200]},
                }
            )
    if not entities:
        return None
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities[:10]}


def video_schema(
    source: str,
    canonical: str,
    name: str,
    description: str,
    image: str,
    modified: str,
) -> dict[str, object] | None:
    video_id = extract_youtube_id(source)
    if not video_id:
        return None
    schema: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "VideoObject",
        "@id": f"{canonical}#video",
        "name": name,
        "description": description,
        "thumbnailUrl": image or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "uploadDate": modified,
        "embedUrl": f"https://www.youtube.com/embed/{video_id}",
        "contentUrl": f"https://www.youtube.com/watch?v={video_id}",
        "isPartOf": {"@id": f"{canonical}#article"},
    }
    return schema


def classify_page(rel_url: str, h1: str, existing: list[dict[str, object]]) -> str:
    localized = rel_url[3:] if rel_url.startswith("/vi/") else rel_url
    if localized == "/":
        return "page"
    if localized in {"/reviews/", "/review/", "/comparisons/", "/compare/", "/categories/", "/hubs/"}:
        return "category"
    if localized.startswith(("/compare/", "/comparisons/")) and localized.count("/") >= 3:
        return "comparison"
    if localized.startswith(("/reviews/", "/review/")) and localized not in {"/reviews/", "/review/"}:
        return "review"
    if localized.startswith(("/category/", "/categories/", "/hub/", "/hubs/")):
        return "category"
    if localized.startswith("/blog/") and localized != "/blog/":
        return "article"
    if " vs " in h1.lower():
        return "comparison"
    if rel_url != "/" and ("review" in h1.lower() or "đánh giá" in h1.lower()):
        return "review"
    if any(payload.get("@type") == "Article" for payload in existing):
        return "article"
    return "page"


def is_excluded_page(source: str, rel_url: str) -> bool:
    robots = extract(source, r"<meta\b(?=[^>]*name=['\"]robots['\"])(?=[^>]*content=['\"]([^'\"]+)['\"])[^>]*>")
    return (
        is_redirect_page(rel_url)
        or rel_url.startswith("/go/")
        or "noindex" in robots.lower()
        or bool(re.search(r"<meta\b[^>]*http-equiv=['\"]?refresh", source, flags=re.I))
    )


def clean_canonical(source: str, rel_url: str) -> str:
    value = extract(source, r"<link\b(?=[^>]*rel=['\"]canonical['\"])(?=[^>]*href=['\"]([^'\"]+)['\"])[^>]*>")
    parsed = urlparse(value)
    if parsed.netloc == "smileaireviewhub.com":
        return f"{BASE_URL}{parsed.path}" if parsed.path != "/" else f"{BASE_URL}/"
    return f"{BASE_URL}{rel_url}"


def schema_dates(existing: list[dict[str, object]], page: Path) -> tuple[str, str]:
    published = ""
    modified = ""
    for payload in existing:
        if payload.get("@type") in {"Article", "BlogPosting", "NewsArticle"}:
            published = str(payload.get("datePublished") or published)
            modified = str(payload.get("dateModified") or modified)
    fallback = date.fromtimestamp(page.stat().st_mtime).isoformat()
    modified = normalize_date(modified) or fallback
    published = normalize_date(published) or modified
    return modified, published


def normalize_date(value: str) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", value or "")
    return match.group(0) if match else ""


def page_language(source: str, rel_url: str) -> str:
    lang = extract(source, r"<html\b[^>]*lang=['\"]([^'\"]+)['\"]").lower()
    return "vi-VN" if rel_url.startswith("/vi/") or lang.startswith("vi") else "en"


def article_section(rel_url: str, page_kind: str) -> str:
    localized = rel_url[3:] if rel_url.startswith("/vi/") else rel_url
    if page_kind == "comparison":
        return "Software Comparisons"
    if page_kind == "review":
        return "Software Reviews"
    if localized.startswith("/blog/"):
        return "AI and SaaS Guides"
    return "AI and SaaS Research"


def review_product_name(h1: str, lang: str) -> str:
    value = re.sub(r"^\s*Đánh giá\s+", "", h1, flags=re.I) if lang == "vi-VN" else h1
    value = re.split(r"\bReview\b|:", value, maxsplit=1, flags=re.I)[0].strip()
    return value or h1


def comparison_tools(h1: str, rel_url: str) -> list[str]:
    value = re.sub(r"\s+20\d{2}.*$", "", h1).strip()
    parts = re.split(r"\s+(?:vs\.?|versus)\s+", value, flags=re.I)
    tools = [part.strip(" :|-") for part in parts if part.strip(" :|-")]
    if len(tools) >= 2:
        return tools[:4]
    slug = [part for part in rel_url.strip("/").split("/") if part][-1]
    slug_parts = re.split(r"-vs-", slug, flags=re.I)
    return [part.replace("-", " ").title() for part in slug_parts if part][:4]


def extract_youtube_id(source: str) -> str:
    patterns = [
        r"youtube\.com/embed/([A-Za-z0-9_-]{6,})",
        r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})",
        r"youtu\.be/([A-Za-z0-9_-]{6,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.I)
        if match:
            return match.group(1)
    return ""


def load_social_profiles() -> list[str]:
    path = settings.base_dir / "config" / "siteStats.json"
    profiles = ["https://youtube.com/@SmileAIReviewHub"]
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            profiles.extend(
                str(item.get("url", "")).strip()
                for item in payload.get("communityChannels", [])
                if str(item.get("url", "")).strip().startswith("https://")
            )
        except (json.JSONDecodeError, OSError):
            pass
    return list(dict.fromkeys(profiles))


def json_ld_payloads(source: str) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for match in re.finditer(
        r"<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
        source,
        flags=re.I | re.S,
    ):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def extract_meta(source: str, name: str) -> str:
    return extract(source, rf"<meta\b(?=[^>]*name=['\"]{re.escape(name)}['\"])(?=[^>]*content=['\"]([^'\"]*)['\"])[^>]*>")


def extract_property(source: str, name: str) -> str:
    return extract(source, rf"<meta\b(?=[^>]*property=['\"]{re.escape(name)}['\"])(?=[^>]*content=['\"]([^'\"]*)['\"])[^>]*>")


def extract(source: str, pattern: str) -> str:
    match = re.search(pattern, source, flags=re.I | re.S)
    return html.unescape(match.group(1).strip()) if match else ""


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()
