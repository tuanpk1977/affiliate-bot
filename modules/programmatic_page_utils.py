from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

import pandas as pd

from config import settings
from modules.tracking_config import analytics_snippet


BASE = (settings.base_site_url or settings.site_domain or "https://review.mssmileenglish.com").rstrip("/")
IMPACT_SITE_VERIFICATION_ID = "e41dba46-8780-4a26-8314-596af1e3980b"


def slugify(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "page"


def offer_map(offer_scores: pd.DataFrame | None) -> dict[str, dict]:
    if offer_scores is None or offer_scores.empty:
        return {}
    result = {}
    for _, row in offer_scores.iterrows():
        brand = str(row.get("brand_name", "")).strip()
        if brand:
            result[slugify(brand)] = row.to_dict()
    return result


def review_url(tool: str) -> str:
    return f"/{slugify(tool)}/"


def official_url(tool: str, offers: dict[str, dict]) -> str:
    data = offers.get(slugify(tool), {})
    return str(data.get("website") or "#")


def affiliate_disclosure() -> str:
    return "<section class='card trust'><h2>Affiliate disclosure</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you. Reviews and comparisons are research-style content, not guaranteed results.</p></section>"


def faq_schema(questions: list[str]) -> str:
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Use this page as a research starting point. Verify pricing, product limits, refund or cancellation terms, integrations, and official vendor policies before buying or promoting the tool.",
                },
            }
            for question in questions
        ],
    }
    return json.dumps(schema, ensure_ascii=False)


def breadcrumb_schema(title: str, path: str) -> str:
    schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": title, "item": f"{BASE}{path}"},
        ],
    }
    return json.dumps(schema, ensure_ascii=False)


def item_list_schema(title: str, items: list[str], path: str) -> str:
    schema = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": title,
        "url": f"{BASE}{path}",
        "itemListElement": [
            {"@type": "ListItem", "position": idx + 1, "name": item, "url": f"{BASE}{review_url(item)}"}
            for idx, item in enumerate(items)
        ],
    }
    return json.dumps(schema, ensure_ascii=False)


def shell(title: str, description: str, path: str, body: str, extra_schema: list[str] | None = None) -> str:
    schema = "\n".join(f'<script type="application/ld+json">{item}</script>' for item in (extra_schema or []))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - {html.escape(settings.site_name)}</title>
  <meta name="description" content="{html.escape(description)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{html.escape(BASE + path, quote=True)}">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:type" content="article">
  <meta property="og:image" content="{html.escape(BASE + '/assets/og/site.svg', quote=True)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{html.escape(BASE + '/assets/og/site.svg', quote=True)}">
  <meta name="google-site-verification" content="{html.escape(settings.google_site_verification, quote=True)}" />
  {impact_site_verification_meta()}
  {analytics_snippet()}
  {schema}
  <style>{css()}</style>
</head>
<body>
  {nav()}
  <main class="wrap">{body}</main>
  {footer()}
</body>
</html>
"""


def impact_site_verification_meta() -> str:
    return f'<meta name="impact-site-verification" value="{html.escape(IMPACT_SITE_VERIFICATION_ID, quote=True)}">'


def impact_site_verification_text() -> str:
    text = f"Impact-Site-Verification: {IMPACT_SITE_VERIFICATION_ID}"
    return (
        "<p class='impact-site-verification-text' "
        "style='position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden;'>"
        f"{html.escape(text)}</p>"
    )


def nav() -> str:
    return f"<nav class='nav'><div class='wrap nav-inner'><a class='logo' href='/'>{html.escape(settings.site_name)}</a><div class='menu'><a href='/'>Home</a><a href='/reviews/'>Reviews</a><a href='/comparisons/'>Comparisons</a><a href='/pricing/'>Pricing</a><a href='/categories/'>Categories</a><a href='/hubs/'>Hubs</a><a href='/blog/'>Blog</a><a href='/contact/'>Contact</a></div><div class='language-switcher' aria-label='Language switcher'><a class='active' href='/'>English</a><span>|</span><a href='/vi/'>Tiếng Việt</a></div></div><div class='wrap'><p class='note'>Some links may be affiliate links. We may earn a commission at no extra cost to you.</p></div></nav>"


def footer() -> str:
    contact = settings.contact_email or "tuanpk1977@gmail.com"
    return f"<footer><div class='wrap'><p><strong>{html.escape(settings.site_name)}</strong></p><p>Contact: <a href='mailto:{html.escape(contact)}'>{html.escape(contact)}</a></p><a href='/privacy/'>Privacy Policy</a><a href='/terms/'>Terms</a><a href='/editorial-policy/'>Editorial Policy</a><a href='/affiliate-disclosure/'>Affiliate Disclosure</a><a href='/about/'>About</a><a href='/contact/'>Contact</a><p>&copy; 2026 {html.escape(settings.site_name)}.</p><p>Some links may be affiliate links. We may earn a commission at no extra cost to you.</p>{impact_site_verification_text()}</div></footer>"


def css() -> str:
    return """:root{--bg:#f7f9fc;--text:#17202a;--muted:#596579;--line:#dbe3ef;--card:#fff;--accent:#0f766e;--warn:#9a3412}*{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text);line-height:1.65}.wrap{max-width:1120px;margin:0 auto;padding:0 20px}.nav{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}.nav-inner{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:18px}.logo{font-weight:800;color:#0f172a;text-decoration:none}.menu{display:flex;gap:18px;flex-wrap:wrap}.menu a{color:#475569;text-decoration:none;font-size:14px}.language-switcher{display:flex;gap:8px;align-items:center;border:1px solid #dbe3ef;border-radius:999px;padding:4px 8px;background:#f8fafc;font-size:13px;white-space:nowrap}.language-switcher span{font-weight:800;color:#0f766e}.language-switcher a{color:#475569;text-decoration:none}.hero{padding:46px 0 18px}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:18px;margin:16px 0;box-shadow:0 1px 2px rgba(15,23,42,.04)}h1{font-size:42px;line-height:1.1;margin:10px 0}h2{font-size:25px;margin:0 0 12px}h3{font-size:18px;margin:0 0 8px}p,li{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}.btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:11px 15px;border-radius:6px;font-weight:800;margin:5px 8px 5px 0}.btn.secondary{background:#e2e8f0;color:#0f172a}.trust{border-left:4px solid var(--warn);background:#fff7ed}.note{font-size:14px;color:#7c2d12}table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line)}th,td{text-align:left;border-bottom:1px solid #e6edf5;padding:12px;vertical-align:top}th{background:#f1f5f9;color:#334155}details{border-top:1px solid #e6edf5;padding:12px 0}summary{cursor:pointer;font-weight:800;color:#334155}footer{margin-top:36px;background:#0f172a;color:#cbd5e1;padding:28px 0}footer a{color:#e2e8f0;text-decoration:none;margin-right:14px}footer p{color:#cbd5e1}@media(max-width:760px){h1{font-size:32px}.nav-inner{align-items:flex-start;flex-direction:column;padding:14px 0}.language-switcher{margin-top:6px}}"""


def write_page(output: Path, path: str, html_text: str) -> Path:
    folder = output / path.strip("/")
    folder.mkdir(parents=True, exist_ok=True)
    page = folder / "index.html"
    page.write_text(html_text, encoding="utf-8")
    return page


def faq_html(questions: list[str]) -> str:
    return "".join(f"<details><summary>{html.escape(question)}</summary><p>Pricing, plans, integrations and terms can change. Verify details on the official vendor website before buying or promoting this tool.</p></details>" for question in questions)


def today() -> str:
    return date.today().isoformat()
