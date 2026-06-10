from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import create_commercial_review_batch as batch
from create_commercial_review_batch import Review


ROOT = Path(__file__).resolve().parents[1]


REVIEWS = [
    Review("hubspot-review-2026", "HubSpot", "CRM and Marketing Automation", ("hubspot review", "crm marketing hub"), "https://www.hubspot.com", ("growing businesses coordinating CRM and marketing", "teams that want sales and marketing data in one platform", "buyers comparing scalable customer platforms"), ("broad CRM and marketing workflow", "strong ecosystem and integration coverage", "useful starting tools for growing teams"), ("advanced hubs can increase total cost", "implementation requires clear ownership", "plan limits and pricing require official verification"), ("CRM", "Marketing Hub", "sales workflows", "reporting and automation"), ("ActiveCampaign", "Pipedrive", "Brevo", "GetResponse"), (("HubSpot overview", "/hubspot/"), ("CRM tools", "/category/crm-tools/"), ("ActiveCampaign review", "/activecampaign/"))),
    Review("constant-contact-review-2026", "Constant Contact", "Email Marketing", ("constant contact review", "email marketing automation"), "https://www.constantcontact.com", ("small businesses running email campaigns", "organizations managing newsletters and events", "buyers comparing approachable marketing platforms"), ("recognizable small-business email workflow", "campaign and contact-management tools", "commercial fit for local organizations"), ("automation depth may not fit every advanced team", "contact growth affects plan selection", "current pricing requires official verification"), ("email campaigns", "automation", "contact management", "events and landing pages"), ("AWeber", "MailerLite", "Brevo", "ActiveCampaign"), (("Email marketing tools", "/category/email-marketing-tools/"), ("MailerLite review", "/mailerlite-review-2026/"), ("ActiveCampaign review", "/activecampaign/"))),
    Review("aweber-review-2026", "AWeber", "Email Marketing", ("aweber review", "email marketing features"), "https://www.aweber.com", ("creators building newsletters", "small businesses starting email marketing", "buyers comparing established email platforms"), ("focused email marketing workflow", "subscriber and campaign tools", "useful option for creators and small teams"), ("advanced automation needs may require comparison", "list size affects buying decisions", "pricing and limits must be verified"), ("newsletters", "email automation", "signup forms", "landing pages"), ("Constant Contact", "ConvertKit", "MailerLite", "GetResponse"), (("Email marketing tools", "/category/email-marketing-tools/"), ("ConvertKit review", "/convertkit-review-2026/"), ("GetResponse review", "/getresponse-review-2026/"))),
    Review("moz-review-2026", "Moz", "SEO Software", ("moz review", "seo software"), "https://moz.com", ("SEO teams researching keywords and links", "small businesses improving organic visibility", "buyers comparing established SEO platforms"), ("recognized SEO research workflow", "keyword, link, and site analysis tools", "useful educational ecosystem"), ("data depth should be tested against competitors", "recommendations still require human judgment", "current plan limits need verification"), ("keyword research", "link research", "site audits", "rank tracking"), ("Semrush", "Ahrefs", "SE Ranking", "Mangools"), (("SEO tools", "/category/seo-tools/"), ("Semrush vs Ahrefs", "/compare/semrush-vs-ahrefs/"), ("SE Ranking review", "/se-ranking-review-2026/"))),
    Review("ubersuggest-review-2026", "Ubersuggest", "SEO Tool", ("ubersuggest review", "seo tool for beginners"), "https://neilpatel.com/ubersuggest/", ("beginners learning SEO research", "small sites planning content", "buyers comparing approachable keyword tools"), ("accessible SEO research workflow", "keyword and competitor ideas", "commercial fit for smaller sites"), ("larger teams may need deeper datasets", "SEO ideas require validation", "current pricing and limits can change"), ("keyword research", "content ideas", "competitor analysis", "site audit"), ("Mangools", "SE Ranking", "Moz", "Semrush"), (("SEO tools", "/category/seo-tools/"), ("Mangools review", "/mangools-review-2026/"), ("Best AI SEO tools", "/best-ai-seo-tools-2026/"))),
    Review("serpstat-review-2026", "Serpstat", "SEO and PPC Platform", ("serpstat review", "seo ppc keyword research"), "https://serpstat.com", ("marketers combining SEO and PPC research", "agencies researching competitors", "teams comparing all-in-one search platforms"), ("broad search marketing workflow", "keyword and competitor research tools", "useful multi-project commercial intent"), ("interface depth can require onboarding", "data quality should be tested in target markets", "plan limits need official verification"), ("SEO research", "PPC research", "keyword analysis", "competitor analysis"), ("Semrush", "SE Ranking", "Moz", "Ahrefs"), (("SEO tools", "/category/seo-tools/"), ("Semrush review", "/semrush/"), ("SE Ranking review", "/se-ranking-review-2026/"))),
    Review("wordtune-review-2026", "Wordtune", "AI Writing Assistant", ("wordtune review", "ai writing assistant"), "https://www.wordtune.com", ("professionals revising everyday writing", "students and knowledge workers improving clarity", "buyers comparing AI rewriting assistants"), ("focused rewriting and clarity workflow", "useful drafting alternatives", "easy fit for individual writing tasks"), ("suggestions require editorial judgment", "usage policies and privacy need review", "current plans and limits can change"), ("rewriting", "tone adjustment", "summarization", "writing suggestions"), ("Grammarly", "QuillBot", "Jasper", "Copy.ai"), (("Writing tools", "/category/writing-tools/"), ("Grammarly review", "/grammarly-review-2026/"), ("Grammarly vs QuillBot", "/compare/grammarly-vs-quillbot/"))),
    Review("jasper-ai-review-2026", "Jasper AI", "AI Writing and Marketing", ("jasper ai review", "ai writing brand voice"), "https://www.jasper.ai", ("marketing teams managing brand voice", "content teams producing campaign drafts", "buyers comparing commercial AI writing platforms"), ("marketing-focused content workflow", "brand voice and team controls", "useful fit for campaign operations"), ("output needs editorial review", "team adoption requires governance", "current pricing must be verified"), ("AI writing", "brand voice", "campaign workflows", "team collaboration"), ("Copy.ai", "Grammarly", "Wordtune", "ChatGPT"), (("Jasper overview", "/jasper-ai/"), ("Writing tools", "/category/writing-tools/"), ("Jasper vs Copy.ai", "/compare/jasper-vs-copy-ai/"))),
    Review("unbounce-review-2026", "Unbounce", "Landing Page Builder", ("unbounce review", "landing page builder ai"), "https://unbounce.com", ("marketing teams testing landing pages", "agencies managing campaign pages", "buyers focused on conversion workflows"), ("landing-page-focused workflow", "testing and optimization features", "commercial fit for campaign teams"), ("not a full replacement for every website platform", "traffic and testing discipline affect value", "current pricing requires official verification"), ("landing pages", "AI copy and optimization", "A/B testing", "lead capture"), ("Leadpages", "ClickFunnels", "Systeme.io", "Webflow"), (("Website builder tools", "/category/website-builder-tools/"), ("ClickFunnels review", "/clickfunnels-review-2026/"), ("Systeme.io review", "/systeme-io-review-2026/"))),
    Review("leadpages-review-2026", "Leadpages", "Landing Page and Lead Capture", ("leadpages review", "landing pages lead capture"), "https://www.leadpages.com", ("small businesses building lead pages", "creators collecting email subscribers", "buyers comparing focused landing-page tools"), ("focused lead-capture workflow", "landing pages and conversion tools", "useful fit for small marketing teams"), ("advanced funnel needs may require another platform", "results depend on offer and traffic quality", "pricing and limits need verification"), ("landing pages", "lead capture", "templates", "conversion tools"), ("Unbounce", "ClickFunnels", "Systeme.io", "Hostinger Website Builder"), (("Website builder tools", "/category/website-builder-tools/"), ("ClickFunnels review", "/clickfunnels-review-2026/"), ("Hostinger Website Builder review", "/hostinger-website-builder-review-2026/"))),
]


TITLES = {
    "hubspot-review-2026": "HubSpot Review 2026: CRM, Marketing Hub, Pricing, Pros and Cons",
    "constant-contact-review-2026": "Constant Contact Review 2026: Email Marketing, Automation, Pricing and Alternatives",
    "aweber-review-2026": "AWeber Review 2026: Email Marketing Features, Pricing, Pros and Cons",
    "moz-review-2026": "Moz Review 2026: SEO Features, Pricing, Pros, Cons and Alternatives",
    "ubersuggest-review-2026": "Ubersuggest Review 2026: SEO Tool for Beginners, Pricing and Alternatives",
    "serpstat-review-2026": "Serpstat Review 2026: SEO, PPC, Keyword Research and Competitor Analysis",
    "wordtune-review-2026": "Wordtune Review 2026: AI Writing Assistant Features, Pricing and Alternatives",
    "jasper-ai-review-2026": "Jasper AI Review 2026: AI Writing, Brand Voice, Pricing and Alternatives",
    "unbounce-review-2026": "Unbounce Review 2026: Landing Page Builder, AI Features, Pricing and Alternatives",
    "leadpages-review-2026": "Leadpages Review 2026: Landing Pages, Lead Capture, Pricing and Alternatives",
}


def tailored_page(review: Review) -> str:
    page = batch.render(review)
    requested_title = TITLES[review.slug]
    page = re.sub(r"<title>.*?</title>", f"<title>{requested_title}</title>", page, count=1)
    page = re.sub(r"<h1>.*?</h1>", f"<h1>{requested_title}</h1>", page, count=1)
    page = re.sub(
        r'<section class="card"><h2>Implementation and Buyer Checklist</h2>.*?</section>',
        "",
        page,
        count=1,
        flags=re.S,
    )
    page = re.sub(
        r'<section class="card"><h2>Research Methodology</h2>.*?</section>',
        "",
        page,
        count=1,
        flags=re.S,
    )
    count = batch.word_count(page)
    if not 1200 <= count <= 1800:
        raise RuntimeError(f"{review.slug} word count outside 1200-1800: {count}")
    return page


def ensure_new() -> None:
    for review in REVIEWS:
        targets = [
            batch.PUBLISHED / review.slug / "index.html",
            batch.SITE / review.slug / "index.html",
            ROOT / "docs" / review.slug / "index.html",
            batch.VIDEO / f"review-{review.slug}",
        ]
        if any(target.exists() for target in targets):
            raise RuntimeError(f"Refusing to overwrite existing article or video: {review.slug}")


def main() -> None:
    ensure_new()
    rows = []
    for review in REVIEWS:
        page = tailored_page(review)
        for root in (batch.PUBLISHED, batch.SITE):
            target = root / review.slug / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page, encoding="utf-8")
        rows.append(
            {
                "offer_id": review.slug,
                "brand_name": review.brand,
                "review_slug": review.slug,
                "title": TITLES[review.slug],
                "output_path": str(batch.SITE / review.slug / "index.html"),
                "status": "built",
                "affiliate_status": "commercial_intent",
            }
        )
        print(f"{review.slug}: {batch.word_count(page)} words")

    batch.REVIEWS = REVIEWS
    batch.upsert(batch.DATA / "review_pages_index.csv", ["offer_id", "brand_name", "review_slug", "title", "output_path", "status", "affiliate_status"], "review_slug", rows)
    batch.update_upload_template()
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reviews": [{"slug": r.slug, "video_folder": f"review-{r.slug}", "title": TITLES[r.slug], "focus_keywords": list(r.focus)} for r in REVIEWS],
    }
    (batch.VIDEO / "next_seo_review_batch_2026.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
