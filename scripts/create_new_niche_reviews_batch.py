from __future__ import annotations

import argparse
import csv
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
PUBLISHED = ROOT / "data" / "published_static_pages"
VIDEO = ROOT / "video_output"
BASE_URL = "https://smileaireviewhub.com"
AUTHOR = "Nguyen Quoc Tuan"


@dataclass(frozen=True)
class Topic:
    slug: str
    brand: str
    category: str
    focus: str
    secondary: str
    official: str
    summary: str
    audience: tuple[str, ...]
    features: tuple[str, ...]
    strengths: tuple[str, ...]
    limits: tuple[str, ...]
    alternatives: tuple[str, ...]
    internal: tuple[tuple[str, str], ...]

    @property
    def folder(self) -> str:
        return f"review-{self.slug}"

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.slug}/"


TOPICS = [
    Topic(
        "neuronwriter-review-2026", "NeuronWriter", "SEO Content Optimization", "neuronwriter review",
        "neuronwriter pricing and alternatives", "https://neuronwriter.com",
        "a content optimization platform for planning, drafting, and improving search-focused articles",
        ("independent publishers building an SEO workflow", "small content teams comparing optimization tools", "editors who want structured recommendations without an enterprise suite"),
        ("content briefs", "SERP-based recommendations", "draft optimization", "content planning"),
        ("focused optimization workflow", "practical fit for smaller publishing teams", "useful alternative to larger SEO suites"),
        ("recommendations still need editorial judgment", "search results and product limits change", "buyers must verify current pricing and credit rules"),
        ("Surfer SEO", "Frase", "Clearscope", "SE Ranking"),
        (("Surfer SEO review", "/review/surfer-seo-review-2026/"), ("Surfer SEO alternatives", "/surfer-seo-alternatives/"), ("Best AI SEO tools", "/best-ai-seo-tools-2026/")),
    ),
    Topic(
        "lowfruits-review-2026", "LowFruits", "Keyword Research", "lowfruits review",
        "low competition keyword research tool", "https://lowfruits.io",
        "a keyword research tool designed to surface search results that may be less difficult to compete for",
        ("small sites looking for realistic keyword opportunities", "niche publishers prioritizing long-tail research", "SEO teams validating low-competition query ideas"),
        ("long-tail keyword discovery", "SERP weakness analysis", "keyword clustering", "competition review"),
        ("clear focus on attainable search opportunities", "useful research angle for smaller sites", "helps prioritize manual SERP review"),
        ("weak-looking SERPs do not guarantee rankings", "credits and data limits require checking", "content quality and authority still matter"),
        ("KeySearch", "Mangools", "Ubersuggest", "SE Ranking"),
        (("Mangools review", "/mangools-review-2026/"), ("Ubersuggest review", "/ubersuggest-review-2026/"), ("SEO tools", "/category/seo-tools/")),
    ),
    Topic(
        "keysearch-review-2026", "KeySearch", "Keyword Research", "keysearch review",
        "affordable keyword research tool", "https://www.keysearch.co",
        "an SEO research platform aimed at keyword discovery, competition checks, and rank monitoring",
        ("bloggers comparing affordable SEO tools", "small businesses building a keyword plan", "publishers who need focused research rather than a large suite"),
        ("keyword research", "competition analysis", "rank tracking", "content research"),
        ("approachable workflow for smaller teams", "combines several common SEO checks", "commercially relevant for budget-conscious publishers"),
        ("metrics require human interpretation", "dataset depth may differ from larger platforms", "current pricing and limits must be verified"),
        ("LowFruits", "Mangools", "Ubersuggest", "Semrush"),
        (("Mangools review", "/mangools-review-2026/"), ("Semrush vs Ahrefs", "/compare/semrush-vs-ahrefs/"), ("SEO tools", "/category/seo-tools/")),
    ),
    Topic(
        "link-whisper-review-2026", "Link Whisper", "Internal Linking", "link whisper review",
        "wordpress internal linking plugin", "https://linkwhisper.com",
        "a WordPress-focused internal linking assistant that helps publishers find and manage link opportunities",
        ("content-heavy WordPress sites", "publishers auditing internal links", "SEO teams that need repeatable link maintenance"),
        ("internal link suggestions", "orphaned content checks", "link reporting", "link workflow management"),
        ("focused solution for a tedious SEO task", "useful for large article libraries", "supports repeatable internal-link reviews"),
        ("suggestions require contextual review", "WordPress-specific fit limits some buyers", "automation cannot replace information architecture"),
        ("Yoast internal linking", "Rank Math", "Ahrefs site audit", "manual internal-link audits"),
        (("Best AI SEO tools", "/best-ai-seo-tools-2026/"), ("SEO tools", "/category/seo-tools/"), ("Surfer SEO review", "/review/surfer-seo-review-2026/")),
    ),
    Topic(
        "tally-forms-review-2026", "Tally Forms", "Online Form Builder", "tally forms review",
        "tally forms pricing and alternatives", "https://tally.so",
        "a lightweight online form builder used for surveys, lead capture, applications, and internal workflows",
        ("creators building simple forms quickly", "small teams collecting structured responses", "operators connecting forms to automation workflows"),
        ("form creation", "conditional logic", "embeds and sharing", "workflow integrations"),
        ("fast and approachable form-building experience", "useful across creator and business workflows", "flexible starting point for structured data collection"),
        ("advanced governance needs require testing", "integration behavior should be validated", "sensitive-data workflows need careful review"),
        ("Typeform", "Jotform", "Google Forms", "Fillout"),
        (("Automation tools", "/category/automation-tools/"), ("Zapier review", "/zapier/"), ("Make vs Zapier", "/compare/make-vs-zapier/")),
    ),
    Topic(
        "plausible-analytics-review-2026", "Plausible Analytics", "Web Analytics", "plausible analytics review",
        "privacy friendly web analytics", "https://plausible.io",
        "a streamlined web analytics platform positioned around clear reporting and a privacy-conscious approach",
        ("small websites that want focused traffic reporting", "publishers reducing analytics complexity", "teams comparing privacy-conscious analytics platforms"),
        ("traffic dashboards", "goal and event tracking", "campaign measurement", "privacy-oriented analytics workflow"),
        ("focused reporting without excessive dashboard complexity", "useful for content and marketing sites", "clear alternative to larger analytics stacks"),
        ("not every advanced analysis workflow will fit", "implementation and consent obligations vary", "buyers should verify current data and hosting terms"),
        ("Fathom Analytics", "Google Analytics", "Matomo", "Simple Analytics"),
        (("SEO tools", "/category/seo-tools/"), ("Best AI SEO tools", "/best-ai-seo-tools-2026/"), ("Website builder tools", "/category/website-builder-tools/")),
    ),
    Topic(
        "fathom-analytics-review-2026", "Fathom Analytics", "Web Analytics", "fathom analytics review",
        "simple privacy focused analytics", "https://usefathom.com",
        "a simple website analytics platform for teams that want practical reporting with less operational complexity",
        ("creators monitoring a portfolio of sites", "businesses wanting a simpler analytics dashboard", "teams comparing privacy-focused measurement tools"),
        ("site traffic reporting", "event tracking", "campaign attribution", "multi-site analytics"),
        ("easy-to-scan reporting", "focused workflow for common website questions", "useful commercial alternative to complex analytics suites"),
        ("specialized analysis needs may require another tool", "privacy requirements still need legal review", "pricing and plan limits can change"),
        ("Plausible Analytics", "Google Analytics", "Matomo", "Simple Analytics"),
        (("Website builder tools", "/category/website-builder-tools/"), ("SEO tools", "/category/seo-tools/"), ("Best Website Builder", "/best-website-builder-2026/")),
    ),
    Topic(
        "bunny-net-review-2026", "Bunny.net", "CDN and Web Infrastructure", "bunny.net review",
        "bunny cdn pricing and alternatives", "https://bunny.net",
        "a web infrastructure platform offering content delivery, storage, video delivery, and related performance services",
        ("website owners comparing CDN options", "developers optimizing content delivery", "publishers evaluating performance infrastructure"),
        ("content delivery network", "storage", "video delivery", "performance and security controls"),
        ("broad infrastructure toolkit", "useful option for performance-conscious sites", "commercially relevant for growing web properties"),
        ("configuration requires technical care", "usage-based costs require modeling", "security and cache rules need ongoing review"),
        ("Cloudflare", "KeyCDN", "Amazon CloudFront", "Fastly"),
        (("Website builder tools", "/category/website-builder-tools/"), ("Hidden AI infrastructure companies", "/hidden-ai-infrastructure-companies-2026/"), ("Webflow pros and cons", "/webflow-pros-and-cons/")),
    ),
    Topic(
        "senja-review-2026", "Senja", "Testimonial Software", "senja review",
        "testimonial collection software", "https://senja.io",
        "a testimonial collection and display platform for creators, SaaS teams, and online businesses",
        ("SaaS teams collecting customer proof", "creators organizing testimonials", "marketers adding social proof to landing pages"),
        ("testimonial collection", "testimonial management", "widgets and embeds", "shareable proof assets"),
        ("focused customer-proof workflow", "useful for organizing scattered testimonials", "practical fit for landing pages and creator businesses"),
        ("testimonial quality still depends on real customers", "consent and accuracy require governance", "widget and plan limits must be verified"),
        ("Testimonial.to", "Trustmary", "Vocal Video", "manual testimonial workflows"),
        (("Website builder tools", "/category/website-builder-tools/"), ("Best Website Builder", "/best-website-builder-2026/"), ("Unbounce review", "/unbounce-review-2026/")),
    ),
    Topic(
        "beehiiv-review-2026", "beehiiv", "Newsletter Platform", "beehiiv review",
        "beehiiv pricing and alternatives", "https://www.beehiiv.com",
        "a newsletter publishing platform built for audience growth, email publishing, and newsletter monetization workflows",
        ("newsletter creators building an owned audience", "publishers comparing newsletter platforms", "small media teams testing growth and monetization workflows"),
        ("newsletter publishing", "audience growth tools", "analytics", "monetization workflows"),
        ("purpose-built newsletter workflow", "useful growth features for publishers", "strong commercial intent among creator businesses"),
        ("not every traditional email-marketing workflow fits", "deliverability depends on responsible practices", "pricing and monetization terms require verification"),
        ("Kit", "MailerLite", "Substack", "Ghost"),
        (("MailerLite review", "/mailerlite-review-2026/"), ("ConvertKit review", "/convertkit-review-2026/"), ("Email marketing tools", "/category/email-marketing-tools/")),
    ),
]


def plain_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", re.sub(r"<[^>]+>", " ", text)))


def paragraph(topic: Topic, purpose: str, detail: str, index: int) -> str:
    feature_text = ", ".join(topic.features)
    audience_text = ", ".join(topic.audience)
    alternative_text = ", ".join(topic.alternatives)
    variants = [
        f"A useful {topic.brand} evaluation begins with a specific job rather than a feature checklist. For {purpose}, define the current process, the person who owns the result, the time spent today, and the failure that would make the purchase regrettable. {topic.brand} is {topic.summary}. That positioning makes it relevant to {audience_text}, but relevance is only the first filter. The tool should earn a place in the workflow by making a repeated task clearer, faster, or easier to measure without creating a larger maintenance burden.",
        f"The practical test for {detail} is whether a new user can complete a realistic task and explain what happened. Important capabilities include {feature_text}. Each one should be tested with the same source material, the same success criteria, and a written review checklist. A polished demo can hide setup work, data cleanup, permissions, integrations, and manual quality control. Recording those hidden steps produces a more honest estimate of value than comparing marketing pages.",
        f"Buyers should compare {topic.brand} with {alternative_text} using one repeatable scenario. Measure completion time, output quality, correction effort, reporting clarity, and the ease of exporting or changing tools later. The cheapest entry plan is not automatically the lowest-cost choice if it requires more manual work or blocks an important capability. The most expensive option is not automatically better if the team uses only a small part of it.",
        f"Risk matters during {purpose}. Product capabilities, limits, and pricing can change after an article is published, so current details must be verified on the official website. Teams should also review data handling, account ownership, cancellation steps, exports, and any dependency created by integrations. A short trial is useful only when it resembles the intended production workflow. Testing an unrealistic sample creates confidence without evidence.",
        f"A disciplined rollout for {topic.brand} starts small. Assign an owner, choose one measurable use case, document the baseline, and decide in advance what result would justify continuing. After the first test, review errors and exceptions rather than only the successful path. This approach is slower than buying from a feature list, but it protects the team from adopting software that looks efficient while quietly moving work into review, repair, or administration.",
    ]
    return f"<p>{html.escape(variants[index % len(variants)])}</p>"


def section(topic: Topic, title: str, purpose: str, details: tuple[str, ...], start: int) -> str:
    paragraphs = "".join(paragraph(topic, purpose, detail, start + i) for i, detail in enumerate(details))
    bullets = "".join(f"<li><strong>{html.escape(detail.title())}:</strong> test it with a real workflow and document the result.</li>" for detail in details)
    return f'<section class="card"><h2>{html.escape(title)}</h2>{paragraphs}<ul>{bullets}</ul></section>'


def schemas(topic: Topic, title: str, description: str, faqs: tuple[tuple[str, str], ...]) -> str:
    article = {
        "@context": "https://schema.org", "@type": "Article", "headline": title, "description": description,
        "url": topic.url, "dateModified": "2026-06-13",
        "author": {"@type": "Person", "name": AUTHOR, "jobTitle": "Founder - MS Smile AI Review Hub"},
        "publisher": {"@type": "Organization", "name": "MS Smile AI Review Hub", "url": BASE_URL},
    }
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs
    ]}
    return "".join(f'<script type="application/ld+json">{json.dumps(item, ensure_ascii=False)}</script>' for item in (article, faq))


def render(topic: Topic) -> str:
    title = f"{topic.brand} Review 2026: Features, Pricing, Pros, Cons & Alternatives"
    description = f"Independent {topic.focus} covering features, pricing checks, pros, cons, alternatives, and practical buyer fit."
    faqs = (
        (f"Is {topic.brand} worth testing in 2026?", f"It is worth testing when its workflow matches a repeated business need. Verify current pricing and use a real project before committing."),
        (f"Who is {topic.brand} best for?", f"It is most relevant to {', '.join(topic.audience)}."),
        (f"How much does {topic.brand} cost?", "Pricing and plan limits can change. Verify current pricing on the official website before buying."),
        (f"What are the best {topic.brand} alternatives?", f"Useful alternatives to compare include {', '.join(topic.alternatives)}."),
        (f"What should teams test first?", f"Start with {topic.features[0]} and {topic.features[1]} using a measurable real workflow."),
        (f"What is the main risk?", f"The main risks include {', '.join(topic.limits)}."),
    )
    pros = "".join(f"<li>{html.escape(x)}</li>" for x in topic.strengths)
    cons = "".join(f"<li>{html.escape(x)}</li>" for x in topic.limits)
    links = "".join(f'<li><a href="{url}">{html.escape(label)}</a></li>' for label, url in topic.internal)
    comparison = "".join(
        f"<tr><td>{html.escape(name)}</td><td>Compare workflow depth, current pricing, limits, integrations, exports, and support.</td><td>Run the same real task before deciding.</td></tr>"
        for name in (topic.brand, *topic.alternatives)
    )
    faq_html = "".join(f"<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>" for q, a in faqs)
    content = [
        section(topic, "Overview", "understanding product fit", (topic.summary, topic.audience[0], topic.audience[1]), 0),
        section(topic, "How We Evaluated This Tool", "research methodology", ("official product information", "realistic workflow design", "buyer risk and alternatives"), 2),
        section(topic, "Key Features", "feature evaluation", topic.features, 4),
        section(topic, "Setup and First-Week Experience", "initial setup", ("account setup", "first useful result", "permissions and ownership"), 1),
        section(topic, "Daily Workflow Fit", "daily operations", ("repeatability", "review effort", "collaboration and handoff"), 3),
        section(topic, "Data, Reporting, and Measurement", "measuring outcomes", ("reporting clarity", "data exports", "decision usefulness"), 0),
        section(topic, "Integrations and Automation", "integration planning", ("integration reliability", "failure handling", "maintenance ownership"), 2),
        section(topic, "Pricing and Total Cost", "pricing evaluation", ("entry plan", "growth-stage cost", "hidden operating effort"), 4),
        section(topic, "Best Use Cases", "best-fit use cases", topic.audience, 1),
        section(topic, "When It Is Not the Best Choice", "poor-fit use cases", topic.limits, 3),
        section(topic, "Implementation Checklist", "responsible rollout", ("define success", "test exceptions", "document ownership"), 0),
        section(topic, "Security, Privacy, and Governance", "risk review", ("data handling", "access control", "retention and exports"), 2),
        section(topic, "Support and Long-Term Ownership", "long-term operations", ("support quality", "documentation", "exit planning"), 4),
        section(topic, "Alternatives and Decision Framework", "alternative comparison", topic.alternatives, 1),
        section(topic, "Final Buyer Checklist", "purchase decision", ("verify official pricing", "compare a real task", "document the final decision"), 3),
    ]
    feature_prompt = (
        f"Editorial software review feature image for {topic.brand}, showing the real workflow category "
        f"{topic.category}, clean professional interface context, no logos copied, no gradients, high contrast, 16:9."
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(description)}"><meta name="robots" content="index,follow">
<link rel="canonical" href="{topic.url}">{schemas(topic, title, description, faqs)}
<style>:root{{--bg:#f5f7fa;--text:#172033;--muted:#526078;--line:#d8e0ea;--accent:#087f5b}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:17px/1.68 Arial,sans-serif}}a{{color:var(--accent);font-weight:700}}.wrap{{max-width:1100px;margin:auto;padding:0 22px}}nav{{background:#fff;border-bottom:1px solid var(--line);padding:18px 0}}nav .wrap{{display:flex;justify-content:space-between;gap:20px}}header{{background:#fff;padding:52px 0 34px}}h1{{font-size:44px;line-height:1.12;max-width:900px}}h2{{font-size:28px;line-height:1.2}}p,li{{color:var(--muted)}}.card{{background:#fff;border:1px solid var(--line);border-radius:8px;padding:24px;margin:20px 0}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:13px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#eef3f7}}.note{{border-left:5px solid #b45309}}details{{border-top:1px solid var(--line);padding:14px 0}}summary{{font-weight:800}}footer{{background:#13202d;color:#fff;padding:30px 0;margin-top:40px}}@media(max-width:760px){{h1{{font-size:34px}}.grid{{grid-template-columns:1fr}}}}</style></head>
<body><nav><div class="wrap"><a href="/">MS Smile AI Review Hub</a><span><a href="/reviews/">Reviews</a> &nbsp; <a href="/comparisons/">Comparisons</a></span></div></nav>
<header><div class="wrap"><p><strong>{html.escape(topic.category)} Review · Updated June 2026</strong></p><h1>{html.escape(title)}</h1>
<p>{html.escape(description)} This guide prioritizes real workflow fit, verifiable details, and buyer risk rather than vendor claims.</p></div></header>
<main class="wrap">
<section class="card note"><h2>Affiliate Disclosure</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you. This does not change the evaluation method. Verify current pricing, terms, and product limits on the official website.</p></section>
<section class="card"><h2>Table of Contents</h2><p>Overview · methodology · features · setup · daily workflow · reporting · integrations · pricing · pros and cons · best use cases · alternatives · FAQ · final verdict</p></section>
<section class="card"><h2>Quick Verdict</h2>{paragraph(topic, "making a fast but responsible shortlist", topic.summary, 0)}
<p><a href="{html.escape(topic.official)}" rel="nofollow sponsored">Visit the official website and verify current pricing</a>.</p></section>
{''.join(content[:8])}
<section class="grid"><article class="card"><h2>Pros</h2><ul>{pros}</ul>{paragraph(topic, "understanding the advantages", topic.strengths[0], 2)}</article>
<article class="card"><h2>Cons</h2><ul>{cons}</ul>{paragraph(topic, "understanding the limitations", topic.limits[0], 3)}</article></section>
{''.join(content[8:14])}
<section class="card"><h2>Comparison Table</h2><table><tr><th>Option</th><th>What to compare</th><th>Decision rule</th></tr>{comparison}</table></section>
{content[14]}
<section class="card"><h2>Related Research</h2><ul>{links}</ul></section>
<section class="card"><h2>FAQ</h2>{faq_html}</section>
<section class="card"><h2>Final Verdict</h2>{paragraph(topic, "reaching a final decision", topic.summary, 4)}
<p>{html.escape(topic.brand)} deserves a shortlist only when its current capabilities and terms match a measurable workflow. Test it against alternatives, document the result, and avoid treating a successful demo as proof of long-term fit.</p></section>
<section class="card"><h2>Feature Image Prompt</h2><p>{html.escape(feature_prompt)}</p></section>
<section class="card"><h2>Author</h2><p><strong>{AUTHOR}</strong><br>Founder - MS Smile AI Review Hub</p></section>
</main><footer><div class="wrap">Independent AI and SaaS buyer research · <a href="/contact/">Contact</a></div></footer></body></html>"""


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def upsert(path: Path, fields: list[str], key: str, additions: list[dict[str, str]]) -> None:
    old_fields, rows = read_csv(path)
    fields = list(dict.fromkeys((old_fields or fields) + fields))
    additions_by_key = {row[key]: row for row in additions}
    output, seen = [], set()
    for row in rows:
        value = row.get(key, "")
        if value in additions_by_key:
            row.update(additions_by_key[value])
            seen.add(value)
        output.append(row)
    output.extend(row for value, row in additions_by_key.items() if value not in seen)
    write_csv(path, fields, output)


def assert_new() -> None:
    roots = (SITE, PUBLISHED, VIDEO, ROOT / "content", ROOT / "public")
    conflicts = []
    for topic in TOPICS:
        for root in roots:
            if not root.exists():
                continue
            for candidate in (root / topic.slug, root / topic.folder):
                if candidate.exists():
                    conflicts.append(str(candidate))
    if conflicts:
        raise RuntimeError("Refusing to duplicate existing content:\n" + "\n".join(conflicts))


def update_rss() -> None:
    path = SITE / "rss.xml"
    text = path.read_text(encoding="utf-8") if path.exists() else f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>MS Smile AI Review Hub</title><link>{BASE_URL}/</link></channel></rss>'
    items = []
    for topic in TOPICS:
        if f"<guid>{topic.url}</guid>" in text:
            continue
        items.append(f"<item><title>{html.escape(topic.brand)} Review 2026</title><link>{topic.url}</link><guid>{topic.url}</guid><description>{html.escape(topic.summary)}</description></item>")
    text = text.replace("</channel>", "".join(items) + "</channel>")
    path.write_text(text, encoding="utf-8")


def write_assets(topic: Topic) -> None:
    folder = VIDEO / topic.folder
    folder.mkdir(parents=True, exist_ok=True)
    feature_prompt = f"Professional editorial feature image for {topic.brand} review, {topic.category} workflow, clear real-world software context, 16:9, no copied logo, no gradients."
    thumb_prompt = f"YouTube thumbnail for {topic.brand} Review 2026, bold readable text '{topic.brand} REVIEW', professional software-review layout, mobile readable, high contrast, 16:9."
    (folder / "feature_image_prompt.txt").write_text(feature_prompt + "\n", encoding="utf-8")
    (folder / "thumbnail_prompt.txt").write_text(thumb_prompt + "\n", encoding="utf-8")
    (folder / "youtube_title.txt").write_text(f"{topic.brand} Review 2026: Features, Pricing, Pros & Cons\n", encoding="utf-8")
    (folder / "youtube_description.txt").write_text(f"Independent {topic.focus}. Read the full review: {topic.url}\n\nWebsite: {BASE_URL}\n", encoding="utf-8")
    (folder / "youtube_tags.txt").write_text(", ".join((topic.focus, topic.secondary, topic.category, "software review 2026")) + "\n", encoding="utf-8")
    (folder / "pinned_comment.txt").write_text(f"Read the full review and compare alternatives: {topic.url}\n", encoding="utf-8")


def srt_timestamp(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def finalize_video_assets() -> None:
    for topic in TOPICS:
        folder = VIDEO / topic.folder
        vi_text = (folder / "subtitles_vi.txt").read_text(encoding="utf-8", errors="ignore").strip()
        if not vi_text:
            raise RuntimeError(f"Missing Vietnamese subtitle text: {folder}")
        chunks = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", vi_text) if part.strip()]
        lines, current = [], 0.0
        for index, chunk in enumerate(chunks, start=1):
            duration = max(2.5, min(7.0, len(chunk.split()) / 2.7))
            lines.extend((str(index), f"{srt_timestamp(current)} --> {srt_timestamp(current + duration)}", chunk, ""))
            current += duration
        (folder / "subtitles_vi.srt").write_text("\n".join(lines), encoding="utf-8")
        print(f"{topic.folder}: subtitles_vi.srt ready")
        for root in (SITE, PUBLISHED):
            page = root / topic.slug / "index.html"
            text = page.read_text(encoding="utf-8", errors="ignore")
            if "<h2>CTA: Compare Before You Commit</h2>" not in text:
                cta = (
                    '<section class="card"><h2>CTA: Compare Before You Commit</h2>'
                    f'<p>Verify current details on the official website, then compare {html.escape(topic.brand)} '
                    'with at least two alternatives using the same real workflow.</p></section>'
                )
                text = text.replace('<section class="card"><h2>Feature Image Prompt</h2>', cta + '<section class="card"><h2>Feature Image Prompt</h2>', 1)
                page.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize-assets", action="store_true")
    args = parser.parse_args()
    if args.finalize_assets:
        finalize_video_assets()
        return
    assert_new()
    review_rows, video_rows, upload_rows, report = [], [], [], []
    for topic in TOPICS:
        page = render(topic)
        count = plain_words(page)
        if count < 3000:
            raise RuntimeError(f"{topic.slug} is below 3000 words: {count}")
        for root in (SITE, PUBLISHED):
            target = root / topic.slug / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page, encoding="utf-8")
        write_assets(topic)
        review_rows.append({"offer_id": topic.slug, "brand_name": topic.brand, "review_slug": topic.slug, "title": f"{topic.brand} Review 2026", "output_path": str(SITE / topic.slug / "index.html"), "status": "built", "affiliate_status": "verify_official_program"})
        video_rows.append({"slug": topic.folder, "title": f"{topic.brand} Review 2026", "output_path": str(SITE / topic.slug / "index.html"), "url": topic.url})
        upload_rows.append({"FolderName": topic.folder, "PageUrl": topic.url, "YoutubeVideoUrl": "", "UploadStatus": "NOT_UPLOADED", "Notes": "New niche review batch"})
        report.append({"title": f"{topic.brand} Review 2026", "slug": topic.slug, "article_url": topic.url, "word_count": count, "video_folder": f"video_output/{topic.folder}", "focus_keyword": topic.focus})
        print(f"{topic.slug}: {count} words")
    upsert(ROOT / "data" / "review_pages_index.csv", ["offer_id", "brand_name", "review_slug", "title", "output_path", "status", "affiliate_status"], "review_slug", review_rows)
    upsert(ROOT / "data" / "video_article_index.csv", ["slug", "title", "output_path", "url"], "slug", video_rows)
    upsert(VIDEO / "upload_links.csv", ["FolderName", "PageUrl", "YoutubeVideoUrl", "UploadStatus", "Notes"], "FolderName", upload_rows)
    update_rss()
    (VIDEO / "new_niche_reviews_batch_report.json").write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "articles": report}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
