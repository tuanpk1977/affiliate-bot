from __future__ import annotations

import csv
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from modules.ai_trend_discovery import (
    TrendDiscoveryEngine,
    classify_content_type,
    classify_search_intent,
    save_discovery_result,
    slugify,
)
from modules.indexing_policy import INDEXABLE_ROBOTS_META


BASE_URL = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
ROOT = settings.base_dir
DATA_DIR = settings.data_dir
SITE_OUTPUT = settings.site_output_dir
PUBLISHED_DIR = DATA_DIR / "published_static_pages"
VIDEO_OUTPUT = ROOT / "video_output"
SOCIAL_DRAFTS = ROOT / "social_drafts"
REPORT_DIR = DATA_DIR / "content_growth_reports"
TRACKING_CSV = DATA_DIR / "content_growth_performance_log.csv"
TRENDING_JSON = DATA_DIR / "trending_topics.json"


@dataclass(frozen=True)
class GeneratedPage:
    topic: str
    slug: str
    url: str
    article_file: Path
    video_folder: Path
    social_folder: Path
    content_type: str
    focus_keyword: str
    warnings: list[str]


def run_daily_content_growth(
    limit: int = 10,
    discover: bool = False,
    build: bool = True,
    submit_indexnow_enabled: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create website articles and manual-publishing assets from trend data.

    This intentionally publishes only to the website output. YouTube and social
    assets are draft files for manual use.
    """

    assert_external_publishing_disabled()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_OUTPUT.mkdir(parents=True, exist_ok=True)
    SOCIAL_DRAFTS.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    topics = load_or_discover_topics(limit=max(limit * 3, 20), discover=discover)
    selected = select_daily_topics(topics, limit=limit)
    generated: list[GeneratedPage] = []
    warnings: list[str] = []

    for topic in selected:
        if dry_run:
            continue
        page = generate_topic_package(topic)
        generated.append(page)
        warnings.extend(page.warnings)
        append_tracking_row(page)

    build_result: dict[str, Any] = {"skipped": not build or dry_run}
    if build and not dry_run and generated:
        build_result = run_build_and_sync()

    indexnow_result: dict[str, Any] = {"skipped": not submit_indexnow_enabled or dry_run or not generated}
    if submit_indexnow_enabled and not dry_run and generated:
        indexnow_result = submit_generated_urls([page.url for page in generated])

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limit": limit,
        "dry_run": dry_run,
        "selected_topics": selected,
        "generated_pages": [page_to_dict(page) for page in generated],
        "build": build_result,
        "indexnow": indexnow_result,
        "warnings": warnings,
        "manual_posting_order": manual_posting_order(generated),
        "next_actions": [
            "Review each generated article for product facts marked needs manual verification.",
            "Upload review_video.mp4 manually only if you render a final video file later.",
            "Copy social draft files manually to social platforms.",
            "Paste YouTube URLs into video_output/upload_links.csv after upload, then run python scripts/update_youtube_links.py.",
        ],
        "safety": {
            "auto_website_publish": True,
            "auto_youtube_upload": False,
            "auto_social_post": False,
        },
    }
    write_daily_report(report)
    return report


def assert_external_publishing_disabled() -> None:
    if truthy(os.getenv("AUTO_YOUTUBE_UPLOAD")):
        raise RuntimeError("AUTO_YOUTUBE_UPLOAD must remain false for this workflow.")
    if truthy(os.getenv("AUTO_SOCIAL_POST")):
        raise RuntimeError("AUTO_SOCIAL_POST must remain false for this workflow.")


def load_or_discover_topics(limit: int, discover: bool) -> list[dict[str, Any]]:
    if discover or not TRENDING_JSON.exists():
        result = TrendDiscoveryEngine().run(limit=limit)
        save_discovery_result(result)
    payload = json.loads(TRENDING_JSON.read_text(encoding="utf-8"))
    selected = payload.get("selected_topics", payload if isinstance(payload, list) else [])
    return [normalize_topic_record(row) for row in selected if isinstance(row, dict)]


def normalize_topic_record(row: dict[str, Any]) -> dict[str, Any]:
    topic = str(row.get("topic") or row.get("title") or "").strip()
    content_type = str(row.get("content_type") or classify_content_type(topic))
    total_score = float(row.get("total_score") or row.get("score") or 0)
    affiliate_score = int(row.get("affiliate_opportunity") or 0)
    cpc_score = int(row.get("cpc_potential") or 0)
    evergreen_score = int(row.get("evergreen_value") or 0)
    return {
        **row,
        "topic": topic,
        "slug": str(row.get("slug") or slugify(topic)),
        "content_type": content_type,
        "search_intent": str(row.get("search_intent") or classify_search_intent(topic)),
        "recommended_priority": str(row.get("recommended_priority") or priority_from_score(total_score)),
        "estimated_business_value": str(row.get("estimated_business_value") or business_value(affiliate_score, cpc_score, evergreen_score)),
        "suggested_article_angle": str(row.get("suggested_article_angle") or default_article_angle(topic, content_type)),
        "suggested_video_angle": str(row.get("suggested_video_angle") or default_video_angle(topic, content_type)),
        "suggested_internal_links": list(row.get("suggested_internal_links") or default_internal_links(topic, content_type)),
        "total_score": total_score,
    }


def select_daily_topics(topics: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    published = existing_slugs()
    selected: list[dict[str, Any]] = []
    content_counts: dict[str, int] = {}
    for topic in sorted(topics, key=lambda row: (-float(row.get("total_score", 0)), str(row.get("topic", "")))):
        slug = str(topic.get("slug", ""))
        if not slug or slug in published:
            continue
        if any(is_near_duplicate(slug, str(existing.get("slug", ""))) for existing in selected):
            continue
        content_type = str(topic.get("content_type") or "article")
        if content_counts.get(content_type, 0) >= 3 and len(selected) < max(4, limit // 2):
            continue
        selected.append(topic)
        content_counts[content_type] = content_counts.get(content_type, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def existing_slugs() -> set[str]:
    slugs: set[str] = set()
    for root in (PUBLISHED_DIR, SITE_OUTPUT, ROOT / "docs", ROOT / "content" / "posts", ROOT / "public" / "posts", VIDEO_OUTPUT):
        if not root.exists():
            continue
        for child in root.iterdir():
            if child.is_dir():
                slugs.add(child.name)
    return slugs


def generate_topic_package(topic: dict[str, Any]) -> GeneratedPage:
    topic_name = str(topic["topic"])
    slug = str(topic["slug"])
    path = f"/{slug}/"
    url = BASE_URL + path
    title = seo_title(topic_name)
    description = meta_description(topic_name)
    links = resolve_internal_links(topic)
    warnings = fact_warnings(topic_name)

    article_html = render_article(topic, title, description, path, links, warnings)
    article_file = write_article(path, article_html)
    write_article(path, article_html, output=SITE_OUTPUT)
    video_folder = write_video_drafts(topic, url, title)
    social_folder = write_social_drafts(topic, url, title)
    return GeneratedPage(
        topic=topic_name,
        slug=slug,
        url=url,
        article_file=article_file,
        video_folder=video_folder,
        social_folder=social_folder,
        content_type=str(topic.get("content_type") or "article"),
        focus_keyword=focus_keyword(topic_name),
        warnings=warnings,
    )


def render_article(
    topic: dict[str, Any],
    title: str,
    description: str,
    path: str,
    links: list[tuple[str, str]],
    warnings: list[str],
) -> str:
    topic_name = str(topic["topic"])
    content_type = str(topic.get("content_type") or "article")
    intent = str(topic.get("search_intent") or "commercial investigation")
    article_angle = str(topic.get("suggested_article_angle") or default_article_angle(topic_name, content_type))
    video_angle = str(topic.get("suggested_video_angle") or default_video_angle(topic_name, content_type))
    canonical = BASE_URL + path
    faq_items = faq_questions(topic_name)
    schemas = [
        article_schema(title, description, canonical, topic_name),
        faq_schema(faq_items),
        breadcrumb_schema(title, canonical),
    ]
    body = f"""
  <main class="wrap">
    <section class="hero">
      <p class="eyebrow">{html.escape(content_type.title())} · Updated June 2026</p>
      <h1>{html.escape(title)}</h1>
      <p class="lede">{html.escape(description)}</p>
      <div class="cta-row">
        <a class="btn" href="#pricing">Check pricing notes</a>
        <a class="btn secondary" href="#alternatives">Compare alternatives</a>
      </div>
    </section>
    <section class="card trust">
      <h2>Affiliate disclosure</h2>
      <p>Some links may be affiliate links. We may earn a commission at no extra cost to you. This article is independent research and does not claim an official partnership.</p>
    </section>
    <section class="card">
      <h2>Table of contents</h2>
      <ol class="toc">
        <li><a href="#overview">Overview</a></li>
        <li><a href="#quick-verdict">Quick verdict</a></li>
        <li><a href="#comparison-table">Comparison table</a></li>
        <li><a href="#pros-cons">Pros and cons</a></li>
        <li><a href="#pricing">Pricing notes</a></li>
        <li><a href="#best-for">Best use cases</a></li>
        <li><a href="#alternatives">Alternatives</a></li>
        <li><a href="#faq">FAQ</a></li>
      </ol>
    </section>
    <section class="card" id="overview">
      <h2>Overview</h2>
      <p>{html.escape(article_angle)} The goal is to help buyers understand where this topic fits, what to verify, and how it compares with related software before spending money.</p>
      <p>Search intent: {html.escape(intent)}. This page is written for practical evaluation: workflow fit, pricing risk, feature tradeoffs, support expectations, and alternatives. Any product-specific pricing or plan limit should be treated as <strong>needs manual verification</strong> on the official vendor website.</p>
      <p>Video angle: {html.escape(video_angle)} The matching YouTube assets are saved as manual upload drafts in the video folder for this page.</p>
    </section>
    <section class="card" id="quick-verdict">
      <h2>Quick verdict</h2>
      <p>{html.escape(topic_name)} is worth covering because the topic combines current search interest with buyer intent. It should be useful for readers comparing tools, checking pricing, or deciding whether a software category belongs in their workflow.</p>
      <ul>
        <li><strong>Best for:</strong> teams that need a clear shortlist before testing software.</li>
        <li><strong>Not best for:</strong> buyers expecting guaranteed pricing, official endorsement, or one-size-fits-all advice.</li>
        <li><strong>Verification required:</strong> pricing, free-trial terms, refund rules, usage limits, integrations, and affiliate terms.</li>
      </ul>
    </section>
    <section class="card" id="comparison-table">
      <h2>Comparison table</h2>
      <div class="table-scroll">
        <table>
          <thead><tr><th>Evaluation area</th><th>What to check</th><th>Why it matters</th></tr></thead>
          <tbody>
            <tr><td>Core features</td><td>Primary workflow, integrations, export options, team roles</td><td>Prevents buying a tool that looks strong but misses daily workflow needs.</td></tr>
            <tr><td>Pricing</td><td>Plan limits, seat pricing, usage caps, renewal terms</td><td>Software costs often change when a team scales usage.</td></tr>
            <tr><td>Alternatives</td><td>Direct competitors and cheaper substitutes</td><td>Helps readers avoid overpaying for features they will not use.</td></tr>
            <tr><td>Commercial fit</td><td>Affiliate terms, brand safety, buyer intent</td><td>Important for creators and marketers evaluating monetization potential.</td></tr>
          </tbody>
        </table>
      </div>
    </section>
    <section class="card" id="pros-cons">
      <h2>Pros and cons</h2>
      <div class="grid">
        <div>
          <h3>Pros</h3>
          <ul>
            <li>Useful for buyers already researching a real software decision.</li>
            <li>Can support comparison, pricing, review, and alternative search intent.</li>
            <li>Works well with internal links to related review and comparison pages.</li>
          </ul>
        </div>
        <div>
          <h3>Cons</h3>
          <ul>
            <li>Pricing and feature claims require manual verification.</li>
            <li>Competitive topics may need stronger examples and screenshots over time.</li>
            <li>Some vendor claims may be marketing language rather than proven outcomes.</li>
          </ul>
        </div>
      </div>
    </section>
    <section class="card" id="pricing">
      <h2>Pricing notes</h2>
      <p>Do not rely on copied pricing snippets. Pricing can change by region, billing period, usage tier, seat count, and promotion. Verify current pricing on the official website before buying or recommending any tool related to {html.escape(topic_name)}.</p>
      <p>When comparing costs, check total monthly cost, annual discounts, free-trial restrictions, cancellation terms, and whether essential features sit behind higher-tier plans.</p>
    </section>
    <section class="card" id="best-for">
      <h2>Best use cases</h2>
      <ul>
        <li>Shortlisting software before a hands-on trial.</li>
        <li>Comparing multiple tools in the same category.</li>
        <li>Checking whether a topic has enough buyer intent for affiliate content.</li>
        <li>Planning YouTube reviews, shorts, and manual social posts around one canonical article.</li>
      </ul>
    </section>
    <section class="card" id="alternatives">
      <h2>Alternatives and related reading</h2>
      <p>Use these related pages to compare adjacent software categories and avoid evaluating this topic in isolation.</p>
      <ul>{''.join(f'<li><a href="{html.escape(href)}">{html.escape(label)}</a></li>' for href, label in links)}</ul>
    </section>
    <section class="card">
      <h2>Research methodology</h2>
      <p>This page uses trend discovery signals, commercial-intent scoring, competition estimates, and existing Smile AI Review Hub topic coverage. It favors useful comparison-focused content over thin news summaries.</p>
      <p>Warnings: {html.escape('; '.join(warnings) if warnings else 'No critical warnings. Verify vendor facts before final promotion.')}</p>
    </section>
    <section class="card" id="faq">
      <h2>FAQ</h2>
      {faq_html(faq_items)}
    </section>
    <section class="card">
      <h2>Final verdict</h2>
      <p>{html.escape(topic_name)} is a good candidate for Smile AI Review Hub because it can serve readers who want practical, buyer-focused guidance. The strongest next step is to add verified screenshots, current pricing checks, and YouTube links after manual upload.</p>
      <a class="btn" href="/">Visit Smile AI Review Hub</a>
    </section>
  </main>
"""
    return html_shell(title, description, canonical, body, schemas)


def html_shell(title: str, description: str, canonical: str, body: str, schemas: list[dict[str, Any]]) -> str:
    schema_tags = "\n".join(
        f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>' for schema in schemas
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <meta name="robots" content="{INDEXABLE_ROBOTS_META}">
  <link rel="canonical" href="{html.escape(canonical, quote=True)}">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{html.escape(canonical, quote=True)}">
  <meta property="og:image" content="{html.escape(BASE_URL + '/assets/og/site.svg', quote=True)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{html.escape(title)}">
  <meta name="twitter:description" content="{html.escape(description)}">
  <meta name="twitter:image" content="{html.escape(BASE_URL + '/assets/og/site.svg', quote=True)}">
  {schema_tags}
  <style>{page_css()}</style>
</head>
<body>
  <nav class="nav"><div class="wrap nav-inner"><a class="logo" href="/">MS Smile AI Review Hub</a><div><a href="/reviews/">Reviews</a><a href="/comparisons/">Comparisons</a><a href="/contact/">Contact</a></div></div></nav>
  {body}
  <footer><div class="wrap"><p><strong>MS Smile AI Review Hub</strong></p><p>Contact: <a href="mailto:contact@smileaireviewhub.com">contact@smileaireviewhub.com</a></p><p><a href="/affiliate-disclosure/">Affiliate Disclosure</a> <a href="/privacy/">Privacy Policy</a> <a href="/about/">About</a></p></div></footer>
</body>
</html>
"""


def page_css() -> str:
    return """:root{--bg:#f7f9fc;--text:#17202a;--muted:#596579;--line:#dbe3ef;--card:#fff;--accent:#0f766e;--warn:#9a3412}*{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text);line-height:1.7}.wrap{max-width:1120px;margin:0 auto;padding:0 20px}.nav{background:#fff;border-bottom:1px solid var(--line)}.nav-inner{min-height:64px;display:flex;justify-content:space-between;align-items:center;gap:16px}.nav a{color:#0f172a;font-weight:700;text-decoration:none;margin-right:16px}.logo{font-size:20px}.hero{padding:54px 0 22px}.eyebrow{font-weight:800;color:#0f766e;text-transform:uppercase;letter-spacing:.02em}.lede{font-size:19px;max-width:920px}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:22px;margin:18px 0;box-shadow:0 1px 2px rgba(15,23,42,.04)}.trust{border-left:4px solid var(--warn)}h1{font-size:44px;line-height:1.08;margin:12px 0;color:#111827}h2{font-size:27px;margin:0 0 12px;color:#111827}h3{font-size:19px;margin:0 0 8px}p,li{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}.btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:11px 15px;border-radius:6px;font-weight:800;margin:5px 8px 5px 0}.btn.secondary{background:#e2e8f0;color:#0f172a}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #e6edf5;padding:12px;vertical-align:top}th{background:#f1f5f9;color:#334155}.toc a{color:#0f766e;text-decoration:none}details{border-top:1px solid #e6edf5;padding:12px 0}summary{cursor:pointer;font-weight:800;color:#334155}footer{margin-top:36px;background:#0f172a;color:#cbd5e1;padding:28px 0}footer p,footer a{color:#cbd5e1}@media(max-width:760px){h1{font-size:32px}.nav-inner{align-items:flex-start;flex-direction:column;padding:14px 0}}"""


def write_article(path: str, text: str, output: Path = PUBLISHED_DIR) -> Path:
    folder = output / path.strip("/")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "index.html"
    target.write_text(text, encoding="utf-8")
    return target


def write_video_drafts(topic: dict[str, Any], url: str, title: str) -> Path:
    slug = str(topic["slug"])
    folder = VIDEO_OUTPUT / slug
    folder.mkdir(parents=True, exist_ok=True)
    script = video_script(topic, url, title)
    files = {
        "youtube_title.txt": f"{title} | Smile AI Review Hub",
        "youtube_description.txt": youtube_description(topic, url),
        "youtube_tags.txt": ", ".join(video_tags(topic)),
        "pinned_comment.txt": f"Read the full guide: {url}\nWhich tool should we compare next?",
        "shorts_script.txt": shorts_script(topic, url),
        "video_script.txt": script,
        "transcript.txt": script,
        "thumbnail_text.txt": thumbnail_text(topic),
        "scenes.json": json.dumps(video_scenes(topic), indent=2, ensure_ascii=False),
        "metadata.json": json.dumps(video_metadata(topic, url, title), indent=2, ensure_ascii=False),
    }
    for name, content in files.items():
        (folder / name).write_text(content, encoding="utf-8")
    return folder


def write_social_drafts(topic: dict[str, Any], url: str, title: str) -> Path:
    folder = SOCIAL_DRAFTS / date.today().isoformat() / str(topic["slug"])
    folder.mkdir(parents=True, exist_ok=True)
    platforms = {
        "facebook.md": facebook_draft(title, url),
        "linkedin.md": linkedin_draft(title, url),
        "quora.md": quora_draft(title, url),
        "reddit.md": reddit_draft(title, url),
        "x-twitter.md": x_draft(title, url),
        "threads.md": threads_draft(title, url),
        "medium.md": medium_draft(title, url),
        "pinterest.md": pinterest_draft(title, url),
    }
    for name, content in platforms.items():
        (folder / name).write_text(content, encoding="utf-8")
    return folder


def run_build_and_sync() -> dict[str, Any]:
    result: dict[str, Any] = {}
    build = subprocess.run([sys.executable, "build_site.py"], cwd=ROOT, text=True, capture_output=True)
    result["build_returncode"] = build.returncode
    result["build_stdout_tail"] = build.stdout[-2000:]
    result["build_stderr_tail"] = build.stderr[-2000:]
    if build.returncode != 0:
        return result
    sync = subprocess.run([sys.executable, "scripts/sync_site_output_to_docs.py"], cwd=ROOT, text=True, capture_output=True)
    result["sync_returncode"] = sync.returncode
    result["sync_stdout_tail"] = sync.stdout[-1000:]
    result["sync_stderr_tail"] = sync.stderr[-1000:]
    return result


def submit_generated_urls(urls: list[str]) -> dict[str, Any]:
    try:
        from scripts.submit_indexnow import submit_indexnow

        result = submit_indexnow(urls, max_urls=len(urls))
        return {"submitted": len(urls), "result": result}
    except Exception as exc:
        return {"warning": f"IndexNow submission failed without stopping workflow: {type(exc).__name__}: {exc}"}


def write_daily_report(report: dict[str, Any]) -> None:
    stamp = date.today().isoformat()
    json_path = REPORT_DIR / f"{stamp}.json"
    md_path = REPORT_DIR / f"{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [
        f"# Daily AI Content Growth Report - {stamp}",
        "",
        "## Generated URLs",
    ]
    for page in report["generated_pages"]:
        lines.append(f"- {page['topic']}: {page['url']}")
    lines.extend(["", "## Manual Posting Order"])
    for item in report["manual_posting_order"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in report["warnings"]] or ["- None"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_tracking_row(page: GeneratedPage) -> None:
    TRACKING_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "publish_date",
        "url",
        "topic",
        "article_type",
        "source_keyword",
        "google_indexed_status",
        "bing_discovered_status",
        "bing_indexed_status",
        "yandex_index_status",
        "impressions",
        "clicks",
        "ctr",
        "average_position",
        "social_views",
        "youtube_views",
        "affiliate_clicks",
        "revenue",
        "notes",
    ]
    exists = TRACKING_CSV.exists()
    with TRACKING_CSV.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "publish_date": date.today().isoformat(),
                "url": page.url,
                "topic": page.topic,
                "article_type": page.content_type,
                "source_keyword": page.focus_keyword,
                "google_indexed_status": "pending",
                "bing_discovered_status": "pending",
                "bing_indexed_status": "pending",
                "yandex_index_status": "pending",
                "impressions": 0,
                "clicks": 0,
                "ctr": 0,
                "average_position": "",
                "social_views": 0,
                "youtube_views": 0,
                "affiliate_clicks": 0,
                "revenue": 0,
                "notes": "Generated by daily content growth pipeline; external posting is manual.",
            }
        )


def resolve_internal_links(topic: dict[str, Any]) -> list[tuple[str, str]]:
    suggestions = [str(item) for item in topic.get("suggested_internal_links", [])]
    defaults = ["/reviews/", "/comparisons/", "/categories/", "/best-website-builder-2026/", "/review/surfer-seo/"]
    candidates = suggestions + defaults
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href in candidates:
        clean = "/" + href.strip("/")
        if clean == "/":
            clean = "/"
        else:
            clean += "/"
        if clean in seen:
            continue
        target = SITE_OUTPUT / clean.strip("/") / "index.html" if clean != "/" else SITE_OUTPUT / "index.html"
        if target.exists() or len(result) < 5:
            result.append((clean, label_from_path(clean)))
            seen.add(clean)
        if len(result) >= 8:
            break
    return result


def article_schema(title: str, description: str, url: str, topic: str) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "url": url,
        "datePublished": date.today().isoformat(),
        "dateModified": date.today().isoformat(),
        "author": {"@type": "Person", "name": "Nguyen Quoc Tuan"},
        "publisher": {"@type": "Organization", "name": "MS Smile AI Review Hub", "url": BASE_URL},
        "about": topic,
    }


def faq_schema(items: list[str]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Use this article as a research starting point and verify pricing, terms, integrations, and limits on the official website before buying.",
                },
            }
            for item in items
        ],
    }


def breadcrumb_schema(title: str, url: str) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": title, "item": url},
        ],
    }


def faq_html(items: list[str]) -> str:
    return "".join(
        f"<details><summary>{html.escape(item)}</summary><p>Verify current pricing, terms, limits, integrations, and official policies before buying or promoting this tool.</p></details>"
        for item in items
    )


def video_script(topic: dict[str, Any], url: str, title: str) -> str:
    topic_name = str(topic["topic"])
    return (
        f"Intro: In this Smile AI Review Hub video, we look at {topic_name}.\n\n"
        "Section one: what the topic means for buyers and creators.\n"
        "Section two: key features or comparison points to verify.\n"
        "Section three: pricing checks. Always verify current pricing on the official website.\n"
        "Section four: pros, cons, and alternatives.\n"
        f"Verdict: {title} is worth reviewing if it matches your workflow and budget.\n\n"
        f"Read the full guide on Smile AI Review Hub: {url}\n"
    )


def shorts_script(topic: dict[str, Any], url: str) -> str:
    return (
        f"Hook: Should you care about {topic['topic']} in 2026?\n"
        "Point one: check workflow fit before pricing.\n"
        "Point two: compare alternatives before buying.\n"
        "Point three: verify current terms on the official site.\n"
        f"CTA: Read the full guide at {url}\n"
    )


def youtube_description(topic: dict[str, Any], url: str) -> str:
    return (
        f"In this video, Smile AI Review Hub covers {topic['topic']} with buyer-focused notes on features, pricing checks, alternatives, and practical fit.\n\n"
        f"Read the full article:\n{url}\n\n"
        "Website:\nhttps://smileaireviewhub.com\n\n"
        "Note: pricing and product details can change. Verify current details on the official website."
    )


def video_tags(topic: dict[str, Any]) -> list[str]:
    words = [word for word in re.split(r"[^a-zA-Z0-9]+", str(topic["topic"]).lower()) if len(word) > 2]
    return list(dict.fromkeys(words + ["ai tools", "saas", "software review", "smile ai review hub"]))[:15]


def video_scenes(topic: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"section": "Hook", "visual": "Title card with software category", "voiceover": f"Why {topic['topic']} matters in 2026."},
        {"section": "Overview", "visual": "Article-style dashboard slide", "voiceover": "Explain the buyer problem and workflow context."},
        {"section": "Pricing", "visual": "Pricing checklist slide", "voiceover": "Verify current pricing and plan limits."},
        {"section": "Pros and Cons", "visual": "Two-column pros and cons slide", "voiceover": "Summarize strengths and risks."},
        {"section": "Verdict", "visual": "CTA slide with website", "voiceover": "Read the full guide on Smile AI Review Hub."},
    ]


def video_metadata(topic: dict[str, Any], url: str, title: str) -> dict[str, Any]:
    return {
        "title": f"{title} | Smile AI Review Hub",
        "description": youtube_description(topic, url),
        "tags": video_tags(topic),
        "article_url": url,
        "manual_upload_only": True,
        "auto_youtube_upload": False,
    }


def page_to_dict(page: GeneratedPage) -> dict[str, Any]:
    return {
        "topic": page.topic,
        "slug": page.slug,
        "url": page.url,
        "article_file": str(page.article_file),
        "video_folder": str(page.video_folder),
        "social_folder": str(page.social_folder),
        "content_type": page.content_type,
        "focus_keyword": page.focus_keyword,
        "warnings": page.warnings,
    }


def manual_posting_order(pages: list[GeneratedPage]) -> list[str]:
    order: list[str] = []
    for page in pages:
        order.append(f"{page.topic}: publish article first, upload YouTube manually, then post LinkedIn/Facebook/X drafts.")
    return order


def seo_title(topic: str) -> str:
    base = topic.strip()
    if "2026" not in base:
        base = f"{base} 2026"
    suffix = ": Pricing, Pros, Cons"
    title = base if len(base) <= 56 else base[:56].rstrip()
    if len(title + suffix) <= 60:
        return title + suffix
    return title


def meta_description(topic: str) -> str:
    text = f"Independent {topic} guide with pricing checks, pros, cons, alternatives, FAQs, and buyer-focused workflow advice."
    return text[:154].rstrip(". ,") + "."


def focus_keyword(topic: str) -> str:
    return re.sub(r"\s+", " ", topic.lower().replace("2026", "")).strip()


def faq_questions(topic: str) -> list[str]:
    return [
        f"What is {topic} best for?",
        f"How should I verify {topic} pricing?",
        f"What are the main alternatives to {topic}?",
        f"Is {topic} suitable for small teams?",
        f"What should I check before buying {topic}?",
        f"Can creators use {topic} for affiliate content?",
    ]


def fact_warnings(topic: str) -> list[str]:
    return [
        f"{topic}: pricing, trial terms, plan limits, and affiliate terms need manual verification before promotion.",
    ]


def thumbnail_text(topic: dict[str, Any]) -> str:
    words = str(topic["topic"]).replace("Review 2026", "").replace("2026", "").strip()
    return f"{words}\nWorth It?"


def facebook_draft(title: str, url: str) -> str:
    return f"{title}\n\nI published a buyer-focused breakdown with pricing checks, pros, cons, and alternatives.\n\nRead it here: {url}\n\n#AITools #SaaS #SoftwareReview\n"


def linkedin_draft(title: str, url: str) -> str:
    return f"New research note: {title}\n\nThe article focuses on workflow fit, pricing verification, alternatives, and buyer risk rather than vendor claims.\n\nFull guide: {url}\n"


def quora_draft(title: str, url: str) -> str:
    return f"Question angle: Is {title} worth considering?\n\nShort answer: it depends on workflow fit, pricing limits, and alternatives. I wrote a full research-style guide here: {url}\n"


def reddit_draft(title: str, url: str) -> str:
    return f"Manual draft only. Suggested post title: {title}\n\nI compared the practical buyer checks: pricing, pros, cons, alternatives, and when the topic is not a fit.\n\nLink: {url}\n"


def x_draft(title: str, url: str) -> str:
    return f"{title}\n\nPricing checks, pros/cons, alternatives, and buyer-fit notes.\n\n{url}\n\n#AI #SaaS #Software"


def threads_draft(title: str, url: str) -> str:
    return f"New guide: {title}\n\nUseful if you are comparing tools and want a practical checklist before buying.\n\n{url}"


def medium_draft(title: str, url: str) -> str:
    return f"# {title}\n\nThis is a manual repost draft. Summarize the buyer checklist, pricing verification steps, alternatives, and link back to the canonical article:\n\n{url}\n"


def pinterest_draft(title: str, url: str) -> str:
    return f"Pin title: {title}\n\nPin description: Compare pricing, pros, cons, alternatives, and buyer fit. Read the full guide: {url}\n"


def label_from_path(path: str) -> str:
    if path == "/":
        return "Smile AI Review Hub"
    return path.strip("/").replace("-", " ").replace("/", " / ").title()


def priority_from_score(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def business_value(affiliate: int, cpc: int, evergreen: int) -> str:
    score = affiliate * 0.45 + cpc * 0.35 + evergreen * 0.2
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def default_article_angle(topic: str, content_type: str) -> str:
    return f"This {content_type} explains {topic} from a practical buyer perspective."


def default_video_angle(topic: str, content_type: str) -> str:
    return f"Use a clear {content_type} video structure: hook, overview, pricing checks, alternatives, and verdict."


def default_internal_links(topic: str, content_type: str) -> list[str]:
    lower = topic.lower()
    links = ["/reviews/", "/comparisons/", "/categories/"]
    if "seo" in lower:
        links.extend(["/review/surfer-seo/", "/category/seo-tools/"])
    if "website" in lower or "builder" in lower:
        links.extend(["/best-website-builder-2026/", "/category/website-builder-tools/"])
    if "automation" in lower or "zapier" in lower:
        links.extend(["/zapier-pricing/", "/category/automation-tools/"])
    if content_type == "comparison":
        links.append("/comparisons/")
    return links


def is_near_duplicate(left: str, right: str) -> bool:
    a = set(left.split("-"))
    b = set(right.split("-"))
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= 0.78


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
