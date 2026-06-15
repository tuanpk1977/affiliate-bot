from __future__ import annotations

import csv
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from create_new_niche_reviews_batch import Topic, plain_words, render
from create_trending_topics_content_batch import make_feature_image, upsert_csv


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
PUBLISHED = ROOT / "data" / "published_static_pages"
VIDEO = ROOT / "video_output"
BASE_URL = "https://smileaireviewhub.com"


TOPICS = [
    {
        "slug": "self-hosting-guide-review-2026",
        "title": "Self-Hosting Guide Review 2026: Build a Practical Home Lab",
        "brand": "Self-Hosting Guide",
        "category": "Developer Infrastructure",
        "focus": "self hosting guide review",
        "secondary": "self hosted software guide",
        "official": "https://github.com/mikeroyal/Self-Hosting-Guide",
        "summary": "an open-source reference that organizes self-hosting tools, infrastructure concepts, and practical resources for running software on systems you control",
        "audience": ("developers planning a home lab", "small teams evaluating self-hosted software", "privacy-conscious users comparing hosted and self-managed tools"),
        "features": ("self-hosting resource directory", "infrastructure and home-lab guidance", "open-source software discovery", "community-maintained technical references"),
        "strengths": ("broad practical reference", "open-source and inspectable", "useful starting point for self-hosting research"),
        "limits": ("not a managed hosting service", "technical skills are required", "security and maintenance remain the operator's responsibility"),
        "alternatives": ("managed SaaS products", "official vendor documentation", "Awesome Selfhosted", "cloud platform tutorials"),
        "internal": (("AI infrastructure companies", "/hidden-ai-infrastructure-companies-2026/"), ("Cloud development tools", "/cloud-development-software-review/"), ("AI coding tools", "/category/ai-coding-tools/")),
    },
    {
        "slug": "agent-reach-review-2026",
        "title": "Agent Reach Review 2026: Open-Source AI Agent Research",
        "brand": "Agent Reach",
        "category": "AI Agent Developer Tools",
        "focus": "agent reach review",
        "secondary": "open source AI agent research",
        "official": "https://github.com/Panniantong/Agent-Reach",
        "summary": "an emerging open-source project for developers researching AI agent capabilities and practical agent workflows",
        "audience": ("AI agent developers", "research teams testing agent workflows", "technical teams evaluating open-source agent projects"),
        "features": ("open-source agent workflow", "developer experimentation", "agent capability research", "community-driven development"),
        "strengths": ("inspectable source code", "timely AI agent research angle", "useful for technical experimentation"),
        "limits": ("early-stage project risk", "technical setup is required", "production readiness must be independently tested"),
        "alternatives": ("LangGraph", "CrewAI", "AutoGen", "custom agent workflows"),
        "internal": (("AI assistant comparison", "/ai-assistant-software-comparison/"), ("AI coding comparison", "/ai-coding-software-comparison/"), ("AI infrastructure companies", "/hidden-ai-infrastructure-companies-2026/")),
    },
    {
        "slug": "ai-engineering-from-scratch-review-2026",
        "title": "AI Engineering From Scratch Review 2026: Learning Guide",
        "brand": "AI Engineering From Scratch",
        "category": "AI Developer Education",
        "focus": "ai engineering from scratch review",
        "secondary": "learn AI engineering",
        "official": "https://github.com/rohitg00/ai-engineering-from-scratch",
        "summary": "an open-source learning project intended to help developers understand practical AI engineering concepts from foundational components upward",
        "audience": ("developers learning AI engineering", "technical creators building educational projects", "teams creating an internal AI learning path"),
        "features": ("structured AI engineering material", "hands-on developer learning", "open-source examples", "foundational workflow coverage"),
        "strengths": ("practical learning orientation", "open-source access", "useful for building foundational knowledge"),
        "limits": ("not a substitute for production experience", "content can change quickly", "learners must verify dependencies and examples"),
        "alternatives": ("official model-provider documentation", "AI engineering courses", "hands-on portfolio projects", "developer community tutorials"),
        "internal": (("AI coding tools", "/category/ai-coding-tools/"), ("Cursor review", "/review/cursor/"), ("AI infrastructure companies", "/hidden-ai-infrastructure-companies-2026/")),
    },
    {
        "slug": "cua-review-2026",
        "title": "CUA Review 2026: Computer-Use Agent Infrastructure",
        "brand": "CUA",
        "category": "AI Agent Developer Tools",
        "focus": "cua review",
        "secondary": "computer use agent infrastructure",
        "official": "https://github.com/trycua/cua",
        "summary": "an open-source computer-use agent project for developers exploring how AI agents interact with desktop and application environments",
        "audience": ("developers building computer-use agents", "automation teams researching agent interfaces", "technical buyers evaluating emerging agent infrastructure"),
        "features": ("computer-use agent tooling", "desktop interaction workflows", "open-source developer infrastructure", "agent experimentation"),
        "strengths": ("relevant emerging agent category", "open-source and inspectable", "useful for technical prototypes"),
        "limits": ("early-stage operational risk", "security controls require careful review", "production reliability must be tested"),
        "alternatives": ("browser automation", "robotic process automation", "custom desktop automation", "other computer-use agent frameworks"),
        "internal": (("Automation software comparison", "/automation-software-comparison/"), ("AI assistant comparison", "/ai-assistant-software-comparison/"), ("AI coding tools", "/category/ai-coding-tools/")),
    },
    {
        "slug": "ai-productivity-software-comparison",
        "title": "AI Productivity Software Comparison 2026",
        "brand": "AI Productivity Software",
        "category": "AI Productivity Tools",
        "focus": "ai productivity software comparison",
        "secondary": "best AI productivity tools",
        "official": "https://chatgpt.com",
        "summary": "a practical comparison of AI assistants, meeting tools, research systems, writing tools, and workflow automation for daily work",
        "audience": ("professionals selecting AI productivity software", "small teams standardizing AI workflows", "creators comparing research and production tools"),
        "features": ("research and drafting", "meeting and task support", "workflow automation", "collaboration and integrations"),
        "strengths": ("covers several daily-work categories", "helps match software to specific jobs", "supports practical shortlist decisions"),
        "limits": ("the best option depends on workflow", "feature availability changes quickly", "outputs and automations need review"),
        "alternatives": ("ChatGPT", "Claude", "Notion AI", "Reclaim AI"),
        "internal": (("Best AI assistant software", "/best-ai-assistant-software/"), ("AI assistant comparison", "/ai-assistant-software-comparison/"), ("Reclaim AI review", "/review/reclaim-ai/")),
    },
    {
        "slug": "ai-seo-software-comparison",
        "title": "AI SEO Software Comparison 2026: Best Tools by Workflow",
        "brand": "AI SEO Software",
        "category": "AI SEO Tools",
        "focus": "ai seo software comparison",
        "secondary": "best AI SEO software",
        "official": "https://surferseo.com",
        "summary": "a buyer-focused comparison of AI-assisted SEO platforms for research, content optimization, audits, competitive analysis, and reporting",
        "audience": ("content teams comparing SEO software", "small businesses choosing an SEO workflow", "agencies evaluating research and optimization tools"),
        "features": ("keyword and topic research", "content optimization", "technical audits", "competitive analysis and reporting"),
        "strengths": ("supports several SEO workflows", "helps buyers compare practical fit", "connects AI assistance with measurable search tasks"),
        "limits": ("SEO recommendations require judgment", "pricing and limits change", "no tool guarantees rankings"),
        "alternatives": ("Surfer SEO", "Semrush", "Ahrefs", "Frase"),
        "internal": (("Surfer SEO review", "/review/surfer-seo-review-2026/"), ("Semrush vs Ahrefs", "/compare/semrush-vs-ahrefs/"), ("Best AI SEO tools", "/best-ai-seo-tools-2026/")),
    },
    {
        "slug": "productivity-software-comparison",
        "title": "Productivity Software Comparison 2026: Choose the Right Stack",
        "brand": "Productivity Software",
        "category": "Productivity Tools",
        "focus": "productivity software comparison",
        "secondary": "best productivity software",
        "official": "https://www.notion.com",
        "summary": "a practical comparison of productivity platforms for documents, tasks, communication, automation, planning, and team knowledge",
        "audience": ("small businesses choosing a productivity stack", "teams consolidating software", "individuals comparing planning and knowledge tools"),
        "features": ("documents and knowledge", "tasks and planning", "communication and collaboration", "automation and integrations"),
        "strengths": ("helps reduce tool overlap", "supports workflow-based comparison", "covers individual and team requirements"),
        "limits": ("migration effort can be significant", "all-in-one tools involve tradeoffs", "team adoption matters more than feature count"),
        "alternatives": ("Notion", "HubSpot", "Reclaim AI", "Zapier"),
        "internal": (("Notion review", "/review/notion/"), ("HubSpot review", "/hubspot-review-2026/"), ("Zapier pricing", "/zapier-pricing/")),
    },
    {
        "slug": "ai-design-software-comparison",
        "title": "AI Design Software Comparison 2026: Best Tools by Use Case",
        "brand": "AI Design Software",
        "category": "AI Design Tools",
        "focus": "ai design software comparison",
        "secondary": "best AI design software",
        "official": "https://www.canva.com",
        "summary": "a practical comparison of AI-assisted design platforms for social graphics, brand assets, websites, advertising, and creative production",
        "audience": ("marketing teams comparing visual tools", "creators building repeatable design workflows", "small businesses choosing accessible design software"),
        "features": ("template and layout assistance", "image generation and editing", "brand controls", "collaboration and export"),
        "strengths": ("covers several creative use cases", "helps non-designers build a shortlist", "supports workflow-based evaluation"),
        "limits": ("generated output requires review", "licensing terms differ", "specialist work may require professional design software"),
        "alternatives": ("Canva", "Adobe Express", "AdCreative.ai", "Framer"),
        "internal": (("Canva review", "/canva/"), ("AdCreative.ai review", "/review/adcreative-ai-review-2026/"), ("Framer review", "/review/framer/")),
    },
    {
        "slug": "ai-image-software-comparison",
        "title": "AI Image Software Comparison 2026: Generators and Editors",
        "brand": "AI Image Software",
        "category": "AI Image Tools",
        "focus": "ai image software comparison",
        "secondary": "best AI image software",
        "official": "https://www.midjourney.com",
        "summary": "a practical comparison of AI image generators and editors for concept work, marketing assets, social content, and creative production",
        "audience": ("creators comparing image generators", "marketing teams producing campaign assets", "designers evaluating AI-assisted ideation"),
        "features": ("text-to-image generation", "editing and variation", "style and composition controls", "export and commercial-use workflow"),
        "strengths": ("supports rapid creative exploration", "covers several production styles", "can accelerate concept development"),
        "limits": ("results vary by prompt", "commercial-use terms require review", "brand consistency and accuracy need human checks"),
        "alternatives": ("Midjourney", "Canva", "Adobe tools", "specialist image editors"),
        "internal": (("Midjourney review", "/review/midjourney/"), ("Canva review", "/canva/"), ("AI design comparison", "/ai-design-software-comparison/")),
    },
    {
        "slug": "ai-meeting-software-comparison",
        "title": "AI Meeting Software Comparison 2026: Notes and Workflows",
        "brand": "AI Meeting Software",
        "category": "AI Meeting Tools",
        "focus": "ai meeting software comparison",
        "secondary": "best AI meeting assistant",
        "official": "https://otter.ai",
        "summary": "a practical comparison of AI meeting assistants for transcription, summaries, action items, search, and follow-up workflows",
        "audience": ("teams comparing meeting assistants", "sales and customer teams documenting calls", "professionals reducing manual meeting notes"),
        "features": ("transcription", "summaries and action items", "meeting search", "integrations and follow-up"),
        "strengths": ("can reduce manual note-taking", "supports searchable meeting records", "helps structure follow-up work"),
        "limits": ("transcription accuracy varies", "privacy and consent require attention", "summaries still need review"),
        "alternatives": ("Otter.ai", "Fireflies.ai", "Fathom", "manual meeting notes"),
        "internal": (("AI productivity comparison", "/ai-productivity-software-comparison/"), ("Productivity comparison", "/productivity-software-comparison/"), ("AI assistant comparison", "/ai-assistant-software-comparison/")),
    },
]


def assert_new(slug: str) -> None:
    roots = (SITE, PUBLISHED, VIDEO, ROOT / "content" / "posts", ROOT / "public" / "posts")
    existing = [str(root / slug) for root in roots if (root / slug).exists()]
    if existing:
        raise RuntimeError(f"Refusing to overwrite existing slug {slug}: {existing}")


def main() -> None:
    trend_data = json.loads((ROOT / "data" / "trending_topics.json").read_text(encoding="utf-8"))
    selected = {row["slug"] for row in trend_data.get("selected_topics", [])}
    expected = {row["slug"] for row in TOPICS}
    if selected != expected:
        raise RuntimeError(f"Trending file changed. Missing={expected-selected}; unexpected={selected-expected}")

    for item in TOPICS:
        assert_new(item["slug"])

    video_rows: list[dict[str, str]] = []
    upload_rows: list[dict[str, str]] = []
    report: list[dict[str, object]] = []
    for item in TOPICS:
        topic = Topic(
            item["slug"], item["brand"], item["category"], item["focus"], item["secondary"],
            item["official"], item["summary"], item["audience"], item["features"], item["strengths"],
            item["limits"], item["alternatives"], item["internal"],
        )
        default_title = f"{topic.brand} Review 2026: Features, Pricing, Pros, Cons & Alternatives"
        page = render(topic).replace(default_title, item["title"])
        page = page.replace(f"{html.escape(topic.brand)} review overview.", f"{html.escape(item['title'])} overview.")
        count = plain_words(page)
        if count < 3000:
            raise RuntimeError(f"{topic.slug} below 3000 words: {count}")
        for root in (SITE, PUBLISHED):
            target = root / topic.slug / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page, encoding="utf-8")
        make_feature_image(topic.slug, item["title"], topic.category)

        folder = VIDEO / topic.slug
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "youtube_title.txt").write_text(item["title"] + "\n", encoding="utf-8")
        (folder / "youtube_description.txt").write_text(
            f"{item['title']}\n\nRead the full article: {topic.url}\n\nWebsite: {BASE_URL}\n",
            encoding="utf-8",
        )
        (folder / "youtube_tags.txt").write_text(
            f"{topic.focus}, {topic.secondary}, AI tools 2026, software comparison\n", encoding="utf-8"
        )
        (folder / "pinned_comment.txt").write_text(f"Read the full analysis: {topic.url}\n", encoding="utf-8")
        (folder / "feature_image_prompt.txt").write_text(
            f"Professional editorial feature image for {item['title']}, practical software workflow, mobile readable, 16:9.\n",
            encoding="utf-8",
        )
        (folder / "thumbnail_prompt.txt").write_text(
            f"YouTube thumbnail for {item['title']}, bold concise headline, professional software analysis, 16:9.\n",
            encoding="utf-8",
        )
        video_rows.append({"slug": topic.slug, "title": item["title"], "output_path": str(SITE / topic.slug / "index.html"), "url": topic.url})
        upload_rows.append({"FolderName": topic.slug, "PageUrl": topic.url, "YoutubeVideoUrl": "", "UploadStatus": "NOT_UPLOADED", "Notes": "AI trend discovery batch 2026-06-15"})
        report.append({"title": item["title"], "slug": topic.slug, "article_url": topic.url, "word_count": count, "video_folder": f"video_output/{topic.slug}"})
        print(f"CREATED {topic.slug}: {count} words")

    upsert_csv(ROOT / "data" / "video_article_index.csv", "slug", video_rows)
    upsert_csv(VIDEO / "upload_links.csv", "FolderName", upload_rows)
    report_path = VIDEO / "trending_topics_2026_06_15_content_report.json"
    report_path.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "articles": report}, indent=2),
        encoding="utf-8",
    )
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
