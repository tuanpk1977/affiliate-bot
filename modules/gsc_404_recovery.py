from __future__ import annotations

import html
import json
from pathlib import Path

from config import settings


PAGES = {
    "crm-alternatives": {
        "title": "Các lựa chọn thay thế CRM tốt nhất năm 2026",
        "description": "So sánh các lựa chọn thay thế CRM cho doanh nghiệp nhỏ, đội bán hàng và marketing trước khi chọn nền tảng.",
        "intro": "Trang này giúp bạn lập danh sách rút gọn các nền tảng CRM theo nhu cầu thực tế. Hãy kiểm tra giá, giới hạn người dùng, tự động hóa, tích hợp và điều khoản mới nhất trên website chính thức trước khi mua.",
        "sections": [
            ("Khi nào nên tìm CRM thay thế?", "Nên cân nhắc đổi CRM khi chi phí tăng nhanh, quy trình bán hàng khó tùy chỉnh, báo cáo không đủ rõ hoặc đội ngũ phải dùng quá nhiều công cụ bổ sung."),
            ("Các lựa chọn nên xem xét", "HubSpot phù hợp với đội ngũ cần CRM kết hợp marketing. Pipedrive tập trung vào pipeline bán hàng. ActiveCampaign phù hợp khi email automation là phần quan trọng của quy trình."),
            ("Cách chọn nền tảng", "So sánh tổng chi phí, số lượng người dùng, tích hợp, khả năng xuất dữ liệu, hỗ trợ và thời gian triển khai. Không nên chọn chỉ dựa trên danh sách tính năng."),
        ],
        "links": [
            ("/vi/best-crm-tools/", "Công cụ CRM tốt nhất"),
            ("/vi/category/crm-tools/", "Danh mục CRM"),
            ("/vi/hub/crm/", "Trung tâm nội dung CRM"),
            ("/vi/review/hubspot/", "Đánh giá HubSpot"),
            ("/vi/review/pipedrive/", "Đánh giá Pipedrive"),
        ],
    },
    "marketing-software-review": {
        "title": "Đánh giá phần mềm marketing năm 2026",
        "description": "Hướng dẫn đánh giá phần mềm marketing theo tự động hóa, email, CRM, nội dung, báo cáo và mức phù hợp quy trình.",
        "intro": "Phần mềm marketing tốt nhất phụ thuộc vào kênh, quy mô đội ngũ và mức độ tự động hóa cần thiết. Trang này trình bày cách đánh giá công cụ mà không dựa vào quảng cáo hoặc tuyên bố chưa được xác minh.",
        "sections": [
            ("Nên đánh giá những gì?", "Kiểm tra email marketing, CRM, automation, báo cáo, quản lý chiến dịch, tích hợp và khả năng xuất dữ liệu. Giá và giới hạn sử dụng cần được xác minh trên website chính thức."),
            ("Phù hợp nhất cho ai?", "Doanh nghiệp nhỏ thường cần công cụ dễ triển khai. Đội marketing lớn cần phân quyền, báo cáo và tích hợp sâu hơn. Người sáng tạo nội dung có thể ưu tiên email và landing page."),
            ("Rủi ro cần kiểm tra", "Chi phí có thể tăng theo số liên hệ, số người dùng hoặc mức sử dụng. Hãy kiểm tra chính sách gửi email, giới hạn automation, hỗ trợ và điều khoản hủy dịch vụ."),
        ],
        "links": [
            ("/vi/email-marketing-software-review/", "Đánh giá phần mềm email marketing"),
            ("/vi/marketing-alternatives/", "Các lựa chọn thay thế marketing"),
            ("/vi/hub/marketing/", "Trung tâm nội dung marketing"),
            ("/vi/review/activecampaign/", "Đánh giá ActiveCampaign"),
            ("/vi/category/email-marketing-tools/", "Danh mục email marketing"),
        ],
    },
}


def write_gsc_404_recovery_pages(output: Path | None = None) -> list[Path]:
    root = output or settings.site_output_dir
    written: list[Path] = []
    for slug, page in PAGES.items():
        target = root / "vi" / slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_page(slug, page), encoding="utf-8")
        written.append(target)
    return written


def render_page(slug: str, page: dict) -> str:
    base = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
    canonical = f"{base}/vi/{slug}/"
    links = "".join(f'<li><a href="{html.escape(url, quote=True)}">{html.escape(label)}</a></li>' for url, label in page["links"])
    sections = "".join(f"<section class='card'><h2>{html.escape(title)}</h2><p>{html.escape(body)}</p></section>" for title, body in page["sections"])
    schema = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": page["title"],
            "description": page["description"],
            "url": canonical,
            "inLanguage": "vi",
            "author": {"@type": "Person", "name": "Nguyen Quoc Tuan"},
            "publisher": {"@type": "Organization", "name": settings.site_name, "url": f"{base}/"},
            "dateModified": "2026-06-12",
        },
        ensure_ascii=False,
    )
    contact = settings.contact_email or "contact@smileaireviewhub.com"
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page["title"])} | {html.escape(settings.site_name)}</title>
<meta name="description" content="{html.escape(page["description"], quote=True)}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{html.escape(canonical, quote=True)}">
<link rel="alternate" hreflang="vi" href="{html.escape(canonical, quote=True)}">
<link rel="alternate" hreflang="x-default" href="{html.escape(canonical, quote=True)}">
<script type="application/ld+json">{schema}</script>
<style>{css()}</style>
</head>
<body>
<nav><div class="wrap"><a href="/vi/"><strong>{html.escape(settings.site_name)}</strong></a><a href="/vi/reviews/">Đánh giá</a><a href="/vi/comparisons/">So sánh</a><a href="/vi/categories/">Danh mục</a><a href="/vi/contact/">Liên hệ</a></div></nav>
<main class="wrap">
<article>
<header class="card"><p class="eyebrow">Hướng dẫn nghiên cứu 2026</p><h1>{html.escape(page["title"])}</h1><p>{html.escape(page["intro"])}</p></header>
{sections}
<section class="card"><h2>Nội dung liên quan</h2><ul>{links}</ul></section>
<section class="card"><h2>Kết luận</h2><p>Dùng trang này để tạo danh sách rút gọn, sau đó xác minh giá, tính năng, giới hạn và điều khoản mới nhất trực tiếp với nhà cung cấp.</p></section>
</article>
</main>
<footer><div class="wrap"><p><strong>{html.escape(settings.site_name)}</strong></p><p>Contact: <!--email_off--><a href="mailto:{html.escape(contact, quote=True)}">{html.escape(contact)}</a><!--/email_off--></p><a href="/vi/about/">Giới thiệu</a><a href="/vi/contact/">Liên hệ</a><a href="/vi/editorial-policy/">Chính sách biên tập</a></div></footer>
</body>
</html>"""


def css() -> str:
    return """*{box-sizing:border-box}body{margin:0;background:#f7f9fc;color:#17202a;font-family:Arial,sans-serif;line-height:1.7}.wrap{max-width:960px;margin:auto;padding:0 20px}nav{background:#fff;border-bottom:1px solid #dbe3ef;padding:18px 0}nav a,footer a{margin-right:18px;color:#0f766e;text-decoration:none}.card{background:#fff;border:1px solid #dbe3ef;border-radius:8px;padding:22px;margin:20px 0}.eyebrow{color:#0f766e;font-weight:700}h1{font-size:38px;line-height:1.2}h2{font-size:25px}li{margin:8px 0}footer{margin-top:36px;background:#0f172a;color:#cbd5e1;padding:28px 0}footer a{color:#e2e8f0}@media(max-width:700px){h1{font-size:30px}nav a{display:inline-block;margin-bottom:8px}}"""
