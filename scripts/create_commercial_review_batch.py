from __future__ import annotations

import csv
import html
import json
import re
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SITE = ROOT / "site_output"
PUBLISHED = DATA / "published_static_pages"
VIDEO = ROOT / "video_output"
BASE_URL = "https://smileaireviewhub.com"
AUTHOR = "Nguyen Quoc Tuan"
UPDATED = "June 2026"
UPLOAD_FIELDS = ["FolderName", "PageUrl", "YoutubeVideoUrl", "UploadStatus", "Notes"]


@dataclass(frozen=True)
class Review:
    slug: str
    brand: str
    category: str
    focus: tuple[str, str]
    official: str
    audience: tuple[str, ...]
    strengths: tuple[str, ...]
    limits: tuple[str, ...]
    features: tuple[str, ...]
    alternatives: tuple[str, ...]
    internal: tuple[tuple[str, str], ...]


REVIEWS = [
    Review("getresponse-review-2026", "GetResponse", "Email Marketing", ("getresponse review", "email marketing software"), "https://www.getresponse.com", ("small businesses building email campaigns", "marketers combining newsletters and automation", "teams comparing all-in-one marketing platforms"), ("broad email marketing workflow", "automation and campaign tools in one platform", "useful commercial intent for growing lists"), ("feature depth can increase setup time", "deliverability depends on list quality and sender practices", "current plan limits require official verification"), ("email campaigns", "marketing automation", "landing pages", "webinars and conversion tools"), ("ActiveCampaign", "Brevo", "ConvertKit", "MailerLite"), (("ActiveCampaign review", "/activecampaign/"), ("Email marketing tools", "/category/email-marketing-tools/"), ("Automation tools", "/category/automation-tools/"))),
    Review("systeme-io-review-2026", "Systeme.io", "Sales Funnel Builder", ("systeme io review", "sales funnel builder"), "https://systeme.io", ("solo entrepreneurs selling digital products", "creators building simple funnels", "small teams consolidating marketing tools"), ("funnel, email, and course tools in one workflow", "accessible starting point for creators", "commercially focused feature set"), ("all-in-one platforms require careful migration planning", "advanced teams may need specialized tools", "plan limits and policies can change"), ("sales funnels", "email campaigns", "online courses", "automation rules"), ("ClickFunnels", "GetResponse", "Kajabi", "MailerLite"), (("Automation tools", "/category/automation-tools/"), ("Website builder tools", "/category/website-builder-tools/"), ("Email marketing tools", "/category/email-marketing-tools/"))),
    Review("clickfunnels-review-2026", "ClickFunnels", "Sales Funnel Software", ("clickfunnels review", "sales funnel software"), "https://www.clickfunnels.com", ("businesses selling through structured funnels", "marketers testing offers and conversion paths", "teams that value funnel templates and sales workflows"), ("strong focus on funnel-based selling", "recognizable ecosystem and training resources", "useful for offer-driven marketing teams"), ("can be more platform than simple sites need", "total cost depends on current plan and add-ons", "results still depend on offer quality and traffic"), ("funnel pages", "checkout workflows", "email follow-up", "offer testing"), ("Systeme.io", "GetResponse", "Shopify", "Webflow"), (("Website builder tools", "/category/website-builder-tools/"), ("Automation tools", "/category/automation-tools/"), ("ActiveCampaign review", "/activecampaign/"))),
    Review("convertkit-review-2026", "ConvertKit", "Creator Email Marketing", ("convertkit review", "creator email marketing"), "https://convertkit.com", ("newsletter creators", "independent publishers", "digital product sellers building audience relationships"), ("creator-focused subscriber workflows", "tagging and automation suited to audience businesses", "clear fit for newsletters and creator products"), ("not every ecommerce or enterprise workflow fits", "pricing grows with audience and plan choices", "buyers should verify current branding and product terms"), ("broadcasts", "subscriber tagging", "visual automation", "creator monetization tools"), ("MailerLite", "Brevo", "GetResponse", "ActiveCampaign"), (("Email marketing tools", "/category/email-marketing-tools/"), ("ActiveCampaign review", "/activecampaign/"), ("Writing tools", "/category/writing-tools/"))),
    Review("brevo-review-2026", "Brevo", "Email Marketing Platform", ("brevo review", "email marketing platform"), "https://www.brevo.com", ("small businesses coordinating email and customer communication", "teams needing transactional and marketing messaging", "buyers comparing contact-based and sending-based models"), ("wide communication toolkit", "useful option for transactional plus marketing email", "commercial fit across small business workflows"), ("interface breadth can require onboarding", "limits vary by plan and sending volume", "deliverability requires responsible list management"), ("email marketing", "transactional messaging", "automation", "sales and customer tools"), ("MailerLite", "GetResponse", "ActiveCampaign", "ConvertKit"), (("Email marketing tools", "/category/email-marketing-tools/"), ("ActiveCampaign review", "/activecampaign/"), ("Automation tools", "/category/automation-tools/"))),
    Review("se-ranking-review-2026", "SE Ranking", "SEO Software", ("se ranking review", "seo software"), "https://seranking.com", ("agencies monitoring multiple SEO campaigns", "small businesses tracking rankings", "marketers comparing broader SEO platforms"), ("broad SEO workflow coverage", "rank tracking and reporting fit", "commercial option for agencies and growing sites"), ("data limits and update frequency vary by plan", "SEO recommendations need human review", "official pricing should be checked before rollout"), ("rank tracking", "website audit", "competitor research", "reporting"), ("Semrush", "Ahrefs", "Mangools", "Surfer SEO"), (("SEO tools", "/category/seo-tools/"), ("Surfer SEO review", "/surfer-seo/"), ("Semrush review", "/semrush/"))),
    Review("mangools-review-2026", "Mangools", "Keyword Research Tool", ("mangools review", "keyword research tool"), "https://mangools.com", ("beginners learning keyword research", "small sites needing approachable SEO tools", "marketers who prefer focused tools over complex suites"), ("approachable keyword research workflow", "focused suite for common SEO checks", "useful shortlist option for smaller teams"), ("large agencies may need deeper datasets", "metrics should be validated against business context", "current limits require official verification"), ("keyword research", "SERP analysis", "rank tracking", "link and site checks"), ("SE Ranking", "Semrush", "Ahrefs", "Surfer SEO"), (("SEO tools", "/category/seo-tools/"), ("Surfer SEO review", "/surfer-seo/"), ("Semrush review", "/semrush/"))),
    Review("grammarly-review-2026", "Grammarly", "AI Writing Assistant", ("grammarly review", "ai writing assistant"), "https://www.grammarly.com", ("professionals polishing everyday writing", "teams standardizing tone and clarity", "writers who want revision assistance across apps"), ("broad writing assistance workflow", "useful clarity and tone feedback", "strong commercial intent for individual and team plans"), ("suggestions still require editorial judgment", "privacy and team policy should be reviewed", "advanced features and limits change by plan"), ("grammar checks", "clarity suggestions", "tone guidance", "team writing controls"), ("ProWritingAid", "QuillBot", "LanguageTool", "Jasper"), (("Writing tools", "/category/writing-tools/"), ("Grammarly pricing", "/pricing/grammarly/"), ("Grammarly vs QuillBot", "/compare/grammarly-vs-quillbot/"))),
    Review("mailerlite-review-2026", "MailerLite", "Email Marketing", ("mailerlite review", "email marketing software"), "https://www.mailerlite.com", ("small businesses and newsletters", "creators wanting approachable email tools", "teams comparing affordable marketing automation"), ("accessible campaign building workflow", "official affiliate program and strong buyer intent", "useful balance of email, pages, and automation"), ("advanced enterprise needs may require another platform", "list growth changes pricing considerations", "official limits and terms must be verified"), ("email campaigns", "automation", "landing pages", "signup forms"), ("Brevo", "ConvertKit", "GetResponse", "ActiveCampaign"), (("Email marketing tools", "/category/email-marketing-tools/"), ("ActiveCampaign review", "/activecampaign/"), ("Automation tools", "/category/automation-tools/"))),
    Review("hostinger-website-builder-review-2026", "Hostinger Website Builder", "AI Website Builder", ("hostinger website builder review", "ai website builder"), "https://www.hostinger.com/website-builder", ("small businesses launching a first website", "creators wanting hosting and site building together", "buyers comparing commercially focused AI website builders"), ("integrated hosting and website workflow", "official affiliate program and strong purchase intent", "useful option for fast small-business launches"), ("complex sites may require a more extensible platform", "renewal and plan details must be verified", "AI output still needs editing and brand review"), ("AI website creation", "templates and editing", "hosting integration", "small-business publishing"), ("Framer", "Durable", "Webflow", "Wix"), (("Website builder tools", "/category/website-builder-tools/"), ("Framer review", "/framer/"), ("Durable review", "/durable/"))),
]


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
    output = []
    seen = set()
    for row in rows:
        value = row.get(key, "")
        if value in additions_by_key:
            merged = dict(row)
            merged.update(additions_by_key[value])
            output.append(merged)
            seen.add(value)
        else:
            output.append(row)
    output.extend(row for value, row in additions_by_key.items() if value not in seen)
    write_csv(path, fields, output)


def paragraphs(review: Review, angle: str, count: int = 3) -> str:
    feature_text = ", ".join(review.features)
    audience_text = ", ".join(review.audience)
    alternatives = ", ".join(review.alternatives)
    templates = [
        f"A practical {review.brand} evaluation starts with the workflow, not the feature list. For {angle}, buyers should map the exact job they want the platform to perform, identify the person responsible for the result, and define what success looks like before starting a trial. {review.brand} is most relevant to {audience_text}. That makes it commercially interesting, but it does not make it the automatic choice for every team.",
        f"The useful question is whether {review.brand} reduces operating friction after the initial setup. Its important capabilities include {feature_text}. Each capability should be tested with a real campaign or project, because a polished demo can hide the time required for configuration, review, permissions, integrations, and ongoing maintenance.",
        f"Buyers should compare {review.brand} with {alternatives} using the same test case. Compare the quality of the output, how quickly a new user can complete the task, what must be checked manually, and how the workflow behaves when volume increases. This produces a more reliable decision than comparing isolated feature checklists.",
        f"Pricing is part of the workflow decision rather than a separate question. Plan names, included usage, seats, credits, contacts, renewal terms, and trial conditions may change. Verify current pricing on the official website and calculate the likely cost at the next stage of growth, not only the entry price shown today.",
        f"Implementation quality matters as much as software capability. Assign an owner, document the initial configuration, create a review checklist, and keep a rollback or export plan. This is especially important when {review.brand} becomes connected to revenue, customer data, published content, or a repeatable team process.",
    ]
    return "".join(f"<p>{html.escape(text)}</p>" for text in templates[:count])


def bullets(items: tuple[str, ...]) -> str:
    return "".join(f"<li>{html.escape(item)}</li>" for item in items)


def internal_links(review: Review) -> str:
    return "".join(f'<li><a href="{url}">{html.escape(label)}</a></li>' for label, url in review.internal)


def faq(review: Review) -> tuple[tuple[str, str], ...]:
    return (
        (f"Is {review.brand} worth it in 2026?", f"{review.brand} is worth testing when its workflow matches a clear business need. Run a small real project and verify current pricing on the official website before committing."),
        (f"What is {review.brand} best for?", f"It is best suited to {', '.join(review.audience)}."),
        (f"How much does {review.brand} cost?", "Pricing, limits, trials, and renewal terms can change. Verify current pricing on the official website."),
        (f"What are the best {review.brand} alternatives?", f"Useful alternatives to compare include {', '.join(review.alternatives)}."),
        (f"Is {review.brand} beginner friendly?", "Beginners can test it with a small workflow, but setup, review, and ongoing maintenance should be included in the evaluation."),
        (f"Can a team use {review.brand} safely?", "Teams should review permissions, data handling, exports, integrations, and approval steps before a broad rollout."),
    )


def render(review: Review) -> str:
    title = f"{review.brand} Review 2026: Features, Pricing, Pros, Cons & Alternatives"
    description = f"Independent {review.focus[0]} for 2026 covering {review.focus[1]}, features, pricing checks, pros, cons, alternatives, FAQ, and final verdict."
    faq_items = faq(review)
    faq_html = "".join(f"<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>" for q, a in faq_items)
    alternatives = "".join(f"<li><strong>{html.escape(name)}</strong>: compare current pricing, workflow depth, integrations, limits, and support.</li>" for name in review.alternatives)
    schema = {
        "@context": "https://schema.org",
        "@type": "Review",
        "name": title,
        "itemReviewed": {"@type": "SoftwareApplication", "name": review.brand, "applicationCategory": review.category},
        "author": {"@type": "Person", "name": AUTHOR, "jobTitle": "Founder - MS Smile AI Review Hub"},
        "dateModified": "2026-06-09",
        "url": f"{BASE_URL}/{review.slug}/",
    }
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(description)}"><meta name="keywords" content="{html.escape(', '.join(review.focus))}">
<meta name="robots" content="index,follow"><link rel="canonical" href="{BASE_URL}/{review.slug}/">
<script type="application/ld+json">{json.dumps(schema)}</script>
<style>:root{{--bg:#f7f9fc;--text:#17202a;--muted:#596579;--line:#dbe3ef;--accent:#0f766e}}*{{box-sizing:border-box}}body{{margin:0;font:16px/1.65 Arial,sans-serif;background:var(--bg);color:var(--text)}}.wrap{{max-width:1080px;margin:auto;padding:0 20px}}nav{{background:#fff;border-bottom:1px solid var(--line)}}nav .wrap{{display:flex;justify-content:space-between;gap:20px;align-items:center;min-height:64px}}nav a,a{{color:var(--accent);font-weight:800;text-decoration:none}}.menu{{display:flex;gap:16px;flex-wrap:wrap}}header{{padding:42px 0 24px;background:#fff}}h1{{font-size:42px;line-height:1.1;margin:12px 0}}h2{{font-size:27px;line-height:1.25;margin:0 0 12px}}h3{{font-size:19px}}p,li{{color:var(--muted)}}.badge{{display:inline-block;padding:5px 10px;border:1px solid #a7f3d0;border-radius:999px;background:#ecfdf5;color:#047857;font-size:13px;font-weight:800;margin-right:6px}}.card{{background:#fff;border:1px solid var(--line);border-radius:8px;padding:20px;margin:18px 0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}.note{{border-left:4px solid #9a3412;background:#fff7ed}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#f1f5f9}}details{{padding:12px 0;border-top:1px solid var(--line)}}summary{{font-weight:900;cursor:pointer}}.youtube-placeholder{{border:2px dashed #94a3b8;background:#f8fafc;text-align:center;padding:30px}}footer{{margin-top:38px;background:#0f172a;color:#dbeafe;padding:28px 0}}footer p{{color:#cbd5e1}}@media(max-width:720px){{h1{{font-size:34px}}nav .wrap{{align-items:flex-start;flex-direction:column;padding:14px 20px}}}}</style></head>
<body><nav><div class="wrap"><a href="/">MS Smile AI Review Hub</a><div class="menu"><a href="/reviews/">Reviews</a><a href="/comparisons/">Comparisons</a><a href="/about-author/">Author</a></div></div></nav>
<header><div class="wrap"><span class="badge">Review</span><span class="badge">{html.escape(review.category)}</span><span class="badge">Last updated: {UPDATED}</span><h1>{html.escape(review.brand)} Review 2026</h1><p>{html.escape(description)}</p><p><strong>Focus keywords:</strong> {html.escape(', '.join(review.focus))}</p></div></header>
<main class="wrap">
<section class="card note"><h2>Affiliate Disclaimer</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you. Editorial conclusions are based on workflow fit, buyer risk, and research checks rather than commission size.</p></section>
<section class="card"><h2>Quick Verdict</h2>{paragraphs(review, "the quick verdict", 1)}<p><a href="{html.escape(review.official)}" rel="nofollow sponsored">Visit the official website and verify current pricing</a>.</p></section>
<section class="card"><h2>{html.escape(review.brand)} Overview</h2>{paragraphs(review, "product fit", 2)}<h3>Related research</h3><ul>{internal_links(review)}</ul></section>
<section class="card"><h2>Key Features and Workflow</h2>{paragraphs(review, "feature and workflow evaluation", 2)}<table><tr><th>Capability</th><th>What to verify</th></tr>{''.join(f'<tr><td>{html.escape(x)}</td><td>Test this capability with a real project, verify current plan access, and document manual review requirements.</td></tr>' for x in review.features)}</table></section>
<section class="grid"><article class="card"><h2>Pros</h2><ul>{bullets(review.strengths)}</ul></article><article class="card"><h2>Cons</h2><ul>{bullets(review.limits)}</ul></article></section>
<section class="card"><h2>Pricing and Plan Checks</h2>{paragraphs(review, "pricing and plan selection", 2)}<p><strong>Pricing rule:</strong> verify current pricing on the official website. Do not make a purchase decision from old screenshots or third-party price tables.</p></section>
<section class="card"><h2>Best For</h2><ul>{bullets(review.audience)}</ul>{paragraphs(review, "best-fit buyer evaluation", 1)}<h2>Not Best For</h2><ul>{bullets(review.limits)}</ul></section>
<section class="card"><h2>Alternatives</h2><ul>{alternatives}</ul>{paragraphs(review, "alternative comparison", 2)}</section>
<section class="card"><h2>Implementation and Buyer Checklist</h2>{paragraphs(review, "implementation planning", 2)}<ol><li>Choose one measurable real workflow.</li><li>Verify current pricing and limits on the official website.</li><li>Test integrations, exports, permissions, and review steps.</li><li>Compare at least two alternatives with the same task.</li><li>Document the decision and reassess after the trial.</li></ol></section>
<section class="card"><h2>Research Methodology</h2>{paragraphs(review, "research methodology", 2)}<p>We prioritize official product information for pricing and policies, compare related tools, separate marketing claims from operational checks, and avoid presenting uncertain pricing as fact.</p></section>
<section class="card"><h2>FAQ</h2>{faq_html}</section>
<section class="card"><h2>Final Verdict</h2>{paragraphs(review, "final purchase decision", 1)}<p><strong>Final recommendation:</strong> shortlist {html.escape(review.brand)} only when its current plan, limits, and workflow match a real business requirement.</p></section>
<section class="card"><h2>CTA: Test the Workflow Before Buying</h2><p>Open the official website, verify current pricing, and test one real workflow. Use the related internal links above to compare alternatives before committing.</p><p><a href="{html.escape(review.official)}" rel="nofollow sponsored">Check {html.escape(review.brand)} on the official website</a></p></section>
<section class="card youtube-placeholder" data-youtube-placeholder="{review.slug}"><h2>Watch Video Review</h2><p>The YouTube review will appear here automatically after a YoutubeVideoUrl is added to <code>video_output/upload_links.csv</code>.</p></section>
<section class="card"><h2>Author</h2><p><strong>{AUTHOR}</strong><br>Founder - MS Smile AI Review Hub</p><p>Last updated: {UPDATED}</p></section>
</main><footer><div class="wrap"><p>MS Smile AI Review Hub - independent AI and SaaS buyer research.</p></div></footer></body></html>"""


def word_count(text: str) -> int:
    plain = re.sub(r"<[^>]+>", " ", text)
    return len(re.findall(r"\b[\w'-]+\b", plain))


def ensure_no_duplicates() -> None:
    roots = [VIDEO, ROOT / "content" / "posts", ROOT / "public" / "posts", SITE, PUBLISHED]
    for review in REVIEWS:
        video_folder = VIDEO / f"review-{review.slug}"
        source_page = PUBLISHED / review.slug / "index.html"
        if video_folder.exists() or source_page.exists():
            raise RuntimeError(f"Refusing to regenerate existing review: {review.slug}")
        for root in roots[1:3]:
            if root.exists() and any(review.slug in path.as_posix() for path in root.rglob("*")):
                raise RuntimeError(f"Refusing to regenerate existing review in {root}: {review.slug}")


def write_pages() -> list[dict[str, str]]:
    rows = []
    for review in REVIEWS:
        page = render(review)
        count = word_count(page)
        if not 1800 <= count <= 3000:
            raise RuntimeError(f"{review.slug} word count outside 1800-3000: {count}")
        for root in (SITE, PUBLISHED):
            target = root / review.slug / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page, encoding="utf-8")
        rows.append(
            {
                "offer_id": review.slug,
                "brand_name": review.brand,
                "review_slug": review.slug,
                "title": f"{review.brand} Review 2026: Features, Pricing, Pros, Cons & Alternatives",
                "output_path": str(SITE / review.slug / "index.html"),
                "status": "built",
                "affiliate_status": "official_or_commercial_intent",
            }
        )
    return rows


def update_upload_template() -> None:
    path = VIDEO / "upload_links.csv"
    _, rows = read_csv(path)
    by_folder = {row.get("FolderName", ""): row for row in rows if row.get("FolderName")}
    for review in REVIEWS:
        folder = f"review-{review.slug}"
        existing = by_folder.get(folder, {})
        existing.update(
            {
                "FolderName": folder,
                "PageUrl": f"{BASE_URL}/{review.slug}/",
                "YoutubeVideoUrl": existing.get("YoutubeVideoUrl", ""),
                "UploadStatus": existing.get("UploadStatus") or "NOT_UPLOADED",
                "Notes": existing.get("Notes", ""),
            }
        )
        by_folder[folder] = existing
    ordered_names = [row.get("FolderName", "") for row in rows if row.get("FolderName")]
    ordered_names.extend(f"review-{r.slug}" for r in REVIEWS if f"review-{r.slug}" not in ordered_names)
    write_csv(path, UPLOAD_FIELDS, [by_folder[name] for name in ordered_names])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true", help="Refresh this batch's article sources without regenerating videos.")
    args = parser.parse_args()
    if not args.overwrite:
        ensure_no_duplicates()
    rows = write_pages()
    upsert(DATA / "review_pages_index.csv", ["offer_id", "brand_name", "review_slug", "title", "output_path", "status", "affiliate_status"], "review_slug", rows)
    update_upload_template()
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reviews": [{"slug": r.slug, "video_folder": f"review-{r.slug}", "focus_keywords": list(r.focus)} for r in REVIEWS],
    }
    (VIDEO / "commercial_review_batch_2026.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for review in REVIEWS:
        print(f"{review.slug}: {word_count(render(review))} words")


if __name__ == "__main__":
    main()
