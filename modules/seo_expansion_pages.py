from __future__ import annotations

import html
from pathlib import Path

from modules.programmatic_page_utils import breadcrumb_schema, faq_html, faq_schema, shell, write_page


COMPARISONS = [
    ("cursor-vs-copilot", "Cursor", "GitHub Copilot", "AI coding workflow", "Cursor is usually stronger when you want an AI-first editor with repository context. GitHub Copilot is usually safer for teams that want AI assistance inside an existing IDE workflow."),
    ("windsurf-vs-copilot", "Windsurf", "GitHub Copilot", "agentic coding versus autocomplete", "Windsurf is more interesting for agent-style project work. GitHub Copilot is more conservative and easier to introduce into existing engineering teams."),
    ("canva-vs-adobe-express", "Canva", "Adobe Express", "design and marketing content", "Canva is often the simpler choice for fast marketing assets and templates. Adobe Express is worth comparing when your team already lives in Adobe workflows."),
]

TOPLISTS = [
    ("best-ai-seo-tools-2026", "Best AI SEO Tools 2026", ["Surfer SEO", "Semrush", "Ahrefs", "Notion AI", "Jasper"], "AI SEO tools should be evaluated by workflow fit, SERP research depth, content brief quality, reporting, and whether the team can verify recommendations instead of blindly publishing them."),
    ("best-ai-writing-tools-2026", "Best AI Writing Tools 2026", ["Jasper", "Copy.ai", "Notion AI", "Canva", "Surfer SEO"], "AI writing tools are useful when they improve outlining, editing, repurposing, and team consistency. They are risky when teams publish generic drafts without editorial review."),
    ("best-ai-video-tools-2026", "Best AI Video Tools 2026", ["Synthesia", "Runway", "Descript", "Pictory", "Canva"], "AI video tools vary widely by use case. Some are better for avatar explainers, some for editing, some for fast social assets, and some for creative generation."),
    ("best-ai-automation-tools-2026", "Best AI Automation Tools 2026", ["Make", "Zapier", "HubSpot", "ActiveCampaign", "Notion AI"], "AI automation tools should be judged by reliability, integration coverage, error handling, team governance, and whether they reduce manual operations without hiding failure states."),
]


def generate_seo_expansion_pages(output: Path) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    for item in COMPARISONS:
        pages.append(generate_comparison(output, *item))
    for item in TOPLISTS:
        pages.append(generate_toplist(output, *item))
    return pages


def generate_comparison(output: Path, slug: str, tool_a: str, tool_b: str, context: str, verdict: str) -> dict[str, str]:
    path = f"/comparisons/{slug}/"
    title = f"{tool_a} vs {tool_b}: Which Tool Should You Choose in 2026?"
    description = f"Compare {tool_a} vs {tool_b} for {context}, including strengths, weaknesses, pricing checks, best use cases, alternatives, and affiliate-safe next steps."
    questions = [
        f"Is {tool_a} better than {tool_b}?",
        f"Which tool is easier for beginners?",
        "How should I compare pricing?",
        "Which tool is better for teams?",
        "What alternatives should I compare?",
        "Should I test both before buying?",
    ]
    body = f"""
<section class='hero card'><h1>{html.escape(title)}</h1><p>{html.escape(description)}</p><p><strong>Quick winner summary:</strong> {html.escape(verdict)}</p><p>{comparison_ctas(slug, tool_a, tool_b)}</p></section>
<section class='card'><h2>Feature comparison table</h2><table><thead><tr><th>Area</th><th>{html.escape(tool_a)}</th><th>{html.escape(tool_b)}</th></tr></thead><tbody>
<tr><td>Best fit</td><td>Best when the workflow benefits from its native strengths and the buyer can verify current terms.</td><td>Best when its ecosystem, onboarding, and team fit are stronger for the buyer.</td></tr>
<tr><td>Ease of use</td><td>Usually strong after the user understands the workflow model.</td><td>Often easier if the user already works in its familiar ecosystem.</td></tr>
<tr><td>Performance</td><td>Test with a real project, not only a demo prompt.</td><td>Check how it behaves under messy, repeated, team-based work.</td></tr>
<tr><td>Pricing</td><td>Verify current pricing, usage limits, refund terms, and team features.</td><td>Verify current pricing, usage limits, refund terms, and team features.</td></tr>
</tbody></table></section>
<section class='grid'><div class='card'><h2>Choose {html.escape(tool_a)} if...</h2><ul><li>You prefer its workflow and can test it on a real task.</li><li>You want deeper control over the use case it is known for.</li><li>Your team accepts the onboarding cost.</li></ul></div><div class='card'><h2>Choose {html.escape(tool_b)} if...</h2><ul><li>You want a more familiar adoption path.</li><li>Your current stack already connects well with it.</li><li>You need a conservative rollout before changing workflow.</li></ul></div></section>
<section class='grid'><div class='card'><h2>{html.escape(tool_a)} pros and cons</h2><p><strong>Pros:</strong> focused workflow fit, strong use-case depth, and useful evaluation path.</p><p><strong>Cons:</strong> may require onboarding, current pricing must be checked, and not every feature fits every team.</p></div><div class='card'><h2>{html.escape(tool_b)} pros and cons</h2><p><strong>Pros:</strong> familiar adoption, broad ecosystem fit, and easy comparison against existing tools.</p><p><strong>Cons:</strong> may be less specialized, can hide usage limits, and still needs policy/pricing verification.</p></div></section>
<section class='card'><h2>Pricing comparison</h2><p>Do not rely on static prices in any review. Pricing may change, plans may differ by region, and team features often sit behind higher tiers. Check official pricing pages before buying or recommending either tool.</p></section>
<section class='card'><h2>Best use case</h2><p>Use this comparison when the buying decision is not only feature count. The better choice is the tool that matches the daily workflow, team size, switching cost, and risk tolerance.</p></section>
<section class='card'><h2>Related reviews and pricing</h2><p>{related_tool_links(output, tool_a, tool_b)}</p></section>
<section class='card'><h2>Alternatives and internal links</h2><p><a href='/reviews/'>Browse all reviews</a> <a href='/comparisons/'>Browse comparisons</a> <a href='/pricing/'>Check pricing guides</a> <a href='/categories/'>Explore categories</a> <a href='{category_link(tool_a, tool_b)}'>Related category</a></p></section>
<section class='card trust'><h2>Affiliate disclosure</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you. Verify official pricing and terms before buying.</p></section>
<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>
"""
    page = shell(title, description, path, body, [faq_schema(questions), breadcrumb_schema(title, path)])
    write_page(output, path, page)
    return {"slug": f"comparisons/{slug}", "title": title, "url_path": path}


def generate_toplist(output: Path, slug: str, title: str, tools: list[str], intro: str) -> dict[str, str]:
    path = f"/{slug}/"
    description = f"{title} shortlist with comparison table, top picks, beginner/team/budget/enterprise notes, pricing cautions, FAQ, and affiliate disclosure."
    questions = [
        f"What is the best option in {title.lower()}?",
        "Which tool is best for beginners?",
        "Which option is better for teams?",
        "How should I compare pricing?",
        "What is the budget-friendly choice?",
        "What should I verify before buying?",
    ]
    rows = "".join(
        f"<tr><td>{html.escape(tool)}</td><td>{best_for(tool)}</td><td>Check official pricing</td><td>{tool_cta(tool, slug, 'best_tools_page')}</td></tr>"
        for tool in tools
    )
    cards = "".join(
        f"<div class='card'><h3>{html.escape(tool)}</h3><p>{best_for(tool)}</p><p>{tool_cta(tool, slug, 'top_pick', css_class='btn secondary')}</p></div>"
        for tool in tools[:4]
    )
    body = f"""
<section class='hero card'><h1>{html.escape(title)}</h1><p>{html.escape(intro)}</p><p>This guide is research-first: verify current pricing, plan limits, and official terms before buying or promoting any tool.</p></section>
<section class='card'><h2>Comparison table</h2><table><thead><tr><th>Tool</th><th>Best for</th><th>Pricing note</th><th>CTA</th></tr></thead><tbody>{rows}</tbody></table></section>
<section class='card'><h2>Top picks</h2><div class='grid'>{cards}</div></section>
<section class='grid'><div class='card'><h2>Best for beginners</h2><p>Choose the tool with the clearest onboarding, useful templates, and low setup friction.</p></div><div class='card'><h2>Best for teams</h2><p>Prioritize collaboration controls, permissions, repeatable workflows, and predictable billing.</p></div><div class='card'><h2>Best budget option</h2><p>Look for the plan that solves the core workflow without forcing unnecessary enterprise features.</p></div><div class='card'><h2>Best enterprise option</h2><p>Check security, admin controls, procurement fit, support, and team usage limits.</p></div></section>
<section class='card'><h2>How to choose</h2><p>Start with the workflow you repeat every week. Then compare integrations, pricing risks, cancellation terms, and whether the tool reduces manual work without creating cleanup.</p></section>
<section class='card'><h2>Related reviews</h2><p>{toplist_related_links(output, tools)}</p></section>
<section class='card'><h2>Related research</h2><p><a href='/reviews/'>Read reviews</a> <a href='/comparisons/'>Compare tools</a> <a href='/pricing/'>Review pricing guides</a> <a href='/categories/'>Explore categories</a></p></section>
<section class='card trust'><h2>Affiliate disclosure</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you. This does not change your price.</p></section>
<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>
"""
    page = shell(title, description, path, body, [faq_schema(questions), breadcrumb_schema(title, path)])
    write_page(output, path, page)
    return {"slug": slug, "title": title, "url_path": path}


def best_for(tool: str) -> str:
    notes = {
        "Surfer SEO": "content optimization teams that need SERP-informed briefs.",
        "Semrush": "SEO teams that need broader research, competitive analysis, and reporting.",
        "Ahrefs": "SEO teams focused on backlink and competitor research.",
        "Jasper": "marketing teams producing repeatable brand-aligned drafts.",
        "Copy.ai": "teams that need campaign copy and sales content workflows.",
        "Synthesia": "teams creating avatar-style explainer videos.",
        "Runway": "creative teams testing generative video workflows.",
        "Descript": "podcast and video teams that edit spoken content.",
        "Make": "builders who want visual automation and flexible scenarios.",
        "Zapier": "teams that need broad app coverage and simple automation.",
    }
    return html.escape(notes.get(tool, "buyers who need to test workflow fit before committing."))


TRACKED_TOOLS = {
    "activecampaign",
    "adcreative-ai",
    "canva",
    "copy-ai",
    "cursor",
    "descript",
    "elevenlabs",
    "gamma",
    "github-copilot",
    "hubspot",
    "jasper",
    "make",
    "notion-ai",
    "runway",
    "semrush",
    "surfer-seo",
    "synthesia",
    "webflow-ai",
    "windsurf",
    "zapier",
}


def comparison_ctas(slug: str, tool_a: str, tool_b: str) -> str:
    return tool_cta(tool_a, f"comparisons/{slug}", "comparison_page") + tool_cta(
        tool_b, f"comparisons/{slug}", "comparison_page", css_class="btn secondary"
    )


def tool_cta(tool: str, source: str, cta: str, css_class: str = "btn") -> str:
    tool_slug = slugify(tool)
    if tool_slug in TRACKED_TOOLS:
        return f"<a class='{html.escape(css_class)}' href='/go/{html.escape(tool_slug)}/?src={html.escape(source)}&cta={html.escape(cta)}' rel='nofollow sponsored'>Visit Official Website</a>"
    return f"<a class='{html.escape(css_class)}' href='/comparisons/'>Compare alternatives</a>"


def related_tool_links(output: Path, tool_a: str, tool_b: str) -> str:
    tools = [tool_a, tool_b]
    links = []
    for tool in tools:
        slug = slugify(tool)
        review = existing_review_path(output, slug)
        pricing = existing_pricing_path(output, slug)
        if review:
            links.append(f"<a href='{html.escape(review)}'>Read {html.escape(tool)} review</a>")
        if pricing:
            links.append(f"<a href='{html.escape(pricing)}'>See {html.escape(tool)} pricing guide</a>")
    if any(slugify(tool) in {"cursor", "windsurf", "github-copilot"} for tool in tools):
        links.extend(
            [
                "<a href='/best-ai-coding-tools-2026/'>Best AI coding tools 2026</a>",
                "<a href='/category/ai-coding-tools/'>AI coding tools category</a>",
                "<a href='/comparisons/cursor-vs-windsurf/'>Cursor vs Windsurf</a>",
            ]
        )
    if any(slugify(tool) in {"canva", "adobe-express"} for tool in tools):
        links.extend(
            [
                "<a href='/review/canva/'>Canva review</a>",
                "<a href='/category/design-tools/'>Design tools category</a>",
                "<a href='/best-ai-presentation-tools/'>Best AI presentation tools</a>",
            ]
        )
    return " ".join(dict.fromkeys(links))


def category_link(tool_a: str, tool_b: str) -> str:
    slugs = {slugify(tool_a), slugify(tool_b)}
    if slugs & {"cursor", "windsurf", "github-copilot"}:
        return "/category/ai-coding-tools/"
    if slugs & {"canva", "adobe-express"}:
        return "/category/design-tools/"
    return "/categories/"


def toplist_related_links(output: Path, tools: list[str]) -> str:
    links = []
    for tool in tools:
        slug = slugify(tool)
        review = existing_review_path(output, slug)
        pricing = existing_pricing_path(output, slug)
        if review:
            links.append(f"<a href='{html.escape(review)}'>{html.escape(tool)} review</a>")
        if pricing:
            links.append(f"<a href='{html.escape(pricing)}'>{html.escape(tool)} pricing</a>")
    category = "/categories/"
    joined = " ".join(slugify(tool) for tool in tools)
    if any(token in joined for token in ["semrush", "surfer", "ahrefs"]):
        category = "/category/seo-tools/"
        links.append("<a href='/comparisons/semrush-vs-ahrefs/'>Semrush vs Ahrefs</a>")
    elif any(token in joined for token in ["jasper", "copy-ai", "notion-ai"]):
        category = "/category/writing-tools/"
        links.append("<a href='/comparisons/jasper-vs-copyai/'>Jasper vs Copy.ai</a>")
    elif any(token in joined for token in ["synthesia", "runway", "descript"]):
        category = "/category/video-tools/"
        links.append("<a href='/comparisons/synthesia-vs-heygen/'>Synthesia vs HeyGen</a>")
    elif any(token in joined for token in ["make", "zapier", "hubspot", "activecampaign"]):
        category = "/category/automation-tools/"
        links.append("<a href='/comparisons/make-vs-zapier/'>Make vs Zapier</a>")
    links.append(f"<a href='{category}'>Related category</a>")
    return " ".join(dict.fromkeys(links))


def existing_review_path(output: Path, slug: str) -> str:
    aliases = {"windsurf": "/windsurf-review/"}
    candidates = [aliases.get(slug, ""), f"/review/{slug}/", f"/{slug}/"]
    for candidate in candidates:
        if candidate and page_exists(output, candidate):
            return candidate
    return ""


def existing_pricing_path(output: Path, slug: str) -> str:
    candidates = [f"/pricing/{slug}/", f"/{slug}-pricing/"]
    for candidate in candidates:
        if page_exists(output, candidate):
            return candidate
    return ""


def page_exists(output: Path, url_path: str) -> bool:
    clean = str(url_path or "").strip("/")
    if not clean:
        return (output / "index.html").exists()
    return (output / clean / "index.html").exists()


def slugify(text: str) -> str:
    import re

    aliases = {"GitHub Copilot": "github-copilot", "Adobe Express": "adobe-express"}
    if text in aliases:
        return aliases[text]
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
