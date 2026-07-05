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
    angle: str
    comparison: tuple[tuple[str, str, str, str], ...]
    review: Review


def review(
    slug: str,
    brand: str,
    category: str,
    focus: str,
    secondary: str,
    official: str,
    audience: tuple[str, ...],
    strengths: tuple[str, ...],
    limits: tuple[str, ...],
    features: tuple[str, ...],
    alternatives: tuple[str, ...],
    internal: tuple[tuple[str, str], ...],
) -> Review:
    return Review(slug, brand, category, (focus, secondary), official, audience, strengths, limits, features, alternatives, internal)


SURFER_LINKS = (
    ("Surfer SEO review", "/review/surfer-seo-review-2026/"),
    ("Surfer SEO free trial", "/surfer-seo-free-trial/"),
    ("Surfer SEO alternatives", "/surfer-seo-alternatives/"),
    ("Surfer SEO vs Frase", "/comparisons/surfer-seo-vs-frase/"),
    ("Surfer SEO vs Clearscope", "/surfer-seo-vs-clearscope/"),
    ("Best AI SEO tools", "/best-ai-seo-tools-2026/"),
)

SPECS = [
    Spec(
        "review/surfer-seo-review-2026", "review-surfer-seo-review-2026",
        "Surfer SEO Review 2026: Pricing, Pros, Cons & Best Alternatives",
        "Surfer SEO Review 2026: Pricing, Pros & Cons",
        "Independent Surfer SEO review covering pricing, workflow, pros, cons, free-trial checks, and the best alternatives for 2026.",
        "surfer seo review", "an independent buyer-focused evaluation of Surfer SEO as a repeatable content optimization workflow",
        (("Content optimization", "Strong guided workflow", "Strong", "Editors and SEO teams"),
         ("Keyword research", "Useful planning support", "Medium", "Content strategists"),
         ("Team workflow", "Briefs and repeatable checks", "Strong", "Active publishing teams"),
         ("Buyer risk", "Pricing and recommendations need verification", "Medium", "Teams with clear process owners")),
        review("surfer-seo-review-2026", "Surfer SEO", "SEO Content Optimization", "surfer seo review", "surfer seo reviews, surfer seo pricing, surfer seo trial", "https://surferseo.com",
               ("SEO teams publishing consistently", "editors building content briefs", "buyers comparing optimization platforms"),
               ("structured optimization workflow", "practical content briefs", "clear fit for active SEO programs"),
               ("recommendations need editorial judgment", "pricing and trial terms can change", "small publishing calendars may not justify the cost"),
               ("Content Editor", "content briefs", "keyword research", "content auditing"), ("Frase", "Clearscope", "Semrush", "Ahrefs"), SURFER_LINKS)),
    Spec(
        "surfer-seo-free-trial", "surfer-seo-free-trial",
        "Surfer SEO Free Trial: Is It Worth Trying in 2026?",
        "Surfer SEO Free Trial 2026: Is It Worth It?",
        "Check Surfer SEO free-trial availability, refund terms, plan limits, test workflow, and alternatives before paying in 2026.",
        "surfer seo free trial", "a risk-controlled trial checklist that helps buyers test Surfer SEO without relying on outdated offers",
        (("Trial availability", "Verify on official site", "Changes over time", "All buyers"),
         ("Workflow test", "Optimize one real article", "High value", "SEO teams"),
         ("Plan limits", "Check credits and seats", "Important", "Growing teams"),
         ("Exit plan", "Confirm cancellation or refund rules", "Essential", "Budget-conscious buyers")),
        review("surfer-seo-free-trial", "Surfer SEO Free Trial", "SEO Trial Guide", "surfer seo free trial", "surfer seo trial, surfer seo pricing", "https://surferseo.com",
               ("buyers testing Surfer SEO before paying", "SEO teams validating a content workflow", "editors comparing trial terms"),
               ("real projects reveal workflow fit", "reduces purchasing risk", "supports direct alternative comparisons"),
               ("trial availability changes", "refund rules require verification", "ranking impact cannot be proven by a short test"),
               ("trial terms", "plan limits", "workflow testing", "cancellation checks"), ("Frase", "Clearscope", "Semrush", "NeuronWriter"), SURFER_LINKS)),
    Spec(
        "surfer-seo-alternatives", "review-surfer-seo-alternatives",
        "Surfer SEO Alternatives: Best SEO Content Optimization Tools",
        "Best Surfer SEO Alternatives for 2026",
        "Compare the best Surfer SEO alternatives for briefs, optimization, research, team workflows, pricing, and practical buyer fit.",
        "surfer seo alternatives", "a practical shortlist of content optimization tools for teams that need a different workflow, budget, or data depth",
        (("Frase", "Briefs and AI-assisted research", "Workflow flexibility", "Writers and lean teams"),
         ("Clearscope", "Premium content optimization", "Editorial clarity", "Established content teams"),
         ("Semrush", "Broader SEO suite", "Research breadth", "Marketing teams"),
         ("Ahrefs", "Research and backlink data", "SEO data depth", "SEO specialists")),
        review("surfer-seo-alternatives", "Surfer SEO Alternatives", "SEO Tool Comparison", "surfer seo alternatives", "content optimization tools", "https://smileaireviewhub.com/category/seo-tools/",
               ("content teams comparing optimization tools", "buyers seeking broader SEO suites", "editors needing a simpler workflow"),
               ("multiple workflow options", "clear comparison criteria", "supports budget and process fit"),
               ("tools use different data and scoring", "pricing changes", "no recommendation replaces editorial quality"),
               ("content briefs", "optimization guidance", "keyword research", "team workflow"), ("Frase", "Clearscope", "Semrush", "Ahrefs"), SURFER_LINKS)),
    Spec(
        "comparisons/surfer-seo-vs-frase", "compare-surfer-seo-vs-frase",
        "Surfer SEO vs Frase: Which AI SEO Tool Is Better?",
        "Surfer SEO vs Frase: Which Is Better in 2026?",
        "Compare Surfer SEO vs Frase for content briefs, optimization, AI workflows, pricing checks, pros, cons, and buyer fit.",
        "surfer seo vs frase", "a task-by-task comparison for buyers choosing between structured optimization and research-led content workflows",
        (("Content optimization", "Structured scoring workflow", "Research-led optimization", "Surfer SEO for guided checks"),
         ("Brief creation", "Strong", "Strong", "Test both with the same topic"),
         ("AI workflow", "Optimization-centered", "Research and drafting support", "Depends on editorial process"),
         ("Pricing", "Verify current plans", "Verify current plans", "Model expected monthly usage")),
        review("surfer-seo-vs-frase", "Surfer SEO vs Frase", "SEO Tool Comparison", "surfer seo vs frase", "ai seo tool comparison", "https://surferseo.com",
               ("SEO teams comparing content workflows", "writers choosing a research tool", "buyers testing optimization platforms"),
               ("clear task-based comparison", "both support content briefs", "useful for workflow selection"),
               ("results depend on editorial quality", "pricing requires verification", "scores are not ranking guarantees"),
               ("content briefs", "optimization", "research workflow", "AI assistance"), ("Clearscope", "Semrush", "Ahrefs", "NeuronWriter"), SURFER_LINKS)),
    Spec(
        "surfer-seo-vs-clearscope", "surfer-seo-vs-clearscope",
        "Surfer SEO vs Clearscope: Best Content Optimization Software",
        "Surfer SEO vs Clearscope: Best SEO Tool?",
        "Compare Surfer SEO vs Clearscope for content optimization, editorial workflows, pricing checks, strengths, limits, and alternatives.",
        "surfer seo vs clearscope", "a buyer-focused comparison between two established content optimization approaches",
        (("Optimization workflow", "Guided and feature-rich", "Editorially focused", "Depends on team process"),
         ("Learning curve", "Moderate", "Often straightforward", "Test with editors"),
         ("Broader tooling", "More workflow options", "Focused optimization", "Surfer SEO"),
         ("Pricing", "Verify current plans", "Verify current plans", "Calculate per publishing volume")),
        review("surfer-seo-vs-clearscope", "Surfer SEO vs Clearscope", "SEO Tool Comparison", "surfer seo vs clearscope", "content optimization software", "https://surferseo.com",
               ("content leaders comparing premium optimization tools", "editors standardizing briefs", "SEO teams evaluating workflow fit"),
               ("both support repeatable optimization", "clear editorial use cases", "useful side-by-side testing"),
               ("scores require human judgment", "pricing can be significant", "data and recommendations differ"),
               ("content optimization", "brief creation", "editorial workflow", "reporting"), ("Frase", "Semrush", "Ahrefs", "NeuronWriter"), SURFER_LINKS)),
    Spec(
        "best-ai-seo-tools-2026", "best-ai-seo-tools-2026",
        "Best AI SEO Tools for Content Creators in 2026",
        "Best AI SEO Tools for Content Creators 2026",
        "Compare the best AI SEO tools for content creators, including research, optimization, briefs, workflow risks, and practical use cases.",
        "best ai seo tools", "a creator-focused comparison of AI SEO tools that emphasizes useful workflows rather than automated publishing volume",
        (("Surfer SEO", "Optimization and briefs", "Structured workflow", "Active SEO content teams"),
         ("Frase", "Research and briefs", "Efficient planning", "Writers and lean teams"),
         ("Semrush", "Broad SEO research", "Suite depth", "Marketing teams"),
         ("Ahrefs", "Research and backlinks", "Data exploration", "SEO specialists")),
        review("best-ai-seo-tools-2026", "Best AI SEO Tools", "SEO Tool Comparison", "best ai seo tools", "ai seo tools for content creators", "https://smileaireviewhub.com/category/seo-tools/",
               ("content creators building search-led workflows", "small SEO teams", "publishers comparing research and optimization tools"),
               ("comparison by real creator tasks", "covers research and optimization", "prioritizes human review"),
               ("AI output requires verification", "tool overlap can waste budget", "automation does not guarantee rankings"),
               ("keyword research", "content briefs", "optimization", "performance review"), ("Surfer SEO", "Frase", "Semrush", "Ahrefs"), SURFER_LINKS)),
    Spec(
        "best-website-builder-2026", "best-website-builder-2026",
        "Best Website Builder for Small Businesses in 2026",
        "Best Website Builder for Small Business 2026",
        "Compare the best website builders for small businesses by setup speed, design control, ownership, pricing checks, and growth fit.",
        "best website builder for small business", "a small-business buying guide that balances launch speed, ongoing control, and long-term operating cost",
        (("Wix", "Managed small-business websites", "Ease of use", "General small businesses"),
         ("Webflow", "Custom marketing sites", "Design control", "Design-led teams"),
         ("Durable", "Fast AI-assisted setup", "Launch speed", "Service businesses"),
         ("Framer", "Modern marketing pages", "Visual publishing", "Startups and creators")),
        review("best-website-builder-2026", "Best Website Builder for Small Businesses", "Website Builder Comparison", "best website builder for small business", "the best website builder", "https://smileaireviewhub.com/category/website-builder-tools/",
               ("small businesses launching a site", "service providers needing leads", "teams comparing managed builders"),
               ("comparison by business use case", "covers AI and traditional builders", "includes ownership and pricing checks"),
               ("no builder fits every business", "renewal pricing requires verification", "migration can be difficult"),
               ("design and editing", "hosting and publishing", "lead capture", "commerce and integrations"), ("Wix", "Webflow", "Durable", "Framer"),
               (("Website builder tools", "/category/website-builder-tools/"), ("Webflow pros and cons", "/webflow-pros-and-cons/"), ("Durable review", "/review/durable-ai-review-2026/")))),
    Spec(
        "best-ai-website-builders-compared", "best-ai-website-builders-compared",
        "Best AI Website Builders Compared: Wix, Webflow, Durable, Framer",
        "Best AI Website Builders Compared in 2026",
        "Compare Wix, Webflow, Durable, and Framer as AI website builders for speed, control, editing, pricing checks, and business fit.",
        "best ai website builders", "a side-by-side comparison of four popular approaches to AI-assisted website creation",
        (("Wix", "Broad managed builder", "Business features", "General small businesses"),
         ("Webflow", "Visual development", "Design and CMS control", "Professional web teams"),
         ("Durable", "Fast AI site generation", "Speed", "Service businesses"),
         ("Framer", "Modern visual publishing", "Design workflow", "Startups and creators")),
        review("best-ai-website-builders-compared", "Best AI Website Builders", "AI Website Builder Comparison", "best ai website builders", "wix vs webflow vs durable vs framer", "https://smileaireviewhub.com/category/website-builder-tools/",
               ("small businesses comparing AI builders", "creators launching marketing sites", "teams testing faster web production"),
               ("clear four-tool comparison", "covers speed and design control", "supports buyer shortlisting"),
               ("AI output needs editing", "pricing and limits change", "migration and ownership matter"),
               ("AI site generation", "visual editing", "CMS and publishing", "business integrations"), ("Wix", "Webflow", "Durable", "Framer"),
               (("Best website builder", "/best-website-builder-2026/"), ("Webflow pros and cons", "/webflow-pros-and-cons/"), ("Durable review", "/review/durable-ai-review-2026/")))),
    Spec(
        "best-affiliate-marketing-software-saas", "best-affiliate-marketing-software-saas",
        "Best Affiliate Marketing Software for SaaS Companies",
        "Best Affiliate Software for SaaS Companies",
        "Compare affiliate marketing software for SaaS companies by tracking, partner onboarding, payouts, integrations, pricing, and control.",
        "best affiliate marketing software for saas", "a SaaS operator's comparison of affiliate and partner-management platforms",
        (("Trackdesk", "Affiliate tracking and management", "Operational flexibility", "Growing SaaS programs"),
         ("PartnerStack", "Partner ecosystem management", "Network and workflow", "B2B SaaS teams"),
         ("Rewardful", "Stripe-focused affiliate tracking", "Simple SaaS setup", "Stripe-based products"),
         ("FirstPromoter", "Affiliate and referral tracking", "SaaS workflows", "Subscription businesses")),
        review("best-affiliate-marketing-software-saas", "Best Affiliate Marketing Software for SaaS", "Affiliate Software Comparison", "best affiliate marketing software for saas", "saas affiliate tracking software", "https://smileaireviewhub.com/",
               ("SaaS companies launching affiliate programs", "partner managers improving operations", "founders comparing tracking platforms"),
               ("comparison by SaaS workflow", "covers tracking and partner operations", "focuses on practical controls"),
               ("attribution requires testing", "payout and tax workflows need review", "pricing and integrations change"),
               ("partner onboarding", "tracking and attribution", "commissions and payouts", "reporting and integrations"), ("Trackdesk", "PartnerStack", "Rewardful", "FirstPromoter"),
               (("Trackdesk review", "/trackdesk-review-2026/"), ("Automation tools", "/category/automation-tools/"), ("SaaS reviews", "/reviews/")))),
    Spec(
        "trackdesk-review-2026", "review-trackdesk-review-2026",
        "Trackdesk Review 2026: Affiliate Tracking, Pricing, Pros & Cons",
        "Trackdesk Review 2026: Pricing, Pros & Cons",
        "Independent Trackdesk review covering affiliate tracking, partner management, pricing checks, pros, cons, and alternatives for SaaS.",
        "trackdesk review", "an independent assessment of Trackdesk for SaaS affiliate and partner-program operations",
        (("Tracking", "Affiliate attribution workflow", "Core capability", "SaaS and ecommerce teams"),
         ("Partner management", "Onboarding and communication", "Operational value", "Program managers"),
         ("Reporting", "Performance visibility", "Decision support", "Growth teams"),
         ("Pricing", "Verify current plans and limits", "Buyer risk", "All buyers")),
        review("trackdesk-review-2026", "Trackdesk", "Affiliate Tracking Software", "trackdesk review", "affiliate tracking software", "https://trackdesk.com",
               ("SaaS companies managing affiliates", "partner managers needing tracking", "businesses comparing affiliate platforms"),
               ("affiliate-focused workflow", "partner operations and reporting", "commercial fit for growing programs"),
               ("attribution needs testing", "integrations require verification", "pricing and limits can change"),
               ("affiliate tracking", "partner onboarding", "commissions and payouts", "reporting"), ("PartnerStack", "Rewardful", "FirstPromoter", "Tapfiliate"),
               (("Best affiliate software for SaaS", "/best-affiliate-marketing-software-saas/"), ("Automation tools", "/category/automation-tools/"), ("SaaS reviews", "/reviews/")))),
]


def comparison_table(spec: Spec) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td><td>{html.escape(d)}</td></tr>"
        for a, b, c, d in spec.comparison
    )
    return (
        '<section class="card" id="comparison"><h2>Comparison</h2>'
        f"<table><tr><th>Option or factor</th><th>Main workflow</th><th>Key consideration</th><th>Best fit</th></tr>{rows}</table></section>"
    )


def useful_detail(spec: Spec) -> str:
    return ""


def schemas(spec: Spec) -> str:
    faq = base.faq(spec.review)
    article = {
        "@context": "https://schema.org", "@type": "Article", "headline": spec.title,
        "description": spec.meta, "url": f"{BASE_URL}/{spec.path}/",
        "author": {"@type": "Person", "name": "Nguyen Quoc Tuan"}, "dateModified": "2026-06-12",
    }
    faq_schema = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq],
    }
    software = {
        "@context": "https://schema.org", "@type": "SoftwareApplication",
        "name": spec.review.brand, "applicationCategory": spec.review.category,
        "url": spec.review.official,
    }
    return "".join(f'<script type="application/ld+json">{json.dumps(item)}</script>' for item in (article, faq_schema, software))


def render(spec: Spec) -> str:
    page = base.render(spec.review)
    canonical = f"{BASE_URL}/{spec.path}/"
    page = re.sub(r"<title>.*?</title>", f"<title>{html.escape(spec.seo_title)}</title>", page, count=1)
    page = re.sub(r'<meta name="description" content=".*?">', f'<meta name="description" content="{html.escape(spec.meta)}">', page, count=1)
    page = re.sub(r'<link rel="canonical" href=".*?">', f'<link rel="canonical" href="{canonical}">', page, count=1)
    page = re.sub(r"<h1>.*?</h1>", f"<h1>{html.escape(spec.title)}</h1>", page, count=1)
    page = page.replace("</head>", schemas(spec) + "</head>", 1)
    page = page.replace(f'data-youtube-placeholder="{spec.review.slug}"', f'data-youtube-placeholder="{spec.video_folder}"', 1)
    page = page.replace('<section class="card"><h2>Key Features and Workflow</h2>', comparison_table(spec) + useful_detail(spec) + '<section class="card"><h2>Key Features and Workflow</h2>', 1)
    page = page.replace("<main class=\"wrap\">", '<main class="wrap"><section class="card"><h2>Table of Contents</h2><p><a href="#comparison">Comparison</a> · <a href="#pricing">Pricing</a> · <a href="#faq">FAQ</a> · <a href="#verdict">Verdict</a></p></section>', 1)
    page = page.replace('<section class="card"><h2>Pricing and Plan Checks</h2>', '<section class="card" id="pricing"><h2>Pricing and Plan Checks</h2>', 1)
    page = page.replace('<section class="card"><h2>FAQ</h2>', '<section class="card" id="faq"><h2>FAQ</h2>', 1)
    page = page.replace('<section class="card"><h2>Final Verdict</h2>', '<section class="card" id="verdict"><h2>Final Verdict</h2>', 1)
    return page


def upsert_video_index() -> None:
    path = ROOT / "data" / "video_article_index.csv"
    fields = ["slug", "title", "output_path", "url"]
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline=""))) if path.exists() else []
    by_slug = {row["slug"]: row for row in rows if row.get("slug")}
    for spec in SPECS:
        by_slug[spec.video_folder] = {"slug": spec.video_folder, "title": spec.title, "output_path": str(SITE / spec.path / "index.html"), "url": f"{BASE_URL}/{spec.path}/"}
    base.write_csv(path, fields, list(by_slug.values()))


def update_upload_links() -> None:
    path = VIDEO / "upload_links.csv"
    _, rows = base.read_csv(path)
    by_folder = {row.get("FolderName", ""): row for row in rows if row.get("FolderName")}
    order = [row.get("FolderName", "") for row in rows if row.get("FolderName")]
    for spec in SPECS:
        current = by_folder.get(spec.video_folder, {})
        current.update({
            "FolderName": spec.video_folder, "PageUrl": f"{BASE_URL}/{spec.path}/",
            "YoutubeVideoUrl": current.get("YoutubeVideoUrl", ""),
            "UploadStatus": current.get("UploadStatus") or "NOT_UPLOADED", "Notes": current.get("Notes", ""),
        })
        by_folder[spec.video_folder] = current
        if spec.video_folder not in order:
            order.append(spec.video_folder)
    base.write_csv(path, base.UPLOAD_FIELDS, [by_folder[name] for name in order])


def update_metadata(spec: Spec) -> None:
    folder = VIDEO / spec.video_folder
    folder.mkdir(parents=True, exist_ok=True)
    article_url = f"{BASE_URL}/{spec.path}/"
    metadata = {
        "title": spec.title,
        "description": f"{spec.meta}\n\nRead the full guide: {article_url}\n\nWebsite: {BASE_URL}",
        "pinned_comment": f"Read the full comparison and related guides: {article_url}",
        "tags": [spec.focus, spec.review.category.lower(), "software review", "Smile AI Review Hub"],
        "hashtags": ["#SoftwareReview", "#AITools", "#SEO"],
        "chapter_timestamps": ["00:00 Introduction", "00:45 Overview", "02:00 Key features", "04:00 Pricing", "05:30 Pros and cons", "07:00 Alternatives", "08:30 Final verdict"],
        "thumbnail_text": spec.title.replace(" 2026", "")[:52],
        "focus_keyword": spec.focus,
        "source_url": article_url,
    }
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (folder / "short_script.txt").write_text(
        f"Considering {spec.review.brand}? Test one real workflow, verify current pricing, and compare {', '.join(spec.review.alternatives[:2])}. Read the full buyer guide at smileaireviewhub.com.\n",
        encoding="utf-8",
    )


def main() -> None:
    report = []
    for spec in SPECS:
        page = render(spec)
        count = base.word_count(page)
        if not 1500 <= count <= 2500:
            raise RuntimeError(f"{spec.path}: article word count {count} is outside 1500-2500")
        for root in (PUBLISHED, SITE):
            target = root / spec.path / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page, encoding="utf-8")
        update_metadata(spec)
        report.append({"title": spec.title, "article_url": f"{BASE_URL}/{spec.path}/", "video_folder": f"video_output/{spec.video_folder}", "focus_keyword": spec.focus, "word_count": count})
        print(f"{spec.path}: {count} words")
    upsert_video_index()
    update_upload_links()
    (VIDEO / "gsc_growth_batch_2026.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
