from __future__ import annotations

import csv
import html
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from create_new_niche_reviews_batch import Topic, plain_words, render


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
PUBLISHED = ROOT / "data" / "published_static_pages"
VIDEO = ROOT / "video_output"
BASE_URL = "https://smileaireviewhub.com"


TOPICS = [
    {
        "slug": "skillspector-review-2026",
        "title": "SkillSpector Review 2026: Open-Source AI Agent Skill Analysis",
        "brand": "SkillSpector",
        "category": "AI Agent Developer Tools",
        "focus": "skillspector review",
        "secondary": "AI agent skill analysis",
        "official": "https://github.com/NVIDIA/SkillSpector",
        "summary": "an open-source NVIDIA research tool for inspecting and understanding skills used by AI agents",
        "audience": ("AI agent developers evaluating agent behavior", "research teams inspecting reusable agent skills", "technical teams testing agent governance"),
        "features": ("agent skill inspection", "skill behavior analysis", "open-source research workflow", "developer-focused evaluation"),
        "strengths": ("open-source and inspectable", "useful research angle for agent developers", "helps teams reason about agent skills"),
        "limits": ("technical setup is required", "research software may change quickly", "not a turnkey business automation platform"),
        "alternatives": ("manual agent evaluation", "LangSmith", "Weights & Biases", "custom observability tooling"),
        "internal": (("AI coding tools", "/category/ai-coding-tools/"), ("AI infrastructure companies", "/hidden-ai-infrastructure-companies-2026/"), ("AI tools workflows", "/ai-tools-in-2026-what-each-platform-does-best-in-real-world-workflows/")),
    },
    {
        "slug": "ai-design-software-review",
        "title": "AI Design Software Review 2026: Best Tools for Real Workflows",
        "brand": "AI Design Software",
        "category": "AI Design Tools",
        "focus": "ai design software review",
        "secondary": "best AI design tools",
        "official": "https://www.canva.com",
        "summary": "a fast-moving category that combines layout, image generation, brand controls, and production workflows",
        "audience": ("small marketing teams producing visual assets", "creators building repeatable content systems", "designers comparing AI-assisted production tools"),
        "features": ("template and layout assistance", "image generation and editing", "brand workflow controls", "collaboration and export"),
        "strengths": ("can accelerate routine design work", "supports non-designers and specialists", "wide range of practical use cases"),
        "limits": ("output quality varies by prompt and tool", "brand consistency still needs review", "licensing and usage terms require checking"),
        "alternatives": ("Canva", "Adobe Express", "Framer", "AdCreative.ai"),
        "internal": (("Canva review", "/canva/"), ("Framer review", "/review/framer/"), ("AdCreative.ai review", "/review/adcreative-ai-review-2026/")),
    },
    {
        "slug": "ai-video-software-review",
        "title": "AI Video Software Review 2026: Best Tools Compared",
        "brand": "AI Video Software",
        "category": "AI Video Tools",
        "focus": "ai video software review",
        "secondary": "best AI video tools",
        "official": "https://runwayml.com",
        "summary": "a software category covering AI-assisted editing, text-to-video generation, avatars, captions, and production automation",
        "audience": ("creators producing frequent video content", "marketing teams repurposing written material", "businesses comparing avatar and generative video tools"),
        "features": ("AI video generation", "editing and scene assembly", "captions and localization", "export and publishing workflow"),
        "strengths": ("reduces time for some production tasks", "makes video experimentation more accessible", "supports multiple production styles"),
        "limits": ("generated footage can be inconsistent", "credits and rendering costs vary", "human review remains essential"),
        "alternatives": ("Runway", "Synthesia", "Descript", "Pictory"),
        "internal": (("Runway review", "/review/runway/"), ("Synthesia review", "/review/synthesia/"), ("Descript review", "/review/descript/")),
    },
    {
        "slug": "ai-writing-software-review",
        "title": "AI Writing Software Review 2026: Best Tools Compared",
        "brand": "AI Writing Software",
        "category": "AI Writing Tools",
        "focus": "ai writing software review",
        "secondary": "best AI writing tools",
        "official": "https://www.jasper.ai",
        "summary": "a category of assistants for drafting, rewriting, research support, brand voice, and editorial production",
        "audience": ("content teams building repeatable editorial workflows", "marketers comparing brand-focused writing tools", "creators who need drafting and revision support"),
        "features": ("draft generation", "rewriting and editing", "brand voice controls", "collaboration and workflow management"),
        "strengths": ("can speed up first drafts and revisions", "useful across many content formats", "supports structured editorial workflows"),
        "limits": ("facts and citations require verification", "generic output needs editing", "privacy and training-data terms differ"),
        "alternatives": ("Jasper", "Copy.ai", "Grammarly", "Wordtune"),
        "internal": (("Jasper AI review", "/jasper-ai-review-2026/"), ("Grammarly review", "/grammarly-review-2026/"), ("Wordtune review", "/wordtune-review-2026/")),
    },
    {
        "slug": "automation-software-comparison",
        "title": "Automation Software Comparison 2026: Zapier, Make and More",
        "brand": "Automation Software",
        "category": "Automation Tools",
        "focus": "automation software comparison",
        "secondary": "best workflow automation software",
        "official": "https://zapier.com",
        "summary": "a category of platforms that connect applications, move data, trigger actions, and reduce repetitive operational work",
        "audience": ("small businesses automating routine work", "operations teams comparing integration platforms", "marketers connecting lead and campaign workflows"),
        "features": ("app integrations", "workflow builders", "error handling and monitoring", "data transformation"),
        "strengths": ("can remove repetitive manual steps", "connects many common business systems", "supports gradual automation adoption"),
        "limits": ("complex workflows require maintenance", "usage-based costs can grow", "failed automations need ownership"),
        "alternatives": ("Zapier", "Make", "ActiveCampaign", "HubSpot"),
        "internal": (("Zapier pricing", "/zapier-pricing/"), ("Make vs Zapier", "/compare/make-vs-zapier/"), ("Automation tools", "/category/automation-tools/")),
    },
    {
        "slug": "ai-tools-in-2026-what-each-platform-does-best-in-real-world-workflows",
        "title": "AI Tools in 2026: What Each Platform Does Best",
        "brand": "AI Tools in Real-World Workflows",
        "category": "AI Productivity Tools",
        "focus": "AI tools in 2026",
        "secondary": "best AI platform for real workflows",
        "official": "https://chatgpt.com",
        "summary": "a practical comparison of major AI platforms based on the jobs they perform well rather than a single overall ranking",
        "audience": ("teams choosing an AI assistant for daily work", "creators comparing research and drafting tools", "developers selecting coding and analysis support"),
        "features": ("research and reasoning", "writing and content work", "coding assistance", "multimodal and productivity workflows"),
        "strengths": ("helps buyers match tools to jobs", "avoids one-size-fits-all rankings", "supports evidence-based tool selection"),
        "limits": ("platform capabilities change quickly", "results vary by prompt and workflow", "sensitive data needs careful governance"),
        "alternatives": ("ChatGPT", "Claude", "Gemini", "Perplexity"),
        "internal": (("ChatGPT vs Claude", "/compare/chatgpt-vs-claude/"), ("ChatGPT review", "/chatgpt/"), ("Claude review", "/claude/")),
    },
    {
        "slug": "ai-assistant-software-comparison",
        "title": "AI Assistant Software Comparison 2026: Which One Fits?",
        "brand": "AI Assistant Software",
        "category": "AI Assistants",
        "focus": "ai assistant software comparison",
        "secondary": "ChatGPT Claude Gemini comparison",
        "official": "https://chatgpt.com",
        "summary": "a buyer-focused comparison of general AI assistants for research, writing, analysis, planning, and everyday productivity",
        "audience": ("professionals choosing a general AI assistant", "small teams standardizing productivity tools", "creators comparing research and writing support"),
        "features": ("conversation and reasoning", "document analysis", "web research", "multimodal productivity"),
        "strengths": ("broad everyday usefulness", "multiple strong platforms to choose from", "can accelerate research and drafting"),
        "limits": ("answers still require verification", "privacy controls vary", "subscription value depends on usage"),
        "alternatives": ("ChatGPT", "Claude", "Gemini", "Perplexity"),
        "internal": (("ChatGPT vs Claude", "/compare/chatgpt-vs-claude/"), ("Perplexity review", "/review/perplexity/"), ("Gemini review", "/review/gemini/")),
    },
    {
        "slug": "aisuite-review-2026",
        "title": "aisuite Review 2026: A Simple Interface for Multiple LLMs",
        "brand": "aisuite",
        "category": "AI Developer Tools",
        "focus": "aisuite review",
        "secondary": "multi-provider LLM Python interface",
        "official": "https://github.com/andrewyng/aisuite",
        "summary": "an open-source Python library that provides a unified interface for working with multiple large-language-model providers",
        "audience": ("Python developers comparing LLM providers", "teams prototyping multi-model applications", "technical buyers reducing provider-specific integration work"),
        "features": ("unified provider interface", "multi-model experimentation", "Python developer workflow", "open-source extensibility"),
        "strengths": ("simplifies early multi-provider experiments", "open-source and inspectable", "useful for developer prototypes"),
        "limits": ("developers still manage provider accounts and costs", "production requirements need deeper engineering", "provider differences cannot be fully abstracted"),
        "alternatives": ("direct provider SDKs", "LiteLLM", "LangChain", "custom abstraction layers"),
        "internal": (("AI coding tools", "/category/ai-coding-tools/"), ("AI infrastructure companies", "/hidden-ai-infrastructure-companies-2026/"), ("Cursor vs GitHub Copilot", "/compare/cursor-vs-github-copilot-2026/")),
    },
    {
        "slug": "best-ai-assistant-software",
        "title": "Best AI Assistant Software 2026: Practical Buyer Guide",
        "brand": "Best AI Assistant Software",
        "category": "AI Productivity Tools",
        "focus": "best ai assistant software",
        "secondary": "best AI assistant for work",
        "official": "https://chatgpt.com",
        "summary": "a practical shortlist of AI assistants evaluated for research, writing, planning, coding support, and everyday business work",
        "audience": ("individual professionals selecting one paid assistant", "small teams creating an AI tool policy", "creators comparing research and production workflows"),
        "features": ("research support", "writing and editing", "document analysis", "workflow integrations"),
        "strengths": ("clear options for different user needs", "high potential for daily productivity", "useful across many job functions"),
        "limits": ("the best choice depends on workflow", "outputs require human review", "feature availability changes frequently"),
        "alternatives": ("ChatGPT", "Claude", "Gemini", "Microsoft Copilot"),
        "internal": (("AI assistant comparison", "/ai-assistant-software-comparison/"), ("ChatGPT vs Claude", "/compare/chatgpt-vs-claude/"), ("AI tools workflows", "/ai-tools-in-2026-what-each-platform-does-best-in-real-world-workflows/")),
    },
    {
        "slug": "ai-coding-software-comparison",
        "title": "AI Coding Software Comparison 2026: Best Tools for Developers",
        "brand": "AI Coding Software",
        "category": "AI Coding Tools",
        "focus": "ai coding software comparison",
        "secondary": "best AI coding assistant",
        "official": "https://github.com/features/copilot",
        "summary": "a practical comparison of coding assistants and AI-native editors for completion, refactoring, debugging, and repository work",
        "audience": ("developers choosing an AI coding assistant", "engineering teams comparing editor integrations", "technical leaders evaluating productivity and governance"),
        "features": ("code completion", "repository-aware assistance", "debugging and refactoring", "team controls and integrations"),
        "strengths": ("can accelerate routine coding tasks", "supports several editor and workflow styles", "useful for exploration and documentation"),
        "limits": ("generated code needs review and testing", "repository context varies by tool", "security and licensing policies require attention"),
        "alternatives": ("Cursor", "GitHub Copilot", "Windsurf", "Replit"),
        "internal": (("Cursor vs GitHub Copilot", "/compare/cursor-vs-github-copilot-2026/"), ("Cursor vs Windsurf", "/compare/cursor-vs-windsurf/"), ("AI coding tools", "/category/ai-coding-tools/")),
    },
]


def upsert_csv(path: Path, key: str, additions: list[dict[str, str]]) -> None:
    rows: list[dict[str, str]] = []
    fields: list[str] = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = list(reader)
    for addition in additions:
        for field in addition:
            if field not in fields:
                fields.append(field)
        match = next((row for row in rows if row.get(key) == addition[key]), None)
        if match:
            match.update(addition)
        else:
            rows.append(addition)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_feature_image(slug: str, title: str, category: str) -> None:
    path = SITE / "assets" / "og" / "pages" / f"{slug}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1600, 900), "#071d2d")
    draw = ImageDraw.Draw(image)
    try:
        bold = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 82)
        medium = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 34)
        small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 28)
    except OSError:
        bold = medium = small = ImageFont.load_default()
    draw.rectangle((0, 0, 1600, 135), fill="#087f78")
    draw.text((70, 48), "MS Smile AI Review Hub", font=medium, fill="white")
    draw.rounded_rectangle((70, 205, 1530, 745), radius=24, fill="#f4f8fb", outline="#55d6c8", width=5)
    draw.text((115, 255), category.upper(), font=medium, fill="#087f78")
    lines = textwrap.wrap(title, width=31)
    y = 330
    for line in lines[:4]:
        draw.text((115, y), line, font=bold, fill="#102236")
        y += 98
    draw.text((115, 675), "Independent workflow-focused analysis | Updated June 2026", font=small, fill="#526078")
    draw.text((70, 820), "smileaireviewhub.com", font=medium, fill="#7be5da")
    image.save(path, optimize=True)


def main() -> None:
    trend_data = json.loads((ROOT / "data" / "trending_topics.json").read_text(encoding="utf-8"))
    selected = {row["slug"] for row in trend_data.get("selected_topics", [])}
    expected = {row["slug"] for row in TOPICS}
    if selected != expected:
        raise RuntimeError(f"Trending file changed. Missing={expected-selected}; unexpected={selected-expected}")

    video_rows = []
    upload_rows = []
    report = []
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
            f"{topic.focus}, {topic.secondary}, AI tools 2026, software review\n", encoding="utf-8"
        )
        (folder / "pinned_comment.txt").write_text(f"Read the full analysis: {topic.url}\n", encoding="utf-8")
        (folder / "feature_image_prompt.txt").write_text(
            f"Professional editorial feature image for {item['title']}, practical software workflow, mobile readable, 16:9.\n",
            encoding="utf-8",
        )
        (folder / "thumbnail_prompt.txt").write_text(
            f"YouTube thumbnail for {item['title']}, bold concise headline, professional AI software analysis, 16:9.\n",
            encoding="utf-8",
        )
        video_rows.append({"slug": topic.slug, "title": item["title"], "output_path": str(SITE / topic.slug / "index.html"), "url": topic.url})
        upload_rows.append({"FolderName": topic.slug, "PageUrl": topic.url, "YoutubeVideoUrl": "", "UploadStatus": "NOT_UPLOADED", "Notes": "AI trend discovery batch 2026-06-14"})
        report.append({"title": item["title"], "slug": topic.slug, "article_url": topic.url, "word_count": count, "video_folder": f"video_output/{topic.slug}"})
        print(f"CREATED {topic.slug}: {count} words")

    upsert_csv(ROOT / "data" / "video_article_index.csv", "slug", video_rows)
    upsert_csv(VIDEO / "upload_links.csv", "FolderName", upload_rows)
    report_path = VIDEO / "trending_topics_content_report.json"
    report_path.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "articles": report}, indent=2),
        encoding="utf-8",
    )
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
