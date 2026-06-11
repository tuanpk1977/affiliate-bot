from __future__ import annotations

import csv
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

import create_commercial_review_batch as base
from create_commercial_review_batch import Review


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
PUBLISHED = ROOT / "data" / "published_static_pages"
VIDEO = ROOT / "video_output"
BASE_URL = "https://smileaireviewhub.com"


@dataclass(frozen=True)
class Spec:
    path: str
    video_folder: str
    title: str
    seo_title: str
    meta: str
    focus: str
    review: Review


def review(slug: str, brand: str, category: str, focus: str, secondary: str, official: str,
           audience: tuple[str, ...], strengths: tuple[str, ...], limits: tuple[str, ...],
           features: tuple[str, ...], alternatives: tuple[str, ...],
           internal: tuple[tuple[str, str], ...]) -> Review:
    return Review(slug, brand, category, (focus, secondary), official, audience, strengths, limits, features, alternatives, internal)


SPECS = [
    Spec("review/surfer-seo-review-2026", "review-surfer-seo-review-2026", "Surfer SEO Review 2026", "Surfer SEO Review 2026: Is It Worth It?", "Surfer SEO review covering pricing, trial options, features, pros, cons, alternatives, and practical buyer fit for 2026.", "surfer seo review",
         review("surfer-seo-review-2026", "Surfer SEO", "SEO Content Optimization", "surfer seo review", "surfer seo reviews, surfer seo free trial, surfer seo pricing", "https://surferseo.com", ("SEO teams publishing content regularly", "editors building repeatable optimization workflows", "buyers comparing content optimization platforms"), ("structured content briefs and optimization checks", "useful workflow for editorial teams", "strong commercial fit for active SEO programs"), ("recommendations still need editorial judgment", "trial and pricing terms must be verified", "small publishing calendars may not justify the workflow"), ("content editor", "content briefs", "keyword research", "auditing and optimization"), ("Frase", "Jasper", "Semrush", "Ahrefs"), (("Surfer SEO overview", "/review/surfer-seo/"), ("Surfer SEO alternatives", "/surfer-seo-alternatives/"), ("SEO tools", "/category/seo-tools/")))),
    Spec("surfer-seo-free-trial", "surfer-seo-free-trial", "Surfer SEO Free Trial 2026", "Surfer SEO Free Trial 2026: What to Verify", "Check Surfer SEO free trial availability, refund terms, plan limits, pricing risks, and alternatives before signing up in 2026.", "surfer seo free trial",
         review("surfer-seo-free-trial", "Surfer SEO Free Trial", "SEO Pricing Guide", "surfer seo free trial", "surfer seo trial, surfer seo pricing", "https://surferseo.com", ("buyers testing Surfer SEO before paying", "SEO teams validating content workflows", "editors comparing trial and refund terms"), ("a trial can validate workflow fit", "real content tests reveal practical value", "useful checkpoint before a paid plan"), ("trial availability can change", "refund rules require official verification", "a short test may not prove ranking impact"), ("trial availability", "refund terms", "plan limits", "content workflow testing"), ("Frase", "Semrush", "Ahrefs", "NeuronWriter"), (("Surfer SEO review", "/review/surfer-seo-review-2026/"), ("Surfer SEO alternatives", "/surfer-seo-alternatives/"), ("Surfer SEO pricing", "/pricing/surfer-seo/")))),
    Spec("compare/chatgpt-vs-claude", "compare-chatgpt-vs-claude", "ChatGPT vs Claude 2026", "ChatGPT vs Claude 2026: Which Is Better?", "Compare ChatGPT vs Claude for writing, research, coding, context, pricing, pros, cons, and practical workflow fit in 2026.", "chatgpt vs claude",
         review("chatgpt-vs-claude", "ChatGPT vs Claude", "AI Assistant Comparison", "chatgpt vs claude", "ai assistant comparison", "https://chatgpt.com", ("writers and researchers comparing AI assistants", "developers testing coding support", "teams evaluating context and workflow fit"), ("both support broad knowledge workflows", "useful comparison across real tasks", "strong options for writing and analysis"), ("outputs require verification", "plans and limits change", "privacy and team policies need review"), ("writing and analysis", "research workflows", "coding assistance", "files and context"), ("Gemini", "Perplexity", "Microsoft Copilot", "Jasper"), (("ChatGPT review", "/review/chatgpt/"), ("Claude review", "/review/claude/"), ("AI assistant tools", "/ai-assistant-software-review/")))),
    Spec("compare/cursor-vs-github-copilot-2026", "compare-cursor-vs-github-copilot-2026", "Cursor vs GitHub Copilot 2026", "Cursor vs GitHub Copilot 2026", "Compare Cursor vs GitHub Copilot for repository context, coding assistance, pricing, pros, cons, and team workflow fit.", "cursor vs github copilot",
         review("cursor-vs-github-copilot-2026", "Cursor vs GitHub Copilot", "AI Coding Comparison", "cursor vs github copilot", "ai coding assistant comparison", "https://www.cursor.com", ("developers comparing AI coding workflows", "teams evaluating repository-aware assistance", "buyers testing editor and extension approaches"), ("useful comparison on real repositories", "both can accelerate routine coding tasks", "strong commercial intent for development teams"), ("generated code needs review and tests", "security policies matter", "pricing and limits require verification"), ("repository context", "code completion", "agent workflows", "team controls"), ("Windsurf", "Replit", "Codeium", "Claude Code"), (("Cursor review", "/cursor/"), ("GitHub Copilot review", "/review/github-copilot/"), ("Cursor vs GitHub Copilot", "/compare/cursor-vs-github-copilot/")))),
    Spec("zapier-pricing", "zapier-pricing", "How Much Does Zapier Cost in 2026?", "Zapier Pricing 2026: How Much Does It Cost?", "Understand Zapier pricing, tasks, plan limits, cost risks, alternatives, and what to verify before choosing a plan in 2026.", "how much does zapier cost",
         review("zapier-pricing", "Zapier Pricing", "Automation Pricing Guide", "how much does zapier cost", "zapier pricing", "https://zapier.com/pricing", ("teams estimating automation costs", "operators planning task volume", "buyers comparing automation platforms"), ("broad integration ecosystem", "useful for multi-step automation", "cost can be modeled from real workflows"), ("task usage can increase cost", "plan limits change", "complex workflows require monitoring"), ("tasks and usage", "multi-step workflows", "premium apps", "team and governance controls"), ("Make", "n8n", "Pipedream", "Power Automate"), (("Zapier review", "/zapier/"), ("Zapier alternatives", "/zapier-alternatives/"), ("Automation tools", "/category/automation-tools/")))),
    Spec("review/adcreative-ai-review-2026", "review-adcreative-ai-review-2026", "AdCreative.ai Review 2026", "AdCreative.ai Review 2026: Pros and Cons", "AdCreative.ai review covering creative workflow, pricing checks, pros, cons, alternatives, and buyer fit for marketing teams.", "adcreative.ai review",
         review("adcreative-ai-review-2026", "AdCreative.ai", "AI Ad Creative", "adcreative.ai review", "ai advertising creative", "https://www.adcreative.ai", ("performance marketers producing ad variations", "small teams testing creative concepts", "agencies comparing AI design workflows"), ("fast creative variation workflow", "useful for campaign ideation", "commercial fit for active advertisers"), ("creative quality needs review", "brand consistency requires controls", "pricing and credits must be verified"), ("ad creative generation", "creative scoring", "brand assets", "campaign variations"), ("Canva", "Adobe Express", "Jasper", "Copy.ai"), (("AdCreative.ai overview", "/adcreative-ai/"), ("Canva vs AdCreative.ai", "/compare/canva-vs-adcreative-ai/"), ("Design tools", "/category/design-tools/")))),
    Spec("webflow-pros-and-cons", "webflow-pros-and-cons", "Webflow Pros and Cons 2026", "Webflow Pros and Cons 2026", "Explore the pros and cons of Webflow, pricing checks, best use cases, limitations, alternatives, and buyer fit in 2026.", "pros and cons of webflow",
         review("webflow-pros-and-cons", "Webflow", "Website Builder", "pros and cons of webflow", "webflow review", "https://webflow.com", ("designers building custom marketing sites", "teams needing visual development control", "buyers comparing professional website builders"), ("strong visual design control", "flexible CMS and publishing workflow", "useful for professional marketing sites"), ("learning curve can be significant", "pricing structure needs careful review", "complex projects require governance"), ("visual development", "CMS", "hosting and publishing", "interactions"), ("Framer", "WordPress", "Wix", "Squarespace"), (("Webflow review", "/webflow/"), ("Website builder tools", "/category/website-builder-tools/"), ("Framer review", "/framer/")))),
    Spec("best-website-builder-2026", "best-website-builder-2026", "Best Website Builder 2026", "Best Website Builder 2026: Top Options", "Compare the best website builder options for business sites, portfolios, stores, AI workflows, pricing, and long-term fit in 2026.", "the best website builder",
         review("best-website-builder-2026", "Best Website Builder", "Website Builder Comparison", "the best website builder", "best ai website builder", "https://smileaireviewhub.com/category/website-builder-tools/", ("small businesses launching websites", "creators building portfolios and landing pages", "teams comparing managed website platforms"), ("clear comparison by use case", "covers AI and traditional builders", "helps buyers shortlist practical options"), ("no single builder fits every project", "renewal pricing requires verification", "migration and ownership matter"), ("design flexibility", "AI site generation", "hosting and publishing", "commerce and integrations"), ("Webflow", "Framer", "Durable", "Hostinger Website Builder"), (("Website builder tools", "/category/website-builder-tools/"), ("Webflow review", "/webflow/"), ("Durable review", "/durable/")))),
    Spec("review/windsurf-review-2026", "review-windsurf-review-2026", "Windsurf Review 2026", "Windsurf Review 2026: Is It Worth It?", "Windsurf review covering AI coding workflow, pricing checks, pros, cons, alternatives, and practical developer fit in 2026.", "windsurf review",
         review("windsurf-review-2026", "Windsurf", "AI Coding", "windsurf review", "ai coding editor", "https://windsurf.com", ("developers testing AI-first coding", "teams comparing Cursor and Copilot", "buyers evaluating repository workflows"), ("repository-aware assistance", "useful AI coding workflow", "worth testing on real development tasks"), ("generated code needs tests", "team policy and security matter", "pricing requires official verification"), ("coding assistance", "repository context", "agent workflows", "editor experience"), ("Cursor", "GitHub Copilot", "Replit", "Codeium"), (("Windsurf overview", "/windsurf-review/"), ("Cursor vs Windsurf", "/compare/cursor-vs-windsurf/"), ("AI coding tools", "/category/ai-coding-tools/")))),
    Spec("review/durable-ai-review-2026", "review-durable-ai-review-2026", "Durable AI Website Builder Review 2026", "Durable AI Review 2026: Website Builder", "Durable AI website builder review covering features, pricing checks, pros, cons, alternatives, and small-business fit.", "durable ai website builder review",
         review("durable-ai-review-2026", "Durable AI Website Builder", "AI Website Builder", "durable ai website builder review", "durable review", "https://durable.co", ("small businesses needing a fast first website", "service providers testing AI site generation", "buyers comparing simple website builders"), ("fast starting point for small-business sites", "integrated AI-assisted workflow", "useful for validating a basic web presence"), ("generated content requires editing", "complex sites may need another platform", "pricing and renewal terms must be verified"), ("AI website generation", "editing and publishing", "business tools", "hosting workflow"), ("Hostinger Website Builder", "Framer", "Webflow", "Wix"), (("Durable overview", "/durable/"), ("Website builder tools", "/category/website-builder-tools/"), ("Hostinger Website Builder review", "/hostinger-website-builder-review-2026/")))),
]


def faq_schema(review: Review) -> dict:
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
        for q, a in base.faq(review)
    ]}


def article_schema(spec: Spec) -> dict:
    return {"@context": "https://schema.org", "@type": "Article", "headline": spec.title,
            "description": spec.meta, "url": f"{BASE_URL}/{spec.path}/",
            "author": {"@type": "Person", "name": "Nguyen Quoc Tuan"}, "dateModified": "2026-06-11"}


def render(spec: Spec) -> str:
    page = base.render(spec.review)
    canonical = f"{BASE_URL}/{spec.path}/"
    page = re.sub(r"<title>.*?</title>", f"<title>{html.escape(spec.seo_title)}</title>", page, count=1)
    page = re.sub(r'<meta name="description" content=".*?">', f'<meta name="description" content="{html.escape(spec.meta)}">', page, count=1)
    page = re.sub(r'<link rel="canonical" href=".*?">', f'<link rel="canonical" href="{canonical}">', page, count=1)
    page = re.sub(r"<h1>.*?</h1>", f"<h1>{html.escape(spec.title)}</h1>", page, count=1)
    intro = (f"{spec.title} addresses a practical search question with strong commercial intent. This guide evaluates the workflow, "
             f"pricing risks, strengths, limitations, and alternatives without treating feature lists as proof of value. The goal is to help buyers test {spec.review.brand} "
             f"against a real task, verify current terms on the official website, and compare related options before committing. Because plans, limits, trials, and product capabilities "
             f"can change, every pricing statement should be confirmed directly. Use the sections below to identify who benefits most, who should choose another tool, and which questions "
             f"matter during a trial or purchasing review.")
    toc = '<section class="card"><h2>Table of Contents</h2><ol><li><a href="#overview">Overview</a></li><li><a href="#features">Key features</a></li><li><a href="#pricing">Pricing</a></li><li><a href="#pros-cons">Pros and cons</a></li><li><a href="#alternatives">Alternatives</a></li><li><a href="#faq">FAQ</a></li><li><a href="#verdict">Final verdict</a></li></ol></section>'
    page = page.replace('<main class="wrap">', f'<main class="wrap"><section class="card"><h2>Introduction</h2><p>{html.escape(intro)}</p></section>{toc}', 1)
    page = page.replace('<section class="card"><h2>' + html.escape(spec.review.brand) + ' Overview</h2>', '<section class="card" id="overview"><h2>Overview</h2>', 1)
    page = page.replace('<section class="card"><h2>Key Features and Workflow</h2>', '<section class="card" id="features"><h2>Key Features and Workflow</h2>', 1)
    page = page.replace('<section class="grid">', '<section class="grid" id="pros-cons">', 1)
    page = page.replace('<section class="card"><h2>Pricing and Plan Checks</h2>', '<section class="card" id="pricing"><h2>Pricing and Plan Checks</h2>', 1)
    page = page.replace('<section class="card"><h2>Alternatives</h2>', '<section class="card" id="alternatives"><h2>Alternatives</h2>', 1)
    page = page.replace('<section class="card"><h2>FAQ</h2>', '<section class="card" id="faq"><h2>FAQ</h2>', 1)
    page = page.replace('<section class="card"><h2>Final Verdict</h2>', '<section class="card" id="verdict"><h2>Final Verdict</h2>', 1)
    schemas = f'<script type="application/ld+json">{json.dumps(article_schema(spec))}</script><script type="application/ld+json">{json.dumps(faq_schema(spec.review))}</script>'
    page = page.replace("</head>", schemas + "</head>", 1)
    page = page.replace(f'data-youtube-placeholder="{spec.review.slug}"', f'data-youtube-placeholder="{spec.video_folder}"', 1)
    return page


def upsert_video_index() -> None:
    path = ROOT / "data" / "video_article_index.csv"
    fields = ["slug", "title", "output_path", "url"]
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline=""))) if path.exists() else []
    mapping = {row.get("slug", ""): row for row in rows}
    for spec in SPECS:
        mapping[spec.video_folder] = {"slug": spec.video_folder, "title": spec.title, "output_path": str(SITE / spec.path / "index.html"), "url": f"{BASE_URL}/{spec.path}/"}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(mapping.values())


def update_video_metadata(spec: Spec) -> None:
    folder = VIDEO / spec.video_folder
    folder.mkdir(parents=True, exist_ok=True)
    metadata_path = folder / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    article_url = f"{BASE_URL}/{spec.path}/"
    hashtags = ["#AITools", "#SoftwareReview", "#" + re.sub(r"[^A-Za-z0-9]", "", spec.review.brand)]
    metadata.update({
        "title": spec.title,
        "description": f"{spec.meta}\n\nRead the full guide:\n{article_url}\n\nWebsite:\n{BASE_URL}",
        "pinned_comment": f"Read the full guide and compare related tools on Smile AI Review Hub: {article_url}",
        "hashtags": hashtags,
        "thumbnail_text": spec.title.replace(" 2026", "")[:44],
        "focus_keyword": spec.focus,
        "source_url": article_url,
    })
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    short_script = (
        f"Considering {spec.review.brand} in 2026? Start with the workflow, not the feature list. "
        f"Test {', '.join(spec.review.features[:2])} on one real task, verify current pricing and limits on the official website, "
        f"and compare {', '.join(spec.review.alternatives[:2])} before paying. "
        f"Read the full guide on Smile AI Review Hub at smileaireviewhub.com."
    )
    (folder / "short_script.txt").write_text(short_script + "\n", encoding="utf-8")


def update_upload_links() -> None:
    path = VIDEO / "upload_links.csv"
    fields, rows = base.read_csv(path)
    by_folder = {row.get("FolderName", ""): row for row in rows if row.get("FolderName")}
    order = [row.get("FolderName", "") for row in rows if row.get("FolderName")]
    for spec in SPECS:
        current = by_folder.get(spec.video_folder, {})
        current.update({"FolderName": spec.video_folder, "PageUrl": f"{BASE_URL}/{spec.path}/",
                        "YoutubeVideoUrl": current.get("YoutubeVideoUrl", ""),
                        "UploadStatus": current.get("UploadStatus") or "NOT_UPLOADED",
                        "Notes": current.get("Notes", "")})
        by_folder[spec.video_folder] = current
        if spec.video_folder not in order:
            order.append(spec.video_folder)
    base.write_csv(path, base.UPLOAD_FIELDS, [by_folder[name] for name in order])


def main() -> None:
    for spec in SPECS:
        page = render(spec)
        for root in (PUBLISHED, SITE):
            target = root / spec.path / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page, encoding="utf-8")
        print(f"{spec.path}: {base.word_count(page)} words")
    upsert_video_index()
    update_upload_links()
    for spec in SPECS:
        update_video_metadata(spec)
    statuses = {}
    status_path = VIDEO / "render_status.csv"
    if status_path.exists():
        statuses = {row.get("FolderName", ""): row for row in csv.DictReader(status_path.open("r", encoding="utf-8-sig", newline=""))}
    report = []
    for spec in SPECS:
        metadata = json.loads((VIDEO / spec.video_folder / "metadata.json").read_text(encoding="utf-8"))
        render_status = statuses.get(spec.video_folder, {}).get("RenderStatus", "")
        report.append({"title": spec.title, "slug": f"/{spec.path}/", "focus_keyword": spec.focus,
                       "status": "VIDEO_READY" if render_status == "DONE" else "ARTICLE_AND_VIDEO_ASSETS_READY",
                       "article_url": f"{BASE_URL}/{spec.path}/", "video_folder": f"video_output/{spec.video_folder}",
                       "video_file": f"video_output/{spec.video_folder}/review_video.mp4", "youtube_title": metadata["title"],
                       "youtube_description": metadata["description"], "pinned_comment": metadata["pinned_comment"],
                       "thumbnail_text": metadata["thumbnail_text"]})
    (VIDEO / "trend_signal_content_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (VIDEO / "trend_signal_content_report.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report[0]))
        writer.writeheader()
        writer.writerows(report)


if __name__ == "__main__":
    main()
