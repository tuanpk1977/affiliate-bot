from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

from modules.programmatic_page_utils import affiliate_disclosure, breadcrumb_schema, faq_html, faq_schema, item_list_schema, offer_map, review_url, shell, write_page


TOPLISTS = [
    ("best-ai-writing-tools", "Best AI Writing Tools", ["Jasper", "Copy.ai", "Notion AI"]),
    ("best-ai-video-tools", "Best AI Video Tools", ["Runway", "Descript", "Synthesia"]),
    ("best-ai-coding-tools", "Best AI Coding Tools", ["Cursor", "GitHub Copilot"]),
    ("best-ai-seo-tools", "Best AI SEO Tools", ["Surfer SEO", "Semrush"]),
    ("best-ai-automation-tools", "Best AI Automation Tools", ["Make", "Zapier"]),
    ("best-ai-presentation-tools", "Best AI Presentation Tools", ["Gamma", "Canva"]),
    ("best-crm-tools", "Best CRM Tools", ["HubSpot", "Pipedrive"]),
    ("best-website-builders", "Best Website Builders", ["Webflow AI", "Framer", "Durable"]),
]


def generate_toplist_pages(output: Path, offer_scores: pd.DataFrame | None = None) -> list[dict[str, str]]:
    offers = offer_map(offer_scores)
    pages = []
    for slug, title, tools in TOPLISTS:
        path = f"/{slug}/"
        description = f"Research-style shortlist of {title.lower()} with best-for notes, pricing cautions, pros and cons, alternatives, FAQ, and affiliate disclosure."
        rows = ""
        for idx, tool in enumerate(tools, start=1):
            data = offers.get(tool.lower().replace(" ", "-"), {})
            score = data.get("total_score", "Research")
            rows += f"<tr><td>{idx}</td><td><a href='{review_url(tool)}'>{html.escape(tool)}</a></td><td>{html.escape(str(score))}</td><td>{best_for(tool, title)}</td><td>Check official pricing</td></tr>"
        questions = [
            f"What is the best tool in {title}?",
            "How should I compare pricing?",
            "Which tool is best for beginners?",
            "Which tool is best for teams?",
            "What alternatives should I compare?",
            "What should I verify before buying?",
        ]
        body = f"""<section class='hero card'><h1>{html.escape(title)}</h1><p>{html.escape(description)}</p><p>This page is a research shortlist, not a guarantee. Test one small workflow before making a long-term SaaS decision.</p></section>
{affiliate_disclosure()}
<section class='card'><h2>Ranking table</h2><table><thead><tr><th>#</th><th>Tool</th><th>Score</th><th>Best for</th><th>Pricing note</th></tr></thead><tbody>{rows}</tbody></table></section>
<section class='grid'><div class='card'><h2>How to choose</h2><ul><li>Start with your real workflow.</li><li>Check current pricing on the official site.</li><li>Review integrations and team plan limits.</li><li>Compare at least two alternatives.</li></ul></div><div class='card'><h2>Pros and cons of this category</h2><ul><li>Pros: faster research and repeatable workflows.</li><li>Cons: pricing, policy, and data limits vary by vendor.</li><li>Always verify terms before affiliate promotion.</li></ul></div></section>
<section class='card'><h2>CTA</h2><p>Read the individual reviews before choosing a product.</p>{''.join(f"<a class='btn' href='{review_url(tool)}'>Read {html.escape(tool)} review</a>" for tool in tools)}</section>
<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>"""
        page = shell(title, description, path, body, [faq_schema(questions), breadcrumb_schema(title, path), item_list_schema(title, tools, path)])
        write_page(output, slug, page)
        pages.append({"slug": slug, "title": title, "type": "toplist"})
    return pages


def best_for(tool: str, title: str) -> str:
    return f"Buyers comparing {title.lower()} and testing {tool} against a real workflow"
