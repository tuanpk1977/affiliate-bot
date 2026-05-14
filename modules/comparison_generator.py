from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

from modules.programmatic_page_utils import affiliate_disclosure, breadcrumb_schema, faq_html, faq_schema, item_list_schema, official_url, offer_map, review_url, shell, slugify, write_page


COMPARISONS = [
    ("chatgpt-vs-claude", "ChatGPT", "Claude", "AI assistants"),
    ("cursor-vs-github-copilot", "Cursor", "GitHub Copilot", "AI coding tools"),
    ("make-vs-zapier", "Make", "Zapier", "automation platforms"),
    ("semrush-vs-ahrefs", "Semrush", "Ahrefs", "SEO platforms"),
    ("canva-vs-gamma", "Canva", "Gamma", "AI design and presentation tools"),
    ("elevenlabs-vs-murf", "ElevenLabs", "Murf", "AI voice tools"),
    ("runway-vs-pika", "Runway", "Pika", "AI video tools"),
    ("notion-ai-vs-clickup-ai", "Notion AI", "ClickUp AI", "AI productivity tools"),
]


def generate_comparison_pages(output: Path, offer_scores: pd.DataFrame | None = None) -> list[dict[str, str]]:
    offers = offer_map(offer_scores)
    pages = []
    for slug, left, right, category in COMPARISONS:
        title = f"{left} vs {right}: Which {category} should you choose?"
        description = f"Research-style comparison of {left} vs {right}: features, best use cases, pricing notes, alternatives, FAQ, and affiliate disclosure."
        path = f"/comparisons/{slug}/"
        questions = [
            f"Is {left} better than {right}?",
            f"Which tool is easier for beginners?",
            f"How should teams compare {left} and {right} pricing?",
            f"What alternatives should I consider?",
            f"Can I use these tools for team workflows?",
            "What should I verify before buying?",
        ]
        body = f"""<section class='hero card'><h1>{html.escape(left)} vs {html.escape(right)}</h1><p>{html.escape(description)}</p><p><strong>Quick take:</strong> Choose the tool that matches your workflow, integrations, and budget. Do not rely on old pricing screenshots; check official pricing before buying.</p><p><a class='btn' href='{safe_review_url(output, left)}'>Read {html.escape(left)} review</a><a class='btn secondary' href='{safe_review_url(output, right)}'>Read {html.escape(right)} review</a></p></section>
{affiliate_disclosure()}
<section class='card'><h2>Feature comparison table</h2><table><thead><tr><th>Criteria</th><th>{html.escape(left)}</th><th>{html.escape(right)}</th></tr></thead><tbody>
<tr><td>Main fit</td><td>Best when your workflow matches the core strengths of {html.escape(left)}.</td><td>Best when your workflow matches the core strengths of {html.escape(right)}.</td></tr>
<tr><td>Pricing</td><td>Check official pricing.</td><td>Check official pricing.</td></tr>
<tr><td>Best for</td><td>Users who need a focused {html.escape(category)} workflow.</td><td>Users comparing another style of {html.escape(category)} workflow.</td></tr>
<tr><td>Review link</td><td><a href='{safe_review_url(output, left)}'>{html.escape(left)} review</a></td><td><a href='{safe_review_url(output, right)}'>{html.escape(right)} review</a></td></tr>
</tbody></table></section>
<section class='grid'><div class='card'><h2>Who should choose {html.escape(left)}?</h2><p>Choose {html.escape(left)} if its workflow, integrations and learning curve fit how you already work. Start with a small test before moving a whole team.</p></div><div class='card'><h2>Who should choose {html.escape(right)}?</h2><p>Choose {html.escape(right)} if it solves the same job with less friction for your team, budget, or existing tool stack.</p></div></section>
<section class='grid'><div class='card'><h2>{html.escape(left)} strengths</h2><ul><li>Good category fit for {html.escape(category)} research.</li><li>Useful if your process needs this specific workflow.</li><li>Worth testing with real tasks.</li></ul><h3>Weaknesses</h3><ul><li>Pricing and terms need verification.</li><li>May not fit every team workflow.</li></ul></div><div class='card'><h2>{html.escape(right)} strengths</h2><ul><li>Strong alternative to compare before buying.</li><li>May fit a different budget or workflow.</li><li>Useful benchmark for feature comparison.</li></ul><h3>Weaknesses</h3><ul><li>Pricing and plan limits need verification.</li><li>Integrations should be checked manually.</li></ul></div></section>
<section class='card'><h2>Pricing comparison</h2><p>Pricing may change. Check official pricing for both tools before buying, writing affiliate content, or sending paid traffic.</p><p><a class='btn' rel='nofollow sponsored' href='{html.escape(official_url(left, offers), quote=True)}'>Visit {html.escape(left)} official site</a><a class='btn secondary' rel='nofollow sponsored' href='{html.escape(official_url(right, offers), quote=True)}'>Visit {html.escape(right)} official site</a></p></section>
<section class='card'><h2>Alternatives</h2><p>Also compare related reviews and broader category pages before deciding.</p><p><a href='/comparisons/'>All comparisons</a> | <a href='/reviews/'>All reviews</a></p></section>
<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>
<section class='card'><h2>Final recommendation</h2><p>Shortlist the tool that matches your daily workflow, not just the tool with the louder brand. Verify pricing, cancellation terms, integrations, and vendor policy before buying.</p></section>"""
        page = shell(title, description, path, body, [faq_schema(questions), breadcrumb_schema(title, path), item_list_schema(title, [left, right], path)])
        write_page(output, f"comparisons/{slug}", page)
        pages.append({"slug": f"comparisons/{slug}", "title": title, "type": "comparison"})
    return pages


def safe_review_url(output: Path, tool: str) -> str:
    slug = slugify(tool)
    if (output / slug / "index.html").exists():
        return review_url(tool)
    return "/reviews/"
