from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd

from config import settings
from modules.programmatic_page_utils import affiliate_disclosure, breadcrumb_schema, faq_html, faq_schema, shell, write_page


INDEX_COLUMNS = [
    "offer_id",
    "brand_name",
    "review_slug",
    "title",
    "output_path",
    "status",
    "affiliate_status",
]


def generate_review_pages(output: Path, offer_scores: pd.DataFrame | None = None, landing_index: pd.DataFrame | None = None) -> list[dict[str, str]]:
    tools = prepare_tools(offer_scores, landing_index)
    if tools.empty:
        safe_write_index(pd.DataFrame(columns=INDEX_COLUMNS))
        return []

    pages: list[dict[str, str]] = []
    index_rows: list[dict[str, str]] = []
    all_tools = tools.to_dict("records")
    for _, row in tools.iterrows():
        tool = normalize_tool(row.to_dict())
        slug = tool["offer_id"]
        if not slug or not tool["brand_name"]:
            continue
        related = select_related_tools(tool, all_tools)
        page_path = write_page(output, f"review/{slug}", render_review_page(tool, related))
        title = review_title(tool)
        affiliate_status = "approved" if tool.get("affiliate_url") else "official_only"
        pages.append({"slug": f"review/{slug}", "title": title, "type": "tool_review"})
        index_rows.append(
            {
                "offer_id": slug,
                "brand_name": tool["brand_name"],
                "review_slug": slug,
                "title": title,
                "output_path": str(page_path),
                "status": "built",
                "affiliate_status": affiliate_status,
            }
        )

    safe_write_index(pd.DataFrame(index_rows, columns=INDEX_COLUMNS))
    return pages


def safe_write_index(index: pd.DataFrame) -> None:
    path = settings.data_dir / "review_pages_index.csv"
    try:
        index.to_csv(path, index=False)
    except PermissionError:
        if not path.exists():
            raise
        print(f"WARNING: {path} is locked. Keeping existing review_pages_index.csv.")


def prepare_tools(offer_scores: pd.DataFrame | None, landing_index: pd.DataFrame | None = None) -> pd.DataFrame:
    if offer_scores is None or offer_scores.empty:
        scores_path = settings.data_dir / "offer_scores.csv"
        offer_scores = pd.read_csv(scores_path).fillna("") if scores_path.exists() else pd.DataFrame()

    if offer_scores is not None and not offer_scores.empty:
        tools = offer_scores.copy().fillna("")
    else:
        landing_path = settings.data_dir / "landing_pages_index.csv"
        if landing_index is None and landing_path.exists():
            landing_index = pd.read_csv(landing_path).fillna("")
        tools = pd.DataFrame()
        if landing_index is not None and not landing_index.empty:
            tools = landing_index.rename(columns={"offer_id": "offer_id", "brand_name": "brand_name"}).copy()

    if tools.empty:
        return pd.DataFrame(columns=["offer_id", "brand_name"])

    if "offer_id" not in tools.columns:
        tools["offer_id"] = tools.get("brand_name", "").map(slugify)
    if "brand_name" not in tools.columns:
        tools["brand_name"] = tools["offer_id"].map(title_from_slug)
    tools["offer_id"] = tools["offer_id"].astype(str).map(slugify)
    tools["brand_name"] = tools["brand_name"].astype(str).str.strip()
    tools = tools[(tools["offer_id"] != "") & (tools["brand_name"] != "")]
    tools = tools.drop_duplicates(subset=["offer_id"], keep="first")
    if "total_score" in tools.columns:
        tools["_sort_score"] = pd.to_numeric(tools["total_score"], errors="coerce").fillna(0)
        tools = tools.sort_values(["_sort_score", "brand_name"], ascending=[False, True])
    else:
        tools = tools.sort_values("brand_name")
    return tools


def normalize_tool(row: dict) -> dict[str, str]:
    slug = slugify(row.get("offer_id") or row.get("brand_name") or "")
    brand = str(row.get("brand_name") or title_from_slug(slug)).strip()
    niche = clean_value(row.get("niche"), "AI/SaaS")
    website = clean_value(row.get("website"), "")
    affiliate_url = clean_value(row.get("affiliate_url"), "")
    score = clean_value(row.get("total_score"), "Not scored")
    risk = clean_value(row.get("risk_level"), "Needs review")
    competition = clean_value(row.get("competition"), "Unknown")
    trend = clean_value(row.get("trend"), "Stable")
    channels = clean_value(row.get("recommended_channels"), "SEO research, comparison pages, and careful paid search tests")
    return {
        "offer_id": slug,
        "brand_name": brand,
        "niche": niche,
        "website": website,
        "affiliate_url": affiliate_url,
        "score": score,
        "risk": risk,
        "competition": competition,
        "trend": trend,
        "recommended_channels": channels,
    }


def render_review_page(tool: dict[str, str], related_tools: list[dict[str, str]] | None = None) -> str:
    related_tools = related_tools or []
    brand = tool["brand_name"]
    slug = tool["offer_id"]
    niche = tool["niche"]
    path = f"/review/{slug}/"
    title = review_title(tool)
    description = review_description(tool)
    questions = faq_questions(brand)
    profile = category_profile(niche)
    body = "\n".join(
        [
            hero_block(tool, profile),
            affiliate_disclosure(),
            quick_verdict_block(tool, profile),
            overview_block(tool, profile),
            ai_coding_builder_block(tool) if is_ai_coding_tool(tool) else "",
            best_fit_block(tool, profile),
            feature_checklist_block(tool, profile),
            use_cases_block(tool, profile),
            pros_cons_block(tool, profile),
            buying_considerations_block(tool, profile),
            pricing_block(tool, profile),
            alternatives_block(tool, related_tools),
            final_verdict_block(tool, profile),
            cta_block(tool),
            faq_block(questions),
        ]
    )
    schemas = [faq_schema(questions), breadcrumb_schema(title, path), product_schema(tool, path)]
    return shell(title, description, path, body, schemas)


def review_title(tool: dict[str, str]) -> str:
    brand = tool["brand_name"]
    niche = tool["niche"]
    return f"{brand} Review for {niche} Buyers: Workflow Fit, Pricing Checks, and Alternatives"


def review_description(tool: dict[str, str]) -> str:
    brand = tool["brand_name"]
    niche = tool["niche"]
    signal = category_profile(niche)["decision_signal"]
    return f"{brand} review for {niche} buyers who need {signal}, realistic pricing research, alternatives, affiliate disclosure, and safe next steps before visiting the official site."


def hero_block(tool: dict[str, str], profile: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    niche = html.escape(tool["niche"])
    score = html.escape(str(tool["score"]))
    risk = html.escape(str(tool["risk"]))
    trend = html.escape(str(tool["trend"]))
    slug = html.escape(tool["offer_id"])
    intro = html.escape(profile["intro"])
    image = screenshot_html(tool["offer_id"], tool["brand_name"])
    return f"""
<section class='hero card'>
  <p><a href='/'>Home</a> / <a href='/reviews/'>Reviews</a> / {brand}</p>
  <p><span class='badge'>Research review</span> <span class='badge'>{niche}</span> <span class='badge'>Score {score}</span></p>
  <h1>{brand} Review for {niche} Buyers</h1>
  {image}
  <p>{intro} This {brand} review is written for readers who want a practical decision page before they click through to the official website. The focus is not hype; it is whether {brand} fits a real workflow, what should be verified, and which alternatives deserve a look.</p>
  <p><strong>Editorial score:</strong> {score} | <strong>Risk level:</strong> {risk} | <strong>Trend:</strong> {trend}</p>
  <p><strong>Pricing summary:</strong> verify current plan limits, usage caps, team seats, cancellation terms, and official pricing before buying or promoting {brand}.</p>
  <p><a class='btn' href='/go/{slug}/?src=review/{slug}&cta=review_page'>Visit Official Website</a><a class='btn secondary' href='/go/{slug}/?src=review/{slug}&cta=pricing_check'>Check current pricing</a></p>
  <p class='note'>CTA status: Official site / affiliate pending when no approved affiliate URL is available.</p>
</section>
"""


def screenshot_html(slug: str, brand: str) -> str:
    source = settings.base_dir / "assets" / "screenshots" / f"{slug}.png"
    if not source.exists():
        return ""
    alt = f"{brand} dashboard screenshot"
    return f"<figure><img class='screenshot' src='/assets/screenshots/{html.escape(slug)}.png' alt='{html.escape(alt)}' width='1200' height='720' loading='lazy' style='width:100%;height:auto;border-radius:8px;border:1px solid #dbe3ef'><figcaption>{html.escape(alt)} used for local editorial review context.</figcaption></figure>"


def quick_verdict_block(tool: dict[str, str], profile: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    niche = html.escape(tool["niche"])
    score = html.escape(str(tool["score"]))
    risk = html.escape(str(tool["risk"]))
    competition = html.escape(str(tool["competition"]))
    verdict = html.escape(profile["verdict"])
    return f"""
<section class='card trust'>
  <h2>Quick verdict</h2>
  <p><strong>{brand} is worth shortlisting if</strong> your {niche} workflow needs {verdict}. It should still be checked against current pricing, plan limits, support expectations, and affiliate policy before any serious purchase or promotion.</p>
  <div class='grid'>
    <div class='card'><h3>Score signal</h3><p>{score}. Treat this as an editorial research score, not proof that the tool will fit every buyer.</p></div>
    <div class='card'><h3>Risk signal</h3><p>{risk}. The main risk is usually policy, pricing, or workflow mismatch rather than the brand name itself.</p></div>
    <div class='card'><h3>Market signal</h3><p>{competition} competition. Comparison and review pages are usually safer than broad claims.</p></div>
  </div>
</section>
"""


def overview_block(tool: dict[str, str], profile: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    niche = html.escape(tool["niche"])
    competition = html.escape(str(tool["competition"]))
    channels = html.escape(str(tool["recommended_channels"]))
    workflow = html.escape(profile["workflow"])
    return f"""
<section class='card'>
  <h2>Overview</h2>
  <p>{brand} sits in the {niche} category, so the review lens is workflow fit rather than hype. In this category, the practical question is whether the tool can support {workflow} without adding a new layer of manual cleanup.</p>
  <p>The market around this type of software can be noisy. Some readers compare tools because they want a faster workflow, while others are checking pricing, alternatives, or whether the product is suitable for a team. This page keeps those questions separate so the decision does not come from a single feature list.</p>
  <p>Current research signals show competition as {competition}. That means a direct paid traffic test should be handled carefully, and organic pages should include comparison context, honest limitations, and a clear disclosure. Recommended discovery channels for this tool category include {channels}.</p>
  <p>A useful review of {brand} should therefore answer three buyer questions: what job the product is likely to help with, what kind of user should avoid it, and what proof still needs to come from the official website before money or traffic is committed.</p>
</section>
"""


def is_ai_coding_tool(tool: dict[str, str]) -> bool:
    slug = str(tool.get("offer_id", "")).lower()
    niche = str(tool.get("niche", "")).lower()
    return "coding" in niche or slug in {"cursor", "github-copilot", "windsurf", "codeium", "tabnine"}


def ai_coding_builder_block(tool: dict[str, str]) -> str:
    slug = html.escape(tool["offer_id"])
    brand = html.escape(tool["brand_name"])
    name = tool["brand_name"]
    if tool["offer_id"] == "cursor":
        verdict = "Cursor is strongest when the repository already has a clean shape and I need fast inline edits, file-aware questions, and controlled refactors."
        failed = "Cursor can loop when the prompt is too broad. I have seen the same fix rephrased several times instead of a smaller diagnosis. The fix is to narrow the file scope and ask for one patch with a testable reason."
        shines = "fast iteration, codebase explanation, small refactors, and editing a known module without leaving the editor"
    elif tool["offer_id"] == "github-copilot":
        verdict = "GitHub Copilot is useful as a steady autocomplete layer, especially when the team already lives inside GitHub and familiar IDEs."
        failed = "Copilot is weaker when the answer depends on architecture across several files. It can complete a local pattern nicely while missing the reason that pattern should not exist in this project."
        shines = "low-friction autocomplete, familiar team rollout, and small helper code where the surrounding context is obvious"
    elif tool["offer_id"] == "windsurf":
        verdict = "Windsurf is most interesting when I want a faster first pass through an agent-style workflow, then a stricter review pass before anything lands."
        failed = "The risk is speed without enough restraint. Agent-style edits can duplicate logic or touch more files than needed, so the review has to focus on diff size, shared helpers, and tests."
        shines = "rapid scaffolding, multi-step exploration, and workflow experiments where a normal autocomplete assistant feels too narrow"
    else:
        verdict = f"{name} should be tested inside a real repository, because AI coding tools only prove their value when they survive code review and build checks."
        failed = "The common failure is plausible code that ignores the existing project structure. A small repository test with failing checks is more useful than a polished demo prompt."
        shines = "focused coding assistance, review support, and practical developer workflow tests"

    return f"""
<section class='card'>
  <h2>My current AI coding workflow with {brand}</h2>
  <p>{html.escape(verdict)}</p>
  <p>In a real builder workflow, I do not ask one assistant to own the whole project. I use agent-style tools for the rough structure, Cursor-style editing for controlled changes, Copilot-style autocomplete for small local work, and Codex-style reasoning when the build or deployment pipeline breaks. That split keeps cost and cleanup under control.</p>
  <p>For {brand}, the practical test is simple: can it help me understand an existing module, make a small multi-file change, explain the failure, and keep the final diff readable? If the answer is yes, the tool belongs on the shortlist. If it only produces confident code that needs heavy cleanup, the subscription is harder to justify.</p>
  <aside class='card trust'><h3>Builder Note</h3><p>{brand} is most useful for {html.escape(shines)}. It should still be reviewed like a junior developer's pull request: useful, sometimes fast, but never automatically correct.</p></aside>
</section>
<section class='card'>
  <h2>What failed during practical testing</h2>
  <p>{html.escape(failed)}</p>
  <p>The mistake I try to avoid is letting the assistant grow the problem. If the first fix fails, I ask for a diagnosis, the exact files involved, and the smallest safe change. That prompt often works better than asking for another implementation.</p>
  <p>Deployment problems are a separate test. A strong AI coding assistant should read error output, check generated files, and reason about configuration before editing application code. This is where Codex-style repair can feel faster than a tool that keeps writing new code after every failure.</p>
</section>
<section class='card'>
  <h2>Practical AI coding comparison</h2>
  <table>
    <thead><tr><th>Area</th><th>{brand}</th><th>Cursor</th><th>Windsurf</th><th>GitHub Copilot</th></tr></thead>
    <tbody>
      <tr><td>Best daily use</td><td>{html.escape(shines)}</td><td>Inline editing and fast iteration</td><td>Rapid scaffolding and agent flow</td><td>Lightweight autocomplete</td></tr>
      <tr><td>Where it can fail</td><td>{html.escape(failed)}</td><td>Repeating the same repair loop</td><td>Duplicating logic across files</td><td>Missing broader project context</td></tr>
      <tr><td>Debugging style</td><td>Use small diffs and verify tests.</td><td>Good when file scope is clear.</td><td>Good when the agent stays focused.</td><td>Best for local syntax and API hints.</td></tr>
      <tr><td>Soft next step</td><td><a href='/go/{slug}/?src=review/{slug}&cta=builder_workflow'>Try {brand}</a></td><td><a href='/pricing/cursor/'>See Cursor pricing</a></td><td><a href='/windsurf-review/'>Read Windsurf review</a></td><td><a href='/review/github-copilot/'>Read Copilot review</a></td></tr>
    </tbody>
  </table>
</section>
"""


def best_fit_block(tool: dict[str, str], profile: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    niche = html.escape(tool["niche"])
    best = profile["best_for"]
    not_best = profile["not_best_for"]
    return f"""
<section class='card'>
  <h2>Best for / Not best for</h2>
  <div class='grid'>
    <div class='card'><h3>Best for</h3><ul>{''.join(f'<li>{html.escape(item)}</li>' for item in best)}</ul></div>
    <div class='card'><h3>Not best for</h3><ul>{''.join(f'<li>{html.escape(item)}</li>' for item in not_best)}</ul></div>
  </div>
  <p>{brand} is most relevant for readers who already know they need help in the {niche} workflow and want to compare a focused tool against broader alternatives. It may be the wrong choice if the use case is vague, if the team cannot verify integrations, or if the buying decision depends on a feature that is not confirmed by the vendor.</p>
</section>
"""


def feature_checklist_block(tool: dict[str, str], profile: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    items = profile["features"]
    return f"""
<section class='card'>
  <h2>Feature checklist</h2>
  <p>Use this checklist as a structured way to evaluate {brand}. It is not a substitute for official documentation, but it helps separate a useful product fit from a tool that merely looks good on a landing page.</p>
  <table>
    <thead><tr><th>Area to check</th><th>Why it matters</th><th>Buyer action</th></tr></thead>
    <tbody>
      {''.join(f"<tr><td>{html.escape(item[0])}</td><td>{html.escape(item[1])}</td><td>{html.escape(item[2])}</td></tr>" for item in items)}
    </tbody>
  </table>
</section>
"""


def use_cases_block(tool: dict[str, str], profile: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    niche = html.escape(tool["niche"])
    scenario = html.escape(profile["scenario"])
    return f"""
<section class='card'>
  <h2>Best use cases</h2>
  <p>The strongest reason to research {brand} is not that it belongs to a popular category. It is that a buyer may have a repeated task in {niche} where a structured tool can reduce manual work, improve consistency, or make collaboration easier to manage.</p>
  <p>A practical example is {scenario}. In that kind of workflow, the value comes from repeatability: the same process can be run again, reviewed by another person, and improved when results are weak.</p>
  <div class='grid'>
    <div class='card'><h3>Workflow setup</h3><p>Use the tool when you need a repeatable workflow that can be documented, reviewed, and improved over time.</p></div>
    <div class='card'><h3>Team comparison</h3><p>Compare it with alternatives when several team members need to understand tradeoffs before choosing a platform.</p></div>
    <div class='card'><h3>Affiliate research</h3><p>Use review-style content when direct linking or trademark bidding is unclear and a safer disclosure page is needed.</p></div>
  </div>
  <p>For paid traffic or affiliate promotion, the safer route is to start with review and comparison keywords. Avoid implying guaranteed outcomes, fixed savings, or current pricing unless those details were verified directly from the vendor at the time of publishing.</p>
</section>
"""


def pros_cons_block(tool: dict[str, str], profile: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    pro = html.escape(profile["pro"])
    con = html.escape(profile["con"])
    return f"""
<section class='card'>
  <h2>Pros and cons</h2>
  <table>
    <thead><tr><th>Pros</th><th>Cons</th></tr></thead>
    <tbody>
      <tr><td>+ {pro}</td><td>- {con}</td></tr>
      <tr><td>+ Can support comparison and review content without exaggerated claims.</td><td>- Not every traffic source or direct-linking method may be allowed.</td></tr>
      <tr><td>+ Useful for building a practical shortlist with alternatives.</td><td>- Real value depends on the user's process, team size, and integrations.</td></tr>
    </tbody>
  </table>
  <p>For {brand}, the main advantage is that it gives buyers a concrete product to evaluate instead of a vague category search. The main limitation is that public research alone is not enough for final buying or promotion decisions. Always confirm terms, plan limits, current pricing, cancellation rules, and allowed promotional methods.</p>
</section>
"""


def buying_considerations_block(tool: dict[str, str], profile: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    niche = html.escape(tool["niche"])
    return f"""
<section class='card'>
  <h2>Real buying considerations</h2>
  <p>Before treating {brand} as the right {niche} choice, slow down and check the operational details that rarely fit into a short product summary. The biggest mistakes usually happen when a buyer assumes a feature is included, a traffic source is allowed, or a team workflow will transfer cleanly from another product.</p>
  <ul>
    <li><strong>Workflow proof:</strong> write down the exact process you expect {brand} to improve, then check whether the product supports each step.</li>
    <li><strong>Team fit:</strong> confirm seats, permissions, sharing, and collaboration limits if more than one person will use it.</li>
    <li><strong>Policy fit:</strong> for affiliate or paid traffic work, confirm PPC, brand bidding, direct linking, coupon rules, and disclosure requirements.</li>
    <li><strong>Exit risk:</strong> understand export options, cancellation rules, and how hard it would be to move to another tool later.</li>
  </ul>
  <p>This review intentionally avoids guaranteed outcomes. A tool can be strong in public research and still be wrong for a particular team, budget, country, or traffic strategy.</p>
</section>
"""


def pricing_block(tool: dict[str, str], profile: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    slug = html.escape(tool["offer_id"])
    return f"""
<section class='card'>
  <h2>Pricing note</h2>
  <p>Pricing can change, and this page does not treat any plan, discount, or payout as permanent. Before buying {brand}, check the official pricing page for plan limits, included seats, usage caps, cancellation rules, trial terms, and whether the features you need are available on the plan you are considering.</p>
  <p>If you are researching the product as an affiliate, also check the affiliate program terms separately. A product can be attractive for buyers while still having restrictions around PPC, coupon keywords, brand bidding, direct linking, or country eligibility.</p>
  <p><a class='btn secondary' href='/go/{slug}/?src=review/{slug}&cta=pricing_research'>Verify pricing on official site</a></p>
</section>
"""


def alternatives_block(tool: dict[str, str], related_tools: list[dict[str, str]]) -> str:
    brand = html.escape(tool["brand_name"])
    if related_tools:
        links = "".join(f"<li><a href='/review/{html.escape(item['offer_id'])}/'>{html.escape(item['brand_name'])}</a> for another {html.escape(item['niche'])} workflow angle.</li>" for item in related_tools[:5])
    else:
        links = "<li><a href='/reviews/'>Browse all reviews</a> to compare related AI and SaaS tools.</li>"
    return f"""
<section class='card'>
  <h2>Alternatives</h2>
  <p>{brand} should be compared against alternatives before a serious purchase or promotion decision. Alternatives help reveal whether the product is priced fairly for your workflow, whether a simpler tool would be enough, and whether a different category solves the same problem with less operational friction.</p>
  <ul>{links}</ul>
  <p>When comparing alternatives, avoid treating a higher score as automatic proof. Look at workflow fit, policy clarity, integrations, support expectations, cancellation terms, and whether the product solves the specific job that led you to search in the first place.</p>
</section>
"""


def final_verdict_block(tool: dict[str, str], profile: dict[str, str]) -> str:
    brand = html.escape(tool["brand_name"])
    risk = html.escape(str(tool["risk"]))
    recommendation = html.escape(profile["recommendation"])
    return f"""
<section class='card'>
  <h2>Final recommendation</h2>
  <p>{brand} is worth researching when the use case is clear and the buyer understands what must be verified on the official website. It is not a tool to promote with exaggerated promises, fixed income claims, or outdated pricing details. The safer approach is to use this review as a screening page, then check the vendor's latest terms before any purchase or campaign.</p>
  <p>For affiliate work, the current risk level is {risk}. That does not mean the offer is automatically unsafe. It means the page should keep disclosure visible, send outbound clicks through tracking, and avoid claims that cannot be supported by current vendor information.</p>
  <p>{recommendation}</p>
  <p>Recommended next step: compare {brand} with at least two alternatives, verify current pricing, and document the policy notes before using paid traffic or recommending it to a specific audience.</p>
</section>
"""


def cta_block(tool: dict[str, str]) -> str:
    slug = html.escape(tool["offer_id"])
    brand = html.escape(tool["brand_name"])
    return f"""
<section class='card trust'>
  <h2>Next step</h2>
  <p>If {brand} still looks relevant after this review, visit the official website through the tracking link below and verify the latest product details yourself. The link may route to an approved affiliate URL when available; otherwise it uses the Official site / affiliate pending destination.</p>
  <p><a class='btn' href='/go/{slug}/?src=review/{slug}&cta=review_page'>Visit Official Website</a><a class='btn secondary' href='/comparisons/'>Compare more tools</a><a class='btn secondary' href='/reviews/'>Browse reviews</a></p>
</section>
"""


def faq_block(questions: list[str]) -> str:
    return f"<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>"


def faq_questions(brand: str) -> list[str]:
    return [
        f"Is {brand} beginner-friendly?",
        f"How should I check {brand} pricing?",
        f"What are the best alternatives to {brand}?",
        f"Can teams use {brand}?",
        f"Does {brand} support integrations?",
        f"What should I verify before promoting {brand} as an affiliate?",
    ]


def product_schema(tool: dict[str, str], path: str) -> str:
    import json

    base = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": tool["brand_name"],
        "category": tool["niche"],
        "url": f"{base}{path}",
        "review": {
            "@type": "Review",
            "author": {"@type": "Person", "name": "Nguyen Quoc Tuan"},
            "reviewBody": f"Research-style review of {tool['brand_name']} for practical buyer comparison, pricing verification, alternatives, and affiliate disclosure.",
        },
    }
    score = str(tool.get("score", "")).strip()
    try:
        rating = float(score)
    except ValueError:
        rating = 0
    if rating > 0:
        schema["review"]["reviewRating"] = {"@type": "Rating", "ratingValue": min(max(rating / 20, 1), 5), "bestRating": 5, "worstRating": 1}
    return json.dumps(schema, ensure_ascii=False)


def category_profile(niche: str) -> dict:
    text = str(niche or "").lower()
    if "coding" in text or "developer" in text:
        return {
            "intro": "AI coding tools are judged by how well they fit daily development work, not by how impressive a single demo looks.",
            "decision_signal": "code editing support, repository context, and developer workflow fit",
            "workflow": "writing, reviewing, refactoring, and explaining code inside a developer workflow",
            "verdict": "developer productivity support, code context, and a workflow that does not interrupt normal engineering habits",
            "scenario": "a developer using AI assistance to inspect an unfamiliar file, draft a safer change, and review edge cases before committing code",
            "pro": "Strong fit when the buyer already has recurring coding, debugging, or documentation work.",
            "con": "Can disappoint teams that expect AI to replace engineering judgment or code review.",
            "recommendation": "Shortlist it when the team can test it inside a real repository and compare output quality against existing editor habits.",
            "best_for": ["Developers comparing AI coding assistants.", "Technical teams with repeated code review or refactor work.", "Buyers who can test the tool in an existing repository."],
            "not_best_for": ["Non-technical users expecting a no-code business app.", "Teams that cannot review generated code safely.", "Buyers who need guaranteed code quality without manual checks."],
            "features": [
                ("Editor workflow", "Coding tools must fit the place where developers already work.", "Test it inside a real project."),
                ("Context handling", "Repository awareness affects answer quality and usefulness.", "Check how it handles multi-file tasks."),
                ("Review safety", "AI suggestions still need human review.", "Keep normal code review active."),
            ],
        }
    if "seo" in text:
        return {
            "intro": "SEO software should be reviewed by research depth, workflow clarity, and whether it helps decisions without encouraging spam.",
            "decision_signal": "keyword research, content planning, competitor checks, and reporting workflow fit",
            "workflow": "finding search opportunities, auditing content, planning pages, and comparing organic competitors",
            "verdict": "SEO planning support with enough structure to improve research without replacing editorial judgment",
            "scenario": "a marketer comparing topic gaps, checking SERP intent, and deciding whether a page deserves a full editorial brief",
            "pro": "Useful when organic research and comparison workflows are already part of the business.",
            "con": "Can become expensive or noisy if the team does not know which SEO questions it needs answered.",
            "recommendation": "Shortlist it when you need repeatable SEO research and can verify data quality against actual search results.",
            "best_for": ["SEO teams building topic plans.", "Content operators comparing competitors.", "Affiliate publishers prioritizing buyer-intent pages."],
            "not_best_for": ["Users who only need a one-time keyword list.", "Teams expecting rankings without editorial work.", "Sites that cannot create useful original content."],
            "features": [
                ("Keyword research", "Search intent drives whether a page can convert.", "Check buyer-intent keyword coverage."),
                ("Competitor analysis", "Comparable pages reveal realistic ranking difficulty.", "Review SERP examples manually."),
                ("Content workflow", "Research has to become publishable briefs.", "Check export and collaboration options."),
            ],
        }
    if "automation" in text:
        return {
            "intro": "Automation tools are best judged by how reliably they connect real processes, not by the number of app logos on a homepage.",
            "decision_signal": "workflow automation logic, app connections, error handling, and maintenance cost",
            "workflow": "connecting apps, moving data, triggering actions, and reducing repeated manual operations",
            "verdict": "automation workflows that save repeated effort without creating fragile processes nobody can maintain",
            "scenario": "a small team routing lead data from a form into a CRM, sending a notification, and logging the action for follow-up",
            "pro": "Good fit for repeated workflows where manual copying or status updates waste time.",
            "con": "Can create hidden maintenance work if automations are built without documentation.",
            "recommendation": "Shortlist it when the workflow is repeated often enough to justify setup, testing, and monitoring.",
            "best_for": ["Operators connecting SaaS tools.", "Small teams reducing repeated admin work.", "Builders who can document and test workflows."],
            "not_best_for": ["One-off tasks that do not repeat.", "Teams without clear process ownership.", "Workflows requiring unsupported private systems."],
            "features": [
                ("App connectors", "The tool must support the apps in your workflow.", "Confirm exact triggers and actions."),
                ("Error handling", "Broken automations can silently lose data.", "Check logs and retry behavior."),
                ("Scenario design", "Complex flows need visual clarity.", "Map the workflow before buying."),
            ],
        }
    if "voice" in text or "video" in text or "design" in text or "presentation" in text:
        return {
            "intro": "Creative AI tools should be evaluated by output quality, editing control, usage rights, and whether the workflow fits a real publishing process.",
            "decision_signal": "creative output quality, editing control, commercial usage terms, and production workflow fit",
            "workflow": "turning ideas into usable creative assets while keeping review, edits, and rights clear",
            "verdict": "creative production support where output quality and licensing can be verified before publishing",
            "scenario": "a creator drafting a campaign asset, reviewing it for accuracy, making revisions, and confirming rights before using it publicly",
            "pro": "Helpful for teams that create repeated visual, audio, or presentation assets.",
            "con": "Output can still require editing, fact checks, brand review, and rights verification.",
            "recommendation": "Shortlist it when the workflow includes human review and the licensing terms match your publishing use case.",
            "best_for": ["Creators producing recurring content.", "Marketing teams testing asset variations.", "Businesses that review brand and legal fit before publishing."],
            "not_best_for": ["Users expecting perfect final assets without editing.", "Teams that cannot verify commercial rights.", "Projects requiring exact brand or legal approval on every output."],
            "features": [
                ("Output quality", "Creative tools must produce assets worth editing.", "Test with your real prompt style."),
                ("Editing control", "Small revisions often decide whether output is usable.", "Check revision workflow."),
                ("Usage rights", "Commercial use rules matter.", "Read licensing terms before publishing."),
            ],
        }
    if "crm" in text or "email" in text or "marketing" in text:
        return {
            "intro": "Marketing and CRM tools should be reviewed by customer workflow fit, reporting clarity, and whether the team can adopt them without creating extra admin work.",
            "decision_signal": "customer data workflow, campaign operations, reporting, and team adoption fit",
            "workflow": "capturing leads, following up, segmenting audiences, and measuring customer or campaign activity",
            "verdict": "customer workflow support that makes follow-up and reporting clearer rather than adding administrative friction",
            "scenario": "a team capturing a lead, assigning ownership, sending the right follow-up, and measuring whether the process actually improved response quality",
            "pro": "Useful when customer communication or sales follow-up needs a repeatable system.",
            "con": "Can become expensive or underused if the team has not defined its customer process.",
            "recommendation": "Shortlist it when the team has a clear funnel and can verify data, automation, and reporting needs before buying.",
            "best_for": ["Sales or marketing teams managing repeated customer interactions.", "Businesses comparing automation and reporting workflows.", "Affiliate publishers writing review and alternative pages."],
            "not_best_for": ["Teams without a defined customer process.", "Users who only need a simple contact list.", "Buyers who cannot verify compliance and data handling requirements."],
            "features": [
                ("Contact workflow", "Customer data must stay organized.", "Check fields, lists, and segmentation."),
                ("Automation", "Follow-up can improve only when rules are clear.", "Test a simple campaign first."),
                ("Reporting", "Teams need to see what changed.", "Review dashboard and export options."),
            ],
        }
    return {
        "intro": "SaaS tools should be reviewed by practical workflow fit, pricing clarity, and whether the product solves a repeatable problem.",
        "decision_signal": "workflow fit, pricing clarity, support expectations, and realistic alternatives",
        "workflow": "organizing a repeated business process and reducing avoidable manual work",
        "verdict": "a clear workflow match and policy details that can be verified before buying or promoting",
        "scenario": "a user documenting a repeated task, testing the product on that task, and comparing the result with at least two alternatives",
        "pro": "Clear category fit for buyers already researching this workflow.",
        "con": "Pricing, limits, and affiliate terms still need official verification.",
        "recommendation": "Shortlist it only after the workflow is defined and the official pricing and policy pages have been checked.",
        "best_for": ["Buyers comparing SaaS tools for a defined workflow.", "Small teams needing repeatable processes.", "Researchers building a careful shortlist."],
        "not_best_for": ["Users with a vague or one-time need.", "Teams that cannot verify vendor terms.", "Buyers looking for guaranteed outcomes."],
        "features": [
            ("Workflow fit", "The product should solve a repeated job.", "Test it against a real use case."),
            ("Pricing clarity", "Plan limits affect value.", "Verify current pricing."),
            ("Policy clarity", "Affiliate and paid traffic rules can change.", "Read official terms."),
        ],
    }


def select_related_tools(tool: dict[str, str], all_tools: list[dict]) -> list[dict[str, str]]:
    current = tool["offer_id"]
    niche_tokens = token_set(tool.get("niche", ""))
    scored = []
    for raw in all_tools:
        item = normalize_tool(raw)
        if item["offer_id"] == current:
            continue
        score = len(niche_tokens & token_set(item.get("niche", ""))) * 3
        score += len(token_set(tool["brand_name"]) & token_set(item["brand_name"]))
        if score <= 0:
            score = 1
        scored.append((score, item["brand_name"], item))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in scored[:5]]


def clean_value(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text and text.lower() not in {"nan", "none"} else fallback


def slugify(text: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def title_from_slug(slug: str) -> str:
    known = {
        "copy-ai": "Copy.ai",
        "github-copilot": "GitHub Copilot",
        "surfer-seo": "Surfer SEO",
        "webflow-ai": "Webflow AI",
        "notion-ai": "Notion AI",
        "elevenlabs": "ElevenLabs",
        "hubspot": "HubSpot",
    }
    return known.get(slug, slug.replace("-", " ").title())


def token_set(text: object) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", str(text).lower()) if token not in {"ai", "tool", "tools", "saas"}}
