from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import urlparse


def render_social_metadata(
    *,
    title: str,
    description: str,
    canonical: str,
    site_name: str,
    page_type: str,
    image_url: str = "",
    image_path: Path | None = None,
) -> str:
    valid_image = image_url if image_url and _valid_image(image_url, image_path) else ""
    card = "summary_large_image" if valid_image else "summary"
    tags = [
        f'<meta property="og:title" content="{html.escape(title, quote=True)}">',
        f'<meta property="og:description" content="{html.escape(description, quote=True)}">',
        f'<meta property="og:type" content="{html.escape(page_type, quote=True)}">',
        f'<meta property="og:url" content="{html.escape(canonical, quote=True)}">',
        f'<meta property="og:site_name" content="{html.escape(site_name, quote=True)}">',
        f'<meta name="twitter:card" content="{card}">',
        f'<meta name="twitter:title" content="{html.escape(title, quote=True)}">',
        f'<meta name="twitter:description" content="{html.escape(description, quote=True)}">',
    ]
    if valid_image:
        escaped = html.escape(valid_image, quote=True)
        tags.insert(5, f'<meta property="og:image" content="{escaped}">')
        tags.append(f'<meta name="twitter:image" content="{escaped}">')
    return "".join(tags)


def homepage_structured_data(
    *,
    site_name: str,
    canonical: str,
    contact_email: str = "",
) -> list[dict]:
    organization = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": site_name,
        "url": canonical,
    }
    if contact_email:
        organization["email"] = contact_email
    website = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site_name,
        "url": canonical,
    }
    return [organization, website]


def article_structured_data(
    *,
    title: str,
    description: str,
    canonical: str,
    site_name: str,
    author_name: str,
    author_url: str = "",
) -> list[dict]:
    base = _site_root(canonical)
    author = {"@type": "Person", "name": author_name}
    if author_url:
        author["url"] = author_url
    return [
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "description": description,
            "url": canonical,
            "mainEntityOfPage": canonical,
            "author": author,
            "publisher": {"@type": "Organization", "name": site_name, "url": base},
        },
        breadcrumb_structured_data(title=title, canonical=canonical),
    ]


def standard_page_structured_data(*, title: str, canonical: str) -> list[dict]:
    return [breadcrumb_structured_data(title=title, canonical=canonical)]


def breadcrumb_structured_data(*, title: str, canonical: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": _site_root(canonical),
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": title,
                "item": canonical,
            },
        ],
    }


def faq_structured_data(items: list[tuple[str, str]]) -> dict | None:
    entities = [
        {
            "@type": "Question",
            "name": question.strip(),
            "acceptedAnswer": {"@type": "Answer", "text": answer.strip()},
        }
        for question, answer in items
        if question.strip() and answer.strip()
    ]
    if not entities:
        return None
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": entities,
    }


def render_json_ld(items: list[dict]) -> str:
    return "".join(
        f'<script type="application/ld+json">{json.dumps(item, ensure_ascii=False)}</script>'
        for item in items
    )


def _valid_image(image_url: str, image_path: Path | None) -> bool:
    parsed = urlparse(image_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return image_path is None or image_path.is_file()


def _site_root(canonical: str) -> str:
    parsed = urlparse(canonical)
    return f"{parsed.scheme}://{parsed.netloc}/"
