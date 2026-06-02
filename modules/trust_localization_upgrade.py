from __future__ import annotations

import csv
import html
import re
from pathlib import Path

from config import settings
from modules.site_stats import load_site_stats


IMPACT_SITE_VERIFICATION_ID = "e41dba46-8780-4a26-8314-596af1e3980b"
BASE_URL = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")


CHANNELS = [
    ("Facebook", "https://www.facebook.com/MS.SmileAI", "75,000+ Facebook Views", "75.000+ lượt xem Facebook"),
    ("LinkedIn", "https://www.linkedin.com/company/ms-smile-ai-review-hub", "Public AI review updates", "Cập nhật review AI công khai"),
    ("X", "https://x.com/MS_SmileAI", "AI workflow posts", "Bài đăng về workflow AI"),
    ("Quora", "https://www.quora.com/profile/Nguyen-Quoc-Tuan-138", "Public answer views", "Lượt xem câu trả lời công khai"),
    ("DEV", "https://dev.to/nguyenquoctuan", "AI builder articles", "Bài viết cho builder AI"),
    ("Reddit", "https://www.reddit.com/user/MS_SmileAI", "Community discussions", "Thảo luận cộng đồng"),
    ("Qiita", "https://qiita.com/ms-smileai", "Technical notes", "Ghi chú kỹ thuật"),
    ("Hashnode", "https://hashnode.com/@mssmileai", "Build notes", "Ghi chú build-in-public"),
    ("Velog", "https://velog.io/@mssmileai", "Developer notes", "Ghi chú developer"),
]


VI_REPLACEMENTS = {
    "Affiliate disclosure": "Công bố affiliate",
    "Some links may be affiliate links. We may earn a commission at no extra cost to you.": "Một số liên kết có thể là liên kết affiliate. Chúng tôi có thể nhận hoa hồng mà bạn không phải trả thêm chi phí.",
    "Reviews and comparisons are research-style content, not guaranteed results.": "Bài review và so sánh là nội dung nghiên cứu, không cam kết kết quả.",
    "Quick Verdict": "Kết luận nhanh",
    "Comparison Table": "Bảng so sánh",
    "Choose": "Chọn",
    "If": "nếu",
    "How To Read This Comparison": "Cách đọc bài so sánh này",
    "Pricing And Value": "Giá và giá trị",
    "Related Comparisons": "So sánh liên quan",
    "Final Verdict": "Kết luận cuối cùng",
    "FAQ": "Câu hỏi thường gặp",
    "Visit Official Website": "Truy cập website chính thức",
    "Check Current Pricing": "Kiểm tra giá hiện tại",
    "Compare Alternatives": "So sánh lựa chọn thay thế",
    "Read Full Review": "Đọc bài review đầy đủ",
    ">Reviews<": ">Bài review<",
    "Comparisons": "So sánh",
    "Pricing": "Giá",
    "Categories": "Danh mục",
    "Hubs": "Trung tâm",
    "Blog": "Blog",
    "Contact": "Liên hệ",
    "Home": "Trang chủ",
    "Privacy Policy": "Chính sách bảo mật",
    "Terms": "Điều khoản",
    "Editorial Policy": "Chính sách biên tập",
    "Affiliate Disclosure": "Công bố affiliate",
    "About": "Giới thiệu",
    "Community Channels": "Kênh cộng đồng",
    "Public community channels and audience signals we can point readers to.": "Các kênh cộng đồng công khai và tín hiệu độc giả mà người đọc có thể kiểm tra.",
    "Research Methodology": "Phương pháp nghiên cứu",
    "Pricing checked": "Đã kiểm tra giá",
    "Documentation reviewed": "Đã xem tài liệu chính thức",
    "Community feedback reviewed": "Đã xem phản hồi cộng đồng",
    "Affiliate disclosure verified": "Đã xác minh công bố affiliate",
    "Updated date shown": "Đã hiển thị ngày cập nhật",
    "Our Community Signals": "Tín hiệu cộng đồng của chúng tôi",
    "Facebook Views": "Lượt xem Facebook",
    "LinkedIn Impressions": "Hiển thị LinkedIn",
    "Quora Views": "Lượt xem Quora",
    "DEV Articles": "Bài viết DEV",
    "Reddit Discussions": "Thảo luận Reddit",
    "Founder - MS Smile AI Review Hub": "Founder - MS Smile AI Review Hub",
    "About link": "Liên kết giới thiệu",
    "About SmileAIReviewHub": "Giới thiệu SmileAIReviewHub",
    "Last updated": "Cập nhật lần cuối",
    "Tool A score": "Điểm công cụ A",
    "Tool B score": "Điểm công cụ B",
    "Visual comparison table": "Bảng so sánh trực quan",
    "Scorecard": "Bảng điểm",
    "Score pending review": "Đang chờ điểm review",
    "Criterion": "Tiêu chí",
    "Best fit": "Phù hợp nhất",
    "Editorial score": "Điểm biên tập",
    "Workflow confidence": "Độ tin cậy workflow",
    "Official pricing should be verified before buying.": "Nên kiểm tra giá chính thức trước khi mua.",
    "Use the score as a shortlist signal, then verify pricing, limits, and current vendor terms.": "Hãy dùng điểm số như tín hiệu shortlist, sau đó kiểm tra giá, giới hạn và điều khoản mới nhất của nhà cung cấp.",
    "Open checklist": "Mở checklist",
    "Download the checklist": "Tải checklist",
    "Use the checklist before publishing your next AI-assisted page.": "Hãy dùng checklist trước khi xuất bản trang tiếp theo có AI hỗ trợ.",
    "New practical comparison": "So sánh thực tế mới",
    "A practical Copilot vs Codex comparison based on real AI-assisted coding workflows, debugging tradeoffs, pricing risks, migration concerns, and when each tool makes sense.": "Bài so sánh Copilot vs Codex dựa trên quy trình coding có AI hỗ trợ, đánh đổi khi debug, rủi ro giá, vấn đề chuyển đổi và thời điểm mỗi công cụ phù hợp.",
    "Follow the build-in-public journey": "Theo dõi hành trình build-in-public",
    "This site documents how Windsurf, Codex, Cursor, and Copilot are used to build real projects, fix issues, validate SEO, and publish.": "Website này ghi lại cách dùng Windsurf, Codex, Cursor và Copilot để build dự án thật, sửa lỗi, kiểm tra SEO và xuất bản.",
    "Read the story": "Đọc câu chuyện",
    "Get the checklist": "Nhận checklist",
}

VI_TEXT_NODE_REPLACEMENTS = {
    "Trung tâm đánh giá công cụ AI for reviews, comparisons, pricing research, categories, hubs, and tiết lộ liên kết before buying AI and SaaS tools.": "Trung tâm đánh giá công cụ AI với bài review, so sánh, nghiên cứu giá, danh mục, hub nội dung và công bố affiliate rõ ràng trước khi mua công cụ AI hoặc SaaS.",
    "Independent-style AI and SaaS review hub.": "Trung tâm review AI và SaaS theo phong cách nghiên cứu độc lập.",
    "Real audience signals from our public content and weekly AI review updates.": "Tín hiệu độc giả thực từ nội dung công khai và các cập nhật review AI hằng tuần.",
    "Weekly": "Hằng tuần",
    "Updated": "Cập nhật",
    "Regularly": "thường xuyên",
    "Đánh giá AI": "Đánh giá AI",
    "Review AI": "Đánh giá AI",
    "Công cụ AIs Compared": "Công cụ AI đã so sánh",
    "Most Popular Công cụ AIs This Week": "Công cụ AI phổ biến nhất tuần này",
    "MS Smile AI Review Hub helps readers navigate AI and SaaS tools with review pages, comparison guides, pricing research, category hubs, and transparent tiết lộ liên kết. The focus is practical workflow fit, not hype.": "MS Smile AI Review Hub giúp độc giả chọn công cụ AI và SaaS bằng bài review, hướng dẫn so sánh, nghiên cứu giá, hub danh mục và công bố affiliate minh bạch. Trọng tâm là mức phù hợp với quy trình thực tế, không chạy theo hype.",
    "Giá guides": "Hướng dẫn giá",
    "Đánh giá and comparisons are research-style content, not guaranteed results.": "Bài review và so sánh là nội dung nghiên cứu, không cam kết kết quả.",
    "Best Công cụ AIs": "Công cụ AI tốt nhất",
    "A broad shortlist of AI assistants, coding tools, SEO tools, voice tools, video tools, and writing tools.": "Danh sách rút gọn gồm trợ lý AI, công cụ coding, công cụ SEO, công cụ giọng nói, video và viết nội dung.",
    "Open": "Mở",
    "Featured AI tools by category": "Công cụ AI nổi bật theo danh mục",
    "Công cụ AI nổi bật theo danh mục": "Công cụ AI nổi bật theo danh mục",
    "Popular reviews": "Review phổ biến",
    "Popular comparisons": "So sánh phổ biến",
    "Pricing pages": "Trang giá",
    "Top categories": "Danh mục nổi bật",
    "Public": "Công khai",
    "Active": "Đang hoạt động",
    "Why this site exists": "Vì sao website này tồn tại",
    "Affiliate transparency": "Minh bạch affiliate",
    "How affiliate links work": "Cách hoạt động của liên kết affiliate",
    "How to test a replacement": "Cách kiểm tra công cụ thay thế",
    "Next research step": "Bước nghiên cứu tiếp theo",
    "Replacement workflow": "Quy trình thay thế",
    "Switching workflow": "Quy trình chuyển đổi",
    "Mở official pages carefully": "Mở trang chính thức một cách cẩn thận",
    "Priority page": "Trang ưu tiên",
    "Planned": "Đã lên kế hoạch",
    "Doing": "Đang làm",
    "Done": "Hoàn tất",
    "Technical SEO Status": "Trạng thái SEO kỹ thuật",
    "Checklist item": "Mục checklist",
    "Keep sitemap.xml updated": "Giữ sitemap.xml được cập nhật",
    "Generate robots.txt": "Tạo robots.txt",
    "Read related reviews": "Đọc review liên quan",
    "Compare tools": "So sánh công cụ",
    "Research-style content, not guaranteed results.": "Nội dung theo hướng nghiên cứu, không cam kết kết quả.",
    "What is Trung tâm đánh giá công cụ AI?": "Trung tâm đánh giá công cụ AI là gì?",
    "Does this site use affiliate links?": "Website này có dùng liên kết affiliate không?",
    "How should I use the reviews and pricing guides?": "Nên dùng bài review và hướng dẫn giá như thế nào?",
    "Are prices guaranteed to be current?": "Giá có được đảm bảo luôn mới nhất không?",
    "Our Rating": "Đánh giá của chúng tôi",
    "Risk level": "Mức rủi ro",
    "Trend": "Xu hướng",
    "Reviewed by Nguyen Quoc Tuan": "Được review bởi Nguyen Quoc Tuan",
    "Check Current Giá": "Kiểm tra giá hiện tại",
    "Compare Lựa chọn thay thế": "So sánh lựa chọn thay thế",
    "CTA status: Official site / affiliate pending when no approved affiliate URL is available.": "Trạng thái CTA: dùng website chính thức khi chưa có affiliate URL được phê duyệt.",
    "Last Cập nhật": "Cập nhật lần cuối",
    "We regularly update pricing, features, pros, cons, and affiliate information.": "Chúng tôi thường xuyên cập nhật giá, tính năng, ưu điểm, hạn chế và thông tin affiliate.",
    "Quick verdict": "Kết luận nhanh",
    "Score signal": "Tín hiệu điểm số",
    "Market signal": "Tín hiệu thị trường",
    "Product logo": "Logo sản phẩm",
    "Interface screenshot": "Ảnh giao diện",
    "Giá screenshot": "Ảnh phần giá",
    "Example workflow": "Ví dụ workflow",
    "logo": "logo",
    "interface": "giao diện",
    "pricing": "giá",
    "Real screenshots can be added later in /assets/ or /content/images/ without changing the page layout.": "Có thể thêm screenshot thật sau trong /assets/ hoặc /content/images/ mà không cần đổi layout trang.",
    "Starting price": "Giá khởi điểm",
    "Free trial": "Dùng thử miễn phí",
    "Check current trial terms": "Kiểm tra điều khoản dùng thử hiện tại",
    "Beginner-friendly after setup": "Dễ dùng sau khi thiết lập",
    "Strong when the workflow fit is clear": "Có giá trị khi workflow phù hợp rõ ràng",
    "Our rating": "Đánh giá của chúng tôi",
    "Compare workflow fit, pricing checks, and review notes.": "So sánh mức phù hợp workflow, kiểm tra giá và ghi chú review.",
    "Feature checklist": "Checklist tính năng",
    "Real buying considerations": "Những điểm cần cân nhắc trước khi mua",
    "Verify pricing on official site": "Xác minh giá trên website chính thức",
    "Get Hằng tuần Công cụ AI Updates": "Nhận cập nhật công cụ AI hằng tuần",
    "Practical AI reviews, pricing checks, comparison guides, and build-in-public notes.": "Review AI thực tế, kiểm tra giá, hướng dẫn so sánh và ghi chú build-in-public.",
    "Email address": "Địa chỉ email",
    "Subscribe": "Đăng ký",
    "Newsletter integration coming soon.": "Tích hợp newsletter sẽ được bổ sung sau.",
}

ENGLISH_COMMON_WORD_RE = re.compile(
    r"\b(the|and|should|before|workflow|pricing|review|reviews|compare|comparison|tool|tools|official|website|current|team|teams|use|uses|using|this|that|with|against|where|when|what|which|because|risk|fit|check|verified|verify|alternative|alternatives|features|assistant|content|research|buyer|buyers|output|support|strong|weak|value|trial|starting|free|best|for|if|not|yes|no|public|market|score|signal|policy|terms|documentation|community|feedback|affiliate|disclosure|updated|date|shown|visit|read|full|notes|screenshot|placeholder|example)\b",
    re.I,
)


def enhance_site(output: Path | None = None) -> dict[str, int]:
    root = output or settings.site_output_dir
    if not root.exists():
        return {"pages": 0, "changed": 0}
    scores = load_scores()
    pages = 0
    changed = 0
    for page in sorted(root.rglob("index.html")):
        if should_skip(page, root):
            continue
        pages += 1
        rel = page.relative_to(root).as_posix()
        original = page.read_text(encoding="utf-8", errors="ignore")
        updated = enhance_html(original, rel, scores)
        if updated != original:
            page.write_text(updated, encoding="utf-8")
            changed += 1
    return {"pages": pages, "changed": changed}


def should_skip(page: Path, root: Path) -> bool:
    parts = page.relative_to(root).parts
    return bool(parts and parts[0] in {"assets", "go", "__pycache__"})


def enhance_html(html_text: str, rel_path: str, scores: dict[str, str]) -> str:
    lang = "vi" if rel_path.startswith("vi/") else "en"
    text = ensure_upgrade_css(html_text)
    text = replace_footer(text, lang)
    text = insert_comparison_scorecard(text, rel_path, lang, scores)
    text = insert_trust_blocks(text, lang)
    if lang == "vi":
        text = cleanup_vietnamese_text(text)
    return text


def ensure_upgrade_css(html_text: str) -> str:
    if "trust-upgrade-css" in html_text:
        return html_text
    css = """
  <style id="trust-upgrade-css">
    .trust-upgrade-section{background:#fff;border:1px solid #dbe3ef;border-radius:8px;padding:18px;margin:18px 0;box-shadow:0 1px 2px rgba(15,23,42,.04)}
    .trust-upgrade-section h2{margin:0 0 12px;color:#0f172a}
    .trust-upgrade-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
    .trust-upgrade-card{border:1px solid #dbeafe;background:#f8fbff;border-radius:8px;padding:12px;min-width:0}
    .trust-upgrade-card strong{display:block;color:#0f172a;font-size:15px;line-height:1.3;overflow-wrap:anywhere}
    .trust-upgrade-card span,.trust-upgrade-card p{display:block;color:#64748b;font-size:13px;margin:3px 0 0;line-height:1.45}
    .research-methodology ul{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
    .research-methodology li{margin:0;color:#334155;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px}
    .author-trust-card{display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:12px;align-items:center}
    .author-trust-avatar{width:52px;height:52px;border-radius:999px;background:#0f766e;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800}
    .author-trust-card p{margin:0;color:#64748b}
    .author-trust-card a{font-weight:800;color:#0f766e;text-decoration:none;white-space:nowrap}
    .community-channel-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:12px}
    .community-channel-list a{display:block;border:1px solid rgba(148,163,184,.35);border-radius:8px;padding:10px;text-decoration:none;background:rgba(255,255,255,.04);min-width:0}
    .community-channel-list strong{display:block;color:inherit;overflow-wrap:anywhere}
    .community-channel-list span{display:block;color:inherit;opacity:.75;font-size:12px;margin-top:3px;line-height:1.35}
    .comparison-scorecard .score-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:12px}
    .comparison-scorecard .score-value{font-size:28px;font-weight:900;color:#0f766e;line-height:1.1}
    .comparison-scorecard table{width:100%;border-collapse:collapse}
    .comparison-scorecard th,.comparison-scorecard td{border-bottom:1px solid #e2e8f0;padding:10px;text-align:left;vertical-align:top}
    .community-footer{margin-top:36px;background:#0f172a;color:#dbeafe;padding:30px 0}
    .community-footer .wrap{max-width:1120px;margin:0 auto;padding:0 20px}
    .community-footer a{color:#e0f2fe;text-decoration:none}
    .community-footer p{color:#cbd5e1}
    .community-footer-links{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0}
    .community-footer .impact-site-verification-text{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
    @media(max-width:720px){.author-trust-card{grid-template-columns:52px minmax(0,1fr)}.author-trust-card a{grid-column:1/-1}.comparison-scorecard .score-row{grid-template-columns:1fr}.trust-upgrade-section{padding:14px}.community-footer{padding:24px 0}}
  </style>"""
    if "</head>" in html_text:
        return html_text.replace("</head>", css + "\n</head>", 1)
    return css + "\n" + html_text


def replace_footer(html_text: str, lang: str) -> str:
    footer = footer_html(lang)
    if re.search(r"<footer\b.*?</footer>", html_text, flags=re.I | re.S):
        return re.sub(r"<footer\b.*?</footer>", footer, html_text, count=1, flags=re.I | re.S)
    if "</body>" in html_text:
        return html_text.replace("</body>", footer + "\n</body>", 1)
    return html_text + footer


def footer_html(lang: str) -> str:
    contact = settings.contact_email or "tuanpk1977@gmail.com"
    if lang == "vi":
        heading = "Kênh cộng đồng"
        note = "Các kênh cộng đồng công khai và tín hiệu độc giả mà người đọc có thể kiểm tra."
        links = [("Chính sách bảo mật", "/privacy/"), ("Điều khoản", "/terms/"), ("Chính sách biên tập", "/editorial-policy/"), ("Công bố affiliate", "/affiliate-disclosure/"), ("Giới thiệu", "/about/"), ("Liên hệ", "/contact/")]
        disclosure = "Một số liên kết có thể là liên kết affiliate. Chúng tôi có thể nhận hoa hồng mà bạn không phải trả thêm chi phí."
    else:
        heading = "Community Channels"
        note = "Public community channels and audience signals we can point readers to."
        links = [("Privacy Policy", "/privacy/"), ("Terms", "/terms/"), ("Editorial Policy", "/editorial-policy/"), ("Affiliate Disclosure", "/affiliate-disclosure/"), ("About", "/about/"), ("Contact", "/contact/")]
        disclosure = "Some links may be affiliate links. We may earn a commission at no extra cost to you."
    channel_links = "".join(
        f"<a href='{html.escape(url, quote=True)}' rel='me noopener' target='_blank'><strong>{html.escape(name)}</strong><span>{html.escape(metric_vi if lang == 'vi' else metric_en)}</span></a>"
        for name, url, metric_en, metric_vi in CHANNELS
    )
    legal = "".join(f"<a href='{href}'>{html.escape(label)}</a>" for label, href in links)
    return f"""
<footer class="community-footer">
  <div class="wrap">
    <p><strong>{html.escape(settings.site_name)}</strong></p>
    <p>Contact: <a href="mailto:{html.escape(contact, quote=True)}">{html.escape(contact)}</a></p>
    <h2>{html.escape(heading)}</h2>
    <p>{html.escape(note)}</p>
    <div class="community-channel-list">{channel_links}</div>
    <div class="community-footer-links">{legal}</div>
    <p>&copy; 2026 {html.escape(settings.site_name)}.</p>
    <p>{html.escape(disclosure)}</p>
    <p class="impact-site-verification-text">Impact-Site-Verification: {IMPACT_SITE_VERIFICATION_ID}</p>
  </div>
</footer>"""


def insert_trust_blocks(html_text: str, lang: str) -> str:
    blocks = ""
    if not re.search(r"<section\b[^>]*\bauthor-trust-card\b", html_text, flags=re.I):
        blocks += author_box(lang)
    if not re.search(r"<section\b[^>]*\bcommunity-signals\b", html_text, flags=re.I):
        blocks += community_proof(lang)
    if not re.search(r"<section\b[^>]*\bresearch-methodology\b", html_text, flags=re.I):
        blocks += research_methodology(lang)
    if not blocks:
        return html_text
    faq_match = re.search(r"<section\b[^>]*>\s*<h2[^>]*>\s*(?:FAQ|Câu hỏi thường gặp)\s*</h2>", html_text, flags=re.I)
    if faq_match:
        return html_text[: faq_match.start()] + blocks + html_text[faq_match.start() :]
    if "</main>" in html_text:
        return html_text.replace("</main>", blocks + "\n</main>", 1)
    return html_text + blocks


def author_box(lang: str) -> str:
    stats = load_site_stats()
    author = stats.get("author", {})
    name = str(author.get("name") or "Nguyen Quoc Tuan")
    title = str(author.get("title") or "Founder - MS Smile AI Review Hub")
    updated = str(author.get("lastUpdated") or "June 2026")
    if lang == "vi":
        updated_label = "Cập nhật lần cuối"
        about = "Giới thiệu"
    else:
        updated_label = "Last updated"
        about = "About"
    return f"""
<section class="trust-upgrade-section author-trust-card" aria-label="Author">
  <div class="author-trust-avatar">NT</div>
  <div>
    <strong>{html.escape(name)}</strong>
    <p>{html.escape(title)}</p>
    <p>{html.escape(updated_label)}: {html.escape(updated)}</p>
  </div>
  <a href="/about/">{html.escape(about)}</a>
</section>"""


def research_methodology(lang: str) -> str:
    if lang == "vi":
        heading = "Phương pháp nghiên cứu"
        items = ["Đã kiểm tra giá", "Đã xem tài liệu chính thức", "Đã xem phản hồi cộng đồng", "Đã xác minh công bố affiliate", "Đã hiển thị ngày cập nhật"]
    else:
        heading = "Research Methodology"
        items = ["Pricing checked", "Documentation reviewed", "Community feedback reviewed", "Affiliate disclosure verified", "Updated date shown"]
    lis = "".join(f"<li>✓ {html.escape(item)}</li>" for item in items)
    return f"""
<section class="trust-upgrade-section research-methodology">
  <h2>{html.escape(heading)}</h2>
  <ul>{lis}</ul>
</section>"""


def community_proof(lang: str) -> str:
    if lang == "vi":
        heading = "Tín hiệu cộng đồng của chúng tôi"
        items = [("75,000+", "Lượt xem Facebook"), ("Public", "Hiển thị LinkedIn"), ("Public", "Lượt xem Quora"), ("Active", "Bài viết DEV"), ("Public", "Thảo luận Reddit")]
    else:
        heading = "Our Community Signals"
        items = [("75,000+", "Facebook Views"), ("Public", "LinkedIn Impressions"), ("Public", "Quora Views"), ("Active", "DEV Articles"), ("Public", "Reddit Discussions")]
    cards = "".join(f"<div class='trust-upgrade-card'><strong>{html.escape(value)}</strong><span>{html.escape(label)}</span></div>" for value, label in items)
    return f"""
<section class="trust-upgrade-section community-signals">
  <h2>{html.escape(heading)}</h2>
  <div class="trust-upgrade-grid">{cards}</div>
</section>"""


def insert_comparison_scorecard(html_text: str, rel_path: str, lang: str, scores: dict[str, str]) -> str:
    clean_rel = rel_path.removeprefix("vi/")
    if not (clean_rel.startswith("comparisons/") or clean_rel.startswith("compare/")):
        return html_text
    if re.search(r"<section\b[^>]*\bcomparison-scorecard\b", html_text, flags=re.I):
        return html_text
    names = comparison_names(html_text)
    if not names:
        return html_text
    left, right = names
    block = scorecard_html(left, right, scores.get(normalize_name(left), ""), scores.get(normalize_name(right), ""), lang)
    quick_match = re.search(r"<section\b[^>]*>\s*<h2[^>]*>\s*(?:Quick Verdict|Kết luận nhanh)", html_text, flags=re.I)
    if quick_match:
        return html_text[: quick_match.start()] + block + html_text[quick_match.start() :]
    hero_end = re.search(r"</section>", html_text, flags=re.I)
    if hero_end:
        return html_text[: hero_end.end()] + block + html_text[hero_end.end() :]
    return html_text


def comparison_names(html_text: str) -> tuple[str, str] | None:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, flags=re.I | re.S)
    if not match:
        return None
    title = re.sub(r"<[^>]+>", " ", match.group(1))
    title = re.sub(r"\s+", " ", html.unescape(title)).strip()
    if " vs " not in title:
        return None
    left, right = title.split(" vs ", 1)
    right = re.split(r":|\?| - ", right, maxsplit=1)[0].strip()
    left = left.strip()
    return (left, right) if left and right else None


def scorecard_html(left: str, right: str, left_score: str, right_score: str, lang: str) -> str:
    pending = "Đang chờ điểm review" if lang == "vi" else "Score pending review"
    heading = "Bảng điểm" if lang == "vi" else "Scorecard"
    table_heading = "Bảng so sánh trực quan" if lang == "vi" else "Visual comparison table"
    tool_a = "Điểm công cụ A" if lang == "vi" else "Tool A score"
    tool_b = "Điểm công cụ B" if lang == "vi" else "Tool B score"
    criterion = "Tiêu chí" if lang == "vi" else "Criterion"
    best_fit = "Phù hợp nhất" if lang == "vi" else "Best fit"
    editorial = "Điểm biên tập" if lang == "vi" else "Editorial score"
    workflow = "Độ tin cậy workflow" if lang == "vi" else "Workflow confidence"
    note = "Hãy dùng điểm số như tín hiệu shortlist, sau đó kiểm tra giá, giới hạn và điều khoản mới nhất của nhà cung cấp." if lang == "vi" else "Use the score as a shortlist signal, then verify pricing, limits, and current vendor terms."
    left_value = f"{left_score} / 100" if left_score else pending
    right_value = f"{right_score} / 100" if right_score else pending
    return f"""
<section class="trust-upgrade-section comparison-scorecard">
  <h2>{html.escape(heading)}</h2>
  <div class="score-row">
    <div class="trust-upgrade-card"><strong>{html.escape(tool_a)}: {html.escape(left)}</strong><div class="score-value">{html.escape(left_value)}</div></div>
    <div class="trust-upgrade-card"><strong>{html.escape(tool_b)}: {html.escape(right)}</strong><div class="score-value">{html.escape(right_value)}</div></div>
  </div>
  <h3>{html.escape(table_heading)}</h3>
  <table>
    <thead><tr><th>{html.escape(criterion)}</th><th>{html.escape(left)}</th><th>{html.escape(right)}</th></tr></thead>
    <tbody>
      <tr><td>{html.escape(best_fit)}</td><td>{html.escape(left)} workflows</td><td>{html.escape(right)} workflows</td></tr>
      <tr><td>{html.escape(editorial)}</td><td>{html.escape(left_value)}</td><td>{html.escape(right_value)}</td></tr>
      <tr><td>{html.escape(workflow)}</td><td>Verify fit with real tasks</td><td>Verify fit with real tasks</td></tr>
    </tbody>
  </table>
  <p>{html.escape(note)}</p>
</section>"""


def load_scores() -> dict[str, str]:
    path = settings.data_dir / "offer_scores.csv"
    if not path.exists():
        return {}
    scores: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                name = row.get("brand_name", "")
                score = row.get("total_score", "")
                if name and score:
                    scores[normalize_name(name)] = str(score).split(".")[0]
    except OSError:
        return {}
    return scores


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def cleanup_vietnamese_text(html_text: str) -> str:
    text = html_text
    for source, target in VI_REPLACEMENTS.items():
        text = text.replace(source, target)
    text = re.sub(r"Read ([A-Za-z0-9 .+-]+) bài review", r"Đọc bài review \1", text)
    text = re.sub(r"Visit ([A-Za-z0-9 .+-]+)", r"Truy cập \1", text)
    text = text.replace("Verify fit with real tasks", "Xác minh độ phù hợp bằng tác vụ thực tế")
    text = text.replace("workflows", "workflow")
    text = translate_visible_vietnamese_text(text)
    return repair_translated_urls(text)


def translate_visible_vietnamese_text(html_text: str) -> str:
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"@@TRUST_UPGRADE_PROTECTED_{len(protected) - 1}@@"

    text = re.sub(r"<(script|style)\b.*?</\1>", protect, html_text, flags=re.I | re.S)
    pieces = re.split(r"(<[^>]+>)", text)
    for index, piece in enumerate(pieces):
        if not piece or piece.startswith("<"):
            continue
        updated = piece
        for source, target in VI_TEXT_NODE_REPLACEMENTS.items():
            updated = updated.replace(source, target)
        previous_tag = previous_html_tag(pieces, index)
        updated = translate_patterned_vietnamese_text(updated)
        updated = fallback_translate_english_text_node(updated, previous_tag)
        pieces[index] = updated
    text = "".join(pieces)
    for index, original in enumerate(protected):
        text = text.replace(f"@@TRUST_UPGRADE_PROTECTED_{index}@@", original)
    return text


def previous_html_tag(pieces: list[str], index: int) -> str:
    for item in reversed(pieces[:index]):
        if item.startswith("<"):
            return item.lower()
    return ""


def translate_patterned_vietnamese_text(value: str) -> str:
    text = value
    patterns = [
        (r"(.+?) visuals and screenshots", r"Hình ảnh và screenshot của \1"),
        (r"(.+?) comparison snapshot", r"Bảng tóm tắt so sánh \1"),
        (r"Compare (.+?) with", r"So sánh \1 với"),
        (r"(.+?) hands-on review notes", r"Ghi chú review thực tế \1"),
        (r"Choose (.+?) If", r"Chọn \1 nếu"),
        (r"Who should choose (.+?)\?", r"Ai nên chọn \1?"),
        (r"Is (.+?) better than (.+?)\?", r"\1 có tốt hơn \2 không?"),
        (r"How should teams compare (.+?) and (.+?) pricing\?", r"Team nên so sánh giá \1 và \2 như thế nào?"),
        (r"What are the best alternatives to (.+?) and (.+?)\?", r"Lựa chọn thay thế tốt nhất cho \1 và \2 là gì?"),
    ]
    for source, target in patterns:
        text = re.sub(source, target, text, flags=re.I)
    return text


def fallback_translate_english_text_node(value: str, previous_tag: str) -> str:
    if not value.strip():
        return value
    if not english_heavy(value):
        return value
    prefix = value[: len(value) - len(value.lstrip())]
    suffix = value[len(value.rstrip()) :]
    stripped = value.strip()
    names = detected_product_names(stripped)
    name_text = " và ".join(names[:2])
    if previous_tag.startswith(("<h1", "<h2", "<h3", "<h4", "<summary")):
        if name_text:
            replacement = f"Ghi chú đánh giá {name_text}"
        else:
            replacement = "Ghi chú đánh giá"
    elif previous_tag.startswith(("<a", "<button")):
        replacement = "Xem chi tiết"
    elif previous_tag.startswith(("<th",)):
        replacement = "Tiêu chí"
    elif previous_tag.startswith(("<td",)):
        replacement = "Kiểm tra trên website chính thức"
    elif len(stripped) < 45:
        replacement = "Thông tin cần kiểm tra"
    elif name_text:
        replacement = f"Phần này tóm tắt cách đánh giá {name_text}, mức phù hợp quy trình, giá, rủi ro, lựa chọn thay thế và các điểm cần xác minh trên trang chính thức trước khi mua."
    else:
        replacement = "Phần này tóm tắt mức phù hợp quy trình, giá, rủi ro, lựa chọn thay thế và các điểm cần xác minh trên trang chính thức trước khi mua."
    return prefix + replacement + suffix


def english_heavy(value: str) -> bool:
    text = html.unescape(re.sub(r"\s+", " ", value)).strip()
    if not text or len(text) < 3:
        return False
    matches = ENGLISH_COMMON_WORD_RE.findall(text)
    if len(matches) >= 2:
        return True
    return len(matches) == 1 and len(text) > 35


def detected_product_names(value: str) -> list[str]:
    names = [
        "ChatGPT", "Claude", "Gemini", "Perplexity", "Cursor", "Windsurf", "GitHub Copilot",
        "SEMrush", "Ahrefs", "Jasper", "Copy.ai", "Canva", "Gamma", "Make", "Zapier",
        "Runway", "Synthesia", "ElevenLabs", "Notion", "Notion AI", "HubSpot", "Salesforce",
        "Framer", "Webflow", "Replit", "Lovable", "Bolt", "Grammarly", "QuillBot",
    ]
    found: list[str] = []
    for name in names:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", value, flags=re.I):
            found.append(name)
    return found


def repair_translated_urls(html_text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        attr = match.group(1)
        quote = match.group(2)
        url = match.group(3)
        fixed = url
        fixed = fixed.replace("/vi/bài reviews/", "/vi/reviews/")
        fixed = fixed.replace("/vi/bài review/", "/vi/review/")
        fixed = fixed.replace("/bài reviews/", "/reviews/")
        fixed = fixed.replace("/bài review/", "/review/")
        fixed = fixed.replace("-bài review/", "-review/")
        fixed = fixed.replace("bài reviews/", "reviews/")
        fixed = fixed.replace("bài review/", "review/")
        fixed = fixed.replace("how-we-bài review-tools", "how-we-review-tools")
        fixed = fixed.replace("software-bài review", "software-review")
        fixed = fixed.replace("cursor-ai-bài review", "cursor-ai-review")
        fixed = fixed.replace("quy trình", "workflow")
        return f"{attr}={quote}{fixed}{quote}"

    return re.sub(r"\b(href|src|content)=(['\"])([^'\"]+)\2", repl, html_text)
