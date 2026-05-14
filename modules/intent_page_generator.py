from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

from modules.programmatic_page_utils import affiliate_disclosure, breadcrumb_schema, faq_html, faq_schema, item_list_schema, official_url, offer_map, review_url, shell, write_page


PRICING_PAGE_SLUGS = [
    "cursor-pricing",
    "github-copilot-pricing",
    "semrush-pricing",
    "surfer-seo-pricing",
    "jasper-pricing",
    "elevenlabs-pricing",
    "make-pricing",
    "zapier-pricing",
]

FALLBACK_TOOL_NAMES = {
    "cursor": "Cursor",
    "github-copilot": "GitHub Copilot",
    "semrush": "Semrush",
    "surfer-seo": "Surfer SEO",
    "jasper": "Jasper",
    "elevenlabs": "ElevenLabs",
    "make": "Make",
    "zapier": "Zapier",
}


def generate_intent_pages(output: Path, offer_scores: pd.DataFrame | None = None) -> list[dict[str, str]]:
    offers = offer_map(offer_scores)
    source_names = source_brand_names(offer_scores)
    pages = []
    for slug in PRICING_PAGE_SLUGS:
        tool_slug = slug.removesuffix("-pricing")
        tool = source_names.get(tool_slug) or FALLBACK_TOOL_NAMES.get(tool_slug) or title_from_slug(tool_slug)
        title = f"Giá {tool}: những điểm cần kiểm tra trước khi mua"
        path = f"/{slug}/"
        description = f"Hướng dẫn nghiên cứu về giá {tool}. Pricing có thể thay đổi, nên cần xác minh plan hiện tại, giới hạn sử dụng, điều khoản hủy, alternatives và policy chính thức."
        questions = [
            f"Giá {tool} hiện nên kiểm tra ở đâu?",
            f"Pricing của {tool} có thể thay đổi không?",
            f"{tool} có refund hoặc hủy gói không?",
            f"{tool} có team plan không?",
            f"Nên so sánh {tool} với alternatives nào?",
            f"Cần kiểm tra gì trước khi mua {tool}?",
        ]
        body = f"""<section class='hero card'><h1>{html.escape(title)}</h1><p>{html.escape(description)}</p><p><strong>Lưu ý:</strong> pricing có thể thay đổi. Trang này không ghi giá cố định nếu chưa có dữ liệu xác minh thủ công.</p><p><a class='btn' rel='nofollow sponsored' href='{html.escape(official_url(tool, offers), quote=True)}'>Kiểm tra giá chính thức của {html.escape(tool)}</a><a class='btn secondary' href='{review_url(tool)}'>Đọc review {html.escape(tool)}</a></p></section>
{affiliate_disclosure()}
<section class='card'><h2>Cần kiểm tra gì trước khi mua?</h2><ul><li>Giới hạn plan tháng/năm hiện tại.</li><li>Seat, credit, export, API hoặc giới hạn workspace.</li><li>Quyền dùng thương mại và data policy.</li><li>Affiliate hoặc paid traffic terms nếu bạn định quảng bá {html.escape(tool)}.</li></ul></section>
<section class='grid'><div class='card'><h2>Refund / cancel note</h2><p>Refund, cancellation và trial rules thay đổi theo vendor. Hãy kiểm tra billing/terms chính thức trước khi mua.</p></div><div class='card'><h2>Team plan note</h2><p>Nếu team dùng {html.escape(tool)}, hãy xác minh seat pricing, admin controls, data permissions và collaboration limits.</p></div></section>
<section class='card'><h2>Alternatives</h2><p>Hãy so sánh alternatives trước khi mua. Giá vào ban đầu thấp chưa chắc rẻ hơn nếu workflow cần add-on, extra seats hoặc workaround thủ công.</p><p><a href='/comparisons/'>Browse comparisons</a> | <a href='/reviews/'>Browse reviews</a></p></section>
<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>
<section class='card'><h2>CTA</h2><p>Dùng trang pricing này như checklist. Xác minh giá chính thức của {html.escape(tool)}, sau đó đọc review đầy đủ trước khi quyết định.</p><p><a class='btn' rel='nofollow sponsored' href='{html.escape(official_url(tool, offers), quote=True)}'>Kiểm tra giá chính thức của {html.escape(tool)}</a><a class='btn secondary' href='{review_url(tool)}'>Đọc review {html.escape(tool)}</a></p></section>"""
        page = shell(title, description, path, body, [faq_schema(questions), breadcrumb_schema(title, path), item_list_schema(title, [tool], path)])
        write_page(output, slug, page)
        pages.append({"slug": slug, "title": title, "type": "pricing"})
    return pages


def source_brand_names(offer_scores: pd.DataFrame | None) -> dict[str, str]:
    if offer_scores is None or offer_scores.empty:
        return {}
    names = {}
    for _, row in offer_scores.iterrows():
        offer_id = str(row.get("offer_id", "")).strip()
        brand = str(row.get("brand_name", "")).strip()
        if offer_id and brand:
            names[offer_id] = brand
    return names


def title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-"))
