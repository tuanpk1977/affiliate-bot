from __future__ import annotations

import html
import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

from config import settings
from modules.affiliate_tracking import generate_go_pages, rewrite_outbound_ctas
from modules.blog_article_data import SUPPORTING_BLOG_ARTICLES, SUPPORTING_BLOG_RELATED
from modules.category_page_builder import generate_category_pages
from modules.comparison_page_builder import generate_comparison_review_pages
from modules.comparison_generator import generate_comparison_pages
from modules.hub_page_builder import generate_hub_pages
from modules.internal_linker import post_process_internal_links
from modules.intent_page_generator import generate_intent_pages
from modules.money_content_builder import generate_money_content_pages
from modules.priority_page_builder import generate_priority_pages
from modules.pricing_page_builder import generate_pricing_pages
from modules.review_page_builder import generate_review_pages
from modules.seo_expansion_pages import generate_seo_expansion_pages
from modules.sitemap_generator import generate_sitemap
from modules.sitemap_generator import NOINDEX_EXACT_PATHS
from modules.toplist_generator import generate_toplist_pages
from modules.tracking_config import analytics_snippet


FAQ_SCHEMA_DISABLED_PATHS = {
    "/comparisons/framer-vs-webflow/",
    "/vi/comparisons/framer-vs-webflow/",
}

LEGAL_SLUGS = ["privacy-policy", "terms", "contact", "affiliate-disclosure"]
CONTENT_SLUGS = [
    "reviews",
    "comparisons",
    "about",
    "about-author",
    "author-profile",
    "editorial-policy",
    "how-we-review-tools",
    "testing-methodology",
]
CATEGORY_SLUGS = [
    "category/ai-video-tools",
    "category/ai-voice-tools",
    "category/ai-coding-tools",
    "category/ai-seo-tools",
    "category/ai-automation-tools",
    "category/crm-tools",
    "category/website-builders",
    "category/ai-presentation-tools",
    "category/ai-writing-tools",
    "category/ai-customer-support-tools",
    "category/ai-writing",
    "category/automation",
    "category/crm",
    "category/seo-tools",
    "category/email-marketing-tools",
    "category/automation-tools",
    "category/design-tools",
    "category/video-tools",
    "category/writing-tools",
    "category/website-builder-tools",
]
COMPARISON_SLUGS = [
    "comparisons/chatgpt-vs-gemini",
    "comparisons/chatgpt-vs-claude",
    "comparisons/cursor-vs-windsurf",
    "comparisons/cursor-vs-vscode",
    "comparisons/make-vs-zapier",
    "comparisons/notion-vs-clickup",
    "comparisons/elevenlabs-vs-playht",
    "comparisons/hubspot-vs-salesforce",
    "comparisons/semrush-vs-ahrefs",
    "comparisons/canva-vs-gamma",
    "comparisons/jasper-vs-copyai",
    "comparisons/runway-vs-pika",
    "comparisons/synthesia-vs-heygen",
    "comparisons/synthesia-vs-runway",
    "comparisons/copilot-vs-tabnine",
    "comparisons/perplexity-vs-chatgpt",
    "comparisons/gemini-vs-claude",
    "comparisons/midjourney-vs-dalle",
    "comparisons/notion-ai-vs-chatgpt",
    "comparisons/elevenlabs-vs-murf",
    "comparisons/framer-vs-webflow",
    "comparisons/copilot-vs-cursor",
]
EXTRA_SLUGS = ["blog", "sitemap", "media-kit", "aeo-action-plan"]

NAV_INDEX_SLUGS = ["reviews", "comparisons", "pricing", "categories", "hubs"]


BLOG_POSTS = [
    ("chatgpt-windsurf-codex-workflow", "ChatGPT Windsurf Codex Workflow", "My real AI building process using ChatGPT for thinking and prompts, Windsurf for the first build, and Codex for debugging, refactoring, and polishing."),
    ("chatgpt-prompts-for-windsurf", "ChatGPT Prompts for Windsurf", "How I use ChatGPT to turn a rough project idea into clearer Windsurf prompts before building, testing, and sending focused fixes to Codex."),
    ("windsurf-prompt-checklist", "Windsurf Prompt Checklist", "A practical checklist I use before sending a coding prompt to Windsurf, with examples for safer first builds."),
    ("fix-windsurf-mixed-language", "Fix Windsurf Mixed Language Issues", "How I fix mixed English and Vietnamese UI or content when Windsurf generates static site pages."),
    ("windsurf-to-codex-workflow", "Windsurf to Codex Workflow", "My practical workflow for using Windsurf to build the first version, then Codex to repair, validate, and clean up the project."),
    ("best-ai-tools-for-small-business", "Best AI Tools for Small Business", "AI tools can help small teams document work, produce content, manage customers, and automate repetitive operations without hiring a large specialist team."),
    ("best-ai-presentation-tools", "Best AI Presentation Tools", "AI presentation tools help turn ideas, outlines, and research notes into clearer decks, pitch pages, and visual explanations."),
    ("best-ai-voice-generators", "Best AI Voice Generators", "AI voice generators are useful for creators and teams that need narration, learning content, and repeatable audio workflows."),
    ("ai-tools-for-marketers", "AI Tools for Marketers", "Marketing teams use AI tools to draft campaigns, create visuals, compare keywords, and speed up research while still reviewing every output."),
    ("ai-website-builders-comparison", "AI Website Builders Comparison", "AI website builders can reduce setup time, but the best choice depends on design control, CMS needs, hosting, and long-term maintenance."),
    ("best-crm-for-startups", "Best CRM for Startups", "Startup teams need CRM tools that keep sales follow-up organized without adding too much administrative friction."),
    ("ai-productivity-tools", "AI Productivity Tools", "AI productivity tools help teams plan tasks, schedule work, summarize information, and reduce manual coordination."),
    ("best-alternatives-to-canva-ai", "Best Alternatives to Canva AI", "Canva is broad and accessible, but some teams need alternatives for presentations, ads, websites, or more specialized creative workflows."),
    ("automation-tools-for-beginners", "Automation Tools for Beginners", "Beginner-friendly automation tools help connect apps, move data, and reduce repeated manual steps across business workflows."),
    ("ai-tools-for-content-creators", "AI Tools for Content Creators", "Content creators can use AI for planning, writing support, audio, visuals, repurposing, and workflow organization."),
    ("ai-tools-under-20-month", "AI Tools Under $20/month", "Low-cost AI tools can be useful for testing workflows before committing to larger SaaS subscriptions."),
    ("how-to-choose-saas-tools-safely", "How to Choose SaaS Tools Safely", "Choosing SaaS tools safely means checking pricing, terms, data policy, cancellation rules, support, and workflow fit before buying."),
]


COMPARISON_TOPICS = [
    ("chatgpt-vs-gemini", "ChatGPT", "Gemini", "AI chatbot", "ChatGPT mạnh ở viết, phân tích, hỗ trợ công việc tổng quát và hệ sinh thái công cụ.", "Gemini phù hợp khi bạn dùng nhiều sản phẩm Google và cần kết nối với hệ sinh thái Google.", "Chọn ChatGPT nếu bạn cần trợ lý AI tổng quát linh hoạt; chọn Gemini nếu workflow của bạn nằm nhiều trong Google Workspace."),
    ("chatgpt-vs-claude", "ChatGPT", "Claude", "AI assistant", "ChatGPT phù hợp cho nhiều tác vụ đa dạng, từ viết nội dung đến phân tích và workflow hằng ngày.", "Claude thường được cân nhắc khi cần xử lý văn bản dài, biên tập và lập luận cẩn thận.", "Chọn ChatGPT cho workflow đa năng; chọn Claude nếu ưu tiên đọc, tóm tắt và phân tích tài liệu dài."),
    ("cursor-vs-windsurf", "Cursor", "Windsurf", "AI coding tool", "Cursor là editor AI-first phù hợp cho lập trình viên muốn code cùng AI ngay trong môi trường làm việc.", "Windsurf phù hợp để so sánh nếu bạn muốn một trải nghiệm coding agent/editor khác.", "Chọn Cursor nếu bạn cần AI coding editor phổ biến; thử Windsurf nếu bạn muốn so sánh workflow agent coding mới hơn."),
    ("cursor-vs-vscode", "Cursor", "VS Code", "code editor", "Cursor tập trung vào trải nghiệm AI coding tích hợp sâu trong editor.", "VS Code là editor phổ biến, linh hoạt, có hệ sinh thái extension rất lớn.", "Chọn Cursor nếu AI là trung tâm workflow; chọn VS Code nếu bạn cần hệ sinh thái extension rộng và workflow quen thuộc."),
    ("make-vs-zapier", "Make", "Zapier", "automation platform", "Make mạnh ở workflow automation trực quan, nhiều nhánh logic và kiểm soát chi tiết.", "Zapier thường dễ bắt đầu hơn và có hệ sinh thái app rộng cho automation đơn giản.", "Chọn Make nếu workflow phức tạp; chọn Zapier nếu bạn cần automation nhanh, dễ triển khai."),
    ("notion-vs-clickup", "Notion", "ClickUp", "productivity workspace", "Notion mạnh ở knowledge base, tài liệu, wiki và workspace linh hoạt.", "ClickUp mạnh hơn khi trọng tâm là project management, task và vận hành nhóm.", "Chọn Notion cho tài liệu và knowledge base; chọn ClickUp cho quản lý dự án và task execution."),
    ("elevenlabs-vs-playht", "ElevenLabs", "PlayHT", "AI voice generator", "ElevenLabs được nhiều người cân nhắc cho giọng AI tự nhiên và workflow audio linh hoạt.", "PlayHT là lựa chọn đáng so sánh cho voiceover, narration và audio content.", "Chọn sau khi nghe thử voice mẫu, kiểm tra quyền sử dụng thương mại và pricing mới nhất."),
    ("elevenlabs-vs-murf", "ElevenLabs", "Murf", "AI voice generator", "ElevenLabs thường được cân nhắc cho voice chất lượng cao và use case creator/developer.", "Murf thường phù hợp với voiceover doanh nghiệp, presentation và training content.", "So sánh cả hai bằng voice quality, quyền sử dụng, ngôn ngữ hỗ trợ và chi phí thực tế."),
    ("hubspot-vs-salesforce", "HubSpot", "Salesforce", "CRM software", "HubSpot phù hợp với team muốn CRM, marketing và sales workflow dễ tiếp cận hơn.", "Salesforce phù hợp hơn với tổ chức lớn cần tùy biến sâu và quy trình enterprise.", "Chọn HubSpot cho SMB/growth team; chọn Salesforce nếu cần enterprise customization."),
    ("semrush-vs-ahrefs", "Semrush", "Ahrefs", "SEO platform", "Semrush là bộ SEO/marketing rộng, có keyword, competitor và content research.", "Ahrefs nổi bật ở backlink analysis, SEO research và kiểm tra cạnh tranh organic.", "Chọn dựa trên nhu cầu chính: marketing suite rộng hay SEO/backlink research sâu."),
    ("framer-vs-webflow", "Framer", "Webflow", "website builder", "Framer mạnh ở landing page hiện đại, thiết kế nhanh và visual publishing.", "Webflow mạnh ở CMS, cấu trúc website marketing và quyền kiểm soát thiết kế.", "Chọn Framer cho landing page/design tốc độ cao; chọn Webflow cho CMS và site dài hạn."),
    ("canva-vs-gamma", "Canva", "Gamma", "AI presentation/design tool", "Canva mạnh ở template design, social graphics và tài sản visual đa dạng.", "Gamma mạnh ở presentation/doc dạng kể chuyện, biến outline thành trang trình bày nhanh.", "Chọn Canva cho design rộng; chọn Gamma cho presentation và document-style storytelling."),
    ("jasper-vs-copyai", "Jasper", "Copy.ai", "AI writing tool", "Jasper thường phù hợp với marketing team cần brand voice và content workflow.", "Copy.ai thường được so sánh cho GTM, sales copy và workflow tạo nội dung nhanh.", "Chọn theo workflow nội dung, khả năng cộng tác, output quality và giá hiện tại."),
    ("runway-vs-pika", "Runway", "Pika", "AI video generator", "Runway mạnh ở AI video generation và creative editing workflow.", "Pika là lựa chọn đáng so sánh cho tạo video AI ngắn, ý tưởng nhanh và creative testing.", "Hãy test bằng cùng một prompt, kiểm tra chất lượng output, quyền sử dụng và chi phí."),
    ("synthesia-vs-heygen", "Synthesia", "HeyGen", "AI avatar video", "Synthesia thường được cân nhắc cho video doanh nghiệp, training và avatar workflow.", "HeyGen thường được so sánh cho avatar video, localization và creator/business video.", "Chọn dựa trên avatar quality, ngôn ngữ, quyền thương mại và workflow team."),
    ("synthesia-vs-runway", "Synthesia", "Runway", "AI video tool", "Synthesia is stronger when the job is structured avatar-led video for training, explainers, onboarding, and repeatable business messages.", "Runway is stronger when the job needs generative video experiments, creative editing, visual iteration, and short-form production tests.", "Choose Synthesia for presenter-style videos and product demos with a controlled script; choose Runway for creative generative video, visual exploration, and editing-heavy workflows."),
    ("copilot-vs-tabnine", "GitHub Copilot", "Tabnine", "AI coding assistant", "GitHub Copilot mạnh nhờ tích hợp hệ sinh thái GitHub và IDE phổ biến.", "Tabnine thường được cân nhắc khi team quan tâm đến coding assistant và kiểm soát môi trường.", "Chọn GitHub Copilot nếu team dùng GitHub sâu; so sánh Tabnine nếu cần tiêu chí privacy/deployment khác."),
    ("perplexity-vs-chatgpt", "Perplexity", "ChatGPT", "AI search assistant", "Perplexity phù hợp khi trọng tâm là AI search, nguồn tham khảo và research nhanh.", "ChatGPT mạnh ở trợ lý tổng quát, viết, phân tích, lập kế hoạch và xử lý đa tác vụ.", "Chọn Perplexity cho research có nguồn; chọn ChatGPT cho workflow sản xuất nội dung và phân tích rộng."),
    ("gemini-vs-claude", "Gemini", "Claude", "AI assistant", "Gemini phù hợp với người dùng trong hệ sinh thái Google.", "Claude phù hợp khi cần xử lý văn bản dài, reasoning và biên tập cẩn thận.", "Chọn theo hệ sinh thái và loại tài liệu bạn xử lý thường xuyên."),
    ("midjourney-vs-dalle", "Midjourney", "DALL-E", "AI image generator", "Midjourney thường được cân nhắc cho hình ảnh sáng tạo, phong cách mạnh và visual concept.", "DALL-E thường phù hợp khi muốn tạo ảnh trực tiếp trong workflow AI dễ tiếp cận.", "Chọn dựa trên style mong muốn, quyền sử dụng, workflow chỉnh sửa và chi phí hiện tại."),
    ("notion-ai-vs-chatgpt", "Notion AI", "ChatGPT", "AI productivity assistant", "Notion AI phù hợp khi nội dung và knowledge base đã nằm trong Notion.", "ChatGPT phù hợp khi cần trợ lý AI độc lập cho nhiều workflow ngoài một workspace.", "Chọn Notion AI nếu workflow nằm trong Notion; chọn ChatGPT nếu bạn cần trợ lý AI tổng quát hơn."),
]


def build_site_output(landing_index: pd.DataFrame | None = None, base_site_url: str = "", offer_scores: pd.DataFrame | None = None) -> dict:
    output = settings.site_output_dir
    landing_root = settings.landing_output_dir
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    pages = collect_landing_pages(landing_index, landing_root, offer_scores)
    built_pages = []
    for page in pages:
        slug = page["slug"]
        target_dir = output / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(page["source"], target_dir / "index.html")
        built_pages.append({**page, "deploy_path": str(target_dir / "index.html"), "url_path": f"/{slug}/"})

    copy_screenshot_assets(output)
    write_og_images(output, built_pages)
    write_index(output, built_pages)
    write_blog_pages(output, built_pages)
    write_content_pages(output, built_pages)
    write_category_pages(output, built_pages)
    write_comparison_detail_pages(output)
    programmatic_pages = []
    programmatic_pages.extend(generate_comparison_pages(output, offer_scores))
    programmatic_pages.extend(generate_toplist_pages(output, offer_scores))
    programmatic_pages.extend(generate_intent_pages(output, offer_scores))
    programmatic_pages.extend(generate_priority_pages(output, offer_scores))
    programmatic_pages.extend(generate_hub_pages(output, offer_scores))
    programmatic_pages.extend(generate_review_pages(output, offer_scores, landing_index))
    programmatic_pages.extend(generate_comparison_review_pages(output, offer_scores))
    programmatic_pages.extend(generate_pricing_pages(output, offer_scores))
    programmatic_pages.extend(generate_category_pages(output, offer_scores))
    write_navigation_index_pages(output, built_pages)
    programmatic_pages.extend(generate_money_content_pages(output, offer_scores))
    programmatic_pages.extend(generate_seo_expansion_pages(output))
    write_legal_pages(output)
    built_pages.extend(copy_user_published_pages(output))
    write_robots(output, base_site_url)
    write_sitemap(output, built_pages, base_site_url)
    write_html_sitemap(output, built_pages)
    write_rss(output, built_pages)
    write_media_kit(output)
    write_aeo_action_plan(output)
    write_github_pages_files(output)
    go_pages = generate_go_pages(output)
    tracked_pages = rewrite_outbound_ctas(output)
    write_llms_txt(output, built_pages, base_site_url)
    write_redirects(output, built_pages)
    link_stats = post_process_internal_links(output)
    return {
        "site_output": str(output.resolve()),
        "pages": len(built_pages),
        "base_site_url": base_site_url,
        "internal_links_added": link_stats.get("links_added", 0),
        "internal_linked_pages": link_stats.get("pages", 0),
        "go_pages": go_pages,
        "tracked_pages": tracked_pages,
    }


def write_github_pages_files(output: Path) -> None:
    domain = (settings.base_site_url or settings.site_domain or "").strip().rstrip("/")
    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    if domain and "yourdomain.com" not in domain:
        (output / "CNAME").write_text(f"{domain}\n", encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")


def collect_landing_pages(landing_index: pd.DataFrame | None, landing_root: Path, offer_scores: pd.DataFrame | None = None) -> list[dict]:
    score_map = {}
    if offer_scores is not None and not offer_scores.empty:
        score_map = offer_scores.set_index("brand_name").to_dict("index")
    pages = []
    if landing_index is not None and not landing_index.empty and "landing_page" in landing_index.columns:
        for _, row in landing_index.iterrows():
            source = Path(str(row.get("landing_page", "")))
            if source.exists():
                brand = str(row.get("brand_name", source.parent.name))
                meta = score_map.get(brand, {})
                pages.append(
                    {
                        "brand_name": brand,
                        "slug": source.parent.name,
                        "source": source,
                        "niche": str(meta.get("niche", "SaaS")),
                        "score": str(meta.get("total_score", "N/A")),
                        "risk": str(meta.get("risk_level", "NEED_REVIEW")),
                        "description": short_description(brand, str(meta.get("niche", "SaaS"))),
                    }
                )
    if pages:
        return pages
    for source in landing_root.glob("*/index.html"):
        brand = source.parent.name.replace("-", " ").title()
        pages.append({"brand_name": brand, "slug": source.parent.name, "source": source, "niche": "SaaS", "score": "N/A", "risk": "NEED_REVIEW", "description": short_description(brand, "SaaS")})
    return pages


def copy_screenshot_assets(output: Path) -> None:
    source_dir = settings.base_dir / "assets" / "screenshots"
    if not source_dir.exists():
        return
    target_dir = output / "assets" / "screenshots"
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in source_dir.glob("*.png"):
        shutil.copy2(source, target_dir / source.name)


def write_index(output: Path, pages: list[dict]) -> None:
    cards = "\n".join(card_html(page) for page in pages)
    category_cards = nav_card_links(
        [
            ("AI Coding Tools", "/category/ai-coding-tools/", "Coding assistants, developer workflows, repository context, and team controls."),
            ("SEO Tools", "/category/seo-tools/", "Keyword research, competitor research, audits, and content planning."),
            ("Email Marketing Tools", "/category/email-marketing-tools/", "List growth, lifecycle automation, deliverability, and CRM-style follow-up."),
            ("Automation Tools", "/category/automation-tools/", "Workflow automation, task volume, integrations, and operational reliability."),
            ("Design Tools", "/category/design-tools/", "Visual content, presentations, ad creative, and brand asset workflows."),
            ("Video Tools", "/category/video-tools/", "AI video generation, editing, exports, and commercial usage checks."),
            ("Writing Tools", "/category/writing-tools/", "Drafting, editing, brand voice, and content quality review."),
            ("Website Builder Tools", "/category/website-builder-tools/", "Landing pages, CMS structure, launch speed, and maintenance needs."),
        ]
    )
    priority_links = list_links_from_csv(settings.data_dir / "priority_pages_index.csv", "suggested_slug", "title", limit=8)
    review_links = nav_card_links([(p["brand_name"], f"/review/{p['slug']}/", p["description"]) for p in pages[:8]])
    comparison_links = nav_card_links(
        [
            ("Cursor vs GitHub Copilot", "/compare/cursor-vs-github-copilot/", "Compare AI coding workflow fit and team adoption."),
            ("Make vs Zapier", "/compare/make-vs-zapier/", "Compare automation setup, maintenance, and task cost."),
            ("Semrush vs Ahrefs", "/compare/semrush-vs-ahrefs/", "Compare SEO research depth and pricing risk."),
            ("ActiveCampaign vs Mailchimp", "/compare/activecampaign-vs-mailchimp/", "Compare email automation and contact growth tradeoffs."),
        ]
    )
    pricing_links = nav_card_links(
        [
            ("Cursor Pricing", "/pricing/cursor/", "Plan fit, trial notes, and hidden cost checks."),
            ("Semrush Pricing", "/pricing/semrush/", "SEO plan limits, exports, users, and project cost checks."),
            ("Make Pricing", "/pricing/make/", "Automation volume, operations, and upgrade triggers."),
            ("Canva Pricing", "/pricing/canva/", "Design plan fit, brand controls, and team usage checks."),
        ]
    )
    hub_links = nav_card_links(
        [
            ("AI Coding Hub", "/hub/ai-coding/", "Research coding tools, reviews, comparisons, and pricing pages."),
            ("AI SEO Hub", "/hub/ai-seo/", "Research SEO tools and content workflow decisions."),
            ("Automation Hub", "/hub/ai-automation/", "Research workflow automation tools and buying risks."),
            ("AI Writing Hub", "/hub/ai-writing/", "Research writing tools, alternatives, and editorial workflows."),
        ]
    )
    homepage_faq = [
        "What is AI Tool Review Center?",
        "Does this site use affiliate links?",
        "How should I use the reviews and pricing guides?",
        "Are prices guaranteed to be current?",
    ]
    faq_schema_text = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": "Use this site as a research starting point. Verify official pricing, terms, product limits, affiliate rules, and workflow fit before buying or promoting any tool."}} for q in homepage_faq]}, ensure_ascii=False)
    sections = section_html("AI Tools", [p for p in pages if "AI" in p["niche"]]) + section_html("Marketing", [p for p in pages if "Marketing" in p["niche"] or "SEO" in p["niche"] or "Design" in p["niche"]]) + section_html("CRM", [p for p in pages if "CRM" in p["niche"]]) + section_html("Website Builder", [p for p in pages if "Website" in p["niche"]]) + section_html("Productivity", [p for p in pages if "Productivity" in p["niche"] or "Meeting" in p["niche"] or "Automation" in p["niche"]])
    updated_label = date.today().strftime("%d/%m/%Y")
    recent = "\n".join(f"<li><a href='/{html.escape(page['slug'])}/'><span translate='no'>{html.escape(page['brand_name'])}</span></a> <span>Updated: {updated_label}</span></li>" for page in pages[:6])
    popular = section_html("Popular Reviews", pages[:6])
    html_text = f"""<!doctype html>
<html lang="en">
  <head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Tool Review Center - {html.escape(settings.site_name)}</title>
  <meta name="description" content="AI Tool Review Center for reviews, comparisons, pricing research, categories, hubs, and affiliate disclosure before buying AI and SaaS tools.">
  <link rel="canonical" href="{html.escape((settings.base_site_url or settings.site_domain or 'https://yourdomain.com').rstrip('/') + '/', quote=True)}">
  <link rel="alternate" type="application/rss+xml" title="{html.escape(settings.site_name)} RSS" href="{html.escape(site_url('/rss.xml'), quote=True)}">
  <meta property="og:title" content="{html.escape(settings.site_name)}">
  <meta property="og:description" content="Independent-style AI and SaaS review hub with practical reviews and comparisons.">
  <meta property="og:image" content="{html.escape(site_url('/assets/og/home.svg'), quote=True)}">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:image" content="{html.escape(site_url('/assets/og/home.svg'), quote=True)}">
  <meta name="google-site-verification" content="{html.escape(settings.google_site_verification, quote=True)}">
  {analytics_snippet()}
  {''.join(f'<script type="application/ld+json">{schema}</script>' for schema in base_schemas(settings.site_name, 'Independent-style AI and SaaS review hub.', (settings.base_site_url or settings.site_domain or 'https://yourdomain.com').rstrip('/') + '/'))}
  <script type="application/ld+json">{faq_schema_text}</script>
  <style>{base_css()}</style>
</head>
<body>
  {nav_html()}
  <header class="hero"><div class="wrap"><span class="badge">Independent-style reviews</span><h1>AI Tool Review Center</h1><p>{html.escape(settings.site_name)} helps readers navigate AI and SaaS tools with review pages, comparison guides, pricing research, category hubs, and transparent affiliate disclosure. The focus is practical workflow fit, not hype.</p><p><a class="btn" href="/reviews/">Browse reviews</a><a class="btn secondary" href="/comparisons/">Compare tools</a><a class="btn secondary" href="/pricing/">Pricing guides</a></p></div></header>
  <main class="wrap" id="reviews">
    <section class="card trust"><h2>Affiliate disclosure</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you. Reviews and comparisons are research-style content, not guaranteed results.</p></section>
    <section><h2>Best AI tools by category</h2><div class="cards">{category_cards}</div></section>
    <section><h2>Top priority pages</h2><div class="cards">{priority_links}</div></section>
    <section><h2>Review pages</h2><div class="cards">{review_links}</div></section>
    <section><h2>Comparison pages</h2><div class="cards">{comparison_links}</div></section>
    <section><h2>Pricing pages</h2><div class="cards">{pricing_links}</div></section>
    <section><h2>Hub pages</h2><div class="cards">{hub_links}</div></section>
    <section><h2>Latest Reviews</h2><div class="cards">{cards}</div></section>
    <section class="list-section"><h2>Recently Updated Reviews</h2><ul>{recent}</ul></section>
    {popular}
    {sections}
    {newsletter_html()}
    <section class="card"><h2>About this review hub</h2><p>This website is an independent-style AI/SaaS review hub for research and comparison purposes. Reviews are written to help readers compare features, tradeoffs, alternatives, and policy notes before visiting an official vendor website.</p></section>
    <section class="card"><h2>FAQ</h2>{faq_html(homepage_faq)}</section>
    <section class="card trust"><h2>Trust and disclosure</h2><p>Some links may become affiliate links after approval. Affiliate commissions do not change the buyer's price. Reviews should not be treated as financial, legal, or business advice.</p></section>
  </main>
  {footer_html()}
</body>
</html>
"""
    (output / "index.html").write_text(html_text, encoding="utf-8")


def card_html(page: dict, extra_class: str = "") -> str:
    class_name = "card" if not extra_class else f"card {extra_class}"
    brand = str(page.get("brand_name", "")).strip()
    category = str(page.get("niche", "SaaS")).strip()
    return f"""<article class="{class_name}">
  <h3 translate="no">{html.escape(brand)}</h3>
  <p class="muted"><strong>Category:</strong> {html.escape(category)}</p>
  <p>{html.escape(page['description'])}</p>
  <p><strong>Score:</strong> {html.escape(page['score'])} | <strong>Risk:</strong> {html.escape(page['risk'])}</p>
  <a class="btn" href="{html.escape(page['url_path'] if 'url_path' in page else '/' + page['slug'] + '/')}">Read review</a>
</article>"""


def section_html(title: str, pages: list[dict]) -> str:
    shown = pages[:6]
    if not shown:
        return ""
    items = "\n".join(f'<li><a href="/{html.escape(page["slug"])}/"><span translate="no">{html.escape(page["brand_name"])}</span></a> <span>{html.escape(page["niche"])}</span></li>' for page in shown)
    return f'<section class="list-section"><h2>{html.escape(title)}</h2><ul>{items}</ul></section>'


def nav_card_links(items: list[tuple[str, str, str]]) -> str:
    return "".join(
        f"<article class='card'><h3>{html.escape(title)}</h3><p>{html.escape(description)}</p><a class='btn' href='{html.escape(url)}'>Open</a></article>"
        for title, url, description in items
    )


def list_links_from_csv(path: Path, slug_column: str, title_column: str, limit: int = 8) -> str:
    if not path.exists():
        return nav_card_links([("Browse reviews", "/reviews/", "Start from the review library and shortlist tools by workflow fit.")])
    try:
        df = pd.read_csv(path).fillna("")
    except Exception:
        return nav_card_links([("Browse reviews", "/reviews/", "Start from the review library and shortlist tools by workflow fit.")])
    cards = []
    for _, row in df.head(limit).iterrows():
        slug = str(row.get(slug_column, "")).strip()
        title = str(row.get(title_column, "")).strip() or slug.replace("-", " ").title()
        if not slug:
            continue
        cards.append((title, f"/{slug}/", "Priority research page built from keyword opportunity planning."))
    return nav_card_links(cards)


def write_content_pages(output: Path, pages: list[dict]) -> None:
    write_reviews_page(output, pages)
    write_comparisons_page(output, pages)
    write_about_page(output)
    write_trust_pages(output)


def write_navigation_index_pages(output: Path, pages: list[dict]) -> None:
    write_pricing_index_page(output)
    write_categories_index_page(output)
    write_hubs_index_page(output)
    write_reviews_page(output, pages)
    write_comparisons_page(output, pages)


def write_pricing_index_page(output: Path) -> None:
    folder = output / "pricing"
    folder.mkdir(parents=True, exist_ok=True)
    items = [
        ("Cursor Pricing", "/pricing/cursor/", "AI coding plan fit, repository workflow, and team policy checks."),
        ("GitHub Copilot Pricing", "/pricing/github-copilot/", "Developer seat billing, organization controls, and upgrade triggers."),
        ("Semrush Pricing", "/pricing/semrush/", "SEO project limits, exports, users, and reporting cost checks."),
        ("Make Pricing", "/pricing/make/", "Automation operations, task volume, and maintenance risk."),
        ("Zapier Pricing", "/pricing/zapier/", "Automation task volume, premium apps, and team handoff checks."),
        ("Canva Pricing", "/pricing/canva/", "Design plan fit, brand controls, exports, and team use."),
        ("ActiveCampaign Pricing", "/pricing/activecampaign/", "Email automation, contact tiers, and CRM-style workflow checks."),
        ("Mailchimp Pricing", "/pricing/mailchimp/", "List size, automation depth, and upgrade pressure checks."),
    ]
    faq = faq_html(["How should I use pricing guides?", "Are prices guaranteed to be current?", "Why do pricing pages use tracking links?", "Should I check official terms before buying?"])
    body = f"""<section class='card'><h1>Pricing Guides</h1><p>Use these pricing research pages to verify plan fit, trial terms, hidden cost risks, and official pricing before buying or promoting an AI or SaaS tool.</p><p><a class='btn' href='/go/cursor/?src=pricing&cta=index_page'>Visit Official Website</a><a class='btn secondary' href='/reviews/'>Read reviews first</a></p></section>
<section><h2>Pricing research pages</h2><div class='cards'>{nav_card_links(items)}</div></section>
<section class='card'><h2>FAQ</h2>{faq}</section>
<section class='card trust'><h2>Pricing disclosure</h2><p>Prices and plan limits can change. Always verify current pricing on the official vendor website before buying or using affiliate content.</p></section>"""
    (folder / "index.html").write_text(page_shell("Pricing Guides", "Pricing research index for AI and SaaS tools, including plan fit, trial notes, hidden cost risk, and official verification.", body, "/pricing/"), encoding="utf-8")


def write_categories_index_page(output: Path) -> None:
    folder = output / "categories"
    folder.mkdir(parents=True, exist_ok=True)
    items = [
        ("AI Coding Tools", "/category/ai-coding-tools/", "Developer assistants, repository context, code review, and team controls."),
        ("SEO Tools", "/category/seo-tools/", "Keyword research, audits, competitor analysis, and content planning."),
        ("Email Marketing Tools", "/category/email-marketing-tools/", "Lifecycle campaigns, segmentation, deliverability, and contact growth."),
        ("Automation Tools", "/category/automation-tools/", "Workflow automation, task volume, integrations, and maintenance risk."),
        ("Design Tools", "/category/design-tools/", "Visual assets, presentations, ad creative, and brand workflows."),
        ("Video Tools", "/category/video-tools/", "AI video generation, editing, export rights, and review workflows."),
        ("Writing Tools", "/category/writing-tools/", "Drafting, editing, brand voice, and content quality checks."),
        ("Website Builder Tools", "/category/website-builder-tools/", "Site structure, CMS needs, launch speed, and design control."),
    ]
    faq = faq_html(["How should I choose a tool category?", "Should I start with reviews or pricing pages?", "Are category rankings final recommendations?", "Do category pages include affiliate disclosure?"])
    body = f"""<section class='card'><h1>Categories</h1><p>Browse AI and SaaS tool categories by workflow. Each category page links to reviews, comparisons, pricing guides, hub pages, and tracked official-site CTAs.</p></section>
<section><h2>Best AI tools by category</h2><div class='cards'>{nav_card_links(items)}</div></section>
<section class='card'><h2>FAQ</h2>{faq}</section>"""
    (folder / "index.html").write_text(page_shell("Categories", "Category index for AI and SaaS tools with links to reviews, comparisons, pricing guides, and research hubs.", body, "/categories/"), encoding="utf-8")


def write_hubs_index_page(output: Path) -> None:
    folder = output / "hubs"
    folder.mkdir(parents=True, exist_ok=True)
    items = [
        ("AI Coding Hub", "/hub/ai-coding/", "Coding reviews, comparisons, pricing pages, and priority topics."),
        ("AI SEO Hub", "/hub/ai-seo/", "SEO tool research, alternatives, comparison pages, and buying checks."),
        ("Automation Hub", "/hub/ai-automation/", "Workflow automation tools, pricing risk, and implementation notes."),
        ("AI Writing Hub", "/hub/ai-writing/", "Writing tools, editorial workflows, alternatives, and reviews."),
        ("AI Video Hub", "/hub/ai-video/", "Video generation, editing tools, avatar video, and export considerations."),
        ("Website Builders Hub", "/hub/website-builders/", "CMS, landing page, site builder, and launch workflow research."),
    ]
    faq = faq_html(["What is a research hub?", "How are hub pages different from category pages?", "Should I use hubs before buying software?", "Do hub pages include affiliate disclosure?"])
    body = f"""<section class='card'><h1>Hubs</h1><p>Hub pages organize related reviews, comparison pages, pricing guides, and category pages so readers can move through a full research path before clicking to an official website.</p><p>A hub is useful when you are still mapping the market and do not yet know which tool deserves a closer look. Instead of pushing one product immediately, a hub connects the broader topic to practical decision pages: review pages for individual tools, comparison pages for close alternatives, pricing guides for plan risk, and category pages for a wider shortlist.</p><p>The best way to use a hub is to start with the workflow you want to improve. For example, a coding hub should help you compare editor fit, repository context, privacy questions, and team adoption. An SEO hub should help you compare keyword research, audits, reporting, and content workflows. An automation hub should help you think about task volume, maintenance, ownership, and failure handling. This keeps the research process grounded in real work rather than brand popularity.</p></section>
<section><h2>Research hubs</h2><div class='cards'>{nav_card_links(items)}</div></section>
<section class='card'><h2>How to use these hubs</h2><p>Open the hub that matches your current buying question, then follow at least three internal links before making a decision. Read one review to understand a specific product, open one comparison to see tradeoffs, and check one pricing guide to identify plan limits. This pattern gives you a more balanced view than jumping straight from a social media recommendation to a checkout page.</p><p>For affiliate research, hubs also help identify which topics have enough depth for trustworthy content. A thin affiliate site often has isolated product pages with little context. A stronger review site connects tools through categories, pricing, alternatives, and buyer questions. That structure helps readers navigate naturally and gives search engines clearer topical relationships.</p><p>These pages do not guarantee outcomes, rankings, commissions, or software performance. They are editorial research paths. Always verify current vendor terms, pricing, refund rules, affiliate policy, and paid traffic restrictions on the official website before buying, promoting, or running ads.</p></section>
<section class='card'><h2>FAQ</h2>{faq}</section>
<section class='card trust'><h2>Affiliate disclosure</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you.</p></section>"""
    (folder / "index.html").write_text(page_shell("Hubs", "Research hub index for AI and SaaS categories, reviews, comparisons, pricing pages, and buyer decision paths.", body, "/hubs/"), encoding="utf-8")


def write_blog_pages(output: Path, pages: list[dict]) -> None:
    blog_root = output / "blog"
    blog_root.mkdir(parents=True, exist_ok=True)
    cards = "\n".join(blog_card(slug, title, summary) for slug, title, summary in BLOG_POSTS)
    index_body = f"<section><h1>Blog</h1><p>Informational guides for comparing AI tools, SaaS software, automation, CRM, and productivity workflows.</p><div class='cards'>{cards}</div></section>{newsletter_html()}"
    (blog_root / "index.html").write_text(page_shell("Blog", "AI and SaaS research guides for safer software evaluation.", index_body, "/blog/", image_path="/assets/og/blog.svg"), encoding="utf-8")
    for slug, title, summary in BLOG_POSTS:
        folder = blog_root / slug
        folder.mkdir(parents=True, exist_ok=True)
        body = blog_article_html(slug, title, summary, pages)
        (folder / "index.html").write_text(page_shell(title, summary, body, f"/blog/{slug}/", image_path=f"/assets/og/{slug}.svg", page_type="article"), encoding="utf-8")


def blog_card(slug: str, title: str, summary: str) -> str:
    return f"<article class='card'><h3>{html.escape(title)}</h3><p>{html.escape(summary)}</p><p class='muted'>8 min read</p><a class='btn' href='/blog/{html.escape(slug)}/'>Read article</a></article>"


def blog_article_html(slug: str, title: str, summary: str, pages: list[dict]) -> str:
    if slug == "chatgpt-windsurf-codex-workflow":
        return ai_workflow_article_html(slug, title)
    if slug == "chatgpt-prompts-for-windsurf":
        return chatgpt_prompts_for_windsurf_article_html(slug, title)
    if slug in SUPPORTING_BLOG_ARTICLES:
        return supporting_blog_article_html(slug)
    related = related_links_for_blog(slug, pages)
    sections = [
        ("overview", "Overview", summary),
        ("evaluation", "How to evaluate the category", "Start with the problem you are trying to solve, then compare workflow fit, pricing model, cancellation terms, data handling, integrations, and support. A tool that looks impressive in a demo may still be the wrong choice if it does not match your daily process or if the pricing changes after a trial period."),
        ("tools", "Tools to compare", "A practical shortlist should include one category leader, one budget-friendly option, and one specialized alternative. For example, teams comparing creative tools may look at Gamma, Canva, Webflow AI, and AdCreative AI depending on whether they need presentations, websites, or ad concepts."),
        ("use-cases", "Common use cases", "Small businesses often use AI and SaaS tools for drafting documents, creating marketing assets, organizing sales follow-up, producing voice or video content, and automating repetitive admin work. The safest approach is to test a narrow workflow before adopting a tool across the whole business."),
        ("risks", "Risks and limitations", "Do not assume that AI output is ready to publish. Review accuracy, brand tone, copyright concerns, privacy implications, and platform policy before using any output in public campaigns. For affiliate or paid advertising, also verify trademark bidding, direct linking, and disclosure rules."),
        ("decision", "Decision checklist", "Before paying for software, check whether the tool saves real time, improves output quality, fits your team process, and has acceptable terms. Keep notes from your trial so you can compare tools based on evidence instead of first impressions."),
    ]
    section_html_text = "".join(f"<section class='card' id='{sid}'><h2>{html.escape(heading)}</h2><p>{html.escape(text)}</p><p>{html.escape(expand_article_paragraph(title, heading))}</p></section>" for sid, heading, text in sections)
    toc = "".join(f"<a href='#{sid}'>{html.escape(heading)}</a>" for sid, heading, _ in sections)
    faq = faq_html([f"What is the main benefit of {title.lower()}?", "How should I compare tools safely?", "Should I rely only on AI recommendations?", "Are affiliate links used on this site?", "What should I verify before buying?"])
    return f"""<nav class='breadcrumb'><a href='/'>Home</a> / <a href='/blog/'>Blog</a> / {html.escape(title)}</nav>
    <article class='review-layout'><aside class='card toc'><h2>Contents</h2>{toc}</aside><div><section class='card'><h1>{html.escape(title)}</h1><p>{html.escape(summary)}</p><p class='muted'>8 min read | Last updated {date.today().isoformat()}</p>{share_buttons(f'/blog/{slug}/', title)}</section>{section_html_text}<section class='card' id='faq'><h2>FAQ</h2>{faq}</section><section class='card related'><h2>Related Reviews</h2>{related}</section><section class='card'><h2>Next step</h2><p><a class='btn' href='/reviews/'>Read related reviews</a><a class='btn secondary' href='/comparisons/'>Compare tools</a></p></section>{newsletter_html()}</div></article>"""


def expand_article_paragraph(title: str, heading: str) -> str:
    return (
        f"For {title.lower()}, the useful question is not whether the category is popular, but whether the tool improves a real workflow. "
        "Review the official website, compare at least two alternatives, and document what changed during a trial. "
        "This research-first approach is slower than chasing hype, but it reduces the chance of buying software that looks good and then sits unused. "
        "If a tool will be promoted through affiliate content or paid traffic, the review also needs clear disclosure, accurate pricing notes, and careful wording around benefits."
    )


def related_links_for_blog(slug: str, pages: list[dict]) -> str:
    picks = pages[:4]
    if "crm" in slug:
        picks = [p for p in pages if "CRM" in p["niche"]][:4] or picks
    elif "voice" in slug:
        picks = [p for p in pages if "Voice" in p["niche"] or "Video" in p["niche"]][:4] or picks
    elif "website" in slug or "presentation" in slug or "canva" in slug:
        picks = [p for p in pages if p["slug"] in {"gamma", "webflow-ai", "canva", "adcreative-ai"}][:4] or picks
    return "".join(f"<a href='/{html.escape(page['slug'])}/'>{html.escape(page['brand_name'])}</a> " for page in picks)


def chatgpt_prompts_for_windsurf_article_html(slug: str, title: str) -> str:
    toc_items = [
        ("why-prompts-matter", "Why ChatGPT prompts matter before Windsurf"),
        ("workflow", "My practical AI coding prompt workflow"),
        ("before-writing", "What I prepare before asking Windsurf"),
        ("prompt-landing-page", "Prompt example 1 - Build a landing page"),
        ("prompt-language", "Prompt example 2 - Fix a mixed language issue"),
        ("prompt-seo", "Prompt example 3 - Add SEO metadata"),
        ("prompt-internal-links", "Prompt example 4 - Create internal links"),
        ("prompt-404", "Prompt example 5 - Fix a broken route or 404"),
        ("how-i-test", "How I test the Windsurf output"),
        ("codex-handoff", "When I hand the task to Codex"),
        ("mistakes", "Prompt mistakes I try to avoid"),
        ("checklist", "My reusable Windsurf prompt checklist"),
        ("faq", "FAQ"),
    ]
    toc = "".join(f"<a href='#{sid}'>{html.escape(label)}</a>" for sid, label in toc_items)
    prompt_landing = """I want you to build a clean static landing page for my AI workflow checklist. Keep the current site style. Add a clear headline, short intro, 5 benefit bullets, an email setup-mode notice, and CTA buttons linking to /free-ai-coding-workflow-checklist/ and /blog/chatgpt-windsurf-codex-workflow/. Do not add external APIs, fake claims, or affiliate links. After editing, tell me which files changed and what command I should run to test."""
    prompt_language = """Inspect the generated English and Vietnamese pages for mixed language UI. English pages should use English labels. Vietnamese pages should use natural Vietnamese labels. Fix the source generator, not only docs output. Preserve product names like ChatGPT, Windsurf, Codex, Cursor, and GitHub Copilot. Rebuild the site and confirm language integrity passes."""
    prompt_seo = """Add or verify SEO metadata for this page: unique title, meta description, canonical URL, Open Graph title/description/image, Twitter card, and one H1. Do not change the domain. Do not add fake analytics IDs. If the config is empty, the build should still work. Update sitemap through the normal pipeline."""
    prompt_links = """Add natural internal links from this article to the main ChatGPT Windsurf Codex workflow article, Windsurf review, Cursor vs Windsurf comparison, and AI coding workflow checklist. Keep link density moderate. Use descriptive anchors. Do not create broken URLs. Do not add fake affiliate links."""
    prompt_404 = """The URL /blog/chatgpt-windsurf-codex-workflow/ returns 404 on GitHub Pages. Check whether the route exists in site_output and docs, whether sitemap includes it, and whether the source blog routing list includes the slug. Fix the source pipeline, rebuild, sync docs, and report the exact files that need to be committed."""
    return f"""<nav class='breadcrumb'><a href='/'>Home</a> / <a href='/blog/'>Blog</a> / {html.escape(title)}</nav>
    <article class='review-layout'>
      <aside class='card toc'><h2>Contents</h2>{toc}</aside>
      <div>
        <section class='card hero-section'>
          <p class='muted'>AI coding prompt workflow | Windsurf examples | Last updated {date.today().isoformat()}</p>
          <h1>How to Use ChatGPT to Write Better Prompts for Windsurf</h1>
          <p>I do not send rough ideas directly to Windsurf anymore. When I do, the first build usually moves fast, but the output can miss important details: the wrong route, a weak layout, mixed language labels, missing SEO metadata, or a feature that looks finished but does not survive testing.</p>
          <p>My current workflow is more deliberate. I start with the idea, use ChatGPT to turn that idea into a clearer coding prompt, send the prompt to Windsurf for the first build, test the result myself, then use ChatGPT again to understand errors before handing focused repair work to Codex. This article explains that middle step: how I use ChatGPT prompts for Windsurf so the first build starts cleaner.</p>
          <div class='cta-row'><a class='btn' href='/blog/chatgpt-windsurf-codex-workflow/'>Read the full workflow</a><a class='btn secondary' href='/free-ai-coding-workflow-checklist/'>Get the workflow checklist</a></div>
          {share_buttons(f'/blog/{slug}/', "ChatGPT Prompts for Windsurf")}
        </section>

        <section class='card' id='why-prompts-matter'>
          <h2>Why ChatGPT prompts matter before Windsurf</h2>
          <p>Windsurf is useful when I need to move from an idea to a working first version. It can create files, adjust UI, connect routes, and make a project feel alive quickly. But Windsurf is not a mind reader. If I give it a vague instruction, the first version usually reflects that vagueness.</p>
          <p>A better prompt does not make the tool perfect. It makes the first build easier to inspect. It gives Windsurf the boundaries: what to change, what to preserve, what not to invent, what files matter, what validation commands should run, and how the final answer should be reported.</p>
          <p>That is why I use ChatGPT before Windsurf. ChatGPT helps me slow down for a few minutes and turn a messy request into a practical implementation brief. In real projects, those few minutes often save more time than trying to fix a chaotic first draft later.</p>
        </section>

        <section class='card' id='workflow'>
          <h2>My practical AI coding prompt workflow</h2>
          <p>The flow I use is simple:</p>
          <p><strong>Idea -> ChatGPT prompt -> Windsurf first build -> test -> ChatGPT review -> Codex fix</strong></p>
          <p>For example, if I want to add a new article to this AI tool review site, I do not ask Windsurf to "write a blog post and fix SEO." That is too broad. I first ask ChatGPT to help define the article purpose, internal links, CTA, sitemap behavior, language requirements, and validation steps.</p>
          <p>After Windsurf builds the first version, I test the page in the browser and through local scripts. If the output has broken links, strange Vietnamese labels, layout overlap, or a GitHub Pages route problem, I take screenshots or copy the error. Then ChatGPT helps me write a focused prompt for Codex. Codex is better when the problem is specific.</p>
          <p>This is the same workflow I described in my main article, <a href='/blog/chatgpt-windsurf-codex-workflow/'>How I Use ChatGPT, Windsurf and Codex to Build Real AI Projects</a>. This supporting guide zooms in on the prompt-writing part.</p>
        </section>

        <section class='card' id='before-writing'>
          <h2>What I prepare before asking Windsurf</h2>
          <p>Before I write a Windsurf prompt, I try to collect four things. First, I write the user goal in plain language. Second, I list the files, folders, or pages that are likely involved. Third, I define the safety rules, such as no external API calls, no fake affiliate links, no auto-posting, and no manual edits inside generated docs unless the build pipeline handles it. Fourth, I specify the tests or validation scripts that should run afterward.</p>
          <p>This makes the prompt more like a short engineering ticket than a wish. It also makes it easier to review the result. If the task says "update sitemap through the pipeline," then I know to check `sitemap.xml`. If the task says "do not break the language switcher," then I know to check English and Vietnamese versions.</p>
          <p>For beginners, this matters because you do not need to know every line of code. You need to know how to describe the result and how to test whether the result actually works.</p>
        </section>

        <section class='card' id='prompt-landing-page'>
          <h2>Prompt example 1 - Build a landing page</h2>
          <p>When I want Windsurf to create a first version of a landing page, I include the purpose, page structure, internal links, and constraints.</p>
          <pre><code>{html.escape(prompt_landing)}</code></pre>
          <p>This prompt works better than "build a landing page" because it tells Windsurf what page to support, what style to keep, which CTA links to use, and what not to do. It also protects the project from fake claims or accidental external integrations.</p>
        </section>

        <section class='card' id='prompt-language'>
          <h2>Prompt example 2 - Fix a mixed language issue</h2>
          <p>Mixed language is a real issue I have had to fix on this site. A page might have Vietnamese navigation but English table headings, or an English page might accidentally contain Vietnamese UI text. The prompt needs to mention both source and generated output.</p>
          <pre><code>{html.escape(prompt_language)}</code></pre>
          <p>The important part is "fix the source generator, not only docs output." If a tool only edits the generated HTML, the problem comes back the next time I run the build. A good Windsurf prompt should push the fix upstream.</p>
        </section>

        <section class='card' id='prompt-seo'>
          <h2>Prompt example 3 - Add SEO metadata</h2>
          <p>SEO tasks are easy to make messy because there are many small pieces: title, description, canonical, Open Graph, Twitter card, schema, sitemap, and internal links. I try to keep the prompt specific.</p>
          <pre><code>{html.escape(prompt_seo)}</code></pre>
          <p>This is useful for a static site because a page can look fine visually and still be weak for Google Search Console. I want Windsurf to update the right source path and keep the build safe when tracking IDs or verification fields are empty.</p>
        </section>

        <section class='card' id='prompt-internal-links'>
          <h2>Prompt example 4 - Create internal links</h2>
          <p>Internal links should help the reader move through the topic, not just fill the page with anchors. For this article, the most useful supporting links are the main workflow article, the <a href='/windsurf-review/'>Windsurf review</a>, the <a href='/comparisons/cursor-vs-windsurf/'>Cursor vs Windsurf comparison</a>, and the <a href='/free-ai-coding-workflow-checklist/'>AI coding workflow checklist</a>.</p>
          <pre><code>{html.escape(prompt_links)}</code></pre>
          <p>I like prompts that say "keep link density moderate" because AI tools can overdo internal linking. A few useful links are better than a page that feels like a navigation dump.</p>
        </section>

        <section class='card' id='prompt-404'>
          <h2>Prompt example 5 - Fix a broken route or 404</h2>
          <p>Broken routes are common in static sites when the source generated the page locally but the committed `docs/` folder did not include the new output. This is exactly the kind of issue where a focused prompt helps.</p>
          <pre><code>{html.escape(prompt_404)}</code></pre>
          <p>This prompt tells Windsurf where to look: source routing, `site_output`, `docs`, sitemap, and the commit list. Without that detail, the tool might patch the wrong place or assume the problem is hosting when it is actually a missing generated folder.</p>
        </section>

        <section class='card' id='how-i-test'>
          <h2>How I test the Windsurf output</h2>
          <p>After Windsurf creates the first build, I do not assume it is ready. I open the page, click internal links, check the CTA, inspect the sitemap, and run the local validation scripts. I look for obvious human issues too: does the page read naturally, does the Vietnamese text make sense, does the heading match the search intent, and does the first screen explain why the article exists?</p>
          <p>For AI coding content, I especially check whether the article links back to the main workflow. A supporting post should not live alone. It should help readers discover the bigger system: <a href='/blog/chatgpt-windsurf-codex-workflow/'>ChatGPT for planning, Windsurf for the first build, Codex for fixing</a>.</p>
          <p>If the page passes local validation but still feels robotic, I revise the prompt. Practical content needs examples from real work: broken routes, mixed language bugs, SEO metadata, internal linking, layout issues, and screenshots. Those details make the article useful.</p>
        </section>

        <section class='card' id='codex-handoff'>
          <h2>When I hand the task to Codex</h2>
          <p>I usually hand the task to Codex when the issue is no longer about creating a first draft. If Windsurf generated the page but the route is missing in `docs`, or the FAQ schema is duplicated, or the language switcher needs source-level changes, Codex is a better fit.</p>
          <p>The Codex prompt is more surgical. I include the exact failing URL, the expected behavior, the source files to inspect, the validation commands, and what not to change. This prevents broad refactors and keeps the project stable.</p>
          <p>In practice, Windsurf gives me speed and Codex gives me repair quality. ChatGPT connects both by helping me write clearer prompts.</p>
        </section>

        <section class='card' id='mistakes'>
          <h2>Prompt mistakes I try to avoid</h2>
          <p>The first mistake is asking for too much at once. "Improve the website" can mean SEO, design, content, routing, language, tracking, and social distribution. That is too broad for one pass.</p>
          <p>The second mistake is leaving out constraints. If I do not say "do not call external APIs" or "do not create fake affiliate links," the tool might suggest something that does not fit the project. Constraints are not negative. They keep the work aligned with the real goal.</p>
          <p>The third mistake is failing to define the test. A useful prompt should end with something like: run the build, sync docs, validate site, check language integrity, and report the files changed. That makes the result easier to trust.</p>
        </section>

        <section class='card' id='checklist'>
          <h2>My reusable Windsurf prompt checklist</h2>
          <ul>
            <li>State the exact page, feature, or bug.</li>
            <li>Explain the reader or user goal.</li>
            <li>List required internal links and CTA destinations.</li>
            <li>Tell Windsurf what not to invent or change.</li>
            <li>Ask it to fix source generator files, not only generated output.</li>
            <li>Specify the build and validation commands.</li>
            <li>Ask for a short report with files changed and test results.</li>
          </ul>
          <p>If you want a broader version of this process, use the <a href='/free-ai-coding-workflow-checklist/'>free AI coding workflow checklist</a>. It covers the full loop from idea to ChatGPT, Windsurf, Codex, GitHub Pages, SEO checks, and social drafts.</p>
          <div class='cta-row'><a class='btn' href='/free-ai-coding-workflow-checklist/'>Download the workflow checklist</a><a class='btn secondary' href='/windsurf-review/'>Read the Windsurf review</a></div>
        </section>

        <section class='card' id='faq'>
          <h2>FAQ</h2>
          <details><summary>What are good ChatGPT prompts for Windsurf?</summary><p>Good prompts explain the goal, files involved, constraints, expected output, and validation steps. The best prompts are specific enough for Windsurf to build a useful first version without guessing too much.</p></details>
          <details><summary>Should beginners use ChatGPT before Windsurf?</summary><p>Yes. ChatGPT helps beginners organize the idea before asking Windsurf to create files or UI. This reduces vague output and makes the first build easier to test.</p></details>
          <details><summary>Can Windsurf build apps from a prompt?</summary><p>Windsurf can create first versions quickly, especially for pages, UI, routes, and project structure. The output still needs testing, cleanup, and sometimes Codex repair.</p></details>
          <details><summary>When should I use Codex instead of Windsurf?</summary><p>I use Codex when the project already exists and needs focused fixes: bugs, refactors, SEO corrections, routing issues, language switching problems, or production-readiness checks.</p></details>
          <details><summary>What is the safest AI coding workflow for beginners?</summary><p>Start with a real idea, use ChatGPT to write a clear prompt, let Windsurf create the first version, test the result, then use ChatGPT and Codex to fix specific issues.</p></details>
        </section>

        <section class='card related'><h2>Related guides</h2>
          <ul>
            <li><a href='/blog/windsurf-prompt-checklist/'>Windsurf prompt checklist</a></li>
            <li><a href='/blog/fix-windsurf-mixed-language/'>Fix mixed-language Windsurf output</a></li>
            <li><a href='/blog/windsurf-to-codex-workflow/'>Windsurf to Codex workflow</a></li>
          </ul>
        </section>
        <section class='card related'><h2>Related reading</h2><p><a href='/blog/chatgpt-windsurf-codex-workflow/'>Full ChatGPT + Windsurf + Codex workflow</a> <a href='/windsurf-review/'>Windsurf review</a> <a href='/comparisons/cursor-vs-windsurf/'>Cursor vs Windsurf</a> <a href='/free-ai-coding-workflow-checklist/'>AI coding workflow checklist</a></p></section>
        {newsletter_html()}
      </div>
    </article>"""


def supporting_blog_article_html(slug: str) -> str:
    article = SUPPORTING_BLOG_ARTICLES[slug]
    title = article["title"]
    toc_items = [(section["id"], section["heading"]) for section in article["sections"]] + [("faq", "FAQ"), ("cta", "Next step")]
    toc = "".join(f"<a href='#{html.escape(sid)}'>{html.escape(label)}</a>" for sid, label in toc_items)
    intro = "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in article["intro"])
    sections_html: list[str] = []
    for section in article["sections"]:
        paragraphs = "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in section.get("paragraphs", []))
        code = ""
        if section.get("code"):
            code = f"<pre><code>{html.escape(section['code'])}</code></pre>"
        sections_html.append(
            f"<section class='card' id='{html.escape(section['id'])}'><h2>{html.escape(section['heading'])}</h2>{paragraphs}{code}</section>"
        )
    faq = "\n".join(
        f"<details><summary>{html.escape(question)}</summary><p>{html.escape(answer)}</p></details>"
        for question, answer in article["faq"]
    )
    related = " ".join(
        f"<a href='/blog/{html.escape(link_slug)}/'>{html.escape(en_anchor)}</a>"
        for link_slug, en_anchor, _ in SUPPORTING_BLOG_RELATED
        if link_slug != slug
    )
    return f"""<nav class='breadcrumb'><a href='/'>Home</a> / <a href='/blog/'>Blog</a> / {html.escape(title)}</nav>
    <article class='review-layout'>
      <aside class='card toc'><h2>Contents</h2>{toc}</aside>
      <div>
        <section class='card hero-section'>
          <p class='muted'>{html.escape(article['eyebrow'])} {date.today().isoformat()}</p>
          <h1>{html.escape(article['h1'])}</h1>
          {intro}
          <div class='cta-row'><a class='btn' href='/blog/chatgpt-prompts-for-windsurf/'>Read ChatGPT prompts for Windsurf</a><a class='btn secondary' href='/free-ai-coding-workflow-checklist/'>Get the workflow checklist</a></div>
          {share_buttons(f'/blog/{slug}/', title)}
        </section>
        {''.join(sections_html)}
        <section class='card' id='faq'><h2>FAQ</h2>{faq}</section>
        <section class='card related'><h2>Related links</h2><p><a href='/blog/chatgpt-prompts-for-windsurf/'>ChatGPT prompts for Windsurf</a> <a href='/blog/chatgpt-windsurf-codex-workflow/'>My full ChatGPT-to-Windsurf workflow</a> <a href='/windsurf-review/'>Windsurf review</a> <a href='/comparisons/cursor-vs-windsurf/'>Cursor vs Windsurf</a> <a href='/free-ai-coding-workflow-checklist/'>Workflow checklist</a></p><p>{related}</p></section>
        <section class='card' id='cta'><h2>Next step</h2><p>If you want to use this process on your own static site or app idea, start with the main workflow article, then use the checklist before sending your next prompt to Windsurf.</p><a class='btn' href='/blog/chatgpt-prompts-for-windsurf/'>Read the main prompt workflow</a><a class='btn secondary' href='/free-ai-coding-workflow-checklist/'>Download the checklist</a></section>
        {newsletter_html()}
      </div>
    </article>"""


def ai_workflow_article_html(slug: str, title: str) -> str:
    toc_items = [
        ("why-not-one-tool", "Why I Do Not Use Only One AI Tool"),
        ("real-workflow", "My Real Workflow"),
        ("step-1", "Step 1 - I Start With a Real Idea"),
        ("step-2", "Step 2 - ChatGPT Turns the Idea Into a Clear Prompt"),
        ("step-3", "Step 3 - Windsurf Builds the First Version"),
        ("step-4", "Step 4 - I Test and Collect Real Problems"),
        ("step-5", "Step 5 - ChatGPT Reviews the Problem"),
        ("step-6", "Step 6 - Codex Fixes and Improves the Project"),
        ("real-example", "Real Example"),
        ("comparison-table", "Comparison Table"),
        ("non-developers", "Why This Workflow Helps Non-Developers"),
        ("where-site-fits", "Where My Bot/Website Fits In"),
        ("final-recommendation", "Final Recommendation"),
        ("faq", "FAQ"),
    ]
    toc = "".join(f"<a href='#{sid}'>{html.escape(label)}</a>" for sid, label in toc_items)
    return f"""<nav class='breadcrumb'><a href='/'>Home</a> / <a href='/blog/'>Blog</a> / {html.escape(title)}</nav>
    <article class='review-layout'>
      <aside class='card toc'><h2>Contents</h2>{toc}</aside>
      <div>
        <section class='card hero-section'>
          <p class='muted'>AI coding workflow | Builder story | Last updated {date.today().isoformat()}</p>
          <h1>How I Use ChatGPT, Windsurf and Codex to Build Real AI Projects</h1>
          <p>Many people ask which AI coding tool is the best. In my real work, that question is too simple. I do not use only one tool. I combine ChatGPT, Windsurf, and Codex in one workflow, then I test the output myself until the project becomes usable.</p>
          <p>This is not theory. This is the process I use while building websites, SEO pages, automation systems, review pages, and app ideas. The important part is not pretending AI can do everything in one click. The important part is knowing which tool should think, which tool should build, and which tool should fix.</p>
          <div class='cta-row'><a class='btn' href='/about/'>Explore My AI Workflow Bot</a><a class='btn secondary' href='/category/ai-coding-tools/'>See My AI Coding Tools Reviews</a></div>
          {share_buttons(f'/blog/{slug}/', "ChatGPT Windsurf Codex Workflow")}
        </section>

        <section class='card' id='why-not-one-tool'>
          <h2>Why I Do Not Use Only One AI Tool</h2>
          <p>When I started using AI for real projects, I made the same mistake many beginners make: I expected one tool to understand the whole idea, create the first version, debug the mistakes, improve the design, fix SEO, and prepare the project for publishing. That is not how it works reliably.</p>
          <p>ChatGPT is strong at thinking. I use it to explain my idea, organize messy notes, ask better questions, and turn a vague plan into a detailed prompt. It helps me see what the project needs before I ask any coding tool to touch the files.</p>
          <p>Windsurf is strong when I need momentum. If I want a first version of a website, dashboard, landing page, or app structure, Windsurf helps me move faster than writing every file manually. It can create pages, connect routes, generate UI, and give me something I can test.</p>
          <p>Codex is where I usually go when the project becomes real enough to break. When there are bugs, layout issues, language switching problems, SEO mistakes, broken links, or messy code, Codex is better when I give it a focused task and real context. The real power is the workflow, not one single tool.</p>
        </section>

        <section class='card' id='real-workflow'>
          <h2>My Real Workflow</h2>
          <p>My usual AI coding workflow looks like this:</p>
          <p><strong>Idea -> ChatGPT -> Prompt -> Windsurf -> First Version -> Test -> Screenshot/Error -> ChatGPT Review -> Codex Prompt -> Codex Fix -> Test Again</strong></p>
          <p>I repeat this loop until the project is stable enough to use. Sometimes the first version is surprisingly good. Sometimes it looks good on the surface but breaks when I test routes, mobile layout, SEO metadata, language switching, or generated content. That is normal. AI building is still building. You still need to inspect the result.</p>
          <p>The workflow matters because every step has a clear purpose. ChatGPT helps me think. Windsurf helps me create. Codex helps me repair and polish. Testing is the part that keeps the project honest.</p>
        </section>

        <section class='card' id='step-1'>
          <h2>Step 1 - I Start With a Real Idea</h2>
          <p>I do not start by asking AI to build a random app. I start with a real problem I want to solve. Sometimes it is a website I want to publish. Sometimes it is a bot I want to improve. Sometimes it is an SEO page, a dashboard feature, a parent-child connection app idea, or a video creation tool idea.</p>
          <p>For example, this project started as an AI coding tools review website and became a bigger workflow system. I needed review pages, comparison pages, bilingual pages, sitemap checks, social drafts, content quality validation, and a local dashboard. That is too much to ask one tool to do perfectly in one command.</p>
          <p>So I describe the idea in plain language first. I explain what the user should see, what data should be stored, what should not happen, and which parts must remain safe. This is especially important when I am building local-first systems that should not auto-post, should not create fake affiliate links, and should not break the static site.</p>
        </section>

        <section class='card' id='step-2'>
          <h2>Step 2 - ChatGPT Turns the Idea Into a Clear Prompt</h2>
          <p>ChatGPT helps me turn the idea into a better instruction. I use it to organize requirements, define features, split the work into phases, and write prompts that Windsurf or Codex can actually follow.</p>
          <p>This step is more important than it looks. A weak prompt usually creates weak code. A clear prompt tells the coding tool what to build, what not to touch, which files are important, which tests to run, and which behavior must stay unchanged.</p>
          <p>For example, if I want to improve a page, I do not simply say, "make it better." I ask ChatGPT to help me define what better means: add a real workflow section, improve internal links, keep CTA links local, preserve canonical tags, update sitemap, and run validation. That gives the coding tool a focused task instead of a vague wish.</p>
        </section>

        <section class='card' id='step-3'>
          <h2>Step 3 - Windsurf Builds the First Version</h2>
          <p>After the prompt is clear, I send it to Windsurf when I need a first working version. Windsurf is useful for creating files, building pages, generating UI, connecting routes, and moving from idea to something I can open in the browser.</p>
          <p>I like using Windsurf when the project is still early. It is fast for rough structure. It can scaffold a feature, produce a dashboard section, or create static pages quickly. That speed is valuable because a visible version gives me something concrete to test.</p>
          <p>But I do not expect the first version to be perfect. Sometimes Windsurf creates duplicated logic. Sometimes it gets the layout close but misses a responsive detail. Sometimes it writes content that feels too generic. That is not a failure. It is the first draft of the project.</p>
        </section>

        <section class='card' id='step-4'>
          <h2>Step 4 - I Test and Collect Real Problems</h2>
          <p>This is the step many people skip. I test the result myself. I click links. I open pages on desktop and mobile. I check whether the button goes to the right route. I inspect SEO title, meta description, canonical URL, hreflang, sitemap, and robots.txt. I look for mixed language issues, broken internal links, layout overlap, and pages that look like placeholders.</p>
          <p>When something breaks, I collect evidence. Screenshots are useful because they show the exact visual issue. Error logs are useful because they show what the program actually said. A broken page URL is useful because it gives the tool a concrete target.</p>
          <p>For this site, I have used this approach for issues like mixed English and Vietnamese text, a table of contents blocking the article, duplicate FAQ schema, footer identity problems, GitHub Pages docs sync, and pages that needed better internal links. The project improved because the bugs were real, not imagined.</p>
        </section>

        <section class='card' id='step-5'>
          <h2>Step 5 - ChatGPT Reviews the Problem</h2>
          <p>When I find a problem, I often send the screenshot or error back to ChatGPT first. I do this because the first question is not always "what code should change?" The first question is usually "what is actually wrong?"</p>
          <p>ChatGPT helps me interpret the issue and create a debugging prompt. If a page has mixed language, the prompt should mention source content, templates, generated docs, language switcher, hreflang, and validation. If a layout block overlaps content, the prompt should mention CSS classes, sticky behavior, mobile behavior, and where the generated HTML lives.</p>
          <p>This turns a messy bug report into a focused task for Codex. Instead of asking Codex to "fix the site," I ask it to inspect specific files, identify the generator, patch the source, rebuild, sync docs, and run tests.</p>
        </section>

        <section class='card' id='step-6'>
          <h2>Step 6 - Codex Fixes and Improves the Project</h2>
          <p>I use Codex when the project needs careful repair. Codex is good for fixing bugs, cleaning code, refactoring logic, improving SEO output, fixing routes, adjusting language switching, and making the project more production-ready.</p>
          <p>The key is context. Codex performs much better when I give it a clear problem, the expected behavior, the files to inspect, and the commands to run. It is not magic. It still needs a target. But when the target is clear, it can move through the codebase, patch the right source files, rebuild the static output, and check whether the result passes validation.</p>
          <p>In my workflow, Codex is the final fixer. It is not always the fastest tool for creating a first screen from nothing, but it is strong when the project already exists and needs to become stable.</p>
        </section>

        <section class='card' id='real-example'>
          <h2>Real Example</h2>
          <p>A practical example is this AI coding tools review website. At first, the site had many moving parts: review pages, comparison pages, pricing pages, bilingual English and Vietnamese output, sitemap generation, FAQ schema, internal links, CTA tracking, and a dashboard for content workflow.</p>
          <p>Some pages had mixed English and Vietnamese content. Some comparison pages needed better internal links. Some pages needed cleaner SEO metadata. A few layout issues only became obvious after opening the live page in the browser. I did not treat those problems as proof that AI failed. I treated them as input for the next loop.</p>
          <p>I used ChatGPT to describe the problem clearly. Then I used Windsurf or Codex to update the code. Then I tested again. Over time, the site became more useful: it now includes pages such as the <a href='/category/ai-coding-tools/'>AI coding tools category</a>, <a href='/cursor/'>Cursor review</a>, <a href='/windsurf-review/'>Windsurf review</a>, <a href='/comparisons/cursor-vs-windsurf/'>Cursor vs Windsurf comparison</a>, <a href='/comparisons/copilot-vs-cursor/'>Copilot vs Cursor comparison</a>, and <a href='/best-ai-coding-tools-2026/'>Best AI Coding Tools 2026</a>.</p>
          <p>The same workflow also applies to other ideas I am exploring, including the MsSmileEnglish website/app, an SEO content system, an AI workflow bot, a parent-child connection app idea, and a video creation tool idea. The pattern is the same: explain the idea, build a first version, test the result, then fix what is real.</p>
        </section>

        <section class='card' id='comparison-table'>
          <h2>Comparison Table</h2>
          <div class='table-wrap'><table><thead><tr><th>Tool</th><th>My Role for This Tool</th><th>Best Use</th><th>Weakness</th></tr></thead><tbody>
            <tr><td>ChatGPT</td><td>Planner and prompt writer</td><td>Ideas, structure, debugging prompts</td><td>Does not automatically fix the whole project unless connected to files</td></tr>
            <tr><td>Windsurf</td><td>First builder</td><td>Fast project generation and UI</td><td>First version may need cleanup</td></tr>
            <tr><td>Codex</td><td>Final fixer</td><td>Debugging, refactoring, polishing</td><td>Needs clear context and focused prompts</td></tr>
          </tbody></table></div>
        </section>

        <section class='card' id='non-developers'>
          <h2>Why This Workflow Helps Non-Developers</h2>
          <p>If you are not a professional developer, the biggest advantage of this workflow is that you do not need to know everything before starting. You need to know what you are trying to build and how to describe the problem clearly.</p>
          <p>You can start with a plain idea: "I want a page that explains my AI workflow and links to my review site." ChatGPT can help you turn that into requirements. Windsurf can create a first version. Codex can fix problems after you test it. Each round teaches you more about the project.</p>
          <p>Screenshots, logs, and clear prompts become your practical language. You do not have to understand every line of code at the beginning, but you do need to inspect the result. AI tools are much better when each one has a clear role and when you give them real feedback from the project.</p>
        </section>

        <section class='card' id='where-site-fits'>
          <h2>Where My Bot/Website Fits In</h2>
          <p>My bot and website are where I organize this AI building workflow. Instead of keeping every experiment inside private chat history, I use the site to document what I learn, publish practical comparisons, and share the mistakes that happen when building real projects with AI.</p>
          <p>The site is not only a review site. It is also a record of the process: how I create SEO pages, how I compare tools, how I fix language problems, how I prepare social drafts, how I check sitemap and structured data, and how I keep the workflow safe before publishing.</p>
          <p>If you want to follow the same process, start with the <a href='/about/'>build-in-public story</a>, read the <a href='/reviews/'>AI tool reviews</a>, compare tools in the <a href='/comparisons/'>comparison hub</a>, or download the <a href='/free-ai-coding-workflow-checklist/'>AI coding workflow checklist</a>.</p>
          <div class='cta-row'><a class='btn' href='/free-ai-coding-workflow-checklist/'>Learn How I Build Projects With AI</a><a class='btn secondary' href='/reviews/'>See My AI Coding Tools Reviews</a></div>
        </section>

        <section class='card' id='final-recommendation'>
          <h2>Final Recommendation</h2>
          <p>If you are trying to build a website, app, bot, or automation project with AI, do not ask which single tool is the best. That question usually leads to shallow answers.</p>
          <p>Build a workflow instead: ChatGPT for thinking and prompts. Windsurf for the first build. Codex for fixing and polishing. Then test, document, and improve the process step by step.</p>
          <p>This approach is slower than believing in a one-click demo, but it is much closer to how real projects become usable.</p>
        </section>

        <section class='card' id='faq'>
          <h2>FAQ</h2>
          <details><summary>Can I build apps with AI if I am not a developer?</summary><p>Yes, but you should start with small, testable projects. AI can help you plan, create a first version, and fix problems, but you still need to review the output and test the workflow carefully.</p></details>
          <details><summary>Why use ChatGPT before Windsurf?</summary><p>ChatGPT helps turn a rough idea into a clearer plan. That makes the prompt stronger before Windsurf starts creating files, pages, routes, or UI.</p></details>
          <details><summary>Why not use Windsurf alone?</summary><p>Windsurf is fast for a first build, but first versions often need cleanup. I prefer using ChatGPT for planning and Codex for focused debugging after I test the project.</p></details>
          <details><summary>What is Codex best for?</summary><p>Codex is strongest when I give it a clear issue inside an existing project: fixing bugs, refactoring logic, improving SEO output, adjusting routes, or cleaning production problems.</p></details>
          <details><summary>What is the best workflow for building AI projects?</summary><p>My current workflow is: idea, ChatGPT prompt, Windsurf first version, manual testing, screenshot or error review, Codex fix, and another test cycle.</p></details>
        </section>

        <section class='card related'><h2>Related pages</h2><p><a href='/cursor/'>Cursor review</a> <a href='/windsurf-review/'>Windsurf review</a> <a href='/github-copilot/'>GitHub Copilot review</a> <a href='/comparisons/copilot-vs-cursor/'>Copilot vs Cursor</a> <a href='/best-ai-coding-tools-2026/'>Best AI Coding Tools 2026</a></p></section>
        {newsletter_html()}
      </div>
    </article>"""


def write_reviews_page(output: Path, pages: list[dict]) -> None:
    folder = output / "reviews"
    folder.mkdir(parents=True, exist_ok=True)
    cards = "\n".join(card_html(page, extra_class="review-card") for page in pages)
    page = page_shell(
        "Reviews",
        "Browse AI and SaaS reviews by product, category, score, and risk level.",
        f'<section><h1>Latest Reviews</h1><p>Browse practical AI and SaaS tool reviews for research and comparison.</p><label for="reviewSearch">Search reviews by tool or category</label><input class="search" id="reviewSearch" type="search"><div class="cards" id="reviewGrid">{cards}</div></section><script>const q=document.getElementById("reviewSearch");const cards=[...document.querySelectorAll(".review-card")];q.addEventListener("input",()=>{{const v=q.value.toLowerCase();cards.forEach(c=>c.style.display=c.innerText.toLowerCase().includes(v)?"block":"none")}});</script>',
        "/reviews/",
    )
    (folder / "index.html").write_text(page, encoding="utf-8")


def write_comparisons_page(output: Path, pages: list[dict]) -> None:
    folder = output / "comparisons"
    folder.mkdir(parents=True, exist_ok=True)
    english_intro = (
        "A list of high-intent comparison pages written for pre-purchase research. "
        "Content helps readers compare tools by use case, workflow, pricing notes, and vendor fit."
    )

    def comparison_anchor(slug: str, left: str, right: str) -> str:
        if slug == "synthesia-vs-runway":
            return "Synthesia vs Runway comparison"
        return f"{left} vs {right}"

    def english_quick_recommendation(slug: str, left: str, right: str, category: str) -> str:
        english_recommendations = {
            "chatgpt-vs-gemini": "Choose ChatGPT for flexible general AI assistance; choose Gemini if your workflow is heavily tied to Google Workspace.",
            "chatgpt-vs-claude": "Choose ChatGPT for broad daily workflows; choose Claude if long-document reading, summarization, and careful analysis matter more.",
            "cursor-vs-windsurf": "Choose Cursor for an established AI coding editor; test Windsurf if you want to compare newer agent-style coding workflows.",
            "cursor-vs-vscode": "Choose Cursor when AI is central to the coding workflow; choose VS Code when extension depth and familiar setup matter more.",
            "framer-vs-webflow": "Choose Framer for fast landing pages and visual iteration; choose Webflow for CMS-heavy sites and structured website operations.",
            "synthesia-vs-runway": "Choose Synthesia for presenter-style product videos; choose Runway for generative video experiments and creative editing workflows.",
        }
        if slug in english_recommendations:
            return english_recommendations[slug]
        if slug == "synthesia-vs-runway":
            return "Choose Synthesia for presenter-style product videos; choose Runway for generative video experiments and creative editing workflows."
        return f"Compare {left} and {right} by use case, workflow fit, pricing notes, and vendor fit before choosing a {category}."

    topic_rows = "\n".join(
        f"<tr><td><a href='/comparisons/{html.escape(slug)}/'>{html.escape(comparison_anchor(slug, left, right))}</a></td><td>{html.escape(category)}</td><td>{html.escape(english_quick_recommendation(slug, left, right, category))}</td></tr>"
        for slug, left, right, category, _, _, recommendation in COMPARISON_TOPICS
    )
    review_rows = "\n".join(
        f"<tr><td><a href='/{html.escape(page['slug'])}/'>{html.escape(page['brand_name'])}</a></td><td>{html.escape(page['niche'])}</td><td>{html.escape(page['score'])}</td><td>{html.escape(page['risk'])}</td></tr>"
        for page in pages[:12]
    )
    body = f"""<nav class='breadcrumb'><a href='/'>Home</a> / Comparisons</nav>
    <section class='card'><h1>Comparisons AI/SaaS tools</h1><p>{english_intro}</p></section>
    <section class='card'><h2>High-intent comparison pages</h2><table><thead><tr><th>Comparison keyword</th><th>Category</th><th>Quick recommendation</th></tr></thead><tbody>{topic_rows}</tbody></table></section>
    <section class='card'><h2>Related reviews</h2><table><thead><tr><th>Tool</th><th>Category</th><th>Score</th><th>Risk</th></tr></thead><tbody>{review_rows}</tbody></table></section>"""
    (folder / "index.html").write_text(page_shell("Comparisons", "Compare AI and SaaS tools by category, score, risk, and research notes.", body, "/comparisons/"), encoding="utf-8")


def write_about_page(output: Path) -> None:
    folder = output / "about"
    folder.mkdir(parents=True, exist_ok=True)
    body = f"""<section class="card"><h1>About {html.escape(settings.site_name)}</h1>
    <p>{html.escape(settings.site_name)} is a practical AI tools review hub focused on real workflow questions, not polished software demos.</p>
    <p>The site covers AI coding tools, SEO tools, automation software, and builder workflows. The goal is to help readers understand where a tool fits, where it fails, what needs manual verification, and whether it is worth adding to a shortlist.</p>
    <p>Most pages are written from a research-first perspective: compare the workflow, check pricing risk, verify official terms, and avoid exaggerated claims. We do not promise outcomes, rankings, revenue, or guaranteed productivity.</p>
    <p>Contact: <a href="mailto:{html.escape(settings.contact_email)}">{html.escape(settings.contact_email)}</a></p></section>"""
    (folder / "index.html").write_text(page_shell("About", "About this practical AI coding, SEO, automation, and workflow review hub.", body, "/about/"), encoding="utf-8")


def write_category_pages(output: Path, pages: list[dict]) -> None:
    categories = {
        "ai-video-tools": ("AI Video Tools", lambda p: "Video" in p["niche"] or p["slug"] in {"synthesia", "runway", "descript"}),
        "ai-voice-tools": ("AI Voice Tools", lambda p: "Voice" in p["niche"] or p["slug"] in {"elevenlabs"}),
        "ai-coding-tools": ("AI Coding Tools", lambda p: "Coding" in p["niche"] or p["slug"] in {"cursor", "github-copilot"}),
        "ai-seo-tools": ("AI SEO Tools", lambda p: "SEO" in p["niche"] or p["slug"] in {"surfer-seo", "semrush"}),
        "ai-automation-tools": ("AI Automation Tools", lambda p: "Automation" in p["niche"] or p["slug"] in {"zapier", "make"}),
        "crm-tools": ("CRM Tools", lambda p: "CRM" in p["niche"] or p["slug"] in {"hubspot", "pipedrive", "pipedrive-crm"}),
        "website-builders": ("Website Builders", lambda p: "Website" in p["niche"] or p["slug"] in {"webflow", "webflow-ai", "framer", "durable"}),
        "ai-presentation-tools": ("AI Presentation Tools", lambda p: p["slug"] in {"gamma", "canva"}),
        "ai-writing-tools": ("AI Writing Tools", lambda p: "Writing" in p["niche"] or p["slug"] in {"jasper", "jasper-ai", "copy-ai"}),
        "ai-customer-support-tools": ("AI Customer Support Tools", lambda p: "Customer" in p["niche"] or p["slug"] in {"hubspot"}),
        "ai-writing": ("AI Writing", lambda p: "Writing" in p["niche"] or "AI" in p["niche"]),
        "automation": ("Automation", lambda p: "Automation" in p["niche"] or "Productivity" in p["niche"]),
        "crm": ("CRM", lambda p: "CRM" in p["niche"]),
    }
    category_root = output / "category"
    category_root.mkdir(parents=True, exist_ok=True)
    for slug, (title, predicate) in categories.items():
        folder = category_root / slug
        folder.mkdir(parents=True, exist_ok=True)
        selected = [page for page in pages if predicate(page)]
        related = ""
        if slug == "ai-video-tools":
            related = """<section class="card"><h2>Related AI video comparisons</h2>
            <p>For avatar-led product explainers versus generative video workflows, read the <a href="/comparisons/synthesia-vs-runway/">Synthesia vs Runway comparison</a>. You can also compare <a href="/comparisons/runway-vs-pika/">Runway vs Pika</a> and <a href="/comparisons/synthesia-vs-heygen/">Synthesia vs HeyGen</a> before choosing a video workflow.</p></section>"""
        body = f'<section><h1>{html.escape(title)}</h1><p>Reviews and comparisons for {html.escape(title.lower())} tools.</p><div class="cards">{"".join(card_html(page) for page in selected)}</div></section>{related}'
        (folder / "index.html").write_text(page_shell(title, f"Browse {title} reviews and SaaS comparison notes.", body, f"/category/{slug}/"), encoding="utf-8")


def write_comparison_detail_pages(output: Path) -> None:
    root = output / "comparisons"
    root.mkdir(parents=True, exist_ok=True)
    for slug, left, right, category, left_strength, right_strength, recommendation in COMPARISON_TOPICS:
        folder = root / slug
        folder.mkdir(parents=True, exist_ok=True)
        if slug == "synthesia-vs-runway":
            (folder / "index.html").write_text(render_synthesia_runway_comparison_page(slug), encoding="utf-8")
            continue
        title = f"{left} vs {right}"
        left_url = review_url_for(left)
        right_url = review_url_for(right)
        faq_questions = [
            f"{left} vs {right}: which tool should you choose?",
            f"Who should use {left}?",
            f"Who should use {right}?",
            "How should you compare pricing?",
            "Does this page use affiliate links?",
        ]
        faq = faq_html(faq_questions)
        left_pros = [left_strength, "Phù hợp khi nhu cầu chính trùng với thế mạnh của công cụ.", "Đáng đưa vào shortlist nếu pricing và policy phù hợp."]
        right_pros = [right_strength, "Phù hợp khi workflow của bạn cần thế mạnh riêng của công cụ này.", "Đáng kiểm tra nếu bạn muốn một lựa chọn thay thế thực tế."]
        left_cons = ["Có thể không phù hợp nếu workflow của bạn cần thế mạnh của công cụ còn lại.", "Cần kiểm tra pricing, giới hạn plan và điều khoản chính thức."]
        right_cons = ["Có thể không phù hợp nếu workflow của bạn cần thế mạnh của công cụ còn lại.", "Cần kiểm tra pricing, giới hạn plan và điều khoản chính thức."]
        list_left_pros = "".join(f"<li>{html.escape(item)}</li>" for item in left_pros)
        list_right_pros = "".join(f"<li>{html.escape(item)}</li>" for item in right_pros)
        list_left_cons = "".join(f"<li>{html.escape(item)}</li>" for item in left_cons)
        list_right_cons = "".join(f"<li>{html.escape(item)}</li>" for item in right_cons)
        schemas = comparison_schemas(title, slug, left, right, category, recommendation, faq_questions)
        body = f"""<nav class='breadcrumb'><a href='/'>Home</a> / <a href='/comparisons/'>Comparisons</a> / {html.escape(title)}</nav>
        {schemas}
        <article class='review-layout'><aside class='card toc'><h2>Nội dung</h2><a href='#overview'>Overview</a><a href='#table'>Feature comparison</a><a href='#pricing'>Pricing comparison</a><a href='#best-for'>Best for</a><a href='#pros-cons'>Pros and cons</a><a href='#faq'>FAQ</a><a href='#verdict'>Final recommendation</a></aside><div>
        <section class="card" id="overview"><h1>{html.escape(title)}</h1><p><strong>Khuyến nghị nhanh:</strong> {html.escape(recommendation)}</p><p>Trang so sánh {html.escape(title)} này dành cho người đang tìm kiếm {html.escape(category)} và muốn hiểu khác biệt thực tế trước khi đăng ký. Nội dung tập trung vào use case, pricing note, pros/cons và bước kiểm tra cần làm trước khi mua.</p><p class='muted'>7 min read | Last updated {date.today().isoformat()}</p>{share_buttons(f'/comparisons/{slug}/', title)}</section>
        <section class="card trust"><strong>Affiliate disclosure:</strong> Some links may be affiliate links. We may earn a commission at no extra cost to you.</section>
        <section class="card" id="table"><h2>Feature comparison table</h2><table><thead><tr><th>Tiêu chí</th><th>{html.escape(left)}</th><th>{html.escape(right)}</th></tr></thead><tbody><tr><td>Thế mạnh chính</td><td>{html.escape(left_strength)}</td><td>{html.escape(right_strength)}</td></tr><tr><td>Loại người dùng phù hợp</td><td>Người dùng có workflow trùng với thế mạnh của {html.escape(left)}.</td><td>Người dùng có workflow trùng với thế mạnh của {html.escape(right)}.</td></tr><tr><td>Pricing</td><td>Kiểm tra website chính thức để xem giá mới nhất.</td><td>Kiểm tra website chính thức để xem giá mới nhất.</td></tr><tr><td>Internal review</td><td><a href='{html.escape(left_url)}'>Đọc review {html.escape(left)}</a></td><td><a href='{html.escape(right_url)}'>Đọc review {html.escape(right)}</a></td></tr></tbody></table></section>
        <section class="card" id="pricing"><h2>Pricing comparison</h2><p>Không nên dựa vào giá cũ. Hãy kiểm tra website chính thức của {html.escape(left)} và {html.escape(right)} để xác nhận plan hiện tại, giới hạn sử dụng, trial, điều khoản hủy và quyền dùng thương mại.</p></section>
        <section class="grid" id="best-for"><div class="card"><h2>Ai nên chọn {html.escape(left)}?</h2><p>{html.escape(left_strength)}</p><p>Chọn {html.escape(left)} nếu đây là nhu cầu chính trong workflow của bạn.</p></div><div class="card"><h2>Ai nên chọn {html.escape(right)}?</h2><p>{html.escape(right_strength)}</p><p>Chọn {html.escape(right)} nếu workflow của bạn cần thế mạnh này hơn.</p></div></section>
        <section class="grid" id="pros-cons"><div class="card"><h2>{html.escape(left)} pros</h2><ul>{list_left_pros}</ul><h2>{html.escape(left)} cons</h2><ul>{list_left_cons}</ul></div><div class="card"><h2>{html.escape(right)} pros</h2><ul>{list_right_pros}</ul><h2>{html.escape(right)} cons</h2><ul>{list_right_cons}</ul></div></section>
        <section class="card"><h2>CTA</h2><p>Đọc cả hai review liên quan, kiểm tra pricing chính thức, sau đó chọn công cụ phù hợp nhất với workflow thật của bạn.</p><p><a class='btn' href='{html.escape(left_url)}'>Đọc review {html.escape(left)}</a><a class='btn secondary' href='{html.escape(right_url)}'>Đọc review {html.escape(right)}</a></p></section>
        <section class="card" id="faq"><h2>FAQ</h2>{faq}</section>
        <section class="card trust"><h2>Affiliate disclosure</h2><p>Some links may be affiliate links. We may earn a commission at no extra cost to you.</p></section>
        <section class="card" id="verdict"><h2>Final recommendation</h2><p>{html.escape(recommendation)}</p><p>Đây là trang nghiên cứu, không phải cam kết kết quả. Trước khi mua hoặc quảng bá affiliate, hãy kiểm tra pricing, terms, privacy, traffic policy và quyền dùng thương mại trên website chính thức.</p><p><a class='btn' href='{html.escape(left_url)}'>Đọc review {html.escape(left)}</a><a class='btn secondary' href='{html.escape(right_url)}'>Đọc review {html.escape(right)}</a></p></section>{newsletter_html()}</div></article>"""
        (folder / "index.html").write_text(page_shell(title, f"So sánh {left} vs {right}: overview, feature comparison, pricing, best for, pros/cons, FAQ và khuyến nghị cuối.", body, f"/comparisons/{slug}/"), encoding="utf-8")


def render_synthesia_runway_comparison_page(slug: str) -> str:
    title = "Synthesia vs Runway"
    path = f"/comparisons/{slug}/"
    description = "Synthesia vs Runway comparison for marketers, creators, and product demos. Compare avatar videos, generative video workflows, pricing checks, pros, cons, and use cases."
    faq_questions = [
        "Is Synthesia better than Runway for product demos?",
        "Is Runway better for creators and visual experiments?",
        "How should I compare Synthesia and Runway pricing?",
        "Can I use these AI video tools for marketing content?",
        "Which AI video tool should a small team try first?",
    ]
    body = f"""<nav class='breadcrumb'><a href='/'>Home</a> / <a href='/comparisons/'>Comparisons</a> / Synthesia vs Runway</nav>
<article class='review-layout'>
  <aside class='card toc'><h2>Contents</h2><a href='#overview'>Overview</a><a href='#verdict'>Quick verdict</a><a href='#best-for'>Best for table</a><a href='#features'>Feature comparison</a><a href='#workflow'>Video workflow comparison</a><a href='#pricing'>Pricing and usage considerations</a><a href='#pros-cons'>Pros and cons</a><a href='#choose'>Which should you choose?</a><a href='#faq'>FAQ</a></aside>
  <div>
    <section class='card' id='overview'>
      <h1>Synthesia vs Runway</h1>
      <p><strong>Synthesia vs Runway is not a simple AI video generator comparison.</strong> Synthesia is built around controlled presenter-style videos with avatars, scripts, and repeatable business messaging. Runway is built around generative video creation, visual experimentation, editing, and creative iteration.</p>
      <p>If you are a marketer creating training videos, onboarding explainers, or product demo narration, Synthesia is usually easier to evaluate first. If you are a creator, designer, or product marketer testing visual concepts, motion ideas, or short-form creative scenes, Runway is usually the more flexible creative tool.</p>
      <p class='muted'>7 min read | Last updated {date.today().isoformat()}</p>{share_buttons(path, title)}
    </section>
    <section class='card trust'><strong>Affiliate disclosure:</strong> Some links may be affiliate links. We may earn a commission at no extra cost to you. Current CTA routes use official or approved destinations only; no fake affiliate link is created here.</section>
    <section class='card' id='verdict'>
      <h2>Quick verdict</h2>
      <p>Choose <strong>Synthesia</strong> if you need structured avatar videos, product explainers, training clips, sales enablement videos, or repeatable messaging where the script is more important than cinematic experimentation.</p>
      <p>Choose <strong>Runway</strong> if you need generative video experiments, visual exploration, social creative, concept testing, editing workflows, or a tool that helps you create and refine scenes rather than present a script through an avatar.</p>
      <p>The safest workflow is to test one real asset in both tools: one product demo script for Synthesia and one visual concept or short scene for Runway. Then compare review time, output quality, export constraints, and how much manual editing remains.</p>
    </section>
    <section class='card' id='best-for'>
      <h2>Best for table</h2>
      <table><thead><tr><th>Use case</th><th>Synthesia</th><th>Runway</th></tr></thead><tbody>
        <tr><td>Product demos</td><td>Strong when the demo is script-led, presenter-style, and needs a consistent voice or avatar.</td><td>Better when the demo needs visual concept shots, dynamic scenes, or creative video transitions.</td></tr>
        <tr><td>Marketing teams</td><td>Good for repeatable explainers, training, internal enablement, and localized business messaging.</td><td>Good for campaign visuals, short-form creative tests, and experimental assets for social or ads.</td></tr>
        <tr><td>Creators</td><td>Useful if the creator wants a controlled spokesperson-style format.</td><td>More flexible for creators who want to iterate on style, movement, mood, and visual storytelling.</td></tr>
        <tr><td>Review friction</td><td>Review focuses on script, avatar, pronunciation, branding, and compliance.</td><td>Review focuses on visual consistency, prompt quality, scene quality, rights, and editability.</td></tr>
      </tbody></table>
    </section>
    <section class='card' id='features'>
      <h2>Feature comparison</h2>
      <p>Synthesia is easier to understand as a business video system: start with a script, choose an avatar or presentation style, review the spoken result, and export a polished explainer. That makes it practical for teams that want predictable output more than experimental visuals.</p>
      <p>Runway is closer to a creative video lab. The workflow is less about a talking-head script and more about generating, editing, extending, and refining visual assets. It can be more powerful for creative work, but it may also require more review time and stronger visual direction.</p>
      <table><thead><tr><th>Feature area</th><th>Synthesia</th><th>Runway</th></tr></thead><tbody>
        <tr><td>Avatar / presenter workflow</td><td>Core strength.</td><td>Not the main reason to choose it.</td></tr>
        <tr><td>Generative video</td><td>Secondary compared with script-led production.</td><td>Core strength.</td></tr>
        <tr><td>Editing flexibility</td><td>Good for structured business video revisions.</td><td>Stronger for visual iteration and creative edits.</td></tr>
        <tr><td>Team review</td><td>Usually easier when stakeholders review a script and presenter output.</td><td>Better when stakeholders can review visual direction and creative variants.</td></tr>
      </tbody></table>
    </section>
    <section class='card' id='workflow'>
      <h2>Video generation workflow comparison</h2>
      <p>For Synthesia, I would start with a short product demo script, define the audience, decide whether the tone should be educational or sales-oriented, and check whether the avatar delivery feels natural enough for the brand. The key question is whether the output saves presenter recording time without making the demo feel artificial.</p>
      <p>For Runway, I would start with a visual brief instead of a script. The prompt should describe scene style, motion, mood, camera feel, and intended use. The key question is whether the generated clips are good enough to support the campaign after editing, not whether the first output is perfect.</p>
      <p>This is why the comparison matters: Synthesia helps turn words into structured video communication, while Runway helps turn visual ideas into experimental video assets.</p>
    </section>
    <section class='card' id='pricing'>
      <h2>Pricing and usage considerations</h2>
      <p>Do not rely on old pricing screenshots for either tool. Check official pricing before buying, including plan limits, video minutes or credits, export quality, watermark rules, commercial usage rights, team seats, cancellation terms, and whether the workflow you need is included in the plan.</p>
      <p>For marketing and product teams, usage limits matter as much as the monthly price. One tool may look cheaper until you need more exports, more seats, higher quality output, or different commercial rights.</p>
      <p><a class='btn' href='/go/synthesia/?src=comparisons/synthesia-vs-runway&cta=pricing_check' rel='nofollow sponsored'>Check Synthesia official pricing</a><a class='btn secondary' href='/go/runway/?src=comparisons/synthesia-vs-runway&cta=pricing_check' rel='nofollow sponsored'>Check Runway official pricing</a></p>
    </section>
    <section class='grid' id='pros-cons'>
      <div class='card'><h2>Pros and cons of Synthesia</h2><h3>Pros</h3><ul><li>Strong fit for presenter-style training, onboarding, and product explainers.</li><li>More predictable when the message is script-led.</li><li>Easier for teams that need repeatable business video formats.</li></ul><h3>Cons</h3><ul><li>Less flexible for cinematic or experimental visual concepts.</li><li>Avatar delivery still needs human review for tone and trust.</li><li>Plan limits and commercial usage terms should be verified before scaling.</li></ul></div>
      <div class='card'><h2>Pros and cons of Runway</h2><h3>Pros</h3><ul><li>Strong fit for generative video, visual experiments, and creative iteration.</li><li>Useful for campaign concepts, social creative, and product mood videos.</li><li>Better when the goal is visual exploration rather than a fixed presenter script.</li></ul><h3>Cons</h3><ul><li>Outputs may need more review and editing before they are client-ready.</li><li>Prompt quality and creative direction matter a lot.</li><li>Usage credits, export rights, and consistency should be checked carefully.</li></ul></div>
    </section>
    <section class='card' id='choose'>
      <h2>Which should you choose?</h2>
      <p>Choose Synthesia if your team needs a repeatable way to explain products, train users, onboard customers, or turn a script into a polished business video. Choose Runway if your team needs a creative engine for visual testing, generative clips, social concepts, or product mood pieces.</p>
      <p>If neither feels like a perfect fit, compare the broader AI video category before buying. Useful next pages include <a href='/best-ai-video-tools-2026/'>Best AI Video Tools 2026</a>, <a href='/category/video-tools/'>Video Tools category</a>, <a href='/comparisons/runway-vs-pika/'>Runway vs Pika</a>, and <a href='/comparisons/synthesia-vs-heygen/'>Synthesia vs HeyGen</a>.</p>
      <p><a class='btn' href='/go/synthesia/?src=comparisons/synthesia-vs-runway&cta=comparison_page' rel='nofollow sponsored'>Visit Synthesia official site</a><a class='btn secondary' href='/go/runway/?src=comparisons/synthesia-vs-runway&cta=comparison_page' rel='nofollow sponsored'>Visit Runway official site</a></p>
    </section>
    <section class='card' id='faq'><h2>FAQ</h2>{faq_html(faq_questions)}</section>
    {newsletter_html()}
  </div>
</article>"""
    return page_shell(title, description, body, path)


def review_url_for(brand: str) -> str:
    mapping = {
        "Canva": "/canva/",
        "Make": "/make/",
        "Zapier": "/zapier/",
        "Surfer SEO": "/surfer-seo/",
        "Semrush": "/semrush/",
        "Webflow": "/webflow/",
        "Webflow AI": "/webflow-ai/",
        "Framer": "/framer/",
        "Copy.ai": "/copy-ai/",
        "Jasper": "/jasper/",
        "ElevenLabs": "/elevenlabs/",
        "HubSpot": "/hubspot/",
        "Pipedrive": "/pipedrive/",
        "Cursor": "/cursor/",
        "GitHub Copilot": "/github-copilot/",
        "Synthesia": "/synthesia/",
        "Runway": "/runway/",
        "Notion": "/notion/",
        "Notion AI": "/notion-ai/",
        "Gamma": "/gamma/",
    }
    return mapping.get(brand, "/reviews/")


def comparison_schemas(title: str, slug: str, left: str, right: str, category: str, recommendation: str, faq_questions: list[str]) -> str:
    base = (settings.base_site_url or settings.site_domain or "https://yourdomain.com").rstrip("/")
    url = f"{base}/comparisons/{slug}/"
    review_schema = {
        "@context": "https://schema.org",
        "@type": "Review",
        "itemReviewed": {
            "@type": "SoftwareApplication",
            "name": f"{left} vs {right}",
            "applicationCategory": category,
        },
        "name": title,
        "url": url,
        "reviewBody": recommendation,
        "author": {"@type": "Person", "name": "Nguyen Quoc Tuan"},
        "publisher": {"@type": "Organization", "name": settings.site_name},
    }
    scripts = []
    if slug != "framer-vs-webflow":
        faq_schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": question,
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Use this page as a research starting point, then verify pricing, terms, policy, and workflow fit on the official website before buying or promoting either tool.",
                    },
                }
                for question in faq_questions
                if str(question).strip()
            ],
        }
        if faq_schema["mainEntity"]:
            scripts.append(f'<script type="application/ld+json">{json.dumps(faq_schema, ensure_ascii=False)}</script>')
    scripts.append(f'<script type="application/ld+json">{json.dumps(review_schema, ensure_ascii=False)}</script>')
    return "".join(scripts)


def write_trust_pages(output: Path) -> None:
    pages = {
        "about-author": ("About Author", "<section class='card'><h1>About the Author</h1><p><strong>Nguyen Quoc Tuan</strong> is an Independent AI & SaaS Researcher researching AI tools, SaaS software, automation systems, and productivity workflows.</p></section>"),
        "author-profile": ("Author Profile", "<section class='card'><h1>Author Profile</h1><p><strong>Nguyen Quoc Tuan</strong><br>Independent AI & SaaS Researcher</p><p>Researching AI tools, SaaS software, automation systems, and productivity workflows.</p></section>"),
        "editorial-policy": ("Editorial Policy", "<section class='card'><h1>Editorial Policy</h1><p>Reviews are written for research and comparison. We do not publish fake guarantees, fake users, fake traffic counters, or misleading claims. Affiliate relationships are disclosed clearly.</p></section>"),
        "how-we-review-tools": ("How We Review Tools", "<section class='card'><h1>How We Review Tools</h1><p>Our review process considers public feature information, pricing notes, UI evaluation, workflow comparison, user feedback research, alternatives, limitations, and affiliate transparency.</p></section>"),
        "testing-methodology": ("Testing Methodology", "<section class='card'><h1>Testing Methodology</h1><p>We review tools through public feature research, pricing review, UI and workflow evaluation, comparison against alternatives, policy checks, and affiliate transparency checks. When hands-on testing is not completed, the page is marked as research-based and should be verified against the official vendor website.</p></section>"),
    }
    for slug, (title, body) in pages.items():
        folder = output / slug
        folder.mkdir(parents=True, exist_ok=True)
        robots = "noindex,follow" if slug in NOINDEX_EXACT_PATHS else "index,follow"
        (folder / "index.html").write_text(page_shell(title, f"{title} for AI Tool Review Hub.", body, f"/{slug}/", robots=robots), encoding="utf-8")


def copy_user_published_pages(output: Path) -> list[dict]:
    source_root = settings.data_dir / "published_static_pages"
    if not source_root.exists():
        return []
    pages = []
    for source in source_root.glob("*/index.html"):
        slug = source.parent.name
        target_dir = output / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_dir / "index.html")
        title = slug.replace("-", " ").title()
        pages.append(
            {
                "brand_name": title,
                "slug": slug,
                "source": source,
                "niche": "Published Draft",
                "score": "N/A",
                "risk": "Human approved",
                "description": f"Human-approved published draft: {title}.",
                "deploy_path": str((target_dir / "index.html").resolve()),
                "url_path": f"/{slug}/",
            }
        )
    return pages


def page_shell(
    title: str,
    description: str,
    body: str,
    path: str | None = None,
    image_path: str = "/assets/og/site.svg",
    page_type: str = "article",
    robots: str = "index,follow",
) -> str:
    base = (settings.base_site_url or settings.site_domain or "https://yourdomain.com").rstrip("/")
    canonical = base + (path or f"/{title.lower().replace(' ', '-')}/")
    schema_items = base_schemas(title, description, canonical)
    schema_items.append(json.dumps({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Home", "item": f"{base}/"}, {"@type": "ListItem", "position": 2, "name": title, "item": canonical}]}, ensure_ascii=False))
    if (path or "") not in FAQ_SCHEMA_DISABLED_PATHS and ("FAQ" in body or "<details" in body):
        schema_items.append(json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": f"What should I verify before using {title}?", "acceptedAnswer": {"@type": "Answer", "text": "Verify current pricing, terms, integrations, limitations, and official vendor policy before buying or promoting any tool."}}]}, ensure_ascii=False))
    schemas = "\n".join(
        f'<script type="application/ld+json">{schema}</script>'
        for schema in schema_items
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)} - {html.escape(settings.site_name)}</title><meta name="description" content="{html.escape(description)}"><meta name="robots" content="{html.escape(robots, quote=True)}"><link rel="canonical" href="{html.escape(canonical, quote=True)}"><link rel="alternate" type="application/rss+xml" title="{html.escape(settings.site_name)} RSS" href="{html.escape(site_url('/rss.xml'), quote=True)}"><meta property="og:title" content="{html.escape(title)} - {html.escape(settings.site_name)}"><meta property="og:description" content="{html.escape(description)}"><meta property="og:type" content="{html.escape(page_type)}"><meta property="og:image" content="{html.escape(site_url(image_path), quote=True)}"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{html.escape(site_url(image_path), quote=True)}"><meta name="google-site-verification" content="{html.escape(settings.google_site_verification, quote=True)}">{analytics_snippet()}{schemas}<style>{base_css()}</style></head>
<body>{nav_html()}<main class="wrap legal">{body}</main>{footer_html()}</body></html>"""


def write_legal_pages(output: Path) -> None:
    for slug, (title, body) in legal_pages().items():
        folder = output / slug
        folder.mkdir(parents=True, exist_ok=True)
        robots = "noindex,follow" if slug in NOINDEX_EXACT_PATHS else "index,follow"
        page = page_shell(title, f"{title} for {settings.site_name}.", f"<h1>{html.escape(title)}</h1>{body}", f"/{slug}/", robots=robots)
        (folder / "index.html").write_text(page, encoding="utf-8")


def write_og_images(output: Path, pages: list[dict]) -> None:
    og_dir = output / "assets" / "og"
    og_dir.mkdir(parents=True, exist_ok=True)
    write_og_svg(og_dir / "home.svg", settings.site_name, "AI & SaaS Reviews")
    write_og_svg(og_dir / "site.svg", settings.site_name, "Independent research hub")
    write_og_svg(og_dir / "blog.svg", "AI & SaaS Blog", settings.site_name)
    for page in pages:
        write_og_svg(og_dir / f"{page['slug']}.svg", f"{page['brand_name']} Review", settings.site_name)
    for slug, title, _ in BLOG_POSTS:
        write_og_svg(og_dir / f"{slug}.svg", title, settings.site_name)


def write_og_svg(path: Path, title: str, subtitle: str) -> None:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#0f766e"/><stop offset="1" stop-color="#1e293b"/></linearGradient></defs>
  <rect width="1200" height="630" fill="url(#g)"/>
  <rect x="70" y="70" width="1060" height="490" rx="28" fill="rgba(255,255,255,.12)" stroke="rgba(255,255,255,.28)"/>
  <text x="110" y="170" fill="#d1fae5" font-family="Arial, Helvetica, sans-serif" font-size="34" font-weight="700">{html.escape(subtitle)}</text>
  <text x="110" y="300" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-size="68" font-weight="800">{html.escape(title[:42])}</text>
  <text x="110" y="410" fill="#e2e8f0" font-family="Arial, Helvetica, sans-serif" font-size="30">Research-first reviews, comparisons, and disclosure</text>
</svg>"""
    path.write_text(svg, encoding="utf-8")


def write_html_sitemap(output: Path, pages: list[dict]) -> None:
    folder = output / "sitemap"
    folder.mkdir(parents=True, exist_ok=True)
    review_links = "".join(f"<li><a href='/{html.escape(page['slug'])}/'>{html.escape(page['brand_name'])} Review</a></li>" for page in pages)
    blog_links = "".join(f"<li><a href='/blog/{html.escape(slug)}/'>{html.escape(title)}</a></li>" for slug, title, _ in BLOG_POSTS)
    static_links = "".join(f"<li><a href='/{html.escape(slug)}/'>/{html.escape(slug)}/</a></li>" for slug in CONTENT_SLUGS + CATEGORY_SLUGS + COMPARISON_SLUGS + LEGAL_SLUGS + ["blog", "media-kit"])
    body = f"<section class='card'><h1>HTML Sitemap</h1><h2>Reviews</h2><ul>{review_links}</ul><h2>Blog</h2><ul>{blog_links}</ul><h2>Site pages</h2><ul>{static_links}</ul></section>"
    (folder / "index.html").write_text(page_shell("Sitemap", "Human-readable sitemap for AI Tool Review Hub.", body, "/sitemap/", robots="noindex,follow"), encoding="utf-8")


def write_rss(output: Path, pages: list[dict] | None = None) -> None:
    base = (settings.base_site_url or settings.site_domain or "https://yourdomain.com").rstrip("/")
    blog_items = "\n".join(
        f"<item><title>{html.escape(title)}</title><link>{base}/blog/{html.escape(slug)}/</link><guid>{base}/blog/{html.escape(slug)}/</guid><description>{html.escape(summary)}</description></item>"
        for slug, title, summary in BLOG_POSTS
    )
    review_items = "\n".join(
        f"<item><title>{html.escape(page['brand_name'])} Review</title><link>{base}/{html.escape(page['slug'])}/</link><guid>{base}/{html.escape(page['slug'])}/</guid><description>{html.escape(page['description'])}</description></item>"
        for page in (pages or [])[:20]
    )
    comparison_items = "\n".join(
        f"<item><title>{html.escape(slug.split('/')[-1].replace('-', ' ').title())}</title><link>{base}/{html.escape(slug)}/</link><guid>{base}/{html.escape(slug)}/</guid><description>AI and SaaS comparison page.</description></item>"
        for slug in COMPARISON_SLUGS[:10]
    )
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>{html.escape(settings.site_name)}</title><link>{base}/</link><description>AI and SaaS reviews, comparisons, and research guides.</description>{review_items}{comparison_items}{blog_items}</channel></rss>"""
    (output / "rss.xml").write_text(rss, encoding="utf-8")


def write_media_kit(output: Path) -> None:
    folder = output / "media-kit"
    folder.mkdir(parents=True, exist_ok=True)
    body = f"""<section class='card'><h1>Media Kit</h1><p><strong>{html.escape(settings.site_name)}</strong> is an independent-style AI and SaaS review hub focused on research, comparisons, and transparent affiliate disclosure.</p><p>Contact: <a href='mailto:{html.escape(settings.contact_email)}'>{html.escape(settings.contact_email)}</a></p></section>
    <section class='grid'><div class='card'><h2>Categories</h2><ul><li>AI Tools</li><li>Marketing</li><li>CRM</li><li>Website Builders</li><li>Productivity</li></ul></div><div class='card'><h2>Social preview</h2><img loading='lazy' src='/assets/og/home.svg' alt='AI Tool Review Hub social preview' style='width:100%;border-radius:8px'></div></section>"""
    (folder / "index.html").write_text(page_shell("Media Kit", "Brand, category, contact, and social preview information.", body, "/media-kit/", robots="noindex,follow"), encoding="utf-8")


def write_aeo_action_plan(output: Path) -> None:
    folder = output / "aeo-action-plan"
    folder.mkdir(parents=True, exist_ok=True)
    sections = {
        "Technical SEO": [("Done", "Keep sitemap.xml updated"), ("Done", "Generate robots.txt and llms.txt"), ("Doing", "Submit site to Google Search Console"), ("Planned", "Check Core Web Vitals after deployment"), ("Done", "Validate schema markup")],
        "Content": [("Doing", "Publish deeper review updates"), ("Done", "Add comparison answers for high-intent queries"), ("Planned", "Refresh pricing notes monthly")],
        "Off-page": [("Planned", "Share useful summaries on LinkedIn and Medium"), ("Planned", "Answer relevant questions without spam"), ("Planned", "Build citations from real communities")],
        "Internal Links": [("Done", "Link categories to reviews"), ("Done", "Link reviews to comparisons"), ("Doing", "Add related reviews to every article")],
        "AI Visibility Tracking": [("Planned", "Track ChatGPT/Gemini/Perplexity mentions"), ("Planned", "Record competitors cited"), ("Doing", "Create missing answer pages")],
        "Affiliate Conversion": [("Doing", "Add clear CTA sections"), ("Planned", "Replace pending affiliate routes after approval"), ("Planned", "Verify current pricing and terms before paid traffic")],
    }
    blocks = ""
    for title, items in sections.items():
        rows = "".join(f"<tr><td>{status_badge(status)}</td><td>{html.escape(item)}</td></tr>" for status, item in items)
        blocks += f"<section class='card'><h2>{html.escape(title)}</h2><table><thead><tr><th>Status</th><th>Checklist item</th></tr></thead><tbody>{rows}</tbody></table></section>"
    body = f"<section class='card'><h1>AEO Action Plan</h1><p>Manual checklist for improving AI search visibility, SEO trust, and affiliate conversion without automation spam.</p><p><span class='status planned'>Planned</span> <span class='status doing'>Doing</span> <span class='status done'>Done</span></p></section>{blocks}"
    (folder / "index.html").write_text(page_shell("AEO Action Plan", "Manual AEO tasks for technical SEO, content, off-page work, links, and AI visibility tracking.", body, "/aeo-action-plan/"), encoding="utf-8")


def status_badge(status: str) -> str:
    css_class = status.lower()
    return f"<span class='status {html.escape(css_class)}'>{html.escape(status)}</span>"


def write_llms_txt(output: Path, pages: list[dict], base_site_url: str) -> None:
    base = (base_site_url or settings.base_site_url or settings.site_domain or "https://yourdomain.com").rstrip("/")
    review_lines = "\n".join(f"- {page['brand_name']} Review: {base}/{page['slug']}/" for page in pages)
    tool_review_lines = "\n".join(f"- {base}/{slug}/" for slug in discover_paths(output, "review"))
    comparison_lines = "\n".join(f"- {base}/{slug}/" for slug in discover_paths(output, "comparisons"))
    compare_lines = "\n".join(f"- {base}/{slug}/" for slug in discover_paths(output, "compare"))
    category_lines = "\n".join(f"- {base}/{slug}/" for slug in CATEGORY_SLUGS)
    toplist_lines = "\n".join(f"- {base}/{slug}/" for slug in discover_prefix_pages(output, "best-"))
    pricing_lines = "\n".join(f"- {base}/{slug}/" for slug in discover_suffix_pages(output, "-pricing"))
    pricing_directory_lines = "\n".join(f"- {base}/{slug}/" for slug in discover_paths(output, "pricing"))
    hub_lines = "\n".join(f"- {base}/{slug}/" for slug in discover_paths(output, "hub"))
    text = f"""# {settings.site_name}

Purpose: independent-style AI and SaaS review website for research, comparison, affiliate disclosure, and safer software evaluation.

Important pages:
- Home: {base}/
- Reviews: {base}/reviews/
- Comparisons: {base}/comparisons/
- Editorial Policy: {base}/editorial-policy/
- Affiliate Disclosure: {base}/affiliate-disclosure/
- Testing Methodology: {base}/testing-methodology/
- Sitemap: {base}/sitemap.xml

Categories:
{category_lines}

Review pages:
{review_lines}

Tool review engine pages:
{tool_review_lines}

Comparison pages:
{comparison_lines}

Decision comparison pages:
{compare_lines}

Top list pages:
{toplist_lines}

Pricing and intent pages:
{pricing_lines}
{pricing_directory_lines}

Hub pages:
{hub_lines}

Editorial notes: content is research-based, avoids fake guarantees, discloses affiliate relationships, and asks readers to verify current pricing and vendor terms.
"""
    (output / "llms.txt").write_text(text, encoding="utf-8")


def discover_paths(output: Path, prefix: str) -> list[str]:
    root = output / prefix
    if not root.exists():
        return []
    return sorted(str(path.parent.relative_to(output)).replace("\\", "/") for path in root.rglob("index.html"))


def discover_prefix_pages(output: Path, prefix: str) -> list[str]:
    return sorted(path.parent.name for path in output.glob(f"{prefix}*/index.html"))


def discover_suffix_pages(output: Path, suffix: str) -> list[str]:
    return sorted(path.parent.name for path in output.glob(f"*{suffix}/index.html"))


def base_schemas(title: str, description: str, canonical: str) -> list[str]:
    base = (settings.base_site_url or settings.site_domain or "https://yourdomain.com").rstrip("/")
    schemas = [
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": settings.site_name,
            "url": base + "/",
            "contactPoint": {"@type": "ContactPoint", "email": settings.contact_email or "", "contactType": "editorial"},
        },
        {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": "Nguyen Quoc Tuan",
            "jobTitle": "Independent AI & SaaS Researcher",
        },
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": settings.site_name,
            "url": base + "/",
        },
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": f"{title} - {settings.site_name}",
            "description": description,
            "url": canonical,
            "author": {"@type": "Person", "name": "Nguyen Quoc Tuan"},
            "publisher": {"@type": "Organization", "name": settings.site_name},
            "dateModified": date.today().isoformat(),
        },
    ]
    return [json.dumps(schema, ensure_ascii=False) for schema in schemas]


def write_robots(output: Path, base_site_url: str) -> None:
    base = (base_site_url or settings.base_site_url or settings.site_domain or "").rstrip("/")
    sitemap = f"Sitemap: {base}/sitemap.xml\n" if base else ""
    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /go/\n"
        "Disallow: /__pycache__/\n"
        "Disallow: /draft_output/\n"
        "Disallow: /data/\n"
        "Disallow: /config/\n"
        "Disallow: /logs/\n"
        "Disallow: /rss.xml\n"
        "Disallow: /sitemap/\n"
        "Disallow: /media-kit/\n"
        "Disallow: /about-author/\n"
        "Disallow: /author-profile/\n"
        f"{sitemap}"
    )
    (output / "robots.txt").write_text(robots, encoding="utf-8")


def write_sitemap(output: Path, pages: list[dict], base_site_url: str) -> None:
    generate_sitemap(output, base_site_url or settings.base_site_url or settings.site_domain)


def write_redirects(output: Path, pages: list[dict]) -> None:
    redirect_map = legacy_redirects(pages)
    lines = ["/home / 301"]
    lines.extend(f"{source} {target} 301" for source, target in redirect_map.items())
    for page in pages:
        lines.append(f"/{page['slug']} /{page['slug']}/ 301")
    (output / "_redirects").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_static_redirect_pages(output, redirect_map)


def legacy_redirects(pages: list[dict]) -> dict[str, str]:
    redirects = {
        "/reviews/windsurf/": "/windsurf-review/",
        "/reviews/windsurf": "/windsurf-review/",
        "/reviews/windsurf-review/": "/windsurf-review/",
        "/reviews/windsurf-review": "/windsurf-review/",
    }
    for page in pages:
        slug = str(page.get("slug", "")).strip("/")
        if slug:
            redirects.setdefault(f"/reviews/{slug}/", f"/{slug}/")
            redirects.setdefault(f"/reviews/{slug}", f"/{slug}/")
    return redirects


def write_static_redirect_pages(output: Path, redirects: dict[str, str]) -> None:
    for source, target in redirects.items():
        source_path = source.strip("/")
        if not source_path:
            continue
        folder = output / source_path
        folder.mkdir(parents=True, exist_ok=True)
        title = "Redirecting"
        description = f"Redirecting to {target}"
        target_url = site_url(target)
        body = f"""
<section class="card">
  <h1>Redirecting</h1>
  <p>This page has moved to <a href="{html.escape(target)}">{html.escape(target)}</a>.</p>
  <p><a class="btn" href="{html.escape(target)}">Continue to the current page</a><a class="btn secondary" href="/">Home</a><a class="btn secondary" href="/reviews/">Reviews</a></p>
</section>
<script>window.location.replace("{html.escape(target, quote=True)}");</script>
"""
        page = page_shell(title, description, body, source if source.endswith("/") else f"{source}/", page_type="website", robots="noindex,follow")
        page = page.replace(
            f'<link rel="canonical" href="{html.escape(site_url(source if source.endswith("/") else f"{source}/"), quote=True)}">',
            f'<link rel="canonical" href="{html.escape(target_url, quote=True)}">',
        )
        page = page.replace(
            "<head><meta charset",
            f'<head><meta http-equiv="refresh" content="0; url={html.escape(target, quote=True)}"><meta charset',
        )
        (folder / "index.html").write_text(page, encoding="utf-8")


def short_description(brand: str, niche: str) -> str:
    return f"A research-focused review of {brand} for buyers comparing {niche} tools."


def nav_html() -> str:
    return f'<nav class="nav"><div class="wrap nav-inner"><a class="logo" href="/">{html.escape(settings.site_name)}</a><div class="menu"><a href="/">Home</a><a href="/reviews/">Reviews</a><a href="/comparisons/">Comparisons</a><a href="/pricing/">Pricing</a><a href="/categories/">Categories</a><a href="/hubs/">Hubs</a><a href="/blog/">Blog</a><a href="/contact/">Contact</a></div><div class="language-switcher" aria-label="Language switcher"><span>Tiếng Việt</span><a href="?lang=en">English</a></div></div><div class="wrap"><p class="note">Some links may be affiliate links. We may earn a commission at no extra cost to you.</p></div></nav>'


def footer_html() -> str:
    contact = settings.contact_email or "tuanpk1977@gmail.com"
    return f'<footer><div class="wrap"><p><strong>{html.escape(settings.site_name)}</strong></p><p>Contact: <a href="mailto:{html.escape(contact)}">{html.escape(contact)}</a></p><a href="/privacy/">Privacy Policy</a><a href="/terms/">Terms</a><a href="/editorial-policy/">Editorial Policy</a><a href="/affiliate-disclosure/">Affiliate Disclosure</a><a href="/about/">About</a><a href="/contact/">Contact</a><a href="/reviews/">Reviews</a><a href="/comparisons/">Comparisons</a><a href="/pricing/">Pricing</a><a href="/categories/">Categories</a><a href="/hubs/">Hubs</a><p>&copy; 2026 {html.escape(settings.site_name)}.</p><p>Some links may be affiliate links. We may earn a commission at no extra cost to you.</p><p>Reviews are for research purposes only.</p></div></footer>'


def newsletter_html() -> str:
    return "<section class='card trust'><h2>Get new AI tool reviews and comparisons.</h2><p>Join the research list for new AI/SaaS review updates. This static form is prepared for a future email provider.</p><form><input class='search' type='email' aria-label='Email address'><button class='btn' type='button'>Notify me</button></form></section>"


def share_buttons(path: str, title: str) -> str:
    url = site_url(path)
    text = html.escape(title)
    encoded_url = html.escape(url, quote=True)
    encoded_text = html.escape(text.replace(" ", "%20"), quote=True)
    return f"<p class='share'><strong>Share:</strong> <a href='https://www.linkedin.com/sharing/share-offsite/?url={encoded_url}'>LinkedIn</a> <a href='https://www.pinterest.com/pin/create/button/?url={encoded_url}&description={encoded_text}'>Pinterest</a> <a href='https://www.facebook.com/sharer/sharer.php?u={encoded_url}'>Facebook</a> <a href='https://twitter.com/intent/tweet?url={encoded_url}&text={encoded_text}'>X/Twitter</a></p>"


def faq_html(questions: list[str]) -> str:
    return "".join(f"<details><summary>{html.escape(question)}</summary><p>Use this guide as a research starting point, then verify pricing, terms, policy, and workflow fit on the official vendor website before buying or promoting a tool.</p></details>" for question in questions)


def site_url(path: str) -> str:
    base = (settings.base_site_url or settings.site_domain or "https://yourdomain.com").rstrip("/")
    return base + "/" + path.lstrip("/")


def legal_pages() -> dict[str, tuple[str, str]]:
    site_name = html.escape(settings.site_name)
    owner = html.escape(settings.site_owner or "Site owner")
    email = html.escape(settings.contact_email or "tuanpk1977@gmail.com")
    domain = html.escape(settings.site_domain or settings.base_site_url or "")
    contact_link = f'<a href="mailto:{email}">{email}</a>'
    return {
        "contact": (
            "Contact",
            f"""
            <section class="card">
              <h2>{site_name}</h2>
              <p><strong>Owner:</strong> {owner}</p>
              <p><strong>Website:</strong> {domain}</p>
              <p><strong>Contact email:</strong> {contact_link}</p>
              <p>This website publishes practical AI/SaaS tool reviews for research and comparison purposes, with a strong focus on AI coding, SEO, automation, and real workflow decisions.</p>
              <p>If you want to suggest a tool, report an outdated pricing note, or ask about editorial/affiliate disclosure, email the address above.</p>
            </section>
            """,
        ),
        "privacy-policy": (
            "Privacy Policy",
            f"""
            <section class="card">
              <p>{site_name} does not ask visitors to submit sensitive personal information.</p>
              <p>This site may use basic analytics, cookies, or similar technologies in the future to understand traffic and improve review content.</p>
              <p>If a contact form or email link is used, the information you send is used only to respond to your request.</p>
              <p>You can contact the site owner at {contact_link} for privacy-related questions.</p>
            </section>
            """,
        ),
        "privacy": (
            "Privacy Policy",
            f"""
            <section class="card">
              <p>{site_name} does not ask visitors to submit sensitive personal information.</p>
              <p>This site may use basic analytics, cookies, or similar technologies in the future to understand traffic and improve review content.</p>
              <p>If you contact the site by email, your message is used only to respond to your request.</p>
              <p>You can contact the site owner at {contact_link} for privacy-related questions.</p>
              <p><strong>CTA:</strong> Use the contact page if you need to ask about privacy, corrections, or site ownership.</p>
              <p><a class="btn" href="/contact/">Contact the site</a><a class="btn secondary" href="/about/">About this review hub</a></p>
            </section>
            <section class="card" id="faq"><h2>FAQ</h2>
              <details><summary>Does this site collect sensitive personal information?</summary><p>No. The site is designed as a static research hub and does not ask visitors for sensitive personal information.</p></details>
              <details><summary>Can I request privacy-related changes?</summary><p>Yes. Contact the site owner by email for privacy-related questions.</p></details>
            </section>
            """,
        ),
        "terms": (
            "Terms",
            f"""
            <section class="card">
              <p>Content on {site_name} is provided for research and comparison purposes only.</p>
              <p>No result is promised. Software outcomes, pricing, availability, affiliate terms, payouts, and policies can change at any time.</p>
              <p>Users should verify current pricing, product details, and official terms directly with each vendor before buying, promoting, or running ads.</p>
              <p>By using this site, you agree that decisions based on the information here are your own responsibility.</p>
            </section>
            """,
        ),
        "affiliate-disclosure": (
            "Affiliate Disclosure",
            f"""
            <section class="card">
              <p>{site_name} may receive affiliate commissions when visitors purchase through links on this website.</p>
              <p>Affiliate commission does not change the price paid by the buyer.</p>
              <p>Reviews are based on practical research, available product information, workflow evaluation, and clearly marked limitations. They should not be treated as financial, legal, or business advice.</p>
              <p>Always check the vendor's official website for the latest pricing, features, and terms.</p>
            </section>
            """,
        ),
        "disclosure": (
            "Disclosure",
            f"""
            <section class="card">
              <p>Some links on {site_name} may be affiliate links. If you buy through those links, the site may earn a commission at no extra cost to you.</p>
              <p>Affiliate relationships do not change the editorial goal: explain the practical workflow fit, risks, alternatives, and checks a buyer should make before choosing a tool.</p>
              <p>Always verify official pricing, terms, and affiliate rules directly with the vendor.</p>
              <p><a class="btn" href="/reviews/">Read reviews</a><a class="btn secondary" href="/comparisons/">Compare tools</a></p>
            </section>
            <section class="card" id="faq"><h2>FAQ</h2>
              <details><summary>Do affiliate links change the buyer's price?</summary><p>No. Affiliate commissions do not add extra cost to the buyer.</p></details>
              <details><summary>Are recommendations guaranteed?</summary><p>No. Reviews are research and comparison notes. Always verify current vendor pricing, features, and terms.</p></details>
            </section>
            """,
        ),
    }


def base_css() -> str:
    return """
    *{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:#f7f9fc;color:#17202a;line-height:1.6}.wrap{max-width:1120px;margin:0 auto;padding:0 20px}
    .nav{background:#fff;border-bottom:1px solid #dbe3ef}.nav-inner{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:18px;flex-wrap:wrap}.logo{font-weight:800;color:#0f172a;text-decoration:none;flex:0 0 auto}.menu{display:flex;gap:18px;flex-wrap:wrap;align-items:center}.menu a{color:#475569;text-decoration:none;font-size:14px}.language-switcher{display:flex;gap:6px;align-items:center;justify-content:center;flex-wrap:wrap;border:1px solid #dbe3ef;border-radius:999px;padding:4px 10px;background:#f8fafc;font-size:13px;line-height:1.2;max-width:100%;white-space:normal}.language-switcher span{font-weight:800;color:#0f766e}.language-switcher a{color:#475569;text-decoration:none;white-space:nowrap}
    .hero{padding:56px 0;background:linear-gradient(180deg,#fff,#f7f9fc)}h1{font-size:44px;line-height:1.08;margin:10px 0}h2{font-size:26px;line-height:1.25;margin:28px 0 12px;white-space:normal;overflow:visible;text-overflow:clip;word-break:normal}h3{margin:0 0 8px}.muted,p,li{color:#596579}.badge{display:inline-block;border:1px solid #a7f3d0;background:#ecfdf5;color:#047857;border-radius:999px;padding:5px 10px;font-size:13px;font-weight:700}
    .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}.card{background:#fff;border:1px solid #dbe3ef;border-radius:8px;padding:18px;box-shadow:0 1px 2px rgba(15,23,42,.04);max-width:100%;overflow-wrap:break-word}.btn{display:inline-block;background:#0f766e;color:#fff;text-decoration:none;padding:10px 14px;border-radius:6px;font-weight:800;margin-right:10px}.btn.secondary{background:#e2e8f0;color:#0f172a}.search{width:100%;padding:12px 14px;border:1px solid #cbd5e1;border-radius:8px;margin:8px 0 18px}.share a{display:inline-block;margin:0 8px 8px 0;color:#0f766e;font-weight:700}.breadcrumb{font-size:14px;color:#64748b;margin-bottom:18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}.review-layout{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:20px;align-items:start}.review-layout>.breadcrumb{grid-column:1/-1}.review-layout>.toc{grid-column:2;grid-row:2;position:sticky;top:84px;max-height:70vh;overflow-y:auto;z-index:1}.review-layout>div{grid-column:1;grid-row:2;min-width:0}.toc{position:relative;max-width:100%}.toc a{display:block;color:#475569;text-decoration:none;padding:6px 0;border-bottom:1px solid #edf2f7}.auto-toc-block{margin:18px 0;max-height:70vh;overflow-y:auto}.note{font-size:13px;color:#7c2d12}.status{display:inline-block;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:800}.status.planned{background:#f1f5f9;color:#334155}.status.doing{background:#fef3c7;color:#92400e}.status.done{background:#dcfce7;color:#166534}.list-section ul{background:#fff;border:1px solid #dbe3ef;border-radius:8px;padding:18px 28px}.list-section li{margin:8px 0}.list-section span{color:#64748b;margin-left:8px}.legal{padding-top:44px;padding-bottom:44px}.trust{border-left:4px solid #9a3412;background:#fff7ed}details{border-top:1px solid #e6edf5;padding:12px 0}summary{cursor:pointer;font-weight:800;color:#334155}pre,.code-block,.prompt{max-width:100%;overflow-x:auto;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;background:#0f172a;color:#e2e8f0;border:1px solid #1e293b;border-radius:8px;padding:14px 16px;font-size:13px;line-height:1.55;box-sizing:border-box}pre code,code{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace}pre code{display:block;white-space:inherit;overflow-wrap:inherit;word-break:inherit;color:inherit}p code,li code{background:#f1f5f9;color:#334155;border-radius:4px;padding:2px 5px;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #dbe3ef;border-radius:8px;overflow:hidden}th,td{text-align:left;border-bottom:1px solid #e6edf5;padding:12px;vertical-align:top}th{background:#f1f5f9;color:#334155}
    footer{margin-top:36px;background:#0f172a;color:#cbd5e1;padding:28px 0}footer a{color:#e2e8f0;text-decoration:none;margin-right:14px}footer p{color:#cbd5e1}@media(max-width:900px){.review-layout{grid-template-columns:1fr}.review-layout>.breadcrumb,.review-layout>.toc,.review-layout>div{grid-column:1;grid-row:auto}.review-layout>.toc,.toc{position:relative;top:auto;max-height:none;overflow:visible}}@media(max-width:760px){.nav-inner{height:auto;padding:14px 0;align-items:flex-start;flex-direction:column}.menu{gap:12px}.language-switcher{margin-top:6px;padding:4px 8px;font-size:12px}h1{font-size:34px}}
    """
