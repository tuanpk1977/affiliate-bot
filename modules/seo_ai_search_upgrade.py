from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from config import settings
from modules.indexing_policy import is_redirect_page, rel_path_for_html


BASE_URL = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
SITE_NAME = settings.site_name or "MS Smile AI Review Hub"
AUTHOR_NAME = "Nguyen Quoc Tuan"
AUTHOR_URL = f"{BASE_URL}/about-author/"
ORG_ID = f"{BASE_URL}/#organization"
WEBSITE_ID = f"{BASE_URL}/#website"
AUTHOR_ID = f"{AUTHOR_URL}#person"
FAQ_SCHEMA_DISABLED_PATHS = {
    "/comparisons/framer-vs-webflow/",
    "/vi/comparisons/framer-vs-webflow/",
}


def apply_seo_ai_search_upgrade(output: Path) -> dict[str, int]:
    stats = {"pages": 0, "changed": 0, "faq_schemas_added": 0, "breadcrumbs_added": 0}
    for page in sorted(output.rglob("index.html")):
        rel_url = rel_path_for_html(page, output)
        if is_redirect_page(rel_url) or "/go/" in rel_url:
            continue
        original = page.read_text(encoding="utf-8", errors="ignore")
        updated, additions = upgrade_html(original, rel_url)
        stats["pages"] += 1
        stats["faq_schemas_added"] += additions["faq"]
        stats["breadcrumbs_added"] += additions["breadcrumb"]
        if updated != original:
            page.write_text(updated, encoding="utf-8")
            stats["changed"] += 1
    write_robots_txt(output)
    write_llms_txt(output)
    return stats


def upgrade_html(html_text: str, rel_url: str) -> tuple[str, dict[str, int]]:
    additions = {"faq": 0, "breadcrumb": 0}
    canonical = extract(html_text, r'<link\b[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)')
    canonical = canonical or f"{BASE_URL}{rel_url}"
    title = clean_text(extract(html_text, r"<title[^>]*>(.*?)</title>")) or SITE_NAME
    h1 = clean_text(extract(html_text, r"<h1[^>]*>(.*?)</h1>")) or title.split(" - ")[0]
    description = extract(html_text, r'<meta\b[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)')
    lang = extract(html_text, r'<html\b[^>]*lang=["\']([^"\']+)') or "en"

    if rel_url in FAQ_SCHEMA_DISABLED_PATHS:
        html_text = remove_schema_type(html_text, "FAQPage")
    schemas = schema_types(html_text)
    blocks: list[dict[str, object]] = []
    if "Organization" not in schemas:
        blocks.append(organization_schema())
    if "Person" not in schemas:
        blocks.append(person_schema())
    if rel_url == "/" and "WebSite" not in schemas:
        blocks.append(website_schema())
    if rel_url != "/" and "BreadcrumbList" not in schemas:
        blocks.append(breadcrumb_schema(rel_url, h1))
        additions["breadcrumb"] = 1
    if is_review_page(rel_url, h1):
        product_name = review_product_name(h1)
        if "SoftwareApplication" not in schemas:
            blocks.append(software_schema(product_name, canonical, description))
        if "Review" not in schemas:
            blocks.append(review_schema(product_name, canonical, description))
    if rel_url not in FAQ_SCHEMA_DISABLED_PATHS and "FAQPage" not in schemas:
        faq = faq_schema_from_details(html_text)
        if faq:
            blocks.append(faq)
            additions["faq"] = 1

    if blocks:
        schema_html = "\n".join(
            f'<script type="application/ld+json">{json.dumps(block, ensure_ascii=False, separators=(",", ":"))}</script>'
            for block in blocks
        )
        html_text = html_text.replace("</head>", schema_html + "\n</head>", 1)

    html_text = ensure_affiliate_disclosure_link(html_text, lang)
    html_text = improve_images(html_text, h1)
    return html_text, additions


def organization_schema() -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": ORG_ID,
        "name": SITE_NAME,
        "url": f"{BASE_URL}/",
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
        "sameAs": [
            "https://youtube.com/@SmileAIReviewHub",
            "https://www.facebook.com/MS.SmileAI",
            "https://www.linkedin.com/company/ms-smile-ai-review-hub",
            "https://x.com/MS_SmileAI",
        ],
    }


def person_schema() -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "@id": AUTHOR_ID,
        "name": AUTHOR_NAME,
        "url": AUTHOR_URL,
        "jobTitle": "Founder - MS Smile AI Review Hub",
        "worksFor": {"@id": ORG_ID},
    }


def website_schema() -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": WEBSITE_ID,
        "name": SITE_NAME,
        "url": f"{BASE_URL}/",
        "publisher": {"@id": ORG_ID},
        "inLanguage": ["en", "vi"],
    }


def breadcrumb_schema(rel_url: str, page_name: str) -> dict[str, object]:
    parts = [part for part in rel_url.strip("/").split("/") if part]
    items: list[dict[str, object]] = [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE_URL}/"}
    ]
    for position, part in enumerate(parts, start=2):
        path = "/" + "/".join(parts[: position - 1]) + "/"
        name = page_name if position == len(parts) + 1 else part.replace("-", " ").title()
        items.append({"@type": "ListItem", "position": position, "name": name, "item": f"{BASE_URL}{path}"})
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}


def software_schema(name: str, canonical: str, description: str) -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": name,
        "url": canonical,
        "description": description,
        "applicationCategory": "BusinessApplication",
        "operatingSystem": "Web",
    }


def review_schema(name: str, canonical: str, description: str) -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "Review",
        "url": canonical,
        "name": f"{name} review",
        "reviewBody": description,
        "author": {"@id": AUTHOR_ID},
        "publisher": {"@id": ORG_ID},
        "itemReviewed": {"@type": "SoftwareApplication", "name": name, "url": canonical},
    }


def faq_schema_from_details(html_text: str) -> dict[str, object] | None:
    entities: list[dict[str, object]] = []
    pattern = re.compile(r"<details\b[^>]*>(.*?)</details>", flags=re.I | re.S)
    for details in pattern.findall(html_text):
        question = clean_text(extract(details, r"<summary\b[^>]*>(.*?)</summary>"))
        answer_html = re.sub(r"<summary\b[^>]*>.*?</summary>", "", details, count=1, flags=re.I | re.S)
        answer = clean_text(answer_html)
        if question and answer and len(question) <= 220 and len(answer) >= 20:
            entities.append(
                {
                    "@type": "Question",
                    "name": question,
                    "acceptedAnswer": {"@type": "Answer", "text": answer[:1200]},
                }
            )
    if len(entities) < 2:
        return None
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities[:10]}


def ensure_affiliate_disclosure_link(html_text: str, lang: str) -> str:
    if 'href="/affiliate-disclosure/"' in html_text or 'href="/vi/affiliate-disclosure/"' in html_text:
        return html_text
    label = "Tiết lộ affiliate" if lang.lower().startswith("vi") else "Affiliate Disclosure"
    href = "/vi/affiliate-disclosure/" if lang.lower().startswith("vi") else "/affiliate-disclosure/"
    link = f'<p class="seo-disclosure-link"><a href="{href}">{label}</a></p>'
    if "</footer>" in html_text:
        return html_text.replace("</footer>", link + "\n</footer>", 1)
    return html_text.replace("</body>", link + "\n</body>", 1)


def improve_images(html_text: str, page_name: str) -> str:
    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        if not re.search(r"\balt\s*=", tag, flags=re.I):
            tag = tag[:-1] + f' alt="{html.escape(page_name, quote=True)}">' if tag.endswith(">") else tag
        if not re.search(r"\bloading\s*=", tag, flags=re.I) and not re.search(r"\bfetchpriority\s*=\s*[\"']high", tag, flags=re.I):
            tag = tag[:-1] + ' loading="lazy">' if tag.endswith(">") else tag
        if not re.search(r"\bdecoding\s*=", tag, flags=re.I):
            tag = tag[:-1] + ' decoding="async">' if tag.endswith(">") else tag
        return tag

    return re.sub(r"<img\b[^>]*>", replace, html_text, flags=re.I)


def write_robots_txt(output: Path) -> None:
    agents = [
        "*",
        "Googlebot",
        "Bingbot",
        "OAI-SearchBot",
        "ChatGPT-User",
        "PerplexityBot",
        "ClaudeBot",
        "Google-Extended",
        "facebookexternalhit",
        "Facebot",
        "meta-externalagent",
    ]
    blocks = [f"User-agent: {agent}\nAllow: /" for agent in agents]
    text = "\n\n".join(blocks) + f"\n\nSitemap: {BASE_URL}/sitemap.xml\n"
    (output / "robots.txt").write_text(text, encoding="utf-8")


def write_llms_txt(output: Path) -> None:
    important = [
        ("Home", "/"),
        ("Reviews", "/reviews/"),
        ("Comparisons", "/comparisons/"),
        ("AI SEO hub", "/hub/ai-seo/"),
        ("AI coding hub", "/hub/ai-coding/"),
        ("Website builders hub", "/hub/website-builders/"),
        ("Editorial policy", "/editorial-policy/"),
        ("Testing methodology", "/testing-methodology/"),
        ("Affiliate disclosure", "/affiliate-disclosure/"),
        ("About", "/about/"),
        ("Author", "/about-author/"),
        ("Contact", "/contact/"),
        ("Sitemap", "/sitemap.xml"),
    ]
    lines = "\n".join(f"- {label}: {BASE_URL}{path}" for label, path in important)
    text = f"""# {SITE_NAME}

> Independent research-focused reviews and comparisons of AI tools, SEO software, SaaS, email marketing tools, automation tools, and website builders.

## Editorial identity
- Publisher: {SITE_NAME}
- Founder and author: {AUTHOR_NAME}
- Business contact: contact@smileaireviewhub.com
- Partnership contact: admin@smileaireviewhub.com
- Website: {BASE_URL}/

## Content and citation guidance
- Prefer the canonical URL shown on each page.
- Reviews explain workflow fit, limitations, pricing checks, alternatives, and who should or should not use a tool.
- Pricing and vendor terms can change; verify them on the official vendor website.
- Affiliate relationships are disclosed and do not represent official vendor partnerships.
- English is the primary editorial language; Vietnamese versions are available under /vi/.

## Important URLs
{lines}
"""
    (output / "llms.txt").write_text(text, encoding="utf-8")


def is_review_page(rel_url: str, h1: str) -> bool:
    lowered = rel_url.lower()
    return (
        lowered.startswith("/review/")
        or ("review" in h1.lower() and not any(token in lowered for token in ("/compare/", "/comparisons/")))
    )


def review_product_name(h1: str) -> str:
    value = re.split(r"\bReview\b|:", h1, maxsplit=1, flags=re.I)[0].strip()
    return value or h1


def schema_types(html_text: str) -> set[str]:
    return set(re.findall(r'["@\']type["\']\s*:\s*["\']([^"\']+)["\']', html_text))


def remove_schema_type(html_text: str, schema_type: str) -> str:
    pattern = re.compile(
        r'\s*<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        flags=re.I | re.S,
    )

    def replace(match: re.Match[str]) -> str:
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return match.group(0)
        if isinstance(payload, dict) and payload.get("@type") == schema_type:
            return ""
        return match.group(0)

    return pattern.sub(replace, html_text)


def extract(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.I | re.S)
    return html.unescape(match.group(1).strip()) if match else ""


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()
