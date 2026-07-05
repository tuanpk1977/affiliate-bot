from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
DATA = ROOT / "data"
VIDEO = ROOT / "video_output"
URL = "https://smileaireviewhub.com/compare/semrush-vs-ahrefs/"
TITLE = "Semrush vs Ahrefs 2026: Which SEO Tool Is Better?"
VIDEO_FOLDER = "review-semrush-vs-ahrefs-2026"


def section_paragraphs(subject: str, semrush: str, ahrefs: str, decision: str) -> str:
    paragraphs = [
        f"The practical way to compare Semrush and Ahrefs for {subject} is to begin with the decision the team must make every week. Semrush usually feels broader because it connects SEO research with content, advertising, competitive intelligence, and reporting workflows. Ahrefs usually feels more concentrated around organic search research, backlinks, competitor discovery, and the process of finding opportunities from search data. Neither positioning automatically makes one platform better.",
        f"For Semrush, the most important test is whether {semrush}. Teams should run that test with a real domain, a real competitor, and a real reporting deadline. A large toolset creates value only when people use the connected workflow consistently. If the team uses only one report, the breadth can become cost and complexity instead of an advantage.",
        f"For Ahrefs, the central test is whether {ahrefs}. Its research experience can be especially useful when an SEO needs to move quickly from a competitor, keyword, or backlink clue to a prioritized action. However, research depth still needs editorial judgment, technical validation, and a clear business objective.",
        f"The buying decision should therefore focus on {decision}. Compare both tools with the same websites and the same questions. Record how long each task takes, which exports are useful, what needs manual checking, and which plan limits affect the workflow. This makes the comparison repeatable instead of impressionistic.",
    ]
    return "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)


def render() -> str:
    faq = [
        ("Is Semrush better than Ahrefs in 2026?", "Semrush is often the stronger fit for teams wanting a broad digital marketing and SEO suite. Ahrefs is often the stronger fit for focused organic search and backlink research. Test both against the same workflow."),
        ("Which tool is better for keyword research?", "Semrush offers a broad keyword and marketing research workflow. Ahrefs offers a focused organic research workflow. The better choice depends on the markets, reports, and prioritization process your team uses."),
        ("Which tool is better for backlinks?", "Ahrefs is widely shortlisted for backlink and organic competitor research. Semrush also provides backlink tools and may fit teams that want those insights inside a broader marketing suite."),
        ("Which tool is better for site audits?", "Both platforms support technical audit workflows. Compare issue prioritization, crawl limits, reporting, and how easily the findings become assigned tasks."),
        ("Which tool is cheaper?", "Plan names, limits, credits, projects, users, and pricing can change. Verify current pricing on the official Semrush and Ahrefs websites."),
        ("Can an agency use both Semrush and Ahrefs?", "Yes. Some agencies use both because the platforms support different research and reporting preferences, but the additional cost should be justified by repeatable client work."),
        ("Do these tools guarantee rankings?", "No. They support research and decision-making, but rankings depend on content quality, technical implementation, competition, authority, and search-engine changes."),
    ]
    faq_html = "".join(f"<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>" for q, a in faq)
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": TITLE,
        "description": "Detailed Semrush vs Ahrefs 2026 comparison covering pricing, keyword research, backlinks, audits, rank tracking, AI features, use cases, and verdict.",
        "url": URL,
        "author": {"@type": "Person", "name": "Nguyen Quoc Tuan", "jobTitle": "Founder - MS Smile AI Review Hub"},
        "dateModified": "2026-06-09",
    }
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TITLE}</title><meta name="description" content="Semrush vs Ahrefs 2026 comparison: pricing, keyword research, backlink analysis, site audits, rank tracking, AI features, use cases, pros, cons, and final verdict."><meta name="keywords" content="semrush vs ahrefs, semrush review, ahrefs review, seo tools, keyword research, backlink analysis, seo software"><meta name="robots" content="index,follow"><link rel="canonical" href="{URL}">
<script type="application/ld+json">{json.dumps(schema)}</script>
<style>:root{{--bg:#f7f9fc;--text:#17202a;--muted:#596579;--line:#dbe3ef;--accent:#0f766e}}*{{box-sizing:border-box}}body{{margin:0;font:16px/1.68 Arial,sans-serif;background:var(--bg);color:var(--text)}}.wrap{{max-width:1100px;margin:auto;padding:0 20px}}nav{{background:#fff;border-bottom:1px solid var(--line)}}nav .wrap{{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:18px}}a{{color:var(--accent);font-weight:800;text-decoration:none}}.menu{{display:flex;gap:16px;flex-wrap:wrap}}header{{padding:44px 0 26px;background:#fff}}h1{{font-size:44px;line-height:1.08;margin:12px 0}}h2{{font-size:28px;line-height:1.25;margin:0 0 12px}}h3{{font-size:20px}}p,li{{color:var(--muted)}}.badge{{display:inline-block;border:1px solid #a7f3d0;background:#ecfdf5;color:#047857;border-radius:999px;padding:5px 10px;font-size:13px;font-weight:800;margin-right:6px}}.card{{background:#fff;border:1px solid var(--line);border-radius:8px;padding:20px;margin:18px 0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#f1f5f9}}.note{{border-left:4px solid #9a3412;background:#fff7ed}}details{{padding:12px 0;border-top:1px solid var(--line)}}summary{{cursor:pointer;font-weight:900}}.youtube-placeholder{{border:2px dashed #94a3b8;text-align:center;background:#f8fafc}}footer{{margin-top:38px;background:#0f172a;color:#dbeafe;padding:28px 0}}@media(max-width:720px){{h1{{font-size:34px}}nav .wrap{{align-items:flex-start;flex-direction:column;padding:14px 20px}}}}</style></head>
<body><nav><div class="wrap"><a href="/">MS Smile AI Review Hub</a><div class="menu"><a href="/category/seo-tools/">SEO Tools</a><a href="/comparisons/">Comparisons</a><a href="/about-author/">Author</a></div></div></nav>
<header><div class="wrap"><span class="badge">SEO Tools</span><span class="badge">Comparison</span><span class="badge">Updated June 2026</span><h1>{TITLE}</h1><p>Semrush and Ahrefs are two of the most frequently compared SEO platforms. This guide evaluates them as working systems for research, execution, reporting, and buying decisions.</p></div></header><main class="wrap">
<section class="card note"><h2>Affiliate Disclaimer</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you. Verify current pricing, features, and terms on official vendor websites.</p></section>
<section class="card"><h2>Overview</h2>{section_paragraphs("overall SEO operations", "its broader marketing data creates a workflow the team will actually use", "its organic research depth turns into prioritized SEO actions", "workflow coverage, research depth, team adoption, and total cost")}<p><strong>Short verdict:</strong> Semrush is generally better for teams wanting a broad SEO and digital marketing suite. Ahrefs is generally better for focused organic search, competitor, content, and backlink research.</p></section>
<section class="card"><h2>Feature Comparison Table</h2><table><tr><th>Area</th><th>Semrush</th><th>Ahrefs</th><th>Decision question</th></tr>
<tr><td>Platform scope</td><td>Broad SEO and digital marketing suite</td><td>Focused organic search research platform</td><td>Do you need breadth or concentrated SEO research?</td></tr>
<tr><td>Keyword research</td><td>Broad keyword, competitive, and campaign context</td><td>Strong organic keyword and competitor exploration</td><td>Which workflow produces better priorities?</td></tr>
<tr><td>Backlinks</td><td>Backlink research within a wider suite</td><td>Deep backlink and organic competitor workflow</td><td>How central is link research?</td></tr>
<tr><td>Site audit</td><td>Technical audits connected to projects and reporting</td><td>Technical audits connected to organic research</td><td>Which issue workflow is easier to maintain?</td></tr>
<tr><td>Rank tracking</td><td>Campaign and reporting-oriented tracking</td><td>Organic performance tracking and research context</td><td>Which reports match stakeholders?</td></tr>
<tr><td>AI features</td><td>AI assistance across broader marketing workflows</td><td>AI assistance focused around search research tasks</td><td>Does AI reduce real work without reducing review quality?</td></tr></table></section>
<section class="card"><h2>Pricing Comparison</h2>{section_paragraphs("pricing and plan selection", "projects, reports, seats, and broader marketing features justify the selected plan", "credits, projects, reports, and organic research limits fit regular usage", "current official pricing, included limits, add-ons, and the cost at the next growth stage")}<p><strong>Do not rely on old pricing tables.</strong> Verify current pricing on the official websites before buying.</p></section>
<section class="card"><h2>Keyword Research Comparison</h2>{section_paragraphs("keyword research", "its keyword datasets and related marketing context improve prioritization", "its keyword explorer and competitor workflow reveal achievable organic opportunities", "how quickly the team moves from a keyword idea to a defensible content or optimization brief")}</section>
<section class="card"><h2>Backlink Analysis Comparison</h2>{section_paragraphs("backlink analysis", "backlink findings connect usefully with broader competitive and campaign analysis", "link discovery and competitor backlink exploration produce actionable outreach or content decisions", "index usefulness, filtering, historical context, exports, and the actions created from the data")}</section>
<section class="card"><h2>Site Audit Comparison</h2>{section_paragraphs("technical site audits", "audit findings integrate with projects, reporting, and team execution", "audit findings connect clearly to organic search priorities", "crawl limits, issue prioritization, false positives, reporting, ownership, and remediation workflow")}</section>
<section class="card"><h2>Rank Tracking Comparison</h2>{section_paragraphs("rank tracking", "campaign reporting and visibility views match stakeholder needs", "rank changes connect effectively to organic research and competitor analysis", "location, device, update frequency, reporting clarity, and how rank changes influence decisions")}</section>
<section class="card"><h2>AI Features and Workflow Automation</h2>{section_paragraphs("AI-assisted SEO work", "AI assistance saves time across the wider marketing workflow while preserving review steps", "AI assistance improves focused search research without replacing expert judgment", "time saved, quality maintained, transparency, and whether outputs become useful actions")}</section>
<section class="grid"><article class="card"><h2>Semrush Pros and Cons</h2><h3>Pros</h3><ul><li>Broad SEO and marketing workflow coverage</li><li>Strong project, reporting, and competitive research context</li><li>Useful for agencies and multidisciplinary marketing teams</li></ul><h3>Cons</h3><ul><li>Breadth can increase complexity</li><li>Teams may pay for unused capabilities</li><li>Plan limits and add-ons require careful review</li></ul></article><article class="card"><h2>Ahrefs Pros and Cons</h2><h3>Pros</h3><ul><li>Focused organic research experience</li><li>Strong backlink and competitor exploration workflow</li><li>Efficient for content and SEO opportunity discovery</li></ul><h3>Cons</h3><ul><li>May not replace a broader marketing suite</li><li>Usage limits must match team behavior</li><li>Research insights still require implementation resources</li></ul></article></section>
<section class="card"><h2>Best Use Cases</h2>{section_paragraphs("best-fit use cases", "agencies, in-house marketing teams, and businesses benefit from the connected suite", "SEO specialists, content teams, and organic research-heavy workflows benefit from focused exploration", "the recurring jobs, stakeholder reports, and decisions that justify the subscription")}<ul><li><strong>Choose Semrush</strong> when SEO must connect with a wider digital marketing and reporting system.</li><li><strong>Choose Ahrefs</strong> when organic research, backlinks, competitors, and content opportunities are the center of the workflow.</li><li><strong>Consider both</strong> only when distinct repeatable work justifies the combined cost.</li></ul></section>
<section class="card"><h2>Final Verdict</h2>{section_paragraphs("the final buying decision", "the team will consistently use its breadth and reporting capabilities", "the team will consistently use its focused organic research depth", "which platform creates more verified actions per month at an acceptable total cost")}<p><strong>Winner for broader marketing teams: Semrush.</strong> <strong>Winner for focused organic SEO research: Ahrefs.</strong></p></section>
<section class="card"><h2>FAQ</h2>{faq_html}</section>
<section class="card"><h2>Related SEO Research</h2><ul><li><a href="/category/seo-tools/">SEO Tools</a></li><li><a href="/semrush/">Semrush Review</a></li><li><a href="/ahrefs-ai/">Ahrefs AI Review</a></li><li><a href="/surfer-seo/">Surfer SEO Review</a></li><li><a href="/best-ai-seo-tools-2026/">Best AI SEO Tools 2026</a></li></ul></section>
<section class="card youtube-placeholder" data-youtube-placeholder="{VIDEO_FOLDER}"><h2>Watch Video Review</h2><p>The video will appear automatically after its YouTube URL is added to the upload links file.</p></section>
<section class="card"><h2>Research Methodology</h2><p>We compare workflow fit, official pricing verification needs, research depth, reporting, implementation effort, alternatives, and buyer risk. Pricing and product policies should be verified on official websites.</p></section>
<section class="card"><h2>Author</h2><p><strong>Nguyen Quoc Tuan</strong><br>Founder - MS Smile AI Review Hub</p><p>Last updated: June 2026</p></section></main><footer><div class="wrap">MS Smile AI Review Hub</div></footer></body></html>"""


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def upsert_review_index() -> None:
    path = DATA / "review_pages_index.csv"
    fields, rows = read_csv(path)
    row = {
        "offer_id": "semrush-vs-ahrefs-2026",
        "brand_name": "Semrush vs Ahrefs",
        "review_slug": "semrush-vs-ahrefs-2026",
        "title": TITLE,
        "output_path": str(SITE / "compare" / "semrush-vs-ahrefs" / "index.html"),
        "status": "built",
        "affiliate_status": "commercial_intent",
    }
    rows = [existing for existing in rows if existing.get("review_slug") != row["review_slug"]] + [row]
    write_csv(path, fields, rows)


def update_comparison_index() -> None:
    path = DATA / "comparison_pages_index.csv"
    fields, rows = read_csv(path)
    for row in rows:
        if row.get("comparison_slug") == "semrush-vs-ahrefs":
            row["title"] = TITLE
            row["output_path"] = str(SITE / "compare" / "semrush-vs-ahrefs" / "index.html")
    write_csv(path, fields, rows)


def update_upload_links() -> None:
    path = VIDEO / "upload_links.csv"
    fields, rows = read_csv(path)
    fields = list(dict.fromkeys(fields + ["UploadStatus", "Notes"]))
    row = {
        "FolderName": VIDEO_FOLDER,
        "PageUrl": URL,
        "YoutubeVideoUrl": "",
        "UploadStatus": "NOT_UPLOADED",
        "Notes": "Upgraded GSC high-impression comparison",
    }
    rows = [existing for existing in rows if existing.get("FolderName") != VIDEO_FOLDER] + [row]
    write_csv(path, fields, rows)


def inject_related_link(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if "/compare/semrush-vs-ahrefs/" in text:
        return False
    marker = "</main>"
    block = f'<section class="card"><h2>Featured SEO Comparison</h2><p><a href="/compare/semrush-vs-ahrefs/">{TITLE}</a></p></section>'
    if marker in text:
        text = text.replace(marker, block + marker, 1)
    else:
        text += block
    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    page = render()
    words = len(re.findall(r"\b[\w'-]+\b", re.sub(r"<[^>]+>", " ", page)))
    if words < 3000:
        raise RuntimeError(f"Article below 3000 words: {words}")
    target = SITE / "compare" / "semrush-vs-ahrefs" / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    source = DATA / "published_static_pages" / "semrush-vs-ahrefs-2026" / "index.html"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(page, encoding="utf-8")
    upsert_review_index()
    update_comparison_index()
    update_upload_links()
    related = [
        SITE / "category" / "seo-tools" / "index.html",
        SITE / "semrush" / "index.html",
        SITE / "ahrefs-ai" / "index.html",
        SITE / "surfer-seo" / "index.html",
        SITE / "comparisons" / "index.html",
    ]
    changed = [str(path) for path in related if inject_related_link(path)]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "url": URL,
        "title": TITLE,
        "word_count": words,
        "video_folder": VIDEO_FOLDER,
        "related_pages_updated": changed,
        "indexing_status": "READY_FOR_INDEXING",
    }
    (DATA / "semrush_vs_ahrefs_2026_indexing_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
