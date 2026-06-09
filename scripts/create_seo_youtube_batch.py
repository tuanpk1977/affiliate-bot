from __future__ import annotations

import csv
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SITE_OUTPUT = ROOT / "site_output"
PUBLISHED = DATA / "published_static_pages"
VIDEO_OUTPUT = ROOT / "video_output"
BASE_URL = "https://smileaireviewhub.com"
AUTHOR = "Nguyen Quoc Tuan"
AUTHOR_TITLE = "Founder - MS Smile AI Review Hub"
LAST_UPDATED = "June 2026"

UPLOAD_FIELDS = ["FolderName", "PageUrl", "YoutubeVideoUrl", "UploadStatus", "Notes"]


@dataclass(frozen=True)
class BatchPage:
    slug: str
    video_slug: str
    index_type: str
    title: str
    meta: str
    h1: str
    topic: str
    page_type: str
    category: str
    primary_links: tuple[tuple[str, str], ...]
    alternatives: tuple[str, ...]
    best_for: tuple[str, ...]
    not_best_for: tuple[str, ...]
    pros: tuple[str, ...]
    cons: tuple[str, ...]
    faq: tuple[tuple[str, str], ...]


PAGES = [
    BatchPage(
        slug="surfer-seo-pricing-2026",
        video_slug="pricing-surfer-seo",
        index_type="pricing",
        title="Surfer SEO Pricing 2026: Plans, Trial Notes, and Buying Risks",
        meta="Surfer SEO pricing guide for 2026 with plan-fit checks, trial notes, buyer risks, alternatives, FAQ, and official pricing verification guidance.",
        h1="Surfer SEO Pricing 2026",
        topic="Surfer SEO pricing",
        page_type="Pricing Guide",
        category="AI SEO",
        primary_links=(
            ("Surfer SEO review", "/surfer-seo/"),
            ("Surfer SEO alternatives", "/surfer-seo-alternatives/"),
            ("Surfer SEO vs Frase", "/comparisons/surfer-seo-vs-frase/"),
            ("AI SEO tools", "/category/seo-tools/"),
        ),
        alternatives=("Frase", "Jasper", "Semrush", "Ahrefs AI", "NeuronWriter"),
        best_for=("SEO teams with a repeatable content workflow", "Editors who need content brief checks", "Sites that can measure rankings and conversions after publishing"),
        not_best_for=("Buyers who only need one article per month", "Teams that will not verify recommendations manually", "Anyone choosing a plan without checking official limits first"),
        pros=("Useful for content optimization workflows", "Can help standardize briefs and on-page checks", "Strong fit when SEO review is already part of publishing"),
        cons=("Pricing and limits can change, so official verification is required", "Optimization scores should not replace editorial judgment", "May be overkill for very small publishing calendars"),
        faq=(
            ("How much does Surfer SEO cost in 2026?", "Plan prices, limits, and trial terms can change. Verify current pricing on the official website before buying."),
            ("Is Surfer SEO worth paying for?", "It can be worth testing if you publish SEO content regularly and have a workflow for checking recommendations before publishing."),
            ("Does Surfer SEO have a free trial?", "Trial and refund terms change over time. Check the official Surfer SEO pricing page for the current offer."),
        ),
    ),
    BatchPage(
        slug="surfer-seo-alternatives",
        video_slug="surfer-seo-alternatives",
        index_type="review",
        title="Surfer SEO Alternatives 2026: Best Tools to Compare Before Buying",
        meta="Compare Surfer SEO alternatives for 2026, including Frase, Jasper, Semrush, Ahrefs AI, and other SEO content workflow tools.",
        h1="Surfer SEO Alternatives 2026",
        topic="Surfer SEO alternatives",
        page_type="Alternatives Guide",
        category="AI SEO",
        primary_links=(
            ("Surfer SEO pricing", "/surfer-seo-pricing-2026/"),
            ("Surfer SEO review", "/surfer-seo/"),
            ("Surfer SEO vs Frase", "/comparisons/surfer-seo-vs-frase/"),
            ("Best AI SEO tools", "/best-ai-seo-tools-2026/"),
        ),
        alternatives=("Frase", "Jasper", "Semrush", "Ahrefs AI", "Clearscope", "NeuronWriter"),
        best_for=("Buyers comparing SEO content optimization tools", "Teams that need brief generation plus editorial review", "Marketers who want a shortlist before paying"),
        not_best_for=("Users looking for a guaranteed ranking tool", "Teams that do not have an SEO publishing process", "Buyers who will not check official pricing and feature limits"),
        pros=("Good way to compare workflow fit before committing", "Highlights pricing, content, and research tradeoffs", "Useful for teams with different writer and editor roles"),
        cons=("Feature names vary across tools and must be checked manually", "Some alternatives focus on writing while others focus on SEO data", "No tool should be treated as a ranking guarantee"),
        faq=(
            ("What is the best Surfer SEO alternative?", "The best alternative depends on whether you need content briefs, writing assistance, keyword data, or full SEO research."),
            ("Is Frase a Surfer SEO alternative?", "Yes, Frase is commonly compared for SEO content research and brief workflows, but verify current features before choosing."),
            ("Should I compare Jasper with Surfer SEO?", "Yes if your workflow includes AI writing. Jasper is more writing-oriented, while Surfer SEO is more SEO optimization-oriented."),
        ),
    ),
    BatchPage(
        slug="bolt-ai-review-2026",
        video_slug="bolt-ai-review-2026",
        index_type="review",
        title="Bolt AI Review 2026: Features, Pricing Checks, Pros, Cons, and Alternatives",
        meta="Bolt AI review for 2026 covering app-building workflow fit, pricing verification, pros and cons, alternatives, FAQ, and buyer guidance.",
        h1="Bolt AI Review 2026",
        topic="Bolt AI",
        page_type="Review",
        category="AI App Builder",
        primary_links=(
            ("Bolt review", "/bolt/"),
            ("Bolt vs Cursor", "/bolt-ai-vs-cursor/"),
            ("Bolt vs Lovable", "/bolt-ai-vs-lovable/"),
            ("Website builder AI tools", "/category/website-builder-tools/"),
        ),
        alternatives=("Lovable", "Cursor", "Replit", "Durable", "Webflow AI"),
        best_for=("Builders who want to prototype apps quickly", "Creators who prefer prompt-driven app scaffolding", "Teams that can review generated code before shipping"),
        not_best_for=("Production teams without code review", "Buyers who expect every generated app to be deployment-ready", "Users who need exact pricing without checking the official website"),
        pros=("Fast ideation for web app prototypes", "Useful for turning a product idea into a working draft", "Good fit when paired with human code review"),
        cons=("Generated apps still need testing and security review", "Pricing, limits, and integrations should be verified officially", "Complex production systems may need traditional engineering work"),
        faq=(
            ("What is Bolt AI best for?", "Bolt AI is best for fast app prototyping and early product drafts, especially when a human reviews the result before launch."),
            ("Is Bolt AI production-ready?", "It may help produce useful code, but production readiness depends on testing, security review, deployment setup, and maintenance."),
            ("How should I check Bolt AI pricing?", "Verify current pricing on the official website because plans, limits, and trial terms can change."),
        ),
    ),
    BatchPage(
        slug="windsurf-review-2026",
        video_slug="windsurf-review-2026",
        index_type="review",
        title="Windsurf Review 2026: AI Coding Workflow, Pricing Checks, Pros, Cons, and Alternatives",
        meta="Windsurf review for 2026 covering AI coding workflow fit, pricing checks, pros and cons, Cursor and GitHub Copilot comparisons, FAQ, and alternatives.",
        h1="Windsurf Review 2026",
        topic="Windsurf",
        page_type="Review",
        category="AI Coding",
        primary_links=(
            ("Windsurf review", "/windsurf/"),
            ("Windsurf vs Cursor", "/compare/cursor-vs-windsurf/"),
            ("Cursor review", "/cursor/"),
            ("GitHub Copilot review", "/review/github-copilot/"),
        ),
        alternatives=("Cursor", "GitHub Copilot", "Replit", "Codeium", "VS Code with extensions"),
        best_for=("Developers testing AI-first coding workflows", "Teams comparing Cursor, Copilot, and Windsurf", "Users who want coding assistance inside an editor workflow"),
        not_best_for=("Teams without code review or repository policies", "Developers who cannot verify generated code", "Buyers who choose based only on demos"),
        pros=("Strong fit for AI coding exploration", "Useful for repository-aware coding tasks", "Worth comparing directly against Cursor and GitHub Copilot"),
        cons=("Generated code still needs review and tests", "Pricing and free trial details must be verified officially", "Team rollout requires policy and security checks"),
        faq=(
            ("Is Windsurf better than Cursor?", "It depends on your editor preferences, repository workflow, and team policy. Test both on the same task before choosing."),
            ("Does Windsurf have a free trial?", "Trial details can change. Verify current availability on the official Windsurf website."),
            ("Who should use Windsurf?", "Developers who want to evaluate AI coding assistance in a practical coding workflow should shortlist it."),
        ),
    ),
    BatchPage(
        slug="zapier-alternatives",
        video_slug="zapier-alternatives",
        index_type="review",
        title="Zapier Alternatives 2026: Best Automation Tools to Compare Before Buying",
        meta="Zapier alternatives guide for 2026 comparing automation workflow tools, pricing checks, pros and cons, FAQ, and best-fit use cases.",
        h1="Zapier Alternatives 2026",
        topic="Zapier alternatives",
        page_type="Alternatives Guide",
        category="Automation",
        primary_links=(
            ("Zapier review", "/zapier/"),
            ("Zapier pricing", "/pricing/zapier/"),
            ("Make vs Zapier", "/compare/make-vs-zapier/"),
            ("Automation tools", "/category/automation-tools/"),
        ),
        alternatives=("Make", "Pipedream", "n8n", "Microsoft Power Automate", "Workato", "IFTTT"),
        best_for=("Teams comparing automation cost and workflow complexity", "Operators who need multi-step automations", "Buyers who want alternatives before committing to Zapier"),
        not_best_for=("Teams that need enterprise governance without vendor review", "Users who will not test trigger reliability", "Buyers who skip official pricing and usage limit checks"),
        pros=("Helps compare cost, complexity, and control", "Useful for choosing between no-code and developer-friendly automation", "Encourages testing triggers before migration"),
        cons=("Automation pricing depends heavily on volume and task usage", "Migration can break workflows if triggers differ", "Official pricing and limits must be checked before buying"),
        faq=(
            ("What is the best Zapier alternative?", "Make, n8n, Pipedream, Power Automate, and Workato are common alternatives, but the best choice depends on workflow complexity and governance needs."),
            ("Is Make cheaper than Zapier?", "It can be for some workflows, but pricing depends on usage and plan limits. Verify current pricing on official websites."),
            ("Should I migrate away from Zapier?", "Only migrate after testing your most important triggers, error handling, and maintenance process in the alternative tool."),
        ),
    ),
]


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def upsert_csv(path: Path, fieldnames: list[str], key: str, new_rows: list[dict[str, str]]) -> None:
    existing_fields, rows = read_csv(path)
    fields = list(dict.fromkeys((existing_fields or fieldnames) + fieldnames))
    by_key = {row.get(key, ""): row for row in rows if row.get(key)}
    for row in new_rows:
        current = by_key.get(row[key], {})
        current.update(row)
        by_key[row[key]] = current
    untouched = [row for row in rows if not row.get(key) or row.get(key) not in {r[key] for r in new_rows}]
    merged = untouched + [by_key[row[key]] for row in new_rows]
    write_csv(path, fields, merged)


def page_url(page: BatchPage) -> str:
    if page.index_type == "pricing":
        return f"{BASE_URL}/pricing/surfer-seo/"
    return f"{BASE_URL}/{page.slug}/"


def folder_name(page: BatchPage) -> str:
    if page.index_type == "review":
        return f"review-{page.video_slug}"
    return page.video_slug


def site_rel_path(page: BatchPage) -> str:
    if page.index_type == "pricing":
        return "pricing/surfer-seo"
    return page.slug


def link_list(links: tuple[tuple[str, str], ...]) -> str:
    return "".join(f'<li><a href="{html.escape(url)}">{html.escape(label)}</a></li>' for label, url in links)


def bullet_list(items: tuple[str, ...]) -> str:
    return "".join(f"<li>{html.escape(item)}</li>" for item in items)


def faq_html(items: tuple[tuple[str, str], ...]) -> str:
    return "".join(
        f"<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>"
        for q, a in items
    )


def schema(page: BatchPage) -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": page.h1,
        "description": page.meta,
        "url": page_url(page),
        "author": {"@type": "Person", "name": AUTHOR, "jobTitle": AUTHOR_TITLE},
        "publisher": {"@type": "Organization", "name": "MS Smile AI Review Hub"},
        "dateModified": "2026-06-08",
    }
    faq_payload = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in page.faq
        ],
    }
    return (
        '<script type="application/ld+json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script>\n"
        + '<script type="application/ld+json">'
        + json.dumps(faq_payload, ensure_ascii=False)
        + "</script>"
    )


def render_page(page: BatchPage) -> str:
    alt_cards = "".join(
        f"<li><strong>{html.escape(name)}</strong>: compare workflow fit, pricing limits, integrations, and review policy before choosing.</li>"
        for name in page.alternatives
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page.title)}</title>
  <meta name="description" content="{html.escape(page.meta)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{html.escape(page_url(page))}">
  {schema(page)}
  <style>
    :root{{--bg:#f7f9fc;--text:#17202a;--muted:#596579;--line:#dbe3ef;--card:#fff;--accent:#0f766e;--warn:#9a3412}}
    *{{box-sizing:border-box}}body{{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text);line-height:1.62}}
    .wrap{{max-width:1080px;margin:0 auto;padding:0 20px}}.nav{{background:#fff;border-bottom:1px solid var(--line)}}.nav-inner{{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:18px}}.logo{{font-weight:900;color:#0f172a;text-decoration:none}}.menu{{display:flex;gap:16px;flex-wrap:wrap}}.menu a{{color:#475569;text-decoration:none}}
    .hero{{padding:40px 0 22px;background:#fff}}.badge{{display:inline-block;border:1px solid #a7f3d0;background:#ecfdf5;color:#047857;border-radius:999px;padding:5px 10px;font-size:13px;font-weight:800;margin-right:6px}}h1{{font-size:42px;line-height:1.08;margin:14px 0 12px}}h2{{font-size:26px;line-height:1.24;margin:0 0 12px}}h3{{font-size:18px;margin:0 0 8px}}p,li{{color:var(--muted)}}a{{color:#0f766e;font-weight:800}}.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:18px;margin:16px 0;box-shadow:0 1px 2px rgba(15,23,42,.04)}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}}.note{{font-size:14px;color:#7c2d12}}.trust{{border-left:4px solid var(--warn);background:#fff7ed}}table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:8px;overflow:hidden}}th,td{{text-align:left;border-bottom:1px solid #e6edf5;padding:12px;vertical-align:top}}th{{background:#f1f5f9;color:#334155}}details{{border-top:1px solid #e6edf5;padding:12px 0}}summary{{cursor:pointer;font-weight:900;color:#334155}}.author-box{{display:grid;grid-template-columns:58px minmax(0,1fr);gap:12px;align-items:center}}.avatar{{width:58px;height:58px;border-radius:999px;background:#0f766e;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:900}}footer{{margin-top:36px;background:#0f172a;color:#cbd5e1;padding:28px 0}}footer a{{color:#e2e8f0;text-decoration:none;margin-right:14px}}
    @media(max-width:760px){{h1{{font-size:34px}}.nav-inner{{align-items:flex-start;flex-direction:column;padding:14px 0}}.grid{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>
  <nav class="nav"><div class="wrap nav-inner"><a class="logo" href="/">MS Smile AI Review Hub</a><div class="menu"><a href="/">Home</a><a href="/reviews/">Reviews</a><a href="/comparisons/">Comparisons</a><a href="/about-author/">Author</a></div></div><div class="wrap"><p class="note">Some links may be affiliate links. We may earn a commission at no extra cost to you.</p></div></nav>
  <header class="hero"><div class="wrap">
    <span class="badge">{html.escape(page.page_type)}</span><span class="badge">{html.escape(page.category)}</span><span class="badge">Last updated: {LAST_UPDATED}</span>
    <h1>{html.escape(page.h1)}</h1>
    <p>{html.escape(page.meta)}</p>
    <p><strong>Short answer:</strong> Use this page to shortlist {html.escape(page.topic)} options, then verify current pricing, limits, and terms on the official website before buying.</p>
  </div></header>
  <main class="wrap">
    <section class="card trust"><h2>Affiliate Disclaimer</h2><p>Some outbound links may be affiliate links. We may earn a commission at no extra cost to you. Our recommendation is based on workflow fit, pricing verification needs, and editorial review, not on commission size.</p></section>
    <section class="card"><h2>Overview</h2><p>{html.escape(page.h1)} is written for buyers who want a practical decision path, not a hype summary. We focus on workflow fit, current-pricing verification, alternatives, risks, and what to test before committing.</p><ul>{link_list(page.primary_links)}</ul></section>
    <section class="grid">
      <article class="card"><h2>Best For</h2><ul>{bullet_list(page.best_for)}</ul></article>
      <article class="card"><h2>Not Best For</h2><ul>{bullet_list(page.not_best_for)}</ul></article>
    </section>
    <section class="grid">
      <article class="card"><h2>Pros</h2><ul>{bullet_list(page.pros)}</ul></article>
      <article class="card"><h2>Cons</h2><ul>{bullet_list(page.cons)}</ul></article>
    </section>
    <section class="card"><h2>Pricing Notes</h2><p>Do not rely on old screenshots, social posts, or third-party summaries for final pricing. Plan names, usage caps, trial terms, refund rules, and included features may change. <strong>Verify current pricing on the official website</strong> before buying.</p></section>
    <section class="card"><h2>Alternatives to Compare</h2><ul>{alt_cards}</ul></section>
    <section class="card"><h2>Research Methodology</h2><p>We evaluate pages using a buyer workflow model: use case clarity, pricing verification, feature fit, integration needs, risk checks, alternatives, and whether the tool can be tested on a small real workflow before rollout.</p><ul><li>Official website and current product pages should be treated as the final source for pricing and policy details.</li><li>We compare each tool against related alternatives in the same workflow category.</li><li>We separate marketing claims from operational checks such as limits, exports, integrations, and cancellation terms.</li></ul></section>
    <section class="card"><h2>FAQ</h2>{faq_html(page.faq)}</section>
    <section class="card author-box"><div class="avatar">MS</div><div><h2>Author</h2><p><strong>{AUTHOR}</strong><br>{AUTHOR_TITLE}</p><p>Last updated: {LAST_UPDATED}. Research focus: AI tools, SaaS reviews, SEO workflows, automation, and practical buyer checks.</p></div></section>
  </main>
  <footer><div class="wrap"><p>MS Smile AI Review Hub - practical AI and SaaS research.</p><p><a href="/about-author/">Author</a><a href="/affiliate-disclosure/">Affiliate disclosure</a><a href="/contact/">Contact</a></p></div></footer>
</body>
</html>
"""


def write_page(page: BatchPage) -> None:
    rel = site_rel_path(page)
    for root in (SITE_OUTPUT, PUBLISHED):
        target = root / rel / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_page(page), encoding="utf-8")


def update_indices() -> None:
    pricing_rows = []
    review_rows = []
    for page in PAGES:
        output = SITE_OUTPUT / site_rel_path(page) / "index.html"
        if page.index_type == "pricing":
            pricing_rows.append(
                {
                    "tool_slug": "surfer-seo",
                    "tool_name": "Surfer SEO",
                    "title": page.title,
                    "output_path": str(output),
                    "status": "built",
                    "affiliate_status": "approved",
                }
            )
        else:
            review_rows.append(
                {
                    "offer_id": page.video_slug,
                    "brand_name": page.topic,
                    "review_slug": page.video_slug,
                    "title": page.title,
                    "output_path": str(output),
                    "status": "built",
                    "affiliate_status": "official_only",
                }
            )
    upsert_csv(DATA / "pricing_pages_index.csv", ["tool_slug", "tool_name", "title", "output_path", "status", "affiliate_status"], "tool_slug", pricing_rows)
    upsert_csv(DATA / "review_pages_index.csv", ["offer_id", "brand_name", "review_slug", "title", "output_path", "status", "affiliate_status"], "review_slug", review_rows)


def update_upload_links() -> None:
    path = VIDEO_OUTPUT / "upload_links.csv"
    fields, rows = read_csv(path)
    stale_review_names = {page.video_slug for page in PAGES if page.index_type == "review"}
    rows = [row for row in rows if row.get("FolderName", "") not in stale_review_names]
    by_folder = {row.get("FolderName", ""): row for row in rows if row.get("FolderName")}
    for row in rows:
        row.setdefault("UploadStatus", "UPLOADED" if row.get("YoutubeVideoUrl") else "NOT_UPLOADED")
        row.setdefault("Notes", "")
    for page in PAGES:
        folder = folder_name(page)
        existing = by_folder.get(folder, {})
        existing.update(
            {
                "FolderName": folder,
                "PageUrl": page_url(page),
                "YoutubeVideoUrl": existing.get("YoutubeVideoUrl", ""),
                "UploadStatus": existing.get("UploadStatus") or ("UPLOADED" if existing.get("YoutubeVideoUrl") else "NOT_UPLOADED"),
                "Notes": existing.get("Notes", ""),
            }
        )
        by_folder[folder] = existing
    ordered = [by_folder[row.get("FolderName", "")] for row in rows if row.get("FolderName") in by_folder]
    existing_names = {row.get("FolderName", "") for row in ordered}
    ordered.extend(by_folder[folder_name(page)] for page in PAGES if folder_name(page) not in existing_names)
    write_csv(path, UPLOAD_FIELDS, ordered)


def write_batch_manifest() -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pages": [
            {
                "slug": page.slug,
                "video_slug": folder_name(page),
                "url": page_url(page),
                "title": page.title,
            }
            for page in PAGES
        ],
    }
    (VIDEO_OUTPUT / "seo_youtube_batch_1.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    for page in PAGES:
        write_page(page)
    update_indices()
    VIDEO_OUTPUT.mkdir(exist_ok=True)
    update_upload_links()
    write_batch_manifest()
    print("Created SEO + YouTube batch pages:")
    for page in PAGES:
        print(f"- {folder_name(page)}: {page_url(page)}")


if __name__ == "__main__":
    main()
