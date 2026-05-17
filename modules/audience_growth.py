from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from config import settings


BASE_URL = (settings.base_site_url or settings.site_domain or "https://review.mssmileenglish.com").rstrip("/")
SITE_NAME = "MS Smile AI Review Hub"
CONTACT_EMAIL = "tuanpk1977@gmail.com"
LEAD_SLUG = "free-ai-coding-workflow-checklist"
DOWNLOAD_SLUG = "downloads/ai-coding-workflow-checklist"
EMAIL_SETUP_SLUG = "email-capture-setup"
FORMSPREE_SETUP_SLUG = "formspree-setup"
SOCIAL_PLATFORMS = ["facebook", "linkedin", "twitter", "short_video"]


def run_audience_growth_system(output: Path | None = None) -> dict[str, int]:
    root = output or settings.site_output_dir
    root.mkdir(parents=True, exist_ok=True)
    ensure_email_capture_config()
    ensure_subscribers_csv()
    write_about_pages(root)
    write_lead_magnet_pages(root)
    write_checklist_pages(root)
    write_email_capture_setup_pages(root)
    write_formspree_setup_pages(root)
    write_partnerstack_trust_pages(root)
    write_partnerstack_reapply_pack()
    write_affiliate_program_tracker()
    write_go_links_status(root)
    write_formspree_setup_checklist()
    internal_links_added = add_build_in_public_links(root)
    social_posts = write_30_day_social_plan()
    report_rows = write_audience_growth_report(
        about_page_created=True,
        lead_magnet_page_created=True,
        checklist_created=True,
        email_capture_setup_created=True,
        formspree_setup_created=True,
        partnerstack_trust_pages_created=True,
        subscriber_capture_ready=True,
        social_plan_days=30,
        social_posts_created=social_posts,
        internal_links_added=internal_links_added,
        warnings="Static GitHub Pages cannot write form submissions without a future provider/webhook.",
    )
    return {
        "about_pages": 2,
        "lead_magnet_pages": 2,
        "checklist_pages": 4,
        "email_capture_setup_pages": 2,
        "formspree_setup_pages": 2,
        "partnerstack_trust_pages": 4,
        "social_posts_created": social_posts,
        "internal_links_added": internal_links_added,
        "report_rows": report_rows,
    }


def ensure_email_capture_config() -> None:
    path = settings.base_dir / "config" / "email_capture.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    else:
        payload = {}
    payload.setdefault("enabled", False)
    if not payload.get("provider"):
        payload["provider"] = "formspree"
    payload.setdefault("form_endpoint", "")
    payload.setdefault("success_message", "Thanks. Please check your inbox if confirmation is enabled.")
    payload.setdefault("error_message", "The form could not be submitted. Please try again or contact the site owner.")
    payload.setdefault("honeypot_field", "_gotcha")
    payload.setdefault("storage", "csv")
    payload.setdefault("double_opt_in", False)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_email_capture_config() -> dict[str, object]:
    ensure_email_capture_config()
    path = settings.base_dir / "config" / "email_capture.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    return {
        "enabled": bool(payload.get("enabled")),
        "provider": str(payload.get("provider") or "formspree"),
        "form_endpoint": str(payload.get("form_endpoint") or "").strip(),
        "success_message": str(payload.get("success_message") or ""),
        "error_message": str(payload.get("error_message") or ""),
        "honeypot_field": str(payload.get("honeypot_field") or "_gotcha"),
        "storage": str(payload.get("storage") or "csv"),
        "double_opt_in": bool(payload.get("double_opt_in")),
    }


def ensure_subscribers_csv() -> None:
    path = settings.data_dir / "subscribers.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["email", "source_page", "language", "created_at", "status"])


def strip_vi(path: str) -> str:
    if path == "/vi/":
        return "/"
    if path.startswith("/vi/"):
        return "/" + path[4:].strip("/") + "/"
    return "/" + path.strip("/") + ("/" if path.strip("/") else "")


def page_shell(
    title: str,
    description: str,
    path: str,
    body: str,
    lang: str = "en",
    faq_items: list[tuple[str, str]] | None = None,
) -> str:
    en_path = strip_vi(path)
    vi_path = "/vi/" if en_path == "/" else "/vi" + en_path
    current_path = vi_path if lang == "vi" else en_path
    canonical = BASE_URL + current_path
    en_url = BASE_URL + en_path
    vi_url = BASE_URL + vi_path
    schema_blocks = [
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "description": description,
            "inLanguage": lang,
            "url": canonical,
            "publisher": {"@type": "Organization", "name": SITE_NAME},
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home" if lang == "en" else "Trang chủ", "item": BASE_URL + ("/vi/" if lang == "vi" else "/")},
                {"@type": "ListItem", "position": 2, "name": title, "item": canonical},
            ],
        },
    ]
    if faq_items:
        schema_blocks.append(
            {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": question,
                        "acceptedAnswer": {"@type": "Answer", "text": answer},
                    }
                    for question, answer in faq_items
                ],
            }
        )
    schema_html = "\n  ".join(
        f'<script type="application/ld+json">{json.dumps(block, ensure_ascii=False)}</script>'
        for block in schema_blocks
    )
    return f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - {SITE_NAME}</title>
  <meta name="description" content="{html.escape(description)}">
  <link rel="canonical" href="{html.escape(canonical, quote=True)}">
  <link rel="alternate" hreflang="en" href="{html.escape(en_url, quote=True)}">
  <link rel="alternate" hreflang="vi" href="{html.escape(vi_url, quote=True)}">
  <link rel="alternate" hreflang="x-default" href="{html.escape(en_url, quote=True)}">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:type" content="article">
  <meta property="og:image" content="{BASE_URL}/assets/og/site.svg">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{BASE_URL}/assets/og/site.svg">
  {schema_html}
  <style>{css()}</style>
</head>
<body>
  {nav_html(lang, en_path, vi_path)}
  <main class="wrap">{body}</main>
  {footer_html(lang)}
</body>
</html>
"""


def nav_html(lang: str, en_path: str, vi_path: str) -> str:
    if lang == "vi":
        labels = {
            "home": "Trang chủ",
            "reviews": "Đánh giá",
            "comparisons": "So sánh",
            "pricing": "Giá",
            "categories": "Danh mục",
            "blog": "Blog",
            "contact": "Liên hệ",
            "disclosure": "Một số liên kết có thể là liên kết tiếp thị liên kết. Chúng tôi có thể nhận hoa hồng mà không phát sinh thêm chi phí nào cho bạn.",
        }
    else:
        labels = {
            "home": "Home",
            "reviews": "Reviews",
            "comparisons": "Comparisons",
            "pricing": "Pricing",
            "categories": "Categories",
            "blog": "Blog",
            "contact": "Contact",
            "disclosure": "Some links may be affiliate links. We may earn a commission at no extra cost to you.",
        }
    home = "/vi/" if lang == "vi" else "/"
    prefix = "/vi" if lang == "vi" else ""
    return (
        "<nav class='nav'><div class='wrap nav-inner'>"
        f"<a class='logo' href='{home}'>{SITE_NAME}</a>"
        "<div class='menu'>"
        f"<a href='{home}'>{labels['home']}</a>"
        f"<a href='{prefix}/reviews/'>{labels['reviews']}</a>"
        f"<a href='{prefix}/comparisons/'>{labels['comparisons']}</a>"
        f"<a href='{prefix}/pricing/'>{labels['pricing']}</a>"
        f"<a href='{prefix}/categories/'>{labels['categories']}</a>"
        f"<a href='{prefix}/blog/'>{labels['blog']}</a>"
        f"<a href='{prefix}/contact/'>{labels['contact']}</a>"
        "</div>"
        f"<div class='language-switcher'><a class='{'active' if lang == 'en' else ''}' href='{en_path}'>English</a><span>|</span><a class='{'active' if lang == 'vi' else ''}' href='{vi_path}'>Tiếng Việt</a></div>"
        "</div>"
        f"<div class='wrap'><p class='note'>{labels['disclosure']}</p></div></nav>"
    )


def footer_html(lang: str) -> str:
    links = [
        ("/privacy/", "Privacy Policy", "/vi/privacy/", "Chính sách bảo mật"),
        ("/terms/", "Terms", "/vi/terms/", "Điều khoản"),
        ("/editorial-policy/", "Editorial Policy", "/vi/editorial-policy/", "Chính sách biên tập"),
        ("/affiliate-disclosure/", "Affiliate Disclosure", "/vi/affiliate-disclosure/", "Tiết lộ affiliate"),
        ("/about/", "About", "/vi/about/", "Giới thiệu"),
        ("/contact/", "Contact", "/vi/contact/", "Liên hệ"),
    ]
    if lang == "vi":
        contact = f"<p>Liên hệ: <a href='mailto:{CONTACT_EMAIL}'>{CONTACT_EMAIL}</a></p>"
        disclosure = "Một số liên kết có thể là liên kết tiếp thị liên kết. Chúng tôi có thể nhận hoa hồng mà không phát sinh thêm chi phí nào cho bạn."
    else:
        contact = f"<p>Contact: <a href='mailto:{CONTACT_EMAIL}'>{CONTACT_EMAIL}</a></p>"
        disclosure = "Some links may be affiliate links. We may earn a commission at no extra cost to you."
    rendered = []
    for en_href, en_text, vi_href, vi_text in links:
        rendered.append(f"<a href='{vi_href if lang == 'vi' else en_href}'>{vi_text if lang == 'vi' else en_text}</a>")
    return f"<footer><div class='wrap'><p><strong>{SITE_NAME}</strong></p>{contact}<p>{' '.join(rendered)}</p><p>&copy; 2026 {SITE_NAME}.</p><p>{disclosure}</p></div></footer>"


def css() -> str:
    return """:root{--bg:#f7f9fc;--text:#17202a;--muted:#596579;--line:#dbe3ef;--card:#fff;--accent:#0f766e;--warn:#9a3412}*{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text);line-height:1.7}.wrap{max-width:1120px;margin:0 auto;padding:0 20px}.nav{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}.nav-inner{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:18px}.logo{font-weight:800;color:#0f172a;text-decoration:none}.menu{display:flex;gap:18px;flex-wrap:wrap}.menu a{color:#475569;text-decoration:none;font-size:14px}.language-switcher{display:flex;gap:8px;align-items:center;border:1px solid #dbe3ef;border-radius:999px;padding:4px 8px;background:#f8fafc;font-size:13px;white-space:nowrap}.language-switcher span{font-weight:800;color:#0f766e}.language-switcher a{color:#475569;text-decoration:none}.language-switcher .active{font-weight:800}.hero{padding:46px 0 18px}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:20px;margin:18px 0;box-shadow:0 1px 2px rgba(15,23,42,.04)}h1{font-size:42px;line-height:1.12;margin:10px 0}h2{font-size:26px;margin:0 0 12px}h3{font-size:18px;margin:0 0 8px}p,li{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}.btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:12px 16px;border-radius:6px;font-weight:800;margin:6px 8px 6px 0}.btn.secondary{background:#e2e8f0;color:#0f172a}.trust{border-left:4px solid var(--warn);background:#fff7ed}.note{font-size:14px;color:#7c2d12}.email-form input{padding:12px;border:1px solid var(--line);border-radius:6px;min-width:280px}.email-form button{padding:12px 16px;border:0;border-radius:6px;background:var(--accent);color:#fff;font-weight:800}footer{margin-top:36px;background:#0f172a;color:#cbd5e1;padding:28px 0}footer a{color:#e2e8f0;text-decoration:none;margin-right:14px}footer p{color:#cbd5e1}@media(max-width:760px){h1{font-size:32px}.nav-inner{align-items:flex-start;flex-direction:column;padding:14px 0}.language-switcher{margin-top:6px}.email-form input{min-width:100%;margin-bottom:8px}}"""


def write_html(root: Path, path: str, html_text: str) -> Path:
    folder = root / path.strip("/")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "index.html"
    target.write_text(html_text, encoding="utf-8")
    return target


def write_file(root: Path, path: str, html_text: str) -> Path:
    target = root / path.strip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html_text, encoding="utf-8")
    return target


def write_about_pages(root: Path) -> None:
    en_body = f"""
<section class="hero">
  <p class="note">Build in public AI coding research</p>
  <h1>About {SITE_NAME}</h1>
  <p>This site exists to review AI coding tools through real building work, not polished product demos.</p>
</section>
<section class="card">
  <h2>Why this site exists</h2>
  <p>I am using Windsurf, Codex, Cursor, and GitHub Copilot while building this very review site. The goal is to document what actually helps: scaffolding, debugging, refactoring, SEO checks, language integrity, GitHub Pages deployment, and the cleanup work that demos rarely show.</p>
  <p>The reviews are written from a builder workflow perspective. A tool can be fast and still create cleanup debt. Another tool can feel slower but be better when the repository is already messy. That tradeoff is what this site tracks.</p>
  <p>The audience is beginners, small builders, indie makers, and non-technical founders who want to understand AI-assisted website, SEO, and code workflows without pretending every tool is perfect.</p>
</section>
<section class="grid">
  <div class="card"><h2>What I track</h2><ul><li>Which tools speed up real project work.</li><li>Where AI coding tools break or repeat mistakes.</li><li>How SEO, hreflang, sitemap, and deployment checks behave in practice.</li><li>How social drafts and tracking can support affiliate research without spam.</li></ul></div>
  <div class="card"><h2>Follow the journey</h2><p>If you want practical notes on AI coding workflows, start with the free checklist and follow the build process.</p><a class="btn" href="/free-ai-coding-workflow-checklist/">Get the workflow checklist</a></div>
</section>
<section class="card">
  <h2>Editorial and affiliate transparency</h2>
  <p>MS Smile AI Review Hub documents a real build-in-public workflow. The site itself is built, improved, and tested using AI coding tools and GitHub Pages. Reviews focus on practical workflows, limitations, buying checks, and clear disclosure rather than feature lists alone.</p>
  <p><a href="/editorial-policy/">Read the editorial policy</a> · <a href="/affiliate-disclosure/">Read the affiliate disclosure</a> · <a href="/free-ai-coding-workflow-checklist/">Download the AI coding workflow checklist</a></p>
</section>
<section class="card trust"><h2>Disclosure</h2><p>Some links may be affiliate links. Reviews are research notes and practical observations, not guaranteed results.</p></section>
"""
    vi_body = f"""
<section class="hero">
  <p class="note">Ghi chép công khai về workflow AI coding</p>
  <h1>Giới thiệu {SITE_NAME}</h1>
  <p>Website này được xây để review công cụ AI coding bằng trải nghiệm xây dự án thật, không phải chỉ xem demo quảng cáo.</p>
</section>
<section class="card">
  <h2>Vì sao có website này?</h2>
  <p>Mình đang dùng Windsurf, Codex, Cursor và GitHub Copilot để xây chính website review này. Mục tiêu là ghi lại công cụ nào giúp dựng nhanh, công cụ nào sửa lỗi tốt, lỗi nào hay gặp, cách kiểm tra SEO, hreflang, sitemap và cách triển khai lên GitHub Pages.</p>
  <p>Góc nhìn ở đây là workflow của người đang build thật. Một công cụ có thể tạo rất nhanh nhưng tạo thêm nợ cleanup. Một công cụ khác có thể chậm hơn nhưng xử lý repo đang lỗi tốt hơn. Những khác biệt đó là phần mình muốn ghi lại.</p>
  <p>Đối tượng chính là người mới, small builders, indie makers và founder không chuyên kỹ thuật muốn hiểu cách dùng AI để làm website, SEO và code workflow mà không xem công cụ nào là hoàn hảo tuyệt đối.</p>
</section>
<section class="grid">
  <div class="card"><h2>Mình theo dõi điều gì?</h2><ul><li>Công cụ nào giúp tăng tốc khi làm dự án thật.</li><li>AI coding tool thường lỗi ở đâu hoặc lặp sai như thế nào.</li><li>SEO, hreflang, sitemap và deploy hoạt động ra sao trong thực tế.</li><li>Cách tạo social draft và tracking mà không spam.</li></ul></div>
  <div class="card"><h2>Theo dõi hành trình</h2><p>Nếu bạn muốn xem workflow AI coding thực chiến, hãy bắt đầu bằng checklist miễn phí.</p><a class="btn" href="/vi/free-ai-coding-workflow-checklist/">Nhận checklist workflow</a></div>
</section>
<section class="card">
  <h2>Minh bạch biên tập và affiliate</h2>
  <p>MS Smile AI Review Hub ghi lại một workflow build-in-public thật. Chính website này được xây, cải thiện và kiểm tra bằng AI coding tools và GitHub Pages. Các bài review tập trung vào workflow thực tế, giới hạn, điểm cần kiểm tra trước khi mua và disclosure rõ ràng, không chỉ liệt kê tính năng.</p>
  <p><a href="/vi/editorial-policy/">Đọc chính sách biên tập</a> · <a href="/vi/affiliate-disclosure/">Đọc tiết lộ affiliate</a> · <a href="/vi/free-ai-coding-workflow-checklist/">Tải checklist AI coding workflow</a></p>
</section>
<section class="card trust"><h2>Tiết lộ</h2><p>Một số liên kết có thể là liên kết tiếp thị liên kết. Nội dung là ghi chú nghiên cứu và trải nghiệm thực tế, không phải cam kết kết quả.</p></section>
"""
    write_html(root, "about", page_shell("About MS Smile AI Review Hub", "A build-in-public AI coding tools review site focused on real workflows, SEO checks, and deployment lessons.", "/about/", en_body, "en"))
    write_html(root, "vi/about", page_shell("Giới thiệu MS Smile AI Review Hub", "Website review công cụ AI coding theo hướng trải nghiệm thật, SEO, workflow và triển khai dự án.", "/vi/about/", vi_body, "vi"))


def lead_form(lang: str) -> str:
    capture = load_email_capture_config()
    enabled = bool(capture["enabled"]) and bool(capture["form_endpoint"])
    endpoint = html.escape(str(capture["form_endpoint"]), quote=True)
    honeypot = html.escape(str(capture["honeypot_field"]), quote=True)
    source_page = "/vi/free-ai-coding-workflow-checklist/" if lang == "vi" else "/free-ai-coding-workflow-checklist/"
    if enabled:
        button = "Nhận checklist" if lang == "vi" else "Get the checklist"
        placeholder = "Email của bạn" if lang == "vi" else "Your email"
        note = (
            "Form này sẽ gửi email đến Formspree theo endpoint bạn đã cấu hình. Không hard-code API key trong HTML."
            if lang == "vi"
            else "This form submits to your configured Formspree endpoint. No API key is hard-coded in the HTML."
        )
        return f"""<form class="email-form" action="{endpoint}" method="POST" data-email-capture-provider="formspree">
  <input type="email" name="email" placeholder="{placeholder}" required>
  <input type="hidden" name="source_page" value="{source_page}">
  <input type="hidden" name="language" value="{lang}">
  <input type="hidden" name="lead_magnet" value="ai-coding-workflow-checklist">
  <input type="text" name="{honeypot}" tabindex="-1" autocomplete="off" style="display:none">
  <button type="submit">{button}</button>
</form>
<p class="note">{note}</p>"""
    if lang == "vi":
        return """<form class="email-form" data-email-capture-mode="setup" onsubmit="return false;">
  <input type="email" name="email" placeholder="Email của bạn" required>
  <input type="hidden" name="source_page" value="/vi/free-ai-coding-workflow-checklist/">
  <input type="hidden" name="language" value="vi">
  <input type="hidden" name="lead_magnet" value="ai-coding-workflow-checklist">
  <input type="text" name="_gotcha" tabindex="-1" autocomplete="off" style="display:none">
  <button type="button">Nhận checklist</button>
</form>
<p class="note"><strong>Email capture hiện đang ở chế độ thiết lập.</strong> Form này chưa gửi dữ liệu đi đâu và chưa tự lưu email vào hệ thống. Để thu email thật, hãy cấu hình Formspree rồi bật <code>enabled</code>. <a href="/vi/formspree-setup/">Xem hướng dẫn Formspree</a>.</p>"""
    return """<form class="email-form" data-email-capture-mode="setup" onsubmit="return false;">
  <input type="email" name="email" placeholder="Your email" required>
  <input type="hidden" name="source_page" value="/free-ai-coding-workflow-checklist/">
  <input type="hidden" name="language" value="en">
  <input type="hidden" name="lead_magnet" value="ai-coding-workflow-checklist">
  <input type="text" name="_gotcha" tabindex="-1" autocomplete="off" style="display:none">
  <button type="button">Get the checklist</button>
</form>
<p class="note"><strong>Email capture is currently in setup mode.</strong> This form does not submit anywhere and does not save emails yet. To collect real subscribers, add your Formspree endpoint and set <code>enabled</code> to true. <a href="/formspree-setup/">See the Formspree setup guide</a>.</p>"""


def faq_html(items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f"<details><summary>{html.escape(question)}</summary><p>{html.escape(answer)}</p></details>"
        for question, answer in items
    )
    return f"<section class='card'><h2>FAQ</h2>{rows}</section>"


def lead_faq(lang: str) -> list[tuple[str, str]]:
    if lang == "vi":
        return [
            ("Checklist này có miễn phí không?", "Có. Đây là tài liệu miễn phí để bạn tự kiểm tra workflow AI coding trước khi publish."),
            ("Form có gửi dữ liệu vào hệ thống tự động không?", "Chưa. Website đang chạy static trên GitHub Pages nên hiện dùng mailto/fallback và chuẩn bị sẵn file subscribers.csv cho tích hợp sau."),
            ("Checklist có thay thế review thủ công không?", "Không. Checklist giúp bạn nhớ các bước cần kiểm tra, nhưng vẫn cần tự xem lại code, SEO, sitemap và nội dung."),
        ]
    return [
        ("Is the checklist free?", "Yes. It is a free workflow checklist for reviewing AI-assisted coding work before publishing."),
        ("Does the form automatically store my email?", "Not yet. The site is static on GitHub Pages, so the current form uses a mailto fallback while subscribers.csv is prepared for a future integration."),
        ("Does the checklist replace manual review?", "No. It helps you remember what to check, but code, SEO, sitemap, and content still need human review."),
    ]


def write_lead_magnet_pages(root: Path) -> None:
    en_faq = lead_faq("en")
    vi_faq = lead_faq("vi")
    en_body = f"""
<section class="hero">
  <p class="note">Free workflow checklist</p>
  <h1>My AI Coding Workflow: Windsurf → Codex → Cursor → GitHub Pages</h1>
  <p>A practical checklist for building, fixing, validating, and publishing AI-assisted projects without trusting the first generated answer blindly.</p>
  <a class="btn" href="/downloads/ai-coding-workflow-checklist.html">Open checklist</a>
</section>
<section class="card">
  <h2>What the checklist helps you do</h2>
  <ul>
    <li>Use Windsurf for fast scaffolding without skipping review.</li>
    <li>Use Codex for repair, logic cleanup, and build/deploy fixes.</li>
    <li>Use Cursor for repo-aware iteration and smaller edits.</li>
    <li>Check language integrity before publishing bilingual pages.</li>
    <li>Validate SEO title, meta, H1, canonical, hreflang, and sitemap.</li>
    <li>Create social drafts after the page is ready, not before.</li>
    <li>Track what gets clicks and improve content quality over time.</li>
  </ul>
</section>
<section class="card">
  <h2>Get the checklist</h2>
  {lead_form("en")}
</section>
{faq_html(en_faq)}
<section class="card"><h2>CTA</h2><p>Use the checklist before publishing your next AI-assisted page.</p><a class="btn" href="/downloads/ai-coding-workflow-checklist.html">Download the checklist</a></section>
"""
    vi_body = f"""
<section class="hero">
  <p class="note">Checklist workflow miễn phí</p>
  <h1>Workflow AI Coding của mình: Windsurf → Codex → Cursor → GitHub Pages</h1>
  <p>Checklist thực chiến để dựng, sửa, kiểm tra và publish dự án dùng AI mà không tin mù quáng vào câu trả lời đầu tiên.</p>
  <a class="btn" href="/vi/downloads/ai-coding-workflow-checklist.html">Mở checklist</a>
</section>
<section class="card">
  <h2>Checklist này giúp bạn làm gì?</h2>
  <ul>
    <li>Dùng Windsurf để dựng khung nhanh nhưng vẫn có bước review.</li>
    <li>Dùng Codex để sửa logic, cleanup và xử lý lỗi build/deploy.</li>
    <li>Dùng Cursor để chỉnh nhanh trong repo và iterate từng phần nhỏ.</li>
    <li>Kiểm tra language integrity trước khi publish trang song ngữ.</li>
    <li>Kiểm tra SEO title, meta, H1, canonical, hreflang và sitemap.</li>
    <li>Tạo social draft sau khi bài đã sẵn sàng, không làm ngược.</li>
    <li>Theo dõi link nào có click và cải thiện chất lượng nội dung.</li>
  </ul>
</section>
<section class="card">
  <h2>Nhận checklist</h2>
  {lead_form("vi")}
</section>
{faq_html(vi_faq)}
<section class="card"><h2>CTA</h2><p>Dùng checklist trước khi publish trang AI-assisted tiếp theo.</p><a class="btn" href="/vi/downloads/ai-coding-workflow-checklist.html">Tải checklist</a></section>
"""
    write_html(root, LEAD_SLUG, page_shell("Free AI Coding Workflow Checklist", "Download a practical AI coding workflow checklist for Windsurf, Codex, Cursor, SEO validation, and GitHub Pages deployment.", f"/{LEAD_SLUG}/", en_body, "en", en_faq))
    write_html(root, f"vi/{LEAD_SLUG}", page_shell("Checklist workflow AI coding miễn phí", "Checklist workflow AI coding với Windsurf, Codex, Cursor, kiểm tra SEO và triển khai GitHub Pages.", f"/vi/{LEAD_SLUG}/", vi_body, "vi", vi_faq))


def email_capture_setup_faq(lang: str) -> list[tuple[str, str]]:
    if lang == "vi":
        return [
            ("GitHub Pages có tự lưu email được không?", "Không. GitHub Pages chỉ phục vụ file static nên không thể ghi trực tiếp vào data/subscribers.csv nếu không có backend hoặc form provider."),
            ("Hiện form trên site đang làm gì?", "Form đang ở chế độ thiết lập, dùng mailto/fallback để người đọc có thể liên hệ trong khi chờ tích hợp provider thật."),
            ("Nên tích hợp gì sau này?", "Các lựa chọn đơn giản là Formspree, Google Forms, ConvertKit, Mailchimp hoặc Netlify Forms nếu sau này chuyển sang Netlify."),
        ]
    return [
        ("Can GitHub Pages save emails directly?", "No. GitHub Pages serves static files, so it cannot write directly to data/subscribers.csv without a backend or form provider."),
        ("What does the current form do?", "The form is in setup mode. It uses a mailto fallback so readers can contact you while a real provider is not connected yet."),
        ("What should be integrated later?", "Simple options include Formspree, Google Forms, ConvertKit, Mailchimp, or Netlify Forms if the site later moves to Netlify."),
    ]


def write_email_capture_setup_pages(root: Path) -> None:
    en_faq = email_capture_setup_faq("en")
    vi_faq = email_capture_setup_faq("vi")
    en_body = f"""
<section class="hero">
  <p class="note">Local-safe email capture</p>
  <h1>Email Capture Setup</h1>
  <p>This site is currently running on GitHub Pages, so the checklist form is intentionally in setup mode. It does not pretend to save subscribers until a real backend or form provider is connected.</p>
</section>
<section class="card trust">
  <h2>Email capture is currently in setup mode</h2>
  <p>GitHub Pages cannot write new form submissions into <code>data/subscribers.csv</code> on its own. The current form uses a mailto fallback and the local CSV is prepared for future imports or provider exports.</p>
</section>
<section class="grid">
  <div class="card"><h2>Option A: Formspree</h2><p>Use Formspree for a simple hosted endpoint, then export subscribers into your local workflow. Do not hard-code private keys in the static site.</p></div>
  <div class="card"><h2>Option B: Google Forms</h2><p>Embed or link to a Google Form if you want the lowest-maintenance setup. This is not as branded, but it is simple and reliable.</p></div>
  <div class="card"><h2>Option C: Netlify Forms</h2><p>If the site later moves to Netlify, Netlify Forms can capture submissions without building a custom backend.</p></div>
</section>
<section class="card">
  <h2>Recommended next step</h2>
  <p>Keep the current local-safe mode until you choose a provider. Then update <code>config/email_capture.json</code> with the provider name and replace the mailto action with the provider endpoint.</p>
  <a class="btn" href="/free-ai-coding-workflow-checklist/">Back to checklist signup</a>
</section>
{faq_html(en_faq)}
<section class="card"><h2>CTA</h2><p>Use this page as the setup note before enabling real subscriber storage.</p><a class="btn" href="mailto:{CONTACT_EMAIL}">Contact the site owner</a></section>
"""
    vi_body = f"""
<section class="hero">
  <p class="note">Email capture an toàn ở chế độ local</p>
  <h1>Cấu hình email capture</h1>
  <p>Website hiện chạy trên GitHub Pages, vì vậy form nhận checklist đang ở chế độ thiết lập. Site không giả vờ lưu subscriber khi chưa có backend hoặc form provider thật.</p>
</section>
<section class="card trust">
  <h2>Email capture hiện đang ở chế độ thiết lập</h2>
  <p>GitHub Pages không thể tự ghi form submission mới vào <code>data/subscribers.csv</code>. Form hiện dùng mailto/fallback, còn CSV local được chuẩn bị để nhập dữ liệu thủ công hoặc import từ provider sau này.</p>
</section>
<section class="grid">
  <div class="card"><h2>Lựa chọn A: Formspree</h2><p>Dùng Formspree nếu bạn muốn endpoint hosted đơn giản rồi export subscriber về workflow local. Không hard-code private key trong site static.</p></div>
  <div class="card"><h2>Lựa chọn B: Google Forms</h2><p>Nhúng hoặc link tới Google Form nếu muốn cách ít bảo trì nhất. Không đẹp bằng form riêng, nhưng dễ kiểm soát và ổn định.</p></div>
  <div class="card"><h2>Lựa chọn C: Netlify Forms</h2><p>Nếu sau này chuyển site sang Netlify, Netlify Forms có thể nhận submission mà không cần tự viết backend.</p></div>
</section>
<section class="card">
  <h2>Bước tiếp theo nên làm</h2>
  <p>Giữ chế độ local-safe hiện tại cho đến khi chọn provider. Sau đó cập nhật <code>config/email_capture.json</code> và thay mailto action bằng endpoint của provider.</p>
  <a class="btn" href="/vi/free-ai-coding-workflow-checklist/">Quay lại trang nhận checklist</a>
</section>
{faq_html(vi_faq)}
<section class="card"><h2>CTA</h2><p>Dùng trang này như ghi chú cấu hình trước khi bật lưu subscriber thật.</p><a class="btn" href="mailto:{CONTACT_EMAIL}">Liên hệ chủ site</a></section>
"""
    write_html(
        root,
        EMAIL_SETUP_SLUG,
        page_shell(
            "Email Capture Setup",
            "How email capture works on this static GitHub Pages site and which provider options can be connected later.",
            f"/{EMAIL_SETUP_SLUG}/",
            en_body,
            "en",
            en_faq,
        ),
    )
    write_html(
        root,
        f"vi/{EMAIL_SETUP_SLUG}",
        page_shell(
            "Cấu hình email capture",
            "Cách email capture hoạt động trên GitHub Pages static và các lựa chọn tích hợp sau này.",
            f"/vi/{EMAIL_SETUP_SLUG}/",
            vi_body,
            "vi",
            vi_faq,
        ),
    )


def formspree_setup_faq(lang: str) -> list[tuple[str, str]]:
    if lang == "vi":
        return [
            ("Có cần API key trong HTML không?", "Không. Với Formspree, site static chỉ cần form endpoint công khai. Không đưa API key hoặc token riêng vào HTML."),
            ("Khi nào form bắt đầu gửi email thật?", "Chỉ khi config/email_capture.json có enabled=true và form_endpoint là endpoint Formspree thật."),
            ("Nếu endpoint trống thì sao?", "Form vẫn ở chế độ thiết lập, không POST đi đâu và không giả vờ lưu subscriber."),
        ]
    return [
        ("Do I need an API key in the HTML?", "No. With Formspree, the static site only needs the public form endpoint. Do not put private API keys or tokens into HTML."),
        ("When does the form start collecting real emails?", "Only when config/email_capture.json has enabled=true and form_endpoint contains your real Formspree endpoint."),
        ("What happens when the endpoint is empty?", "The form stays in setup mode, does not POST anywhere, and does not pretend to save subscribers."),
    ]


def write_formspree_setup_pages(root: Path) -> None:
    en_faq = formspree_setup_faq("en")
    vi_faq = formspree_setup_faq("vi")
    en_body = f"""
<section class="hero">
  <p class="note">Real email capture integration</p>
  <h1>Formspree Setup for the AI Coding Checklist</h1>
  <p>This guide explains how to connect the checklist form to Formspree while keeping the static GitHub Pages site safe when no endpoint is configured.</p>
</section>
<section class="card">
  <h2>Setup steps</h2>
  <ol>
    <li>Create or log in to a Formspree account.</li>
    <li>Create a new form for the AI Coding Workflow Checklist.</li>
    <li>Copy the Formspree endpoint URL.</li>
    <li>Open <code>config/email_capture.json</code>.</li>
    <li>Set <code>provider</code> to <code>formspree</code>.</li>
    <li>Paste the endpoint into <code>form_endpoint</code>.</li>
    <li>Change <code>enabled</code> to <code>true</code>.</li>
    <li>Run <code>python main.py</code> and <code>python scripts/sync_site_output_to_docs.py</code>.</li>
    <li>Commit and push the updated static files.</li>
    <li>Test a real email submission from the live checklist page.</li>
  </ol>
</section>
<section class="card trust">
  <h2>Current safety rule</h2>
  <p>If <code>enabled=false</code> or <code>form_endpoint</code> is empty, the form remains in setup mode and does not submit anywhere.</p>
</section>
{faq_html(en_faq)}
<section class="card"><h2>CTA</h2><p>After adding a real endpoint, rebuild the static site before testing.</p><a class="btn" href="/free-ai-coding-workflow-checklist/">Open the checklist form</a></section>
"""
    vi_body = f"""
<section class="hero">
  <p class="note">Tích hợp email capture thật</p>
  <h1>Hướng dẫn cấu hình Formspree cho checklist AI Coding</h1>
  <p>Trang này giải thích cách kết nối form checklist với Formspree, đồng thời giữ site GitHub Pages an toàn khi chưa cấu hình endpoint thật.</p>
</section>
<section class="card">
  <h2>Các bước cấu hình</h2>
  <ol>
    <li>Tạo hoặc đăng nhập tài khoản Formspree.</li>
    <li>Tạo form mới cho AI Coding Workflow Checklist.</li>
    <li>Copy URL endpoint của Formspree.</li>
    <li>Mở <code>config/email_capture.json</code>.</li>
    <li>Đặt <code>provider</code> là <code>formspree</code>.</li>
    <li>Dán endpoint vào <code>form_endpoint</code>.</li>
    <li>Đổi <code>enabled</code> thành <code>true</code>.</li>
    <li>Chạy <code>python main.py</code> và <code>python scripts/sync_site_output_to_docs.py</code>.</li>
    <li>Commit và push static files đã cập nhật.</li>
    <li>Test gửi email thật từ trang checklist live.</li>
  </ol>
</section>
<section class="card trust">
  <h2>Quy tắc an toàn hiện tại</h2>
  <p>Nếu <code>enabled=false</code> hoặc <code>form_endpoint</code> trống, form vẫn ở chế độ thiết lập và không gửi dữ liệu đi đâu.</p>
</section>
{faq_html(vi_faq)}
<section class="card"><h2>CTA</h2><p>Sau khi thêm endpoint thật, hãy rebuild static site trước khi test.</p><a class="btn" href="/vi/free-ai-coding-workflow-checklist/">Mở form checklist</a></section>
"""
    write_html(
        root,
        FORMSPREE_SETUP_SLUG,
        page_shell(
            "Formspree Setup for Email Capture",
            "Step-by-step Formspree setup for the AI Coding Workflow Checklist email form on GitHub Pages.",
            f"/{FORMSPREE_SETUP_SLUG}/",
            en_body,
            "en",
            en_faq,
        ),
    )
    write_html(
        root,
        f"vi/{FORMSPREE_SETUP_SLUG}",
        page_shell(
            "Hướng dẫn cấu hình Formspree",
            "Các bước cấu hình Formspree cho form checklist AI Coding trên GitHub Pages.",
            f"/vi/{FORMSPREE_SETUP_SLUG}/",
            vi_body,
            "vi",
            vi_faq,
        ),
    )


def write_formspree_setup_checklist() -> None:
    path = settings.data_dir / "formspree_setup_checklist.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        ("create_formspree_account", "Create or log in to Formspree", "pending"),
        ("create_form", "Create a form for AI Coding Workflow Checklist", "pending"),
        ("copy_endpoint", "Copy the Formspree endpoint URL", "pending"),
        ("update_config_provider", "Set provider=formspree in config/email_capture.json", "pending"),
        ("update_config_endpoint", "Paste endpoint into form_endpoint", "pending"),
        ("enable_capture", "Set enabled=true only after endpoint is real", "pending"),
        ("rebuild_site", "Run python main.py and sync docs", "pending"),
        ("test_live_submission", "Submit a real email from the live checklist page", "pending"),
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["step_id", "task", "status"])
        writer.writeheader()
        for step_id, task, status in rows:
            writer.writerow({"step_id": step_id, "task": task, "status": status})


def write_partnerstack_trust_pages(root: Path) -> None:
    en_editorial = """
<section class="hero">
  <p class="note">Editorial standards</p>
  <h1>Editorial Policy</h1>
  <p>MS Smile AI Review Hub publishes practical AI coding tool reviews based on real builder use cases, not paid praise or generic feature summaries.</p>
</section>
<section class="card">
  <h2>How we approach reviews</h2>
  <p>Reviews focus on AI coding tools, AI-assisted workflow, SEO checks, GitHub Pages deployment, and small builder use cases. The goal is to help beginners, indie builders, small business owners, and non-technical founders understand how a tool behaves in realistic work.</p>
  <p>We may use AI tools to help draft outlines, compare structure, or check consistency, but pages are reviewed before publishing. We check for mixed language, broken links, canonical tags, hreflang, sitemap inclusion, disclosure, and whether the content gives a practical recommendation.</p>
</section>
<section class="card">
  <h2>Independence and sponsored content</h2>
  <p>We do not accept payment to write fake positive reviews. Affiliate commission does not control editorial opinions, rankings, or final recommendations. If sponsored content is ever published in the future, it must be disclosed clearly near the beginning of the page.</p>
  <p>Current content prioritizes practical usefulness over hype: where a tool helps, where it fails, what should be verified, and what a reader should test before adopting it.</p>
</section>
<section class="card trust"><h2>Related pages</h2><p><a href="/affiliate-disclosure/">Affiliate Disclosure</a> · <a href="/about/">About MS Smile AI Review Hub</a> · <a href="/free-ai-coding-workflow-checklist/">AI Coding Workflow Checklist</a></p></section>
"""
    vi_editorial = """
<section class="hero">
  <p class="note">Tiêu chuẩn biên tập</p>
  <h1>Chính sách biên tập</h1>
  <p>MS Smile AI Review Hub xuất bản review công cụ AI coding dựa trên use case thực tế của người đang build, không viết đánh giá giả hoặc nội dung chỉ liệt kê tính năng.</p>
</section>
<section class="card">
  <h2>Cách chúng tôi làm review</h2>
  <p>Nội dung tập trung vào AI coding tools, workflow có AI hỗ trợ, kiểm tra SEO, triển khai GitHub Pages và use case của small builders. Mục tiêu là giúp người mới, indie builders, chủ doanh nghiệp nhỏ và founder không chuyên kỹ thuật hiểu công cụ hoạt động ra sao trong công việc thật.</p>
  <p>Chúng tôi có thể dùng AI để hỗ trợ tạo outline, so sánh cấu trúc hoặc kiểm tra tính nhất quán, nhưng nội dung phải được xem lại trước khi publish. Các bước kiểm tra gồm mixed language, broken links, canonical, hreflang, sitemap, disclosure và tính thực dụng của khuyến nghị.</p>
</section>
<section class="card">
  <h2>Tính độc lập và nội dung tài trợ</h2>
  <p>Chúng tôi không nhận tiền để viết đánh giá tích cực giả. Hoa hồng affiliate không kiểm soát quan điểm biên tập, thứ tự ưu tiên hoặc kết luận cuối. Nếu sau này có nội dung được tài trợ, phần đó phải được tiết lộ rõ ràng ở đầu trang.</p>
  <p>Nội dung hiện ưu tiên tính hữu ích: công cụ giúp ở đâu, lỗi ở đâu, điều gì cần xác minh và người đọc nên test gì trước khi dùng lâu dài.</p>
</section>
<section class="card trust"><h2>Trang liên quan</h2><p><a href="/vi/affiliate-disclosure/">Tiết lộ affiliate</a> · <a href="/vi/about/">Giới thiệu MS Smile AI Review Hub</a> · <a href="/vi/free-ai-coding-workflow-checklist/">Checklist AI Coding Workflow</a></p></section>
"""
    en_affiliate = """
<section class="hero">
  <p class="note">Affiliate transparency</p>
  <h1>Affiliate Disclosure</h1>
  <p>Some links on MS Smile AI Review Hub may be affiliate links. We may earn a commission at no extra cost to the reader.</p>
</section>
<section class="card">
  <h2>How affiliate links work</h2>
  <p>Affiliate links help support the site when a reader chooses to visit or purchase through a tracked link. The reader does not pay extra because of that commission. We only place affiliate-style CTAs where the tool is relevant to the content and the reader has enough context to evaluate it.</p>
  <p>Affiliate relationships do not control editorial opinions. A tool can be mentioned as useful, limited, risky, pending approval, or not recommended depending on the content and use case.</p>
</section>
<section class="card">
  <h2>Current approval status</h2>
  <p>Some outbound links may currently be normal official-site links while affiliate approval is pending. We do not claim to be an official partner unless that approval exists. When a program is approved, links can be updated through the tracking system without changing the editorial recommendation.</p>
</section>
<section class="card trust"><h2>Related pages</h2><p><a href="/editorial-policy/">Editorial Policy</a> · <a href="/about/">About MS Smile AI Review Hub</a> · <a href="/free-ai-coding-workflow-checklist/">AI Coding Workflow Checklist</a></p></section>
"""
    vi_affiliate = """
<section class="hero">
  <p class="note">Minh bạch affiliate</p>
  <h1>Tiết lộ affiliate</h1>
  <p>Một số liên kết trên MS Smile AI Review Hub có thể là liên kết affiliate. Chúng tôi có thể nhận hoa hồng mà không làm người đọc phát sinh thêm chi phí.</p>
</section>
<section class="card">
  <h2>Liên kết affiliate hoạt động như thế nào?</h2>
  <p>Liên kết affiliate giúp duy trì website khi người đọc chọn truy cập hoặc mua qua liên kết có tracking. Người đọc không trả thêm chi phí vì khoản hoa hồng đó. Chúng tôi chỉ đặt CTA theo hướng affiliate khi công cụ liên quan đến nội dung và người đọc đã có đủ ngữ cảnh để đánh giá.</p>
  <p>Quan hệ affiliate không kiểm soát quan điểm biên tập. Một công cụ có thể được mô tả là hữu ích, có giới hạn, cần kiểm tra thêm, đang chờ duyệt affiliate hoặc không phù hợp tùy theo use case.</p>
</section>
<section class="card">
  <h2>Trạng thái hiện tại</h2>
  <p>Một số liên kết outbound hiện có thể chỉ là link website chính thức trong khi chờ phê duyệt affiliate. Chúng tôi không tự nhận là official partner nếu chưa được duyệt. Khi chương trình được duyệt, link có thể được cập nhật qua hệ thống tracking mà không thay đổi kết luận biên tập.</p>
</section>
<section class="card trust"><h2>Trang liên quan</h2><p><a href="/vi/editorial-policy/">Chính sách biên tập</a> · <a href="/vi/about/">Giới thiệu MS Smile AI Review Hub</a> · <a href="/vi/free-ai-coding-workflow-checklist/">Checklist AI Coding Workflow</a></p></section>
"""
    write_html(root, "editorial-policy", page_shell("Editorial Policy", "How MS Smile AI Review Hub reviews AI coding tools, sponsored content, affiliate disclosure, and practical builder workflows.", "/editorial-policy/", en_editorial, "en"))
    write_html(root, "vi/editorial-policy", page_shell("Chính sách biên tập", "Cách MS Smile AI Review Hub review công cụ AI coding, nội dung tài trợ, affiliate disclosure và workflow thực tế.", "/vi/editorial-policy/", vi_editorial, "vi"))
    write_html(root, "affiliate-disclosure", page_shell("Affiliate Disclosure", "Affiliate disclosure for MS Smile AI Review Hub, including pending affiliate approval and normal official outbound links.", "/affiliate-disclosure/", en_affiliate, "en"))
    write_html(root, "vi/affiliate-disclosure", page_shell("Tiết lộ affiliate", "Tiết lộ affiliate của MS Smile AI Review Hub, bao gồm link official trong khi chờ duyệt chương trình affiliate.", "/vi/affiliate-disclosure/", vi_affiliate, "vi"))


def write_partnerstack_reapply_pack() -> None:
    path = settings.data_dir / "partnerstack_reapply_pack.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# PartnerStack Reapply Pack

## A. Short application message

Hello PartnerStack team,

I run MS Smile AI Review Hub at {BASE_URL}. The site publishes practical AI coding tool reviews and comparisons for beginners, indie builders, small business owners, and non-technical founders learning AI-assisted website and code workflows. The content focuses on real workflow use cases, limitations, pricing checks, and transparent affiliate disclosure.

I would like to reapply for relevant AI coding and SaaS affiliate programs when applications reopen. I will only use approved links after acceptance and will keep editorial opinions independent from affiliate commissions.

## B. Long application message

MS Smile AI Review Hub is a practical review site focused on AI coding tools, AI-assisted SEO workflows, GitHub Pages publishing, and small builder use cases. The site documents how tools such as Cursor, Windsurf, GitHub Copilot, and Codex-style workflows fit into real project building: scaffolding, debugging, refactoring, checking language integrity, validating sitemap/canonical/hreflang, and preparing content for search and social distribution.

The site is built in public using the same AI coding workflows it reviews. This gives the content a practical angle beyond feature lists. Articles compare where tools help, where they fail, what needs manual verification, and how a reader should test a tool before adopting it.

## C. Traffic sources description

- Organic search through English and Vietnamese SEO pages.
- Google Search Console indexing for reviews, comparisons, workflow guides, and lead magnet pages.
- Manual social distribution on LinkedIn, Facebook, X/Twitter, and Telegram.
- Internal linking between reviews, comparisons, category pages, pricing checks, and workflow content.
- Email capture is prepared through Formspree setup but remains opt-in and provider-based.

## D. Content strategy description

The content strategy prioritizes high-intent AI coding and SaaS research topics:

- Product reviews for AI coding tools and SaaS tools.
- Practical comparisons such as Cursor vs Windsurf and Copilot vs Cursor.
- Workflow guides showing how builders use multiple tools together.
- Pricing and policy verification notes.
- Build-in-public notes that document real site development and quality checks.

## E. Compliance/disclosure statement

The site clearly discloses that some links may be affiliate links and that commissions do not change the reader's price. Affiliate relationships do not control editorial opinions. The site does not claim official partner status unless approval exists. Sponsored content, if any appears later, will be disclosed clearly.

## F. Why this site is a good fit for AI coding tool affiliate programs

This site is a good fit because it targets readers who are actively evaluating AI coding tools for real workflows. The audience includes beginners, solo builders, small teams, indie makers, and non-technical founders who need practical guidance before choosing a tool. The content is educational, comparison-driven, and transparent about limitations, making it suitable for responsible affiliate referrals.

## G. Notes to update before reapplying

- Monthly visitors:
- GSC clicks:
- GSC impressions:
- Email subscribers:
- Social followers:
- Top performing pages:
- Most clicked CTA pages:
- Approved affiliate programs:
- Programs still pending:
"""
    path.write_text(content, encoding="utf-8")


def write_affiliate_program_tracker() -> None:
    path = settings.data_dir / "affiliate_program_tracker.csv"
    rows = [
        ("Cursor", "AI coding", "https://cursor.com", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Do not claim official partner until approved.", "high"),
        ("Windsurf", "AI coding", "https://windsurf.com", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Track official program availability.", "high"),
        ("GitHub Copilot", "AI coding", "https://github.com/features/copilot", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Microsoft/GitHub affiliate availability must be verified.", "high"),
        ("Hostinger", "hosting", "https://www.hostinger.com", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Relevant for website deployment guides.", "medium"),
        ("Namecheap", "domain", "https://www.namecheap.com", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Relevant for domain setup content.", "medium"),
        ("Canva", "design", "https://www.canva.com", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Verify official creator/affiliate options.", "medium"),
        ("InVideo", "video", "https://invideo.io", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Potential video content fallback.", "medium"),
        ("Pictory", "video", "https://pictory.ai", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Potential video content fallback.", "medium"),
        ("MailerLite", "email marketing", "https://www.mailerlite.com", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Relevant for email capture growth.", "medium"),
        ("GetResponse", "email marketing", "https://www.getresponse.com", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Relevant for email capture growth.", "medium"),
        ("Notion", "productivity", "https://www.notion.so", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Verify current affiliate options.", "low"),
        ("Framer", "website builder", "https://www.framer.com", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Useful for website builder content.", "medium"),
        ("Webflow", "website builder", "https://webflow.com", "to_research", "to_research", "2026-05-26", "to_research", "to_research", "Useful for website builder content.", "medium"),
    ]
    fields = ["tool_name", "category", "official_site", "affiliate_network", "application_status", "reapply_date", "commission_type", "cookie_window", "notes", "priority"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)


def write_go_links_status(root: Path) -> None:
    path = settings.data_dir / "go_links_status.csv"
    rows: list[dict[str, str]] = []
    go_root = root / "go"
    if go_root.exists():
        for index_file in sorted(go_root.glob("*/index.html")):
            slug = index_file.parent.name
            text = index_file.read_text(encoding="utf-8", errors="ignore")
            target = ""
            match = re.search(r'"target_url"\s*:\s*"([^"]+)"', text) or re.search(r"targetUrl\s*=\s*['\"]([^'\"]+)['\"]", text)
            if match:
                target = match.group(1)
            status = "normal_outbound"
            note = "Replace with approved affiliate destination only after program approval."
            if "affiliate_click" in text:
                status = "approved_or_configured_affiliate"
                note = "Review current affiliate link source before claiming partner status."
            rows.append({"go_slug": slug, "current_destination": target, "affiliate_status": status, "notes": note})
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["go_slug", "current_destination", "affiliate_status", "notes"])
        writer.writeheader()
        writer.writerows(rows)


def checklist_items(lang: str) -> list[str]:
    if lang == "vi":
        return [
            "Dùng Windsurf để dựng khung dự án nhanh.",
            "Dùng Codex để sửa/refine logic, kiến trúc và lỗi build.",
            "Kiểm tra language integrity cho English và /vi/.",
            "Kiểm tra SEO title, meta description, H1, canonical và hreflang.",
            "Build sitemap và đảm bảo không có /go/ trong sitemap.",
            "Sync output sang docs cho GitHub Pages.",
            "Submit sitemap trong Google Search Console.",
            "Tạo social drafts để duyệt thủ công.",
            "Theo dõi kết quả bằng UTM/tracking map.",
            "Cải thiện content quality dựa trên lỗi và dữ liệu.",
        ]
    return [
        "Use Windsurf to bootstrap the rough project structure.",
        "Use Codex to fix/refine logic, architecture, build, and deploy issues.",
        "Check language integrity for English and /vi/ pages.",
        "Check SEO title, meta description, H1, canonical, and hreflang.",
        "Build the sitemap and keep /go/ pages out of it.",
        "Sync the static output to docs for GitHub Pages.",
        "Submit the sitemap to Google Search Console.",
        "Create social drafts for manual review.",
        "Track results with UTM links and tracking maps.",
        "Improve content quality based on issues and data.",
    ]


def write_checklist_pages(root: Path) -> None:
    en_faq = lead_faq("en")
    vi_faq = lead_faq("vi")
    en_items = "".join(f"<li>{html.escape(item)}</li>" for item in checklist_items("en"))
    vi_items = "".join(f"<li>{html.escape(item)}</li>" for item in checklist_items("vi"))
    en_body = f"<section class='hero'><h1>AI Coding Workflow Checklist</h1><p>Use this before publishing any AI-assisted page or project update.</p></section><section class='card'><ol>{en_items}</ol></section>{faq_html(en_faq)}<section class='card'><h2>CTA</h2><p>Save this checklist and use it before every AI-assisted publish.</p><a class='btn' href='/free-ai-coding-workflow-checklist/'>Back to signup page</a></section>"
    vi_body = f"<section class='hero'><h1>Checklist workflow AI coding</h1><p>Dùng checklist này trước khi publish trang hoặc cập nhật dự án có AI hỗ trợ.</p></section><section class='card'><ol>{vi_items}</ol></section>{faq_html(vi_faq)}<section class='card'><h2>CTA</h2><p>Lưu checklist này và dùng trước mỗi lần publish nội dung có AI hỗ trợ.</p><a class='btn' href='/vi/free-ai-coding-workflow-checklist/'>Quay lại trang đăng ký</a></section>"
    en_html = page_shell("AI Coding Workflow Checklist", "A practical checklist for AI coding, SEO validation, GitHub Pages publishing, and social draft creation.", f"/{DOWNLOAD_SLUG}/", en_body, "en", en_faq)
    vi_html = page_shell("Checklist workflow AI coding", "Checklist thực tế cho AI coding, kiểm tra SEO, GitHub Pages và social drafts.", f"/vi/{DOWNLOAD_SLUG}/", vi_body, "vi", vi_faq)
    write_html(root, DOWNLOAD_SLUG, en_html)
    write_html(root, f"vi/{DOWNLOAD_SLUG}", vi_html)
    write_file(root, f"{DOWNLOAD_SLUG}.html", en_html)
    write_file(root, f"vi/{DOWNLOAD_SLUG}.html", vi_html)


def add_build_in_public_links(root: Path) -> int:
    targets = [
        ("index.html", "en"),
        ("reviews/index.html", "en"),
        ("comparisons/index.html", "en"),
        ("category/ai-coding-tools/index.html", "en"),
        ("vi/index.html", "vi"),
        ("vi/reviews/index.html", "vi"),
        ("vi/comparisons/index.html", "vi"),
        ("vi/category/ai-coding-tools/index.html", "vi"),
    ]
    added = 0
    for rel, lang in targets:
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "audience-growth-build-public" in text:
            continue
        block = build_public_block(lang)
        if "</main>" in text:
            text = text.replace("</main>", block + "\n</main>", 1)
        else:
            text = text.replace("</body>", block + "\n</body>", 1)
        path.write_text(text, encoding="utf-8")
        added += 2
    return added


def build_public_block(lang: str) -> str:
    if lang == "vi":
        return """<section class="card audience-growth-build-public"><h2>Theo dõi hành trình build in public</h2><p>Website này ghi lại cách dùng Windsurf, Codex, Cursor và Copilot để xây dự án thật, sửa lỗi, kiểm tra SEO và triển khai.</p><a class="btn" href="/vi/about/">Đọc câu chuyện</a><a class="btn secondary" href="/vi/free-ai-coding-workflow-checklist/">Nhận checklist</a></section>"""
    return """<section class="card audience-growth-build-public"><h2>Follow the build-in-public journey</h2><p>This site documents how Windsurf, Codex, Cursor, and Copilot are used to build real projects, fix issues, validate SEO, and publish.</p><a class="btn" href="/about/">Read the story</a><a class="btn secondary" href="/free-ai-coding-workflow-checklist/">Get the checklist</a></section>"""


def write_30_day_social_plan() -> int:
    root = settings.base_dir / "social_assets" / "30_day_plan"
    root.mkdir(parents=True, exist_ok=True)
    topics = [
        "Build in public", "Windsurf vs Cursor", "Codex fixing real bugs", "SEO mistakes",
        "GitHub Pages deployment", "Hreflang and canonical", "Sitemap checks", "AI coding workflow",
        "Beginner-friendly AI coding tools", "Prompt examples", "Cursor cleanup", "Windsurf scaffolding",
        "Codex architecture repair", "Copilot autocomplete", "Language integrity", "Social drafts",
        "Tracking links", "Content quality", "Google Search Console", "Internal linking",
        "Pricing research", "Affiliate disclosure", "Review workflow", "Comparison pages",
        "Noindex decisions", "Robots.txt", "Static site workflow", "Debugging loops",
        "Deployment checklist", "Second failed fix",
    ]
    rows = []
    start = datetime.now().date()
    for day, topic in enumerate(topics, start=1):
        for slot, post_type in [("07:30", "short practical tip"), ("20:30", "story/comparison/case study")]:
            for language in ["en", "vi"]:
                for platform in SOCIAL_PLATFORMS:
                    post_id = f"day-{day:02d}-{slot.replace(':','')}-{language}-{platform}"
                    content = social_plan_content(topic, platform, language, post_type)
                    scheduled_date = (start + timedelta(days=day - 1)).isoformat()
                    payload = {
                        "id": post_id,
                        "day": day,
                        "scheduled_date": scheduled_date,
                        "scheduled_time": slot,
                        "language": language,
                        "platform": platform,
                        "topic": topic,
                        "post_type": post_type,
                        "content": content,
                        "status": "draft",
                    }
                    (root / f"{post_id}.md").write_text(markdown_for_social_plan(payload), encoding="utf-8")
                    rows.append(payload)
    path = settings.data_dir / "social_30_day_plan.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "day", "scheduled_date", "scheduled_time", "language", "platform", "topic", "post_type", "content", "status"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def social_plan_content(topic: str, platform: str, language: str, post_type: str) -> str:
    url = f"{BASE_URL}/vi/free-ai-coding-workflow-checklist/" if language == "vi" else f"{BASE_URL}/free-ai-coding-workflow-checklist/"
    if language == "vi":
        body = (
            f"Ghi chú hôm nay về {topic}:\n\n"
            "Điều đáng giá nhất khi dùng AI coding tool không phải là tạo code thật nhanh, mà là biết bước nào cần kiểm tra lại.\n\n"
            "- Dựng nhanh vẫn cần review.\n"
            "- Lỗi build/deploy thường cần prompt rõ hơn.\n"
            "- SEO và language integrity nên được kiểm tra trước khi publish.\n\n"
            f"Checklist workflow: {url}\n#AICoding #BuildInPublic"
        )
        if post_type.startswith("story"):
            body += "\n\nLỗi mình hay thấy: publish output của AI trước khi kiểm tra các phần nhàm chán nhưng quan trọng."
        if platform == "short_video":
            body += "\n\nVideo: mở bằng hook, nêu vấn đề, đưa checklist, kết thúc bằng link workflow."
        return body.replace("\n\n", "\n") if platform == "twitter" else body

    body = (
        f"Today's build note on {topic}:\n\n"
        "The useful part of AI coding is not generating code fast. It is knowing which stage needs review before publishing.\n\n"
        "- Fast scaffolding still needs cleanup.\n"
        "- Build/deploy bugs need clearer prompts.\n"
        "- SEO and language integrity should be checked before a page goes live.\n\n"
        f"Workflow checklist: {url}\n#AICoding #BuildInPublic"
    )
    if post_type.startswith("story"):
        body += "\n\nThe mistake I keep seeing: people publish the AI output before checking the boring parts."
    if platform == "short_video":
        body += "\n\nVideo: hook, show the problem, show the checklist, close with the workflow link."
    return body.replace("\n\n", "\n") if platform == "twitter" else body


def markdown_for_social_plan(payload: dict[str, object]) -> str:
    return "\n".join(
        [
            "---",
            f"id: {payload['id']}",
            f"day: {payload['day']}",
            f"scheduled_date: {payload['scheduled_date']}",
            f"scheduled_time: {payload['scheduled_time']}",
            f"language: {payload['language']}",
            f"platform: {payload['platform']}",
            f"topic: {payload['topic']}",
            f"status: {payload['status']}",
            "---",
            "",
            str(payload["content"]),
            "",
        ]
    )


def write_audience_growth_report(**kwargs: object) -> int:
    path = settings.data_dir / "audience_growth_report.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "about_page_created",
        "lead_magnet_page_created",
        "checklist_created",
        "email_capture_setup_created",
        "formspree_setup_created",
        "subscriber_capture_ready",
        "social_plan_days",
        "social_posts_created",
        "internal_links_added",
        "warnings",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({column: kwargs.get(column, "") for column in columns})
    return 1
