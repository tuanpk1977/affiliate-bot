from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd

from config import settings
from modules.programmatic_page_utils import affiliate_disclosure, breadcrumb_schema, faq_html, faq_schema, item_list_schema, review_url, shell, write_page


INDEX_COLUMNS = ["keyword", "suggested_slug", "page_type", "title", "output_path", "status"]


def generate_priority_pages(output: Path, offer_scores: pd.DataFrame | None = None, priority_plan: pd.DataFrame | None = None) -> list[dict[str, str]]:
    plan = priority_plan if priority_plan is not None else load_priority_plan()
    if plan.empty:
        safe_write_index(pd.DataFrame(columns=INDEX_COLUMNS))
        return []

    money_pages = plan[plan["page_type"].astype(str) == "money_page"].copy()
    offers = prepare_offers(offer_scores)
    pages: list[dict[str, str]] = []
    index_rows: list[dict[str, str]] = []

    for _, row in money_pages.iterrows():
        keyword = str(row.get("keyword", "")).strip()
        slug = str(row.get("suggested_slug", "")).strip()
        title = str(row.get("target_page_title", "")).strip() or title_from_keyword(keyword)
        if not keyword or not slug:
            continue
        tools = select_tools_for_keyword(keyword, offers)
        page_path = write_page(output, slug, render_priority_page(row.to_dict(), tools))
        pages.append({"slug": slug, "title": title, "type": "priority_page"})
        index_rows.append({"keyword": keyword, "suggested_slug": slug, "page_type": str(row.get("page_type", "")), "title": title, "output_path": str(page_path), "status": "built"})

    safe_write_index(pd.DataFrame(index_rows, columns=INDEX_COLUMNS))
    return pages


def safe_write_index(index: pd.DataFrame) -> None:
    path = settings.data_dir / "priority_pages_index.csv"
    try:
        index.to_csv(path, index=False)
    except PermissionError:
        if not path.exists():
            raise
        print(f"WARNING: {path} is locked. Keeping existing priority_pages_index.csv.")


def load_priority_plan() -> pd.DataFrame:
    path = settings.data_dir / "keyword_priority_plan.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path).fillna("")


def prepare_offers(offer_scores: pd.DataFrame | None) -> pd.DataFrame:
    if offer_scores is None or offer_scores.empty:
        return pd.DataFrame(columns=["offer_id", "brand_name", "niche", "total_score", "risk_level", "recommendation"])
    offers = offer_scores.copy().fillna("")
    offers["_sort_score"] = pd.to_numeric(offers.get("total_score", 0), errors="coerce").fillna(0)
    return offers.sort_values("_sort_score", ascending=False)


def render_priority_page(row: dict, tools: pd.DataFrame) -> str:
    keyword = str(row.get("keyword", "")).strip()
    keyword_group = str(row.get("keyword_group", "")).strip() or infer_keyword_group(keyword)
    slug = str(row.get("suggested_slug", "")).strip()
    variant = stable_variant(slug)
    title = str(row.get("target_page_title", "")).strip() or title_from_keyword(keyword)
    topic = readable_topic(keyword)
    path = f"/{slug}/"
    description = f"Editorial research guide for {keyword}. Compare realistic options, risks, official pricing checks, and tracking-safe next steps before choosing a tool."
    primary_tools = [str(tool.get("brand_name", "")) for _, tool in tools.iterrows() if str(tool.get("brand_name", "")).strip()]
    questions = faq_questions(topic, keyword_group)

    blocks = {
        "method": method_block(keyword_group, variant, topic),
        "tools": tools_block(keyword_group, tools, slug, variant, topic),
        "comparison": comparison_block(keyword_group, tools, variant, topic),
        "choice": choice_block_group(keyword_group, tools, variant, topic),
        "workflow": workflow_block(keyword, keyword_group, primary_tools, variant),
        "risks": risk_block(keyword_group, variant, topic),
        "related": related_block(primary_tools),
        "faq": f"<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>",
        "cta": cta_block(keyword_group, tools, slug, variant),
    }
    sections = [
        hero_block(title, keyword, keyword_group, variant),
        affiliate_disclosure(),
        audience_block(keyword_group, variant, topic),
    ]
    sections.extend(blocks[key] for key in priority_section_order(keyword_group, variant))
    body = "\n".join(sections)
    schemas = [faq_schema(questions), breadcrumb_schema(title, path), item_list_schema(title, primary_tools, path)]
    return shell(title, description, path, body, schemas)


def hero_block(title: str, keyword: str, keyword_group: str, variant: int = 0) -> str:
    return f"""
<section class='hero card'>
  <p><a href='/'>Home</a> / Priority page</p>
  <h1>{html.escape(title)}</h1>
  <p>{priority_intro(keyword, keyword_group, variant)}</p>
  <p>This page is a research aid, not a promise of results, rankings, income, or product fit. Pricing, plan limits, and affiliate terms can change, so confirm the latest details on the official website before buying or promoting a tool.</p>
</section>
"""


def audience_block(keyword_group: str, variant: int = 0, topic: str = "") -> str:
    return f"""
<section class='card'>
  <h2>{audience_heading(keyword_group, variant, topic)}</h2>
  <p>{audience_copy(keyword_group, variant)}</p>
  <p>If the tool will support client work, customer data, paid traffic, or a team workflow, use this page as the first filter only. The final decision should come after checking the product, policy, support terms, and at least one serious alternative.</p>
</section>
"""


def method_block(keyword_group: str, variant: int = 0, topic: str = "") -> str:
    return f"""
<section class='card'>
  <h2>{method_heading(keyword_group, variant, topic)}</h2>
  <p>{method_copy(keyword_group, variant)}</p>
  <ul>
    <li><strong>Workflow fit:</strong> whether the product solves a repeated job rather than a one-time curiosity.</li>
    <li><strong>Buyer intent:</strong> whether the query suggests review, pricing, comparison, or alternatives research.</li>
    <li><strong>Trust signals:</strong> whether enough public product and policy information exists for safe research.</li>
    <li><strong>Promotion risk:</strong> whether PPC, direct linking, or trademark bidding needs manual verification.</li>
    <li><strong>Affiliate practicality:</strong> whether the topic deserves deeper content before any paid traffic test.</li>
  </ul>
</section>
"""


def tools_block(keyword_group: str, tools: pd.DataFrame, source_slug: str, variant: int = 0, topic: str = "") -> str:
    rows = "\n".join(tool_row(tool, source_slug) for _, tool in tools.iterrows())
    cards = "\n".join(tool_card(tool, source_slug) for _, tool in tools.iterrows())
    return f"""
<section class='card'>
  <h2>{tools_heading(keyword_group, variant, topic)}</h2>
  <p>{tools_intro(keyword_group, variant)}</p>
  <table><thead><tr><th>Tool</th><th>Best for</th><th>Risk note</th><th>Actions</th></tr></thead><tbody>{rows}</tbody></table>
</section>
<section class='grid'>{cards}</section>
"""


def comparison_block(keyword_group: str, tools: pd.DataFrame, variant: int = 0, topic: str = "") -> str:
    rows = "\n".join(quick_comparison_row(tool, idx) for idx, (_, tool) in enumerate(tools.iterrows(), start=1))
    return f"""
<section class='card'>
  <h2>{comparison_heading(keyword_group, variant, topic)}</h2>
  <p>{comparison_intro(keyword_group, variant)}</p>
  <table><thead><tr><th>Rank</th><th>Tool</th><th>Likely fit</th><th>What to verify</th></tr></thead><tbody>{rows}</tbody></table>
</section>
"""


def choice_block_group(keyword_group: str, tools: pd.DataFrame, variant: int = 0, topic: str = "") -> str:
    blocks = "\n".join(choice_block(tool, idx) for idx, (_, tool) in enumerate(tools.iterrows(), start=1))
    return f"""
<section class='card'>
  <h2>{choice_heading(keyword_group, variant, topic)}</h2>
  <p>{choice_intro(keyword_group, variant)}</p>
  {blocks}
</section>
"""


def workflow_block(keyword: str, keyword_group: str, tool_names: list[str], variant: int = 0) -> str:
    return f"<section class='card'><h2>{workflow_heading(keyword_group, variant)}</h2>{workflow_section(keyword, keyword_group, tool_names, variant)}</section>"


def risk_block(keyword_group: str, variant: int = 0, topic: str = "") -> str:
    return f"""
<section class='card'>
  <h2>{risk_heading(keyword_group, variant, topic)}</h2>
  <p>{risk_copy(keyword_group, variant)}</p>
  <ul>
    <li>Verify current pricing, plan limits, cancellation terms, and refund rules on the official website.</li>
    <li>Check whether affiliate promotion allows PPC, Google Ads, Bing Ads, direct linking, and trademark bidding.</li>
    <li>Do not assume a high score means the offer is safe for every country, traffic source, or audience.</li>
    <li>Use a landing page with affiliate disclosure if direct linking is restricted or unclear.</li>
    <li>For paid traffic, start with small tests and measure click quality before increasing budget.</li>
  </ul>
</section>
"""


def related_block(tool_names: list[str]) -> str:
    return f"""
<section class='card'>
  <h2>Related research</h2>
  <p><a href='/reviews/'>Browse all reviews</a> | <a href='/comparisons/'>Browse comparisons</a> | <a href='/blog/'>Read research articles</a></p>
  {related_links(tool_names)}
</section>
"""


def cta_block(keyword_group: str, tools: pd.DataFrame, source_slug: str, variant: int = 0) -> str:
    return f"""
<section class='card'>
  <h2>{cta_heading(keyword_group, variant)}</h2>
  <p>{cta_copy(keyword_group, variant)}</p>
  {''.join(priority_cta(tool, source_slug) for _, tool in tools.head(3).iterrows())}
</section>
"""


def priority_section_order(keyword_group: str, variant: int = 0) -> list[str]:
    if keyword_group == "alternatives":
        orders = [
            ["tools", "comparison", "choice", "workflow", "method", "risks", "related", "faq", "cta"],
            ["method", "tools", "choice", "comparison", "risks", "workflow", "related", "faq", "cta"],
            ["workflow", "tools", "comparison", "method", "choice", "risks", "related", "faq", "cta"],
            ["risks", "method", "tools", "comparison", "choice", "workflow", "related", "faq", "cta"],
        ]
        return orders[variant % len(orders)]
    if keyword_group == "pricing":
        return ["risks", "method", "comparison", "tools", "choice", "workflow", "related", "faq", "cta"]
    if keyword_group == "review":
        return ["method", "tools", "workflow", "comparison", "choice", "risks", "related", "faq", "cta"]
    if keyword_group == "comparison":
        return ["comparison", "choice", "tools", "method", "workflow", "risks", "related", "faq", "cta"]
    return ["method", "tools", "comparison", "workflow", "choice", "risks", "related", "faq", "cta"]


def priority_intro(keyword: str, keyword_group: str, variant: int = 0) -> str:
    topic = html.escape(readable_topic(keyword))
    focus = html.escape(subject_focus(keyword))
    variants = {
        "alternatives": [
            f"If {topic} is on your shortlist, the real task is not finding more names. For this topic, the first filter is {focus}, then whether each replacement can handle the workflow without new friction.",
            f"People usually search for {topic} after running into a limit around {focus}. This page starts from that replacement pressure instead of treating every similar product as equal.",
            f"The useful way to research {topic} is to name the job that failed first. Here, that job is mostly about {focus}, so the shortlist is judged against that practical gap.",
            f"A crowded market makes {topic} harder than it looks. This guide narrows the field around {focus}, policy risk, and whether each option deserves a deeper manual review.",
        ],
        "pricing": [
            f"Pricing searches for {topic} are rarely only about price. The real question is whether the plan limits, cancellation terms, and product fit make sense for your use case.",
            f"Before paying for {topic}, the safer move is to define the workflow, then check which plan actually supports it without surprise limits.",
        ],
        "review": [
            f"A useful review search for {topic} should answer more than whether a tool is popular. For this topic, the review lens is {focus}, plus what still needs official confirmation.",
            f"When researching {topic}, treat every review as a starting point. The key is whether {focus} matches your workflow and whether policy details are clear enough.",
            f"The best way to read a {topic} page is to look for practical evidence: where {focus} matters, what the tool does not solve, and what needs vendor verification.",
            f"A review-style page for {topic} should reduce uncertainty before the official-site visit. This one focuses on {focus}, buyer friction, and safe next steps.",
        ],
        "comparison": [
            f"Comparison searches for {topic} usually mean you are close to choosing. This page turns that decision into a shortlist with clear tradeoffs and safer next steps.",
            f"If you are comparing {topic}, the decision should come from workflow fit and risk, not from whichever product has the louder landing page.",
        ],
    }
    options = variants.get(keyword_group) or [f"This guide helps narrow {topic} into a practical shortlist, with context around workflow fit, risks, related reviews, and official-site checks."]
    return options[variant % len(options)]


def pick(options: list[str], variant: int) -> str:
    return options[variant % len(options)]


def audience_heading(group: str, variant: int = 0, topic: str = "") -> str:
    topic = topic or "This topic"
    if group == "alternatives":
        return [
            f"Who should use this {topic} guide",
            f"Best-fit readers for {topic}",
            f"Use this page if you are switching {topic}",
            f"Who gets value from this {topic} map",
        ][variant % 4]
    return {
        "pricing": ["Who needs this pricing research", "Who should check plan details first"],
        "review": [f"Who should read this {topic} review path", f"Best-fit readers for {topic} research", f"When this {topic} guide helps", f"Who needs a structured look at {topic}"],
        "comparison": ["Who should compare these options", "Who needs a side-by-side view"],
    }.get(group, ["Who this page is for"])[variant % len({"alternatives": [1, 2, 3, 4]}.get(group, [1]))]


def audience_copy(group: str, variant: int = 0) -> str:
    return {
        "alternatives": [
            "Use this page if you are replacing a tool, comparing similar products, or building an affiliate article that needs more than a generic list.",
            "This page is for readers who already know the category but need a practical way to decide which alternative deserves testing.",
            "Use this shortlist when the current tool feels too expensive, too limited, too complex, or too weak for the workflow you actually run.",
            "This page helps buyers and affiliate researchers move from broad alternatives research into a smaller set of pages worth reading carefully.",
        ][variant % 4],
        "pricing": "Use this page if price is only one part of the decision and you also need to check limits, upgrade paths, refunds, and policy restrictions.",
        "review": "Use this page if you want a structured review path before opening the official product page or creating affiliate content.",
        "comparison": "Use this page if you have two or more serious options and need to decide which one deserves the next trial or deeper review.",
    }.get(group, "Use this page if you need a structured research path before buying software, writing affiliate content, or planning traffic tests.")


def method_heading(group: str, variant: int = 0, topic: str = "") -> str:
    topic = topic or "These options"
    if group == "alternatives":
        return [
            f"How {topic} options are filtered",
            f"How this {topic} shortlist is screened",
            f"What makes a {topic} replacement credible",
            f"Evaluation notes for {topic}",
        ][variant % 4]
    return {
        "pricing": ["How the buying risk is evaluated", "How pricing risk is reviewed"],
        "review": [f"How {topic} is reviewed", f"What this {topic} review checks", f"How we frame {topic} risk", f"Evaluation notes for {topic}"],
        "comparison": ["How the comparison is framed", "How tradeoffs are evaluated"],
    }.get(group, ["How we evaluate tools"])[variant % len({"alternatives": [1, 2, 3, 4]}.get(group, [1]))]


def method_copy(group: str, variant: int = 0) -> str:
    return {
        "alternatives": "Alternatives are not ranked only by popularity. The better filter is whether each tool solves the same job, has enough public information to verify, and can be promoted without unclear policy risk.",
        "pricing": "Pricing research starts with the official page, but the decision also depends on usage limits, team plans, cancellation rules, and whether the tool can recover its cost in the workflow.",
        "comparison": "The comparison is framed around use case, implementation friction, risk, and next-step clarity rather than broad feature checklists.",
    }.get(group, "The shortlist is organized around practical buying criteria rather than hype, including workflow fit, commercial intent, policy clarity, and whether a dedicated review is justified.")


def tools_heading(group: str, variant: int = 0, topic: str = "") -> str:
    topic = topic or "Alternative"
    if group == "alternatives":
        return [
            f"{topic} tools worth checking",
            f"Replacement options for {topic}",
            f"Tools that may fit {topic}",
            f"Shortlisted {topic} alternatives",
        ][variant % 4]
    return {
        "pricing": ["Tools to price-check first", "Products to verify on official pricing pages"],
        "review": [f"{topic} options to inspect", f"Tools connected to {topic}", f"Shortlist for {topic} research", f"{topic} tools in context"],
        "comparison": ["Options in the shortlist", "Tools included in this decision"],
    }.get(group, ["Best tools to consider"])[variant % len({"alternatives": [1, 2, 3, 4]}.get(group, [1]))]


def tools_intro(group: str, variant: int = 0) -> str:
    return {
        "alternatives": "Start with the options below, then read the review pages before deciding whether any tool deserves a trial.",
        "pricing": "Use these tools as a pricing research queue. Open the official page only after you know what limit or feature you need to verify.",
        "comparison": "The table below keeps the options close together so the tradeoffs are easier to inspect.",
    }.get(group, "The tools below are starting points for research. Use the review links for context before clicking through.")


def comparison_heading(group: str, variant: int = 0, topic: str = "") -> str:
    topic = topic or "Alternative"
    if group == "alternatives":
        return [
            f"Quick {topic} comparison",
            f"{topic} replacement scan",
            f"{topic} shortlist at a glance",
            f"Fast fit check for {topic}",
        ][variant % 4]
    return {
        "pricing": ["Quick cost and fit comparison", "Plan-fit comparison"],
        "review": [f"Quick {topic} fit check", f"{topic} research scan", f"Fast review notes for {topic}", f"{topic} shortlist view"],
        "comparison": ["Side-by-side decision notes", "Decision table"],
    }.get(group, ["Quick comparison"])[variant % len({"alternatives": [1, 2, 3, 4]}.get(group, [1]))]


def comparison_intro(group: str, variant: int = 0) -> str:
    return {
        "alternatives": "A useful alternatives page should make the replacement logic clear, not just list names.",
        "pricing": "Price only matters after you know what the plan includes and what work the tool will actually replace.",
    }.get(group, "Use this table as a fast scan before reading the deeper review or official page.")


def choice_heading(group: str, variant: int = 0, topic: str = "") -> str:
    topic = topic or "Each alternative"
    if group == "alternatives":
        return [
            f"When each {topic} alternative makes sense",
            f"How to choose between {topic} replacements",
            f"Which {topic} option to test first",
            f"Where each {topic} tool fits",
        ][variant % 4]
    return {
        "pricing": ["Which option deserves a price check", "What to inspect before paying"],
        "review": [f"When {topic} is worth testing", f"How to decide on {topic}", f"What to do after reading this {topic} review", f"Where {topic} fits best"],
        "comparison": ["When to choose each side", "How to make the final call"],
    }.get(group, ["When to choose each option"])[variant % len({"alternatives": [1, 2, 3, 4]}.get(group, [1]))]


def choice_intro(group: str, variant: int = 0) -> str:
    return {
        "alternatives": "The best replacement depends on the job you are trying to protect, not on the longest feature list.",
        "pricing": "A cheap plan can still be a poor choice if it misses the workflow feature you need.",
    }.get(group, "A good shortlist should make the next decision easier and show which tool deserves a trial or deeper review.")


def workflow_heading(group: str, variant: int = 0) -> str:
    return {
        "alternatives": ["Replacement workflow", "Switching workflow", "Practical migration path", "How to test a replacement"],
        "pricing": ["Pricing research workflow", "Plan verification workflow"],
        "review": ["Workflow fit", "Daily workflow check", "Practical usage path", "Testing workflow"],
        "comparison": ["Decision workflow", "Comparison workflow"],
    }.get(group, ["Workflow fit"])[variant % len({"alternatives": [1, 2, 3, 4]}.get(group, [1]))]


def risk_heading(group: str, variant: int = 0, topic: str = "") -> str:
    topic = topic or "tools"
    if group == "alternatives":
        return [
            f"Risks before switching {topic}",
            f"{topic} replacement risks to verify",
            f"What can go wrong with {topic}",
            f"Checks before choosing {topic}",
        ][variant % 4]
    return {
        "pricing": ["Risks before paying", "Pricing traps to check"],
        "review": [f"{topic} risks before buying", f"What to verify about {topic}", f"{topic} policy and pricing risks", f"Checks before trusting {topic}"],
        "comparison": ["Risks before choosing", "Decision risks"],
    }.get(group, ["Risks before buying"])[variant % len({"alternatives": [1, 2, 3, 4]}.get(group, [1]))]


def risk_copy(group: str, variant: int = 0) -> str:
    return {
        "alternatives": "The biggest switching mistakes happen when teams copy features from the old tool without checking integrations, migration effort, and policy terms.",
        "pricing": "The biggest pricing mistakes happen when the visible price is treated as the full cost. Usage limits, add-ons, team seats, and cancellation rules can matter more.",
    }.get(group, "The biggest mistakes usually happen before the product is tested: assuming pricing is current, using an affiliate link without approval, or publishing a review that sounds more certain than the data supports.")


def cta_heading(group: str, variant: int = 0) -> str:
    return {
        "alternatives": ["Open official pages carefully", "Verify the shortlist", "Continue with official research", "Next research step"],
        "pricing": ["Check current official pricing", "Verify plans on official pages"],
    }.get(group, ["Next step"])[variant % len({"alternatives": [1, 2, 3, 4]}.get(group, [1]))]


def cta_copy(group: str, variant: int = 0) -> str:
    return {
        "pricing": "Use the links below to verify current pricing and plan terms. If an affiliate link is pending approval, the redirect page uses the official URL instead.",
        "alternatives": "Use the links below as research shortcuts, not final recommendations. If an affiliate link is pending approval, the redirect page uses the official URL instead.",
    }.get(group, "Use these links as research shortcuts. If an affiliate link is pending approval, the redirect page will use the official website URL instead.")


def faq_questions(topic: str, group: str) -> list[str]:
    base = [
        f"What should I compare before choosing tools for {topic}?",
        "Should I rely on pricing shown on a review website?",
        "Which option should a beginner test first?",
        "Can affiliates promote these tools with paid ads?",
        "What risks should I check before buying?",
        "How should I use this shortlist without overpaying?",
    ]
    if group == "alternatives":
        base[0] = f"What makes a good alternative for {topic}?"
    if group == "pricing":
        base[0] = f"What should I check before paying for {topic}?"
    return base


def infer_keyword_group(keyword: str) -> str:
    text = keyword.lower()
    if "alternative" in text:
        return "alternatives"
    if "pricing" in text:
        return "pricing"
    if " vs " in f" {text} " or "comparison" in text:
        return "comparison"
    if "review" in text:
        return "review"
    return "other"


def tool_row(tool: pd.Series, source_slug: str) -> str:
    brand = str(tool.get("brand_name", "")).strip()
    offer_id = str(tool.get("offer_id", "")).strip()
    niche = str(tool.get("niche", "SaaS")).strip()
    risk = str(tool.get("risk_level", "Need review")).strip()
    return f"<tr><td><a href='/review/{html.escape(offer_id)}/'>{html.escape(brand)}</a></td><td>{html.escape(niche)} workflows and buyer research</td><td>{html.escape(risk)} - verify current affiliate policy.</td><td><a class='btn' href='/go/{html.escape(offer_id)}/?src=/{html.escape(source_slug)}/&cta=priority_page'>Visit Official Website</a><a class='btn secondary' href='/review/{html.escape(offer_id)}/'>Read review</a></td></tr>"


def tool_card(tool: pd.Series, source_slug: str) -> str:
    brand = str(tool.get("brand_name", "")).strip()
    offer_id = str(tool.get("offer_id", "")).strip()
    score = str(tool.get("total_score", "Research")).strip()
    recommendation = str(tool.get("recommendation", "Review the tool against your workflow before buying.")).strip()
    return f"<article class='card'><h3>{html.escape(brand)}</h3><p><strong>Score:</strong> {html.escape(score)}</p><p>{html.escape(recommendation)}</p><p><a class='btn' href='/go/{html.escape(offer_id)}/?src=/{html.escape(source_slug)}/&cta=priority_page'>Visit Official Website</a><a class='btn secondary' href='/review/{html.escape(offer_id)}/'>Read review</a></p></article>"


def priority_cta(tool: pd.Series, source_slug: str) -> str:
    brand = str(tool.get("brand_name", "")).strip()
    offer_id = str(tool.get("offer_id", "")).strip()
    return f"<a class='btn' href='/go/{html.escape(offer_id)}/?src=/{html.escape(source_slug)}/&cta=priority_page'>Visit Official Website: {html.escape(brand)}</a>"


def quick_comparison_row(tool: pd.Series, rank: int) -> str:
    brand = str(tool.get("brand_name", "")).strip()
    niche = str(tool.get("niche", "SaaS")).strip()
    risk = str(tool.get("risk_level", "Need review")).strip()
    return f"<tr><td>{rank}</td><td>{html.escape(brand)}</td><td>{html.escape(niche)} research, evaluation, and workflow testing.</td><td>Current pricing, affiliate terms, direct-linking rules, and policy risk: {html.escape(risk)}.</td></tr>"


def choice_block(tool: pd.Series, rank: int) -> str:
    brand = str(tool.get("brand_name", "")).strip()
    niche = str(tool.get("niche", "SaaS")).strip()
    recommendation = str(tool.get("recommendation", "")).strip() or "Consider this option when it fits your workflow and the official terms are clear."
    return f"<div class='card'><h3>{rank}. {html.escape(brand)}</h3><p>Choose {html.escape(brand)} when the main need connects to {html.escape(niche)} and the current product page confirms the features you need.</p><p>{html.escape(recommendation)}</p><p>Do not choose it only because it appears in a list. First check the current product page, compare alternatives, and confirm whether the affiliate or paid-traffic policy fits your plan.</p></div>"


def workflow_section(keyword: str, keyword_group: str, tool_names: list[str], variant: int = 0) -> str:
    topic = readable_topic(keyword)
    tools_text = ", ".join(tool_names[:3]) if tool_names else "the shortlisted tools"
    if keyword_group == "alternatives":
        lead = f"For {html.escape(topic)}, start by writing down what the current tool fails to solve, then compare {html.escape(tools_text)} against that specific gap."
    elif keyword_group == "pricing":
        lead = f"For {html.escape(topic)}, start with the workflow you need to run, then check whether {html.escape(tools_text)} include the relevant limits in the plan you can afford."
    else:
        lead = f"For {html.escape(topic)}, start with a narrow problem, then compare a few serious options such as {html.escape(tools_text)}."
    return f"<p>{lead}</p><p>If you are building affiliate content, the next step is usually a review page, an alternatives page, and one comparison page. If you are buying software for your own use, the next step is a small trial with one real workflow rather than a broad feature tour.</p><p>If the tool will be promoted with ads, separate the research workflow from the traffic workflow. The buying page can be useful for SEO, but paid traffic usually needs a compliant landing page, clear disclosure, and careful keyword selection.</p>"


def related_links(tool_names: list[str]) -> str:
    links = []
    for tool in tool_names[:5]:
        links.append(f"<li><a href='{review_url(tool)}'>Read {html.escape(tool)} review</a></li>")
    if len(tool_names) >= 2:
        left = slugify(tool_names[0])
        right = slugify(tool_names[1])
        comparison_path = settings.site_output_dir / "comparisons" / f"{left}-vs-{right}" / "index.html"
        if comparison_path.exists():
            links.append(f"<li><a href='/comparisons/{left}-vs-{right}/'>Compare {html.escape(tool_names[0])} vs {html.escape(tool_names[1])}</a></li>")
    return "<ul>" + "".join(links) + "</ul>"


def select_tools_for_keyword(keyword: str, offers: pd.DataFrame) -> pd.DataFrame:
    if offers.empty:
        return offers
    text = keyword.lower()
    matched = offers[offers.apply(lambda row: offer_matches_keyword(row, text), axis=1)]
    if matched.empty:
        matched = offers
    return matched.head(5).reset_index(drop=True)


def offer_matches_keyword(row: pd.Series, keyword: str) -> bool:
    haystack = " ".join([str(row.get("brand_name", "")), str(row.get("offer_id", "")), str(row.get("niche", ""))]).lower()
    tokens = [token for token in re.split(r"[^a-z0-9]+", keyword) if token and token not in {"best", "tools", "tool", "alternatives", "alternative", "software", "review", "pricing"}]
    return any(token in haystack for token in tokens)


def title_from_keyword(keyword: str) -> str:
    return " ".join(part.upper() if part in {"ai", "seo", "crm"} else part.capitalize() for part in keyword.split())


def readable_topic(keyword: str) -> str:
    return " ".join(part.upper() if part in {"ai", "seo", "crm"} else part for part in str(keyword).split())


def subject_focus(keyword: str) -> str:
    text = keyword.lower()
    if "email" in text:
        return "deliverability, automation depth, and list management"
    if "seo" in text:
        return "keyword research, content optimization, and ranking workflow"
    if "coding" in text:
        return "developer productivity, code understanding, and IDE fit"
    if "voice" in text:
        return "voice quality, licensing, and multilingual audio workflow"
    if "website" in text:
        return "publishing speed, CMS control, and long-term site maintenance"
    if "meeting" in text:
        return "meeting capture, summaries, and follow-up workflow"
    if "productivity" in text:
        return "daily execution, team adoption, and time saved"
    if "automation" in text:
        return "workflow reliability, app connectors, and maintenance effort"
    if "marketing" in text:
        return "campaign execution, measurement, and channel fit"
    if "writing" in text:
        return "editorial workflow, brand voice, and human review"
    if "design" in text:
        return "creative speed, asset control, and collaboration"
    if "video" in text:
        return "output quality, editing control, and usage rights"
    if "crm" in text:
        return "pipeline visibility, sales follow-up, and customer data structure"
    return "workflow fit, verification effort, and policy risk"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def stable_variant(value: str) -> int:
    total = sum(ord(char) for char in str(value))
    return total % 4
