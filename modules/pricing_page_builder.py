from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

from config import settings
from modules.affiliate_links import load_affiliate_links, save_affiliate_links
from modules.comparison_page_builder import build_tool_map
from modules.programmatic_page_utils import affiliate_disclosure, breadcrumb_schema, faq_html, faq_schema, shell, write_page


INDEX_COLUMNS = [
    "tool_slug",
    "tool_name",
    "title",
    "output_path",
    "status",
    "affiliate_status",
]


PRICING_TOOLS = [
    "cursor",
    "github-copilot",
    "semrush",
    "make",
    "zapier",
    "canva",
    "activecampaign",
    "mailchimp",
    "pictory",
    "grammarly",
]


PRICING_FALLBACK_TOOLS = {
    "cursor": {"offer_id": "cursor", "brand_name": "Cursor", "niche": "AI Coding", "website": "https://cursor.com"},
    "github-copilot": {"offer_id": "github-copilot", "brand_name": "GitHub Copilot", "niche": "AI Coding", "website": "https://github.com/features/copilot"},
    "semrush": {"offer_id": "semrush", "brand_name": "Semrush", "niche": "AI SEO", "website": "https://www.semrush.com"},
    "make": {"offer_id": "make", "brand_name": "Make", "niche": "Automation", "website": "https://www.make.com"},
    "zapier": {"offer_id": "zapier", "brand_name": "Zapier", "niche": "Automation", "website": "https://zapier.com"},
    "canva": {"offer_id": "canva", "brand_name": "Canva", "niche": "AI Design", "website": "https://www.canva.com"},
    "activecampaign": {"offer_id": "activecampaign", "brand_name": "ActiveCampaign", "niche": "Email Marketing", "website": "https://www.activecampaign.com"},
    "mailchimp": {"offer_id": "mailchimp", "brand_name": "Mailchimp", "niche": "Email Marketing", "website": "https://mailchimp.com"},
    "pictory": {"offer_id": "pictory", "brand_name": "Pictory", "niche": "AI Video", "website": "https://pictory.ai"},
    "grammarly": {"offer_id": "grammarly", "brand_name": "Grammarly", "niche": "AI Writing", "website": "https://www.grammarly.com"},
}


EXISTING_REVIEW_SLUGS = {
    "activecampaign",
    "adcreative-ai",
    "canva",
    "copy-ai",
    "cursor",
    "descript",
    "durable",
    "elevenlabs",
    "framer",
    "gamma",
    "github-copilot",
    "hubspot",
    "jasper",
    "jasper-ai",
    "make",
    "notion",
    "notion-ai",
    "pipedrive",
    "pipedrive-crm",
    "reclaim-ai",
    "runway",
    "semrush",
    "surfer-seo",
    "synthesia",
    "webflow",
    "webflow-ai",
    "zapier",
}


def generate_pricing_pages(output: Path, offer_scores: pd.DataFrame | None = None) -> list[dict[str, str]]:
    tool_map = build_tool_map(offer_scores)
    for slug, data in PRICING_FALLBACK_TOOLS.items():
        tool_map.setdefault(slug, normalize_tool(data))
    ensure_pricing_tracking_links(tool_map)

    pages: list[dict[str, str]] = []
    index_rows: list[dict[str, str]] = []
    for slug in PRICING_TOOLS:
        tool = tool_map.get(slug)
        if not tool:
            continue
        tool = normalize_tool(tool)
        page_path = write_page(output, f"pricing/{slug}", render_pricing_page(tool, related_links_for(slug)))
        title = pricing_title(tool)
        affiliate_status = affiliate_status_for(slug)
        pages.append({"slug": f"pricing/{slug}", "title": title, "type": "pricing_page"})
        index_rows.append(
            {
                "tool_slug": slug,
                "tool_name": tool["brand_name"],
                "title": title,
                "output_path": str(page_path),
                "status": "built",
                "affiliate_status": affiliate_status,
            }
        )

    safe_write_index(pd.DataFrame(index_rows, columns=INDEX_COLUMNS))
    return pages


def normalize_tool(row: dict) -> dict[str, str]:
    slug = str(row.get("offer_id") or row.get("tool_slug") or "").strip()
    brand = str(row.get("brand_name") or row.get("tool_name") or slug.replace("-", " ").title()).strip()
    niche = str(row.get("niche") or "AI/SaaS").strip()
    website = str(row.get("website") or row.get("official_url") or "").strip()
    score = str(row.get("total_score") or row.get("score") or "Research required").strip()
    risk = str(row.get("risk_level") or row.get("risk") or "Needs review").strip()
    competition = str(row.get("competition") or "Medium").strip()
    return {
        "offer_id": slug,
        "brand_name": brand,
        "niche": niche,
        "website": website,
        "score": score,
        "risk": risk,
        "competition": competition,
    }


def safe_write_index(index: pd.DataFrame) -> None:
    path = settings.data_dir / "pricing_pages_index.csv"
    try:
        index.to_csv(path, index=False)
    except PermissionError:
        if not path.exists():
            raise
        print(f"WARNING: {path} is locked. Keeping existing pricing_pages_index.csv.")


def ensure_pricing_tracking_links(tool_map: dict[str, dict[str, str]]) -> None:
    current = load_affiliate_links()
    existing = set(current["tool_slug"].astype(str).tolist()) | set(current["slug"].astype(str).tolist())
    rows = []
    for slug in PRICING_TOOLS:
        if slug in existing:
            continue
        tool = tool_map.get(slug) or PRICING_FALLBACK_TOOLS.get(slug)
        if not tool:
            continue
        rows.append(
            {
                "tool_slug": slug,
                "tool_name": tool["brand_name"],
                "brand": tool["brand_name"],
                "slug": slug,
                "official_url": tool.get("website", ""),
                "affiliate_url": "",
                "affiliate_status": "official_only",
                "status": "official_only",
                "notes": "Official site only. No affiliate link has been added.",
                "commission_note": "Affiliate link pending approval.",
                "network": "Other",
                "approved": False,
            }
        )
        existing.add(slug)
    if rows:
        save_affiliate_links(pd.concat([current, pd.DataFrame(rows)], ignore_index=True, sort=False))


def affiliate_status_for(slug: str) -> str:
    links = load_affiliate_links()
    if links.empty:
        return "official_only"
    match = links[(links["tool_slug"].astype(str) == slug) | (links["slug"].astype(str) == slug)]
    if match.empty:
        return "official_only"
    return str(match.iloc[0].get("affiliate_status", "official_only") or "official_only")


def render_pricing_page(tool: dict[str, str], related: dict[str, list[str]]) -> str:
    slug = tool["offer_id"]
    path = f"/pricing/{slug}/"
    title = pricing_title(tool)
    description = pricing_description(tool)
    questions = faq_questions(tool["brand_name"])
    body = "\n".join(
        [
            hero_block(tool),
            affiliate_disclosure(),
            quick_verdict_block(tool),
            pricing_plan_block(tool),
            trial_note_block(tool),
            hidden_cost_block(tool),
            plan_fit_block(tool),
            alternative_block(tool, related),
            internal_links_block(tool, related),
            cta_block(tool),
            faq_block(questions),
        ]
    )
    schemas = [faq_schema(questions), breadcrumb_schema(title, path)]
    return shell(title, description, path, body, schemas)


def pricing_title(tool: dict[str, str]) -> str:
    return f"{tool['brand_name']} Pricing Guide: Plans, Trial Notes, and Buying Risks"


def pricing_description(tool: dict[str, str]) -> str:
    brand = tool["brand_name"]
    niche = tool["niche"]
    return f"{brand} pricing research for {niche} buyers. Review plan fit, hidden cost risks, alternatives, official pricing checks, and safe next steps before buying."


def hero_block(tool: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    slug = html.escape(tool["offer_id"])
    niche = html.escape(tool["niche"])
    review_link = f"/review/{slug}/" if tool["offer_id"] in EXISTING_REVIEW_SLUGS else "/reviews/"
    return f"""
<section class='hero card'>
  <p><a href='/'>Home</a> / <a href='/reviews/'>Reviews</a> / <a href='{review_link}'>{brand}</a> / Pricing</p>
  <p class='badge'>Pricing research</p>
  <h1>{brand} Pricing Guide</h1>
  <p>This {brand} pricing guide is written for {niche} buyers who want a practical way to evaluate plans before visiting the official website. It does not publish fixed prices as permanent facts, because SaaS pricing, trial rules, contract terms, and feature limits can change without notice.</p>
  <p>The goal is to help you ask better buying questions: which plan fits a solo workflow, where a small team may hit limits, when an agency should check contract details, and what alternatives are worth comparing before committing budget.</p>
  <p><a class='btn' href='/go/{slug}/?src=pricing/{slug}&cta=pricing_page'>Visit Official Website</a><a class='btn secondary' href='/go/{slug}/?src=pricing/{slug}&cta=pricing_check'>Check current pricing</a></p>
  <p class='note'>CTA status: Official site / affiliate pending when no approved affiliate URL is available.</p>
</section>
"""


def quick_verdict_block(tool: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    profile = pricing_profile(tool)
    return f"""
<section class='card trust'>
  <h2>Quick pricing verdict</h2>
  <p><strong>{brand} can be worth testing when</strong> {html.escape(profile['worth_testing'])}. The safer approach is to start with the smallest plan or trial that lets you validate one real workflow, then upgrade only when the limits are clear.</p>
  <p><strong>Do not buy on pricing page copy alone.</strong> Verify current plan names, usage caps, seat rules, cancellation terms, refund policy, and whether the features you need are locked behind higher tiers. This page is a research guide, not official pricing documentation.</p>
  <div class='grid'>
    <div class='card'><h3>Best first move</h3><p>{html.escape(profile['first_move'])}</p></div>
    <div class='card'><h3>Watch closely</h3><p>{html.escape(profile['watch'])}</p></div>
    <div class='card'><h3>Upgrade trigger</h3><p>{html.escape(profile['upgrade'])}</p></div>
  </div>
</section>
"""


def pricing_plan_block(tool: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    niche = html.escape(tool["niche"])
    profile = pricing_profile(tool)
    return f"""
<section class='card'>
  <h2>Pricing plan explanation</h2>
  <p>Most {niche} software pricing is easier to understand when you separate the advertised plan name from the actual workflow cost. With {brand}, the plan that looks cheapest may not be the best option if your work depends on collaboration, export limits, automation volume, integrations, reporting, or commercial usage rights.</p>
  <p>{html.escape(profile['plan_context'])} A practical review should list the tasks you expect to run weekly, the number of people who need access, and the features that would stop work if they were missing. Then compare those needs against the current official pricing page.</p>
  <table>
    <thead><tr><th>Buyer question</th><th>What to verify before paying</th><th>Why it matters</th></tr></thead>
    <tbody>
      <tr><td>Is the entry plan enough?</td><td>Feature limits, exports, projects, automation volume, or AI usage caps.</td><td>Low entry pricing can become expensive if the plan blocks the core workflow.</td></tr>
      <tr><td>How are seats billed?</td><td>Per-user billing, guest access, admin roles, and whether occasional users need paid seats.</td><td>Team cost can rise faster than expected when every collaborator requires a paid seat.</td></tr>
      <tr><td>What happens at scale?</td><td>Usage overages, premium support, higher-tier integrations, and enterprise contract rules.</td><td>A tool that is cheap for one user may be a larger commitment for an agency or business team.</td></tr>
    </tbody>
  </table>
</section>
"""


def trial_note_block(tool: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    profile = pricing_profile(tool)
    return f"""
<section class='card'>
  <h2>Free plan / trial note</h2>
  <p>If {brand} currently offers a free plan, free trial, credit, or limited starter tier, treat it as a testing window rather than a guarantee that the tool will remain free for your use case. Trial availability, trial length, included features, and credit rules can change, so verify the latest details on the official website before relying on them.</p>
  <p>{html.escape(profile['trial_context'])} During the trial, test one complete workflow from input to output. For example, create a real project, invite one collaborator if teamwork matters, connect a key integration if integrations are important, export the result, and check whether the final output is usable without manual cleanup.</p>
  <p>For affiliate promotion, also verify whether the vendor allows paid search, direct linking, brand bidding, coupon claims, and review-style landing pages. A good pricing page is not enough if the affiliate policy blocks the traffic source you plan to use.</p>
</section>
"""


def hidden_cost_block(tool: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    profile = pricing_profile(tool)
    return f"""
<section class='card'>
  <h2>Hidden cost / contract risk</h2>
  <p>The hidden cost risk with {brand} is usually not one dramatic fee. It is the collection of small limits that appear after the first serious workflow: seat count, usage caps, workspace limits, add-ons, higher-tier integrations, support access, storage, exports, API access, or commercial usage terms.</p>
  <p>{html.escape(profile['risk_context'])} Before buying, write down the exact workflow you want to run for the next 30 days. If the workflow requires a higher plan, annual commitment, or additional seats, calculate the real monthly cost instead of comparing only the lowest public plan.</p>
  <ul>
    <li>Check whether cancellation is self-service or requires support.</li>
    <li>Check refund rules before starting a paid plan.</li>
    <li>Check whether usage credits reset monthly or roll over.</li>
    <li>Check whether exported assets, data, or automations remain accessible after cancellation.</li>
    <li>Check whether commercial use is allowed on the plan you choose.</li>
  </ul>
</section>
"""


def plan_fit_block(tool: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    profile = pricing_profile(tool)
    return f"""
<section class='card'>
  <h2>Best plan for solo user</h2>
  <p>A solo user should usually start with the lowest plan or trial that can complete one end-to-end workflow without forcing a workaround. For {brand}, this means checking whether the plan includes the core features you personally need, not every feature listed on the sales page.</p>
  <p>{html.escape(profile['solo'])} If you only need occasional usage, avoid annual commitments until you know the tool saves enough time or improves output quality consistently.</p>
</section>
<section class='card'>
  <h2>Best plan for small team</h2>
  <p>A small team should focus on collaboration, shared assets, permissions, repeatable templates, billing clarity, and whether each teammate needs a full paid seat. {brand} may be useful for a team only if the workflow becomes easier to hand off, review, and repeat.</p>
  <p>{html.escape(profile['team'])} Run a small team pilot first: one owner, one reviewer, and one backup user. If the pilot works, then compare plan tiers and decide whether the extra collaboration features justify the upgrade.</p>
</section>
<section class='card'>
  <h2>Best plan for agency/business</h2>
  <p>An agency or business buyer should treat {brand} as an operating cost, not a personal productivity purchase. The best plan is the one with predictable usage, clear rights, support expectations, and enough controls for client or department workflows.</p>
  <p>{html.escape(profile['business'])} Ask about usage spikes, client work, data ownership, brand management, admin controls, and whether invoicing or annual contracts are required at larger scale.</p>
</section>
"""


def alternative_block(tool: dict[str, str], related: dict[str, list[str]]) -> str:
    brand = html.escape(tool["brand_name"])
    alternatives = related.get("alternatives", [])
    links = " ".join(f"<a href='{html.escape(url)}'>{html.escape(label)}</a>" for label, url in alternatives[:4])
    if not links:
        links = "<a href='/comparisons/'>Browse related comparisons</a>"
    return f"""
<section class='card'>
  <h2>Alternative if too expensive</h2>
  <p>If {brand} feels too expensive after checking the official pricing page, compare the cost against the workflow value rather than switching immediately. A cheaper tool can still cost more if it requires more manual cleanup, lacks a key integration, or creates work that your team does not trust.</p>
  <p>Good alternatives to evaluate first: {links}.</p>
  <p>Use alternatives as negotiation and validation tools. If a competing product solves the same workflow with fewer seats, clearer limits, or better monthly flexibility, it may be a better first test. If {brand} produces better output or saves more time, a higher plan may still be reasonable.</p>
</section>
"""


def internal_links_block(tool: dict[str, str], related: dict[str, list[str]]) -> str:
    brand = html.escape(tool["brand_name"])
    review = f"/review/{html.escape(tool['offer_id'])}/" if tool["offer_id"] in EXISTING_REVIEW_SLUGS else "/reviews/"
    comparison_links = " ".join(f"<a href='{html.escape(url)}'>{html.escape(label)}</a>" for label, url in related.get("comparisons", [])[:3])
    hub_links = " ".join(f"<a href='{html.escape(url)}'>{html.escape(label)}</a>" for label, url in related.get("hubs", [])[:3])
    return f"""
<section class='card'>
  <h2>Related research before buying</h2>
  <p>Read the full <a href='{review}'>{brand} review</a> before choosing a plan. Pricing only tells part of the story; workflow fit, policy risk, alternatives, and team adoption matter just as much.</p>
  <p><strong>Related comparisons:</strong> {comparison_links or "<a href='/comparisons/'>Browse comparisons</a>"}</p>
  <p><strong>Related hubs:</strong> {hub_links or "<a href='/hubs/'>Browse research hubs</a>"}</p>
</section>
"""


def cta_block(tool: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    slug = html.escape(tool["offer_id"])
    return f"""
<section class='card trust'>
  <h2>Next step: verify {brand} pricing</h2>
  <p>The next safe step is to open the official pricing page, confirm the current plan details, and compare the plan against the workflow notes above. If this site later receives an approved affiliate link, the tracking route can use it; until then it can still send readers to the official site.</p>
  <p><a class='btn' href='/go/{slug}/?src=pricing/{slug}&cta=pricing_page'>Visit Official Website</a><a class='btn secondary' href='/go/{slug}/?src=pricing/{slug}&cta=pricing_check'>Check current pricing</a></p>
  <p class='note'>Official site / affiliate pending. This page only uses the internal tracking route until a real affiliate URL is approved.</p>
</section>
"""


def faq_block(questions: list[str]) -> str:
    return f"<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>"


def faq_questions(brand: str) -> list[str]:
    return [
        f"How should I check {brand} pricing before buying?",
        f"Does {brand} have a free plan or trial?",
        f"Which {brand} plan is best for a solo user?",
        f"Which {brand} plan is best for a small team?",
        f"What hidden costs should I check before paying for {brand}?",
        f"What should I compare before choosing {brand}?",
    ]


def related_links_for(slug: str) -> dict[str, list[tuple[str, str]]]:
    comparison_map = {
        "cursor": [("Cursor vs GitHub Copilot", "/compare/cursor-vs-github-copilot/"), ("Cursor vs Windsurf", "/compare/cursor-vs-windsurf/")],
        "github-copilot": [("Cursor vs GitHub Copilot", "/compare/cursor-vs-github-copilot/"), ("GitHub Copilot vs Codeium", "/compare/github-copilot-vs-codeium/")],
        "semrush": [("Semrush vs Ahrefs", "/compare/semrush-vs-ahrefs/")],
        "make": [("Make vs Zapier", "/compare/make-vs-zapier/")],
        "zapier": [("Make vs Zapier", "/compare/make-vs-zapier/")],
        "canva": [("Canva vs AdCreative AI", "/compare/canva-vs-adcreative-ai/"), ("Canva vs Gamma", "/comparisons/canva-vs-gamma/")],
        "activecampaign": [("ActiveCampaign vs Mailchimp", "/compare/activecampaign-vs-mailchimp/")],
        "mailchimp": [("ActiveCampaign vs Mailchimp", "/compare/activecampaign-vs-mailchimp/")],
        "pictory": [("Synthesia vs Pictory", "/compare/synthesia-vs-pictory/")],
        "grammarly": [("Grammarly vs QuillBot", "/compare/grammarly-vs-quillbot/")],
    }
    alternative_map = {
        "cursor": [("GitHub Copilot review", "/review/github-copilot/"), ("Cursor vs Windsurf", "/compare/cursor-vs-windsurf/")],
        "github-copilot": [("Cursor review", "/review/cursor/"), ("GitHub Copilot vs Codeium", "/compare/github-copilot-vs-codeium/")],
        "semrush": [("Semrush vs Ahrefs", "/compare/semrush-vs-ahrefs/"), ("Surfer SEO review", "/review/surfer-seo/")],
        "make": [("Zapier review", "/review/zapier/"), ("Automation hub", "/hub/ai-automation/")],
        "zapier": [("Make review", "/review/make/"), ("Automation hub", "/hub/ai-automation/")],
        "canva": [("AdCreative AI review", "/review/adcreative-ai/"), ("Gamma review", "/review/gamma/")],
        "activecampaign": [("ActiveCampaign vs Mailchimp", "/compare/activecampaign-vs-mailchimp/"), ("CRM tools", "/hub/crm/")],
        "mailchimp": [("ActiveCampaign review", "/review/activecampaign/"), ("Email marketing hub", "/hub/email-marketing/")],
        "pictory": [("Synthesia review", "/review/synthesia/"), ("Video tools", "/hub/ai-video/")],
        "grammarly": [("Grammarly vs QuillBot", "/compare/grammarly-vs-quillbot/"), ("AI writing tools", "/hub/ai-writing/")],
    }
    hub_map = {
        "cursor": [("AI coding hub", "/hub/ai-coding/"), ("Best AI coding tools", "/best-ai-coding-tools/")],
        "github-copilot": [("AI coding hub", "/hub/ai-coding/"), ("Best AI coding tools", "/best-ai-coding-tools/")],
        "semrush": [("AI SEO hub", "/hub/ai-seo/"), ("Best AI SEO tools", "/best-ai-seo-tools/")],
        "make": [("Automation hub", "/hub/ai-automation/"), ("Best AI automation tools", "/best-ai-automation-tools/")],
        "zapier": [("Automation hub", "/hub/ai-automation/"), ("Best AI automation tools", "/best-ai-automation-tools/")],
        "canva": [("AI presentation hub", "/hub/ai-presentation/"), ("Best AI presentation tools", "/best-ai-presentation-tools/")],
        "activecampaign": [("CRM hub", "/hub/crm/"), ("Best CRM tools", "/best-crm-tools/")],
        "mailchimp": [("CRM hub", "/hub/crm/"), ("Best CRM tools", "/best-crm-tools/")],
        "pictory": [("AI video hub", "/hub/ai-video/"), ("Best AI video tools", "/best-ai-video-tools/")],
        "grammarly": [("AI writing hub", "/hub/ai-writing/"), ("Best AI writing tools", "/best-ai-writing-tools/")],
    }
    return {
        "comparisons": comparison_map.get(slug, []),
        "alternatives": alternative_map.get(slug, []),
        "hubs": hub_map.get(slug, [("Research hubs", "/hubs/")]),
    }


def pricing_profile(tool: dict[str, str]) -> dict[str, str]:
    niche = tool["niche"].lower()
    brand = tool["brand_name"]
    if "coding" in niche:
        return {
            "worth_testing": "the tool can reduce coding friction inside a real repository without creating review or security problems",
            "first_move": "Run a short trial on one non-critical repository and measure whether it reduces repetitive edits.",
            "watch": "Seat billing, privacy settings, repository access, team policy, and whether advanced AI usage is capped.",
            "upgrade": "Upgrade only after the assistant is useful across code review, refactoring, and repeated daily tasks.",
            "plan_context": f"For {brand}, the useful pricing question is whether the plan supports the developer workflow you actually run, not whether it has the longest feature list.",
            "trial_context": "A coding trial should include autocomplete, chat, refactor tasks, tests, and code review notes rather than a single prompt.",
            "risk_context": "Developer tools can create hidden costs through seat expansion, compliance reviews, enterprise controls, and time spent correcting low-quality suggestions.",
            "solo": "A solo developer should focus on whether the assistant saves time in familiar code, handles project context well, and avoids adding review debt.",
            "team": "A small engineering team should check admin controls, repository access, onboarding friction, and whether the tool works across different developer habits.",
            "business": "A business buyer should verify security documentation, procurement requirements, usage reporting, and whether the plan supports managed teams.",
        }
    if "seo" in niche:
        return {
            "worth_testing": "keyword research, competitor review, and content planning are frequent enough to justify a paid SEO workflow",
            "first_move": "Test a small set of live keywords, competitors, and pages before deciding whether the data depth is worth the subscription.",
            "watch": "Database coverage, export limits, user seats, historical data, project limits, and whether content tools require higher plans.",
            "upgrade": "Upgrade only when the tool consistently influences pages, rankings, outreach, or content decisions.",
            "plan_context": f"For {brand}, compare the plan against the number of domains, keywords, exports, and reports you need every month.",
            "trial_context": "A good SEO trial should include one site audit, one competitor gap review, one keyword cluster, and one content brief.",
            "risk_context": "SEO tools can become expensive when reporting, keyword volume, API access, or agency seats are required.",
            "solo": "A solo publisher should avoid paying for large agency features until keyword research and audit reports are used weekly.",
            "team": "A small marketing team should check collaboration, reporting, project limits, and how easily insights move into content production.",
            "business": "An agency should compare client limits, export permissions, white-label needs, and whether reports can be repeated efficiently.",
        }
    if "automation" in niche:
        return {
            "worth_testing": "repeated workflows can be automated without creating fragile handoffs or expensive task overages",
            "first_move": "Build one workflow that replaces a real repeated task and measure maintenance effort after several runs.",
            "watch": "Task operations, run frequency, premium app connectors, error handling, and whether branching requires a higher tier.",
            "upgrade": "Upgrade when automation saves measurable manual work and the workflow remains understandable to someone else.",
            "plan_context": f"For {brand}, pricing should be evaluated by workflow volume and maintenance complexity, not just the number of apps listed.",
            "trial_context": "A useful automation trial includes trigger setup, branching, error recovery, and a small production-like test.",
            "risk_context": "Automation platforms hide costs in task volume, premium connectors, failed runs, and workflows that only one person understands.",
            "solo": "A solo operator should start with one or two automations that remove obvious repetitive work without creating operational risk.",
            "team": "A small team should document ownership, error alerts, and who can edit or pause automations before upgrading.",
            "business": "An agency or business should check task volume, client separation, admin controls, and whether workflows can be audited later.",
        }
    if "email" in niche or "marketing" in niche:
        return {
            "worth_testing": "the list, segmentation, and automation needs are mature enough to benefit from a dedicated email platform",
            "first_move": "Import a small segment, build one campaign, and test whether reporting and automation match your marketing process.",
            "watch": "Contact limits, email send limits, automation tiers, CRM features, deliverability tooling, and contract rules.",
            "upgrade": "Upgrade when segmentation, lifecycle automation, or sales follow-up clearly improves over a simpler tool.",
            "plan_context": f"For {brand}, pricing often depends on contact volume, automation depth, and whether CRM-style features are included.",
            "trial_context": "An email trial should test list management, campaign creation, basic automation, reporting, and unsubscribes.",
            "risk_context": "Email platforms can become expensive as contacts grow, advanced automation is needed, or deliverability support becomes important.",
            "solo": "A solo user should start only after there is a clear mailing list and a simple campaign calendar.",
            "team": "A small team should check templates, approval workflows, segmentation, and how sales or support teams will use the data.",
            "business": "A business buyer should review compliance, deliverability, CRM sync, account permissions, and pricing at larger contact counts.",
        }
    if "video" in niche:
        return {
            "worth_testing": "video output quality is good enough for the channel and the plan allows the amount of content you expect to publish",
            "first_move": "Create one short video from a real script and inspect export quality, editing time, and commercial usage terms.",
            "watch": "Video minutes, export quality, watermark rules, stock assets, voice/avatar rights, and commercial usage limitations.",
            "upgrade": "Upgrade when the tool reliably produces publishable video assets with less editing time than your current workflow.",
            "plan_context": f"For {brand}, pricing should be compared against output minutes, editing needs, and whether the generated assets are usable commercially.",
            "trial_context": "A video trial should test script input, editing, export quality, branding, and one realistic revision cycle.",
            "risk_context": "Video tools can hide costs in credits, render minutes, export quality, watermark removal, and asset rights.",
            "solo": "A solo creator should start with the smallest plan that exports usable videos without watermarks or blocked rights.",
            "team": "A small team should check review workflows, brand assets, collaboration, and whether several people can work on one project.",
            "business": "A business buyer should verify commercial rights, brand controls, approval workflows, and predictable output volume.",
        }
    return {
        "worth_testing": "the workflow is frequent enough that saved time, better output, or cleaner collaboration can justify the monthly cost",
        "first_move": "Test one real project and compare time saved, output quality, and friction against your current process.",
        "watch": "Seat billing, feature gates, usage limits, export rights, integrations, and cancellation policy.",
        "upgrade": "Upgrade only when the tool proves its value in repeated work, not after a single impressive demo.",
        "plan_context": f"For {brand}, match the plan to the workflow you repeat most often instead of buying for every possible feature.",
        "trial_context": "A good trial should include one real project, one revision cycle, one export, and one handoff to another person if teamwork matters.",
        "risk_context": "Hidden costs usually come from collaboration, export limits, storage, premium integrations, support, or annual commitments.",
        "solo": "A solo user should prioritize the plan that removes the main workflow bottleneck without forcing a long contract.",
        "team": "A small team should check permissions, sharing, templates, and whether the tool improves collaboration instead of adding another dashboard.",
        "business": "A business buyer should check admin controls, billing predictability, usage reporting, and official terms before expanding.",
    }
