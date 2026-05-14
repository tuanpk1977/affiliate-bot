from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd

from config import settings
from modules.affiliate_links import load_affiliate_links, save_affiliate_links
from modules.programmatic_page_utils import affiliate_disclosure, breadcrumb_schema, faq_html, faq_schema, item_list_schema, shell, write_page
from modules.review_page_builder import normalize_tool, prepare_tools


INDEX_COLUMNS = [
    "comparison_slug",
    "tool_a_slug",
    "tool_a_name",
    "tool_b_slug",
    "tool_b_name",
    "title",
    "output_path",
    "status",
]


COMPARISON_PAIRS = [
    ("cursor", "github-copilot", "AI coding assistants"),
    ("cursor", "windsurf", "AI coding editors"),
    ("github-copilot", "codeium", "AI coding assistants"),
    ("semrush", "ahrefs", "SEO platforms"),
    ("make", "zapier", "automation platforms"),
    ("canva", "adcreative-ai", "AI design and ad creative tools"),
    ("activecampaign", "mailchimp", "email marketing platforms"),
    ("jasper", "copy-ai", "AI writing tools"),
    ("synthesia", "pictory", "AI video tools"),
    ("grammarly", "quillbot", "AI writing assistants"),
]


FALLBACK_TOOLS = {
    "windsurf": {"offer_id": "windsurf", "brand_name": "Windsurf", "niche": "AI Coding", "website": "https://windsurf.com"},
    "codeium": {"offer_id": "codeium", "brand_name": "Codeium", "niche": "AI Coding", "website": "https://codeium.com"},
    "ahrefs": {"offer_id": "ahrefs", "brand_name": "Ahrefs", "niche": "AI SEO", "website": "https://ahrefs.com"},
    "mailchimp": {"offer_id": "mailchimp", "brand_name": "Mailchimp", "niche": "Email Marketing", "website": "https://mailchimp.com"},
    "pictory": {"offer_id": "pictory", "brand_name": "Pictory", "niche": "AI Video", "website": "https://pictory.ai"},
    "grammarly": {"offer_id": "grammarly", "brand_name": "Grammarly", "niche": "AI Writing", "website": "https://www.grammarly.com"},
    "quillbot": {"offer_id": "quillbot", "brand_name": "QuillBot", "niche": "AI Writing", "website": "https://quillbot.com"},
}


def generate_comparison_review_pages(output: Path, offer_scores: pd.DataFrame | None = None) -> list[dict[str, str]]:
    tool_map = build_tool_map(offer_scores)
    ensure_tracking_links(tool_map)
    pages: list[dict[str, str]] = []
    index_rows: list[dict[str, str]] = []

    for left_slug, right_slug, category in COMPARISON_PAIRS:
        left = tool_map[left_slug]
        right = tool_map[right_slug]
        slug = f"{left_slug}-vs-{right_slug}"
        title = comparison_title(left, right, category)
        page_path = write_page(output, f"compare/{slug}", render_comparison_page(left, right, category))
        pages.append({"slug": f"compare/{slug}", "title": title, "type": "comparison_review"})
        index_rows.append(
            {
                "comparison_slug": slug,
                "tool_a_slug": left_slug,
                "tool_a_name": left["brand_name"],
                "tool_b_slug": right_slug,
                "tool_b_name": right["brand_name"],
                "title": title,
                "output_path": str(page_path),
                "status": "built",
            }
        )

    safe_write_index(pd.DataFrame(index_rows, columns=INDEX_COLUMNS))
    return pages


def safe_write_index(index: pd.DataFrame) -> None:
    path = settings.data_dir / "comparison_pages_index.csv"
    try:
        index.to_csv(path, index=False)
    except PermissionError:
        if not path.exists():
            raise
        print(f"WARNING: {path} is locked. Keeping existing comparison_pages_index.csv.")


def build_tool_map(offer_scores: pd.DataFrame | None) -> dict[str, dict[str, str]]:
    tools = prepare_tools(offer_scores)
    result: dict[str, dict[str, str]] = {}
    for _, row in tools.iterrows():
        tool = normalize_tool(row.to_dict())
        result[tool["offer_id"]] = tool
    for slug, data in FALLBACK_TOOLS.items():
        result.setdefault(slug, normalize_tool(data))
    return result


def ensure_tracking_links(tool_map: dict[str, dict[str, str]]) -> None:
    current = load_affiliate_links()
    existing = set(current["tool_slug"].astype(str).tolist()) | set(current["slug"].astype(str).tolist())
    rows = []
    for left_slug, right_slug, _ in COMPARISON_PAIRS:
        for slug in [left_slug, right_slug]:
            if slug in existing:
                continue
            tool = tool_map[slug]
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


def render_comparison_page(left: dict[str, str], right: dict[str, str], category: str) -> str:
    slug = f"{left['offer_id']}-vs-{right['offer_id']}"
    path = f"/compare/{slug}/"
    title = comparison_title(left, right, category)
    description = comparison_description(left, right, category)
    questions = faq_questions(left["brand_name"], right["brand_name"])
    profile = comparison_profile(category, slug)
    body = "\n".join(
        [
            hero_block(left, right, category, profile),
            affiliate_disclosure(),
            quick_verdict_block(left, right, category, profile),
            quick_table_block(left, right, category),
            coding_builder_comparison_block(left, right, category) if "coding" in category.lower() else "",
            scoring_table_block(left, right, profile),
            choose_block(left, right, profile),
            best_for_block(left, right, profile),
            migration_block(left, right, profile),
            pricing_risk_block(left, right, profile),
            team_size_block(left, right, profile),
            alternative_block(left, right, profile),
            pricing_note_block(left, right),
            strengths_weaknesses_block(left, right),
            use_case_block(left, right, category),
            review_links_block(left, right),
            final_verdict_block(left, right, category),
            cta_block(left, right),
            faq_block(questions),
        ]
    )
    schemas = [faq_schema(questions), breadcrumb_schema(title, path), item_list_schema(title, [left["brand_name"], right["brand_name"]], path)]
    return shell(title, description, path, body, schemas)


def comparison_title(left: dict[str, str], right: dict[str, str], category: str) -> str:
    return f"{left['brand_name']} vs {right['brand_name']}: Which {category} should you choose?"


def comparison_description(left: dict[str, str], right: dict[str, str], category: str) -> str:
    return f"Research-style comparison of {left['brand_name']} vs {right['brand_name']} for {category} buyers. Compare strengths, weaknesses, pricing checks, reviews, tracking CTAs, and safer buying considerations."


def hero_block(left: dict[str, str], right: dict[str, str], category: str, profile: dict) -> str:
    slug = f"{left['offer_id']}-vs-{right['offer_id']}"
    angle = html.escape(pair_opening(left, right, category, profile))
    return f"""
<section class='hero card'>
  <p><a href='/'>Home</a> / <a href='/comparisons/'>Comparisons</a> / {html.escape(left['brand_name'])} vs {html.escape(right['brand_name'])}</p>
  <p class='badge'>Comparison guide</p>
  <h1>{html.escape(left['brand_name'])} vs {html.escape(right['brand_name'])}</h1>
  <p>{angle}</p>
  <p><a class='btn' href='/go/{html.escape(left['offer_id'])}/?src=compare/{html.escape(slug)}&cta=comparison_page'>Visit {html.escape(left['brand_name'])}</a><a class='btn secondary' href='/go/{html.escape(right['offer_id'])}/?src=compare/{html.escape(slug)}&cta=comparison_page'>Visit {html.escape(right['brand_name'])}</a></p>
</section>
"""


def pair_opening(left: dict[str, str], right: dict[str, str], category: str, profile: dict) -> str:
    slug = f"{left['offer_id']}-vs-{right['offer_id']}"
    specific = {
        "cursor-vs-github-copilot": "Cursor vs GitHub Copilot is mainly a choice between an AI-first coding editor experience and an assistant that fits deeply into the GitHub-centered development ecosystem. The first question is whether you want the editor itself to shape the workflow, or whether you want AI support inside tools your team may already use.",
        "cursor-vs-windsurf": "Cursor vs Windsurf is a closer editor-style decision, so the practical test should happen inside one real repository with the same task in both products. Look at context handling, how often the assistant needs correction, and whether the editor makes code review feel clearer or more scattered.",
        "github-copilot-vs-codeium": "GitHub Copilot vs Codeium is less about replacing the whole editor and more about choosing the assistant layer that fits your existing development setup. The useful comparison is how each tool behaves during normal coding, review, and team policy checks.",
        "semrush-vs-ahrefs": "Semrush vs Ahrefs is a classic SEO platform decision, but the right answer depends on whether you need a broad marketing suite or a sharper organic research workflow. A publisher, agency, and in-house SEO team may weigh the same data very differently.",
        "make-vs-zapier": "Make vs Zapier should be tested with a real automation, not a list of app logos. The difference becomes clearer when you map triggers, branching, error handling, and how easy the workflow is to maintain after the first week.",
        "canva-vs-adcreative-ai": "Canva vs AdCreative AI compares a broad design workspace with a more advertising-focused creative workflow. The better choice depends on whether you need everyday visual production or performance-oriented ad variation testing.",
        "activecampaign-vs-mailchimp": "ActiveCampaign vs Mailchimp is a decision between deeper customer automation and a more familiar email marketing workflow. The right choice depends on list maturity, segmentation needs, and how much automation your team can realistically manage.",
        "jasper-vs-copy-ai": "Jasper vs Copy.ai should be judged by how each tool supports an editorial process after the first draft. The useful question is not which one produces more words, but which one reduces rewriting while keeping brand and intent under control.",
        "synthesia-vs-pictory": "Synthesia vs Pictory compares two different video production paths: avatar-led video creation and content repurposing into video. The best test is to start from one script or article and see which workflow reaches a usable asset with less review friction.",
        "grammarly-vs-quillbot": "Grammarly vs QuillBot is a writing workflow decision between editing assistance and rewriting/paraphrasing support. The stronger choice depends on whether your main bottleneck is clarity, tone, grammar, or reshaping existing text.",
    }
    if slug in specific:
        return specific[slug]
    return f"{profile['intro']} This comparison is for readers choosing between two {category} without relying on old pricing screenshots or exaggerated claims."


def quick_verdict_block(left: dict[str, str], right: dict[str, str], category: str, profile: dict) -> str:
    return f"""
<section class='card trust'>
  <h2>{html.escape(profile['verdict_heading'])}</h2>
  <p><strong>Quick verdict:</strong> choose {html.escape(left['brand_name'])} when {html.escape(profile['left_verdict'])}. Choose {html.escape(right['brand_name'])} when {html.escape(profile['right_verdict'])}.</p>
  <p>The safer buying path for {html.escape(category)} is to test one real workflow, verify current pricing, read the individual review pages, and only then click through to the official site. This comparison does not create fake affiliate links or promise that either product will fit every team.</p>
</section>
"""


def quick_table_block(left: dict[str, str], right: dict[str, str], category: str) -> str:
    return f"""
<section class='card'>
  <h2>Quick comparison table</h2>
  <table>
    <thead><tr><th>Decision area</th><th>{html.escape(left['brand_name'])}</th><th>{html.escape(right['brand_name'])}</th></tr></thead>
    <tbody>
      <tr><td>Main category</td><td>{html.escape(left['niche'])}</td><td>{html.escape(right['niche'])}</td></tr>
      <tr><td>Best initial test</td><td>Run one real workflow and check how much manual cleanup remains.</td><td>Run the same workflow and compare speed, quality, and team adoption friction.</td></tr>
      <tr><td>Pricing check</td><td>Verify official pricing, limits, seats, cancellation, and add-ons.</td><td>Verify official pricing, limits, seats, cancellation, and add-ons.</td></tr>
      <tr><td>Affiliate note</td><td>Use tracking CTA only. Do not assume PPC or direct linking is allowed.</td><td>Use tracking CTA only. Do not assume PPC or direct linking is allowed.</td></tr>
      <tr><td>Review link</td><td>{review_link(left)}</td><td>{review_link(right)}</td></tr>
    </tbody>
  </table>
  <p>The table is intentionally practical. For {html.escape(category)}, a useful comparison should reduce uncertainty before a buyer opens either official site. It should not pretend that one tool is always better for every budget, team size, country, or workflow.</p>
</section>
"""


def best_for_block(left: dict[str, str], right: dict[str, str], profile: dict | None = None) -> str:
    return f"""
<section class='grid'>
  <div class='card'>
    <h2>Best for {html.escape(left['brand_name'])}</h2>
    <p>{html.escape(left['brand_name'])} is usually the better starting point when your workflow maps closely to {html.escape(left['niche'])}, you can test the product with a real task, and you want to understand its official limits before committing.</p>
    <ul><li>Teams with a clear use case.</li><li>Buyers who can verify integrations and pricing.</li><li>Researchers comparing affiliate-safe review pages.</li></ul>
  </div>
  <div class='card'>
    <h2>Best for {html.escape(right['brand_name'])}</h2>
    <p>{html.escape(right['brand_name'])} is worth considering when it may solve the same problem with a different interface, pricing model, ecosystem, or learning curve. It is especially useful as a benchmark before choosing {html.escape(left['brand_name'])}.</p>
    <ul><li>Buyers who want a second serious option.</li><li>Teams comparing workflow friction.</li><li>Users who need to check alternatives before buying.</li></ul>
  </div>
</section>
"""


def choose_block(left: dict[str, str], right: dict[str, str], profile: dict) -> str:
    return f"""
<section class='grid'>
  <div class='card'>
    <h2>Choose {html.escape(left['brand_name'])} if...</h2>
    <p>{html.escape(profile['choose_left'])}</p>
    <ul>
      <li>You can describe the workflow you want to improve before opening the official site.</li>
      <li>You are willing to verify pricing, plan limits, and policy details manually.</li>
      <li>You want to compare the tool against at least one serious alternative before buying.</li>
    </ul>
  </div>
  <div class='card'>
    <h2>Choose {html.escape(right['brand_name'])} if...</h2>
    <p>{html.escape(profile['choose_right'])}</p>
    <ul>
      <li>You need a different workflow style, ecosystem, or learning curve.</li>
      <li>Your team can test the same use case in both tools and compare friction honestly.</li>
      <li>You prefer a second option before committing budget or affiliate content to one product.</li>
    </ul>
  </div>
</section>
"""


def coding_builder_comparison_block(left: dict[str, str], right: dict[str, str], category: str) -> str:
    left_name = html.escape(left["brand_name"])
    right_name = html.escape(right["brand_name"])
    slug = html.escape(f"{left['offer_id']}-vs-{right['offer_id']}")
    left_slug = html.escape(left["offer_id"])
    right_slug = html.escape(right["offer_id"])
    return f"""
<section class='card'>
  <h2>Real workflow notes from building projects</h2>
  <p>I would not compare {left_name} and {right_name} with a blank prompt. The better test is a real repository with a broken check, a small feature request, and enough existing structure that bad context becomes obvious. I tested Cursor vs Windsurf on a real project this way: one task for rough scaffolding, one task for a controlled multi-file edit, and one task for debugging a failing build.</p>
  <p>My current workflow uses different assistants for different jobs. Windsurf-style agents are useful when I want rapid structure and momentum. Cursor is stronger when the codebase already has a clear shape and the next step is targeted editing. GitHub Copilot is convenient for lightweight autocomplete, but it is not where I go for architecture-level reasoning. Codex-style repair is most useful when deployment, validation, or test output needs to be understood before changing code.</p>
  <aside class='card trust'><h3>Builder Note</h3><p>The best AI coding tool is the one that leaves the smallest trustworthy diff after review. A tool that writes more code is not automatically faster if the cleanup takes the rest of the afternoon.</p></aside>
</section>
<section class='card'>
  <h2>What failed during the comparison</h2>
  <p>The common failure is overreach. Agent-style tools can duplicate logic because they copy a working pattern instead of reusing an existing helper. Editor-first tools can loop on the same fix when the task is too broad. Autocomplete tools can suggest code that fits the nearby lines while missing the module boundary.</p>
  <p>The recovery pattern is always the same: stop broad generation, ask for the smallest diagnosis, inspect the files involved, then run the validator or tests again. Which AI coding tool actually fixes bugs faster? In practice, the winner is the one that understands why the first patch failed and reduces the next diff.</p>
</section>
<section class='card'>
  <h2>Practical coding workflow table</h2>
  <table>
    <thead><tr><th>Decision area</th><th>{left_name}</th><th>{right_name}</th><th>Builder takeaway</th></tr></thead>
    <tbody>
      <tr><td>Speed</td><td>Fast when the task fits its normal workflow.</td><td>Fast when context and setup are clear.</td><td>Measure accepted changes, not generated lines.</td></tr>
      <tr><td>Context understanding</td><td>Strong only when the right files are in scope.</td><td>Strong only when it follows the repository rules.</td><td>Ask both tools to explain before editing.</td></tr>
      <tr><td>Debugging</td><td>Good for targeted fixes after a clear error.</td><td>Good if it does not drift into unrelated changes.</td><td>Deployment errors need log reading, not guesswork.</td></tr>
      <tr><td>Large project stability</td><td>Safer with small reviewable diffs.</td><td>Safer with explicit boundaries and tests.</td><td>Large refactors need human checkpoints.</td></tr>
      <tr><td>Soft CTA</td><td><a href='/go/{left_slug}/?src=compare/{slug}&cta=builder_table'>Try {left_name}</a></td><td><a href='/go/{right_slug}/?src=compare/{slug}&cta=builder_table'>Try {right_name}</a></td><td><a href='/category/ai-coding-tools/'>Compare the broader AI coding stack</a></td></tr>
    </tbody>
  </table>
</section>
"""


def scoring_table_block(left: dict[str, str], right: dict[str, str], profile: dict) -> str:
    left_scores = profile["left_scores"]
    right_scores = profile["right_scores"]
    labels = [
        ("ease_of_use", "Ease of use"),
        ("pricing_clarity", "Pricing clarity"),
        ("feature_depth", "Feature depth"),
        ("team_fit", "Team fit"),
        ("affiliate_confidence", "Affiliate confidence"),
    ]
    rows = "".join(
        f"<tr><td><code>{key}</code><br>{label}</td><td>{left_scores[key]}/5</td><td>{right_scores[key]}/5</td><td>{html.escape(profile['score_notes'][key])}</td></tr>"
        for key, label in labels
    )
    return f"""
<section class='card'>
  <h2>{html.escape(profile['score_heading'])}</h2>
  <p>This scoring table is an editorial research aid. It is not a guarantee, and it should be updated after checking current product documentation, pricing, and affiliate policy.</p>
  <table>
    <thead><tr><th>Criterion</th><th>{html.escape(left['brand_name'])}</th><th>{html.escape(right['brand_name'])}</th><th>How to read it</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""


def migration_block(left: dict[str, str], right: dict[str, str], profile: dict) -> str:
    return f"""
<section class='card'>
  <h2>{html.escape(profile['migration_heading'])}</h2>
  <p>{html.escape(profile['migration_copy'])}</p>
  <p>If you already use one of these tools, avoid switching because of a single feature demo. Export a small sample, rebuild one workflow, check permissions or collaboration rules, and make sure your team can recover if the new setup creates unexpected friction.</p>
</section>
"""


def pricing_risk_block(left: dict[str, str], right: dict[str, str], profile: dict) -> str:
    return f"""
<section class='card'>
  <h2>Pricing and contract risk</h2>
  <p>{html.escape(profile['pricing_risk'])}</p>
  <p>For both {html.escape(left['brand_name'])} and {html.escape(right['brand_name'])}, verify billing cadence, add-ons, usage limits, seat rules, refund or cancellation terms, and whether the feature you need is available on the plan you are considering. Affiliate publishers should also verify PPC, brand bidding, coupon rules, direct linking, and country restrictions before sending traffic.</p>
</section>
"""


def team_size_block(left: dict[str, str], right: dict[str, str], profile: dict) -> str:
    return f"""
<section class='card'>
  <h2>Team size recommendation</h2>
  <p>{html.escape(profile['team_size'])}</p>
  <div class='grid'>
    <div class='card'><h3>Solo user</h3><p>Pick the tool that is easiest to test in one afternoon without forcing a full migration.</p></div>
    <div class='card'><h3>Small team</h3><p>Check collaboration, permissions, billing seats, and whether the workflow can be explained to non-expert users.</p></div>
    <div class='card'><h3>Growing team</h3><p>Review governance, support expectations, export paths, and the cost of changing tools later.</p></div>
  </div>
</section>
"""


def alternative_block(left: dict[str, str], right: dict[str, str], profile: dict) -> str:
    return f"""
<section class='card'>
  <h2>Best alternative if neither fits</h2>
  <p>{html.escape(profile['alternative'])}</p>
  <p><a href='/reviews/'>Browse individual reviews</a> | <a href='/comparisons/'>Browse older comparison pages</a> | <a href='/hubs/'>Browse research hubs</a></p>
</section>
"""


def pricing_note_block(left: dict[str, str], right: dict[str, str]) -> str:
    slug = f"{left['offer_id']}-vs-{right['offer_id']}"
    return f"""
<section class='card'>
  <h2>Pricing note</h2>
  <p>Pricing may change. This page does not publish fixed price claims for {html.escape(left['brand_name'])} or {html.escape(right['brand_name'])}. Before buying, verify the current plan structure, limits, cancellation terms, refund policy, and whether the features you need are included in the plan you are considering.</p>
  <p>For affiliate work, pricing is only one part of the decision. Also check affiliate terms, PPC rules, trademark bidding, direct linking, country restrictions, coupon restrictions, and whether disclosure is required on the landing page.</p>
  <p><a class='btn' href='/go/{html.escape(left['offer_id'])}/?src=compare/{html.escape(slug)}&cta=pricing_check'>Check {html.escape(left['brand_name'])} pricing</a><a class='btn secondary' href='/go/{html.escape(right['offer_id'])}/?src=compare/{html.escape(slug)}&cta=pricing_check'>Check {html.escape(right['brand_name'])} pricing</a></p>
</section>
"""


def strengths_weaknesses_block(left: dict[str, str], right: dict[str, str]) -> str:
    return f"""
<section class='grid'>
  <div class='card'>
    <h2>{html.escape(left['brand_name'])} strengths / weaknesses</h2>
    <h3>Strengths</h3>
    <ul><li>Clear fit for people already researching {html.escape(left['niche'])}.</li><li>Good candidate for review, alternatives, and comparison research.</li><li>Can be evaluated with a focused workflow test.</li></ul>
    <h3>Weaknesses</h3>
    <ul><li>Official pricing and plan limits still need verification.</li><li>Affiliate policy and paid traffic rules should not be assumed.</li><li>Value depends on workflow adoption, not brand awareness alone.</li></ul>
  </div>
  <div class='card'>
    <h2>{html.escape(right['brand_name'])} strengths / weaknesses</h2>
    <h3>Strengths</h3>
    <ul><li>Useful benchmark against {html.escape(left['brand_name'])}.</li><li>May fit a different budget, interface preference, or use case.</li><li>Helps buyers avoid choosing from a single landing page.</li></ul>
    <h3>Weaknesses</h3>
    <ul><li>Pricing, integrations, and support expectations need direct confirmation.</li><li>May require a different learning curve or migration path.</li><li>Affiliate and promotion rules must be checked separately.</li></ul>
  </div>
</section>
"""


def use_case_block(left: dict[str, str], right: dict[str, str], category: str) -> str:
    return f"""
<section class='card'>
  <h2>Use case recommendation</h2>
  <p>Choose {html.escape(left['brand_name'])} if your current shortlist already leans toward its workflow and you can validate it with a small, realistic task. Choose {html.escape(right['brand_name'])} if the same task feels easier to run, explain, and maintain after a practical test.</p>
  <p>For {html.escape(category)}, the best comparison test is not a feature count. Pick one workflow, run it in both tools, record the output quality, check how much cleanup is needed, and then review whether the pricing and support model still make sense.</p>
  <p>If the goal is affiliate content, build a review page first, keep disclosure visible, and avoid direct claims about fixed savings, guaranteed results, or current discounts unless they are verified from the vendor. A comparison page should help readers choose responsibly, not push them into a rushed signup.</p>
</section>
"""


def review_links_block(left: dict[str, str], right: dict[str, str]) -> str:
    links = [
        review_link(left),
        review_link(right),
        "<a href='/reviews/'>All review pages</a>",
        "<a href='/comparisons/'>All comparison pages</a>",
        "<a href='/hubs/'>Research hubs</a>",
    ]
    return f"""
<section class='card'>
  <h2>Related research links</h2>
  <p>{' | '.join(links)}</p>
  <p>Use these internal links to compare the tools from different angles. The review pages focus on individual product fit, while the comparison page is better for deciding which product deserves the next official-site click.</p>
</section>
"""


def final_verdict_block(left: dict[str, str], right: dict[str, str], category: str) -> str:
    return f"""
<section class='card'>
  <h2>Final verdict</h2>
  <p>{html.escape(left['brand_name'])} vs {html.escape(right['brand_name'])} is not a universal winner-takes-all decision. For {html.escape(category)}, the better option is the one that reduces workflow friction, fits the current budget, and has clear enough terms for the way you plan to use or promote it.</p>
  <p>If both look close, start with the tool that has the clearer use case for your team and the easier way to verify pricing, support, and policy. If neither is clearly right, read the individual reviews and compare alternatives before clicking through.</p>
</section>
"""


def cta_block(left: dict[str, str], right: dict[str, str]) -> str:
    slug = f"{left['offer_id']}-vs-{right['offer_id']}"
    return f"""
<section class='card trust'>
  <h2>Next step</h2>
  <p>Use the tracking-safe buttons below to visit the official site for the tool you want to verify. If an approved affiliate URL is not available, the route uses the official-site destination only.</p>
  <p><a class='btn' href='/go/{html.escape(left['offer_id'])}/?src=compare/{html.escape(slug)}&cta=comparison_page'>Visit {html.escape(left['brand_name'])}</a><a class='btn secondary' href='/go/{html.escape(right['offer_id'])}/?src=compare/{html.escape(slug)}&cta=comparison_page'>Visit {html.escape(right['brand_name'])}</a></p>
</section>
"""


def faq_block(questions: list[str]) -> str:
    return f"<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>"


def faq_questions(left: str, right: str) -> list[str]:
    return [
        f"Is {left} better than {right}?",
        f"Which tool is easier for beginners?",
        f"How should I compare {left} and {right} pricing?",
        "What should I verify before buying either tool?",
        "Can I promote these tools as an affiliate?",
        "Should I read individual reviews before choosing?",
    ]


def comparison_profile(category: str, slug: str) -> dict:
    category_lower = category.lower()
    variant = stable_variant(slug)
    base_scores = {
        "left_scores": {"ease_of_use": 4, "pricing_clarity": 3, "feature_depth": 4, "team_fit": 4, "affiliate_confidence": 3},
        "right_scores": {"ease_of_use": 4, "pricing_clarity": 3, "feature_depth": 4, "team_fit": 4, "affiliate_confidence": 3},
    }
    score_notes = {
        "ease_of_use": "Score the first real workflow, not the homepage demo.",
        "pricing_clarity": "Higher score means fewer plan-limit surprises after checking official pricing.",
        "feature_depth": "Depth matters only if the extra features support your use case.",
        "team_fit": "Team fit depends on collaboration, permissions, and adoption friction.",
        "affiliate_confidence": "Confidence improves only after verifying affiliate and paid traffic terms.",
    }
    if "coding" in category_lower:
        profile = {
            "intro": "Coding comparisons should start inside a real repository, because autocomplete demos do not reveal review quality, context limits, or how much cleanup remains after a suggestion.",
            "verdict_heading": "Quick verdict for developers",
            "left_verdict": "you want the more focused AI coding workflow and can test it with real project context",
            "right_verdict": "you need a coding assistant that fits your existing editor, repository habits, or team policy",
            "choose_left": "Choose the first tool if editor flow and repository context matter more than broad ecosystem familiarity.",
            "choose_right": "Choose the second tool if your team values a different integration path, lower switching cost, or a familiar development setup.",
            "score_heading": "Coding workflow scorecard",
            "migration_heading": "Migration / switching consideration for coding teams",
            "migration_copy": "Switching coding tools affects editor settings, extensions, repository access, security review, and team habits. A small pilot with one repository is safer than moving every developer at once.",
            "pricing_risk": "Developer tools often look inexpensive per seat, but total cost changes when a whole team adopts them, when usage limits appear, or when governance requirements require a higher plan.",
            "team_size": "Solo developers can choose by speed and comfort. Small teams should evaluate review safety and shared standards. Larger teams need permission controls, security review, and predictable seat management.",
            "alternative": "If neither coding tool fits, compare another AI coding assistant or stay with your current editor plus a lighter assistant until the workflow gap is clearer.",
        }
        base_scores["left_scores"].update({"feature_depth": 5, "team_fit": 4})
        base_scores["right_scores"].update({"ease_of_use": 4, "pricing_clarity": 4})
    elif "seo" in category_lower:
        profile = {
            "intro": "SEO platform comparisons should focus on decision quality: whether the tool helps choose better topics, understand competitors, and avoid building pages nobody should publish.",
            "verdict_heading": "Quick verdict for SEO research",
            "left_verdict": "you need broader campaign research and can turn data into editorial briefs",
            "right_verdict": "you care more about deep organic research, backlink context, or focused SEO investigation",
            "choose_left": "Choose the first tool if your workflow combines keyword research, competitor checks, and marketing reporting.",
            "choose_right": "Choose the second tool if your team needs a sharper SEO research lens before content production.",
            "score_heading": "SEO research scorecard",
            "migration_heading": "Migration / switching consideration for SEO teams",
            "migration_copy": "Switching SEO platforms can change saved projects, keyword lists, reports, alerts, and team dashboards. Export key reports and compare sample SERPs before cancelling the old tool.",
            "pricing_risk": "SEO tools can become expensive when seats, projects, tracked keywords, or export limits grow. Review plan limits against your actual publishing cadence.",
            "team_size": "Solo publishers should prioritize actionable reports. Agencies need seats, exports, and client reporting. Larger content teams should check workflow handoff from research to briefs.",
            "alternative": "If neither fits, use a lighter keyword tool plus manual SERP review until the site has enough content velocity to justify a full SEO suite.",
        }
        base_scores["left_scores"].update({"feature_depth": 5, "team_fit": 4})
        base_scores["right_scores"].update({"feature_depth": 5, "ease_of_use": 3})
    elif "automation" in category_lower:
        profile = {
            "intro": "Automation tools should be compared by maintainability. A workflow that looks clever on day one can become risky if nobody can debug it after an app changes.",
            "verdict_heading": "Quick verdict for automation builders",
            "left_verdict": "you need visual workflow control, branching, and room to model more complex operations",
            "right_verdict": "you want fast setup, broad app coverage, and simpler automations for common business tasks",
            "choose_left": "Choose the first tool if your automation needs branching logic, data shaping, or careful scenario design.",
            "choose_right": "Choose the second tool if speed, app coverage, and lower setup friction matter more than visual complexity.",
            "score_heading": "Automation operations scorecard",
            "migration_heading": "Migration / switching consideration for automations",
            "migration_copy": "Automation migration is risky because hidden dependencies can break lead routing, notifications, billing tasks, or reporting. Document triggers and test each workflow before switching.",
            "pricing_risk": "Automation pricing can change with task volume, operations, premium connectors, or execution frequency. Estimate monthly usage before comparing plans.",
            "team_size": "Solo operators should start with the simplest reliable setup. Small teams need ownership and logs. Larger teams need naming rules, monitoring, and change control.",
            "alternative": "If neither tool fits, consider native app automations or a simpler workflow checklist before adding another automation layer.",
        }
        base_scores["left_scores"].update({"feature_depth": 5, "pricing_clarity": 4})
        base_scores["right_scores"].update({"ease_of_use": 5, "team_fit": 4})
    elif "email" in category_lower:
        profile = {
            "intro": "Email platform comparisons should begin with list quality, automation needs, and reporting, not with template galleries or one-time discounts.",
            "verdict_heading": "Quick verdict for email marketers",
            "left_verdict": "you need deeper automation, segmentation, or customer journey control",
            "right_verdict": "you want a simpler newsletter and campaign workflow with a familiar email marketing interface",
            "choose_left": "Choose the first tool if automation and CRM-adjacent follow-up are central to the business.",
            "choose_right": "Choose the second tool if newsletter publishing, simple campaigns, and easier onboarding matter more.",
            "score_heading": "Email marketing scorecard",
            "migration_heading": "Migration / switching consideration for email lists",
            "migration_copy": "Switching email platforms affects subscriber lists, automations, templates, deliverability, forms, and consent records. Export data carefully and test one segment before moving the entire list.",
            "pricing_risk": "Email pricing often scales with contacts, sends, automation depth, and add-ons. A cheap starting plan can become expensive as the list grows.",
            "team_size": "Solo users need speed and deliverability basics. Small teams need automation clarity. Larger teams need roles, reporting, compliance, and integration governance.",
            "alternative": "If neither fits, consider a simpler newsletter platform or a CRM-native email tool until segmentation needs become clearer.",
        }
        base_scores["left_scores"].update({"feature_depth": 5, "team_fit": 4})
        base_scores["right_scores"].update({"ease_of_use": 5, "pricing_clarity": 4})
    elif any(word in category_lower for word in ["design", "video", "creative"]):
        profile = {
            "intro": "Creative tool comparisons should judge the path from idea to publishable asset, including editing control, brand review, usage rights, and whether the output needs heavy cleanup.",
            "verdict_heading": "Quick verdict for creative teams",
            "left_verdict": "you want a practical creative workflow that can produce usable assets with review and edits",
            "right_verdict": "you need an alternative creative workflow that may better match a specific asset type or production style",
            "choose_left": "Choose the first tool if its output style matches the assets you create most often.",
            "choose_right": "Choose the second tool if it gives you better control, easier review, or a more suitable format for your campaign.",
            "score_heading": "Creative production scorecard",
            "migration_heading": "Migration / switching consideration for creative workflows",
            "migration_copy": "Creative switching can affect templates, brand assets, approval steps, usage rights, and file exports. Test a real asset before changing the team's production process.",
            "pricing_risk": "Creative AI pricing may depend on exports, credits, seats, commercial rights, or premium assets. Verify rights and usage limits before publishing work for clients.",
            "team_size": "Solo creators need speed and acceptable output. Small teams need review workflows. Larger teams need brand governance, reusable assets, and clear usage rights.",
            "alternative": "If neither fits, compare a broader design suite, a specialist AI generator, or a manual production workflow for high-value assets.",
        }
        base_scores["left_scores"].update({"ease_of_use": 4, "feature_depth": 4})
        base_scores["right_scores"].update({"ease_of_use": 4, "feature_depth": 4})
    else:
        profile = {
            "intro": "Writing tool comparisons should focus on editing quality, workflow fit, and whether the tool improves the draft without creating generic content that needs heavy rewriting.",
            "verdict_heading": "Quick verdict for writing workflows",
            "left_verdict": "you need a more structured writing workflow for campaigns, briefs, or long-form drafts",
            "right_verdict": "you want a lighter alternative for rewriting, ideation, or focused copy tasks",
            "choose_left": "Choose the first tool if your writing workflow needs structure, repeatability, and brand consistency.",
            "choose_right": "Choose the second tool if you need a focused assistant for smaller copy or rewriting tasks.",
            "score_heading": "Writing workflow scorecard",
            "migration_heading": "Migration / switching consideration for writers",
            "migration_copy": "Writing tool migration affects prompts, templates, brand voice notes, approval steps, and team habits. Test a real draft before moving your content workflow.",
            "pricing_risk": "Writing tools can look affordable until team seats, usage limits, or advanced features are needed. Verify plan limits against your publishing volume.",
            "team_size": "Solo writers should prioritize editing quality. Small teams need shared templates. Larger teams need brand governance and approval workflows.",
            "alternative": "If neither fits, use a general AI assistant plus a strict editorial checklist until the content workflow is better defined.",
        }
        base_scores["left_scores"].update({"feature_depth": 4, "team_fit": 4})
        base_scores["right_scores"].update({"ease_of_use": 4, "pricing_clarity": 4})

    if variant % 2:
        profile["intro"] = profile["intro"] + " In this pair, the practical test is less about popularity and more about which product creates fewer second-order problems after adoption."
        profile["score_heading"] = profile["score_heading"].replace("scorecard", "decision scorecard")
    if variant % 3 == 2:
        profile["verdict_heading"] = profile["verdict_heading"].replace("Quick verdict", "Quick decision verdict")
        profile["migration_heading"] = profile["migration_heading"].replace("Migration / switching", "Switching and migration")

    return {**profile, **base_scores, "score_notes": score_notes}


def stable_variant(text: str) -> int:
    return sum(ord(char) for char in str(text)) % 6


def review_link(tool: dict[str, str]) -> str:
    slug = html.escape(tool["offer_id"])
    name = html.escape(tool["brand_name"])
    if (settings.site_output_dir / "review" / tool["offer_id"] / "index.html").exists():
        return f"<a href='/review/{slug}/'>{name} review</a>"
    return f"<a href='/reviews/'>{name} review pending</a>"


def slugify(text: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
