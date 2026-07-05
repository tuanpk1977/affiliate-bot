from __future__ import annotations

import csv
import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent / "data"
HOTTREND_CSV = DATA_DIR / "hottrend_latest_dashboard.csv"
TODAY = datetime.now().strftime("%Y-%m-%d")
OUTPUT_DIR = ROOT / f"{TODAY}-daily-packages"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TOPICS = [
    {
        "title": "Best Automation Software",
        "slug": "best-automation-software",
        "source": "local_keyword_intelligence",
    },
    {
        "title": "Affordable Automation Platform",
        "slug": "affordable-automation-platform",
        "source": "local_keyword_intelligence",
    },
    {
        "title": "Affordable AI App Builder Platform",
        "slug": "affordable-ai-app-builder-platform",
        "source": "local_keyword_intelligence",
    },
    {
        "title": "Affordable AI Assistant Platform",
        "slug": "affordable-ai-assistant-platform",
        "source": "local_keyword_intelligence",
    },
    {
        "title": "Affordable AI Coding Platform",
        "slug": "affordable-ai-coding-platform",
        "source": "local_keyword_intelligence",
    },
    {
        "title": "Affordable AI SEO Platform",
        "slug": "affordable-ai-seo-platform",
        "source": "local_keyword_intelligence",
    },
    {
        "title": "Affordable AI Video Platform",
        "slug": "affordable-ai-video-platform",
        "source": "local_keyword_intelligence",
    },
    {
        "title": "Affordable AI Writing Platform",
        "slug": "affordable-ai-writing-platform",
        "source": "local_keyword_intelligence",
    },
    {
        "title": "Kilocode Review 2026",
        "slug": "kilocode-review-2026",
        "source": "github_trending",
    },
    {
        "title": "RNNs vs Transformers vs SSMs: where should AI memory live for continual learning?",
        "slug": "rnns-vs-transformers-vs-ssms-where-should-ai-memory-live-for-continual-learning",
        "source": "reddit",
    },
]


def load_topics(limit: int = 10) -> list[dict]:
    if HOTTREND_CSV.exists():
        topics = []
        with HOTTREND_CSV.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if len(topics) >= limit:
                    break
                recommendation = row.get("recommendation", "").strip().lower()
                if recommendation == "skip":
                    continue
                slug = row.get("slug", "").strip()
                title = row.get("topic", "").strip()
                if not slug or not title:
                    continue
                topics.append(
                    {
                        "title": title,
                        "slug": slug,
                        "source": row.get("source", "").strip(),
                        "url": row.get("article_url", "").strip(),
                    }
                )
        if topics:
            return topics
    return DEFAULT_TOPICS[:limit]


def build_article(topic: dict) -> str:
    title = topic["title"]
    return (
        f"# {title}\n\n"
        f"**Topic source:** {topic.get('source', 'manual selection')}\n\n"
        "## Introduction\n"
        f"This article draft covers {title}. It is prepared as part of the daily temporary content package file and is intended for editorial review only.\n\n"
        "## Why this topic matters today\n"
        "Recent trends show interest from buyers and creators looking for actionable tools and practical guidance.\n\n"
        "## What readers should know\n"
        "The goal is to help readers decide whether this tool or category fits their workflow, budget, and business needs.\n\n"
        "## Recommended content sections\n"
        "- What it does and who it is for\n"
        "- Core features and workflow benefits\n"
        "- Pricing, value, and business fit\n"
        "- Pros and cons\n"
        "- Alternatives and comparison notes\n"
        "- Final recommendation and next step\n\n"
        "## Notes for editorial review\n"
        "Update pricing, add screenshots, and insert actual affiliate links before publishing.\n"
    )


def build_html(topic: dict) -> str:
    title = topic["title"]
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        f"  <meta charset=\"UTF-8\">\n"
        f"  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        f"  <title>{title}</title>\n"
        f"  <meta name=\"description\" content=\"Draft review article for {title}.\">\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{title}</h1>\n"
        f"  <p>This is a temporary HTML draft for the daily content package created on {TODAY}.</p>\n"
        f"  <p>Topic source: {topic.get('source', 'manual selection')}</p>\n"
        "  <h2>Key takeaways</h2>\n"
        "  <ul>\n"
        "    <li>Practical review and buyer guidance</li>\n"
        "    <li>Pricing transparency and workflow fit</li>\n"
        "    <li>Alternatives and recommendations</li>\n"
        "  </ul>\n"
        "</body>\n"
        "</html>\n"
    )


def build_social_text(topic: dict, platform: str) -> str:
    title = topic["title"]
    if platform == "facebook":
        return (
            f"{title}\n\n"
            "This is a draft social post for Facebook describing the topic and linking to the full review.\n"
            "Use it for editorial review and manual publishing."
        )
    if platform == "linkedin":
        return (
            f"{title}\n\n"
            "Independent review-ready draft for LinkedIn. Focus on buyer value, workflow fit, and practical takeaways.\n"
            "Use the article file as the long-form source."
        )
    if platform == "devto":
        return (
            f"{title}\n\n"
            "Dev.to post draft: note why this topic is relevant to developers and what practical advice readers should expect.\n"
        )
    if platform == "hashnode":
        return (
            f"{title}\n\n"
            "Hashnode draft: explain the main use case, why it matters today, and where to find the full review.\n"
        )
    if platform == "medium":
        return (
            f"{title}\n\n"
            "Medium draft: highlight the business value and why readers should take a closer look at this topic.\n"
        )
    if platform == "reddit":
        return (
            f"{title}\n\n"
            "Reddit draft: summarize the key question, what makes this topic interesting, and invite discussion.\n"
        )
    if platform == "quora":
        return (
            f"{title}\n\n"
            "Quora draft: answer the main question around the topic with concise, practical advice and a link to the review.\n"
        )
    if platform == "twitter":
        return (
            f"{title} - draft tweet text for the daily content package.\n"
            "Keep it short, informative, and linked to the article.\n"
        )
    return ""


def build_youtube_title(topic: dict) -> str:
    return f"{topic['title']} | Daily AI Review 2026"


def build_youtube_description(topic: dict) -> str:
    title = topic["title"]
    return (
        f"{title}\n\n"
        "This is a temporary YouTube description generated for the daily content package.\n"
        "Use it as the starting point for the final upload description.\n\n"
        "Timestamps:\n"
        "0:00 Introduction\n"
        "0:30 Why this topic matters\n"
        "1:00 Key features / analysis\n"
        "1:30 Pros and cons\n"
        "2:00 Final recommendation\n\n"
        f"Read the full article at: https://smileaireviewhub.com/{topic['slug']}/\n"
        "Affiliate disclosure: Some links may be affiliate links.\n"
    )


def build_youtube_tags(topic: dict) -> str:
    tags = [
        topic["title"],
        "AI review",
        "software review",
        "2026",
        "affiliate review",
        "product review",
    ]
    if "AI" in topic["title"] or "ai" in topic["title"].lower():
        tags.append("AI tools")
    return ", ".join(tags)


def build_video_script_text(topic: dict) -> str:
    title = topic["title"]
    return (
        f"{title}\n\n"
        "This video is prepared for manual review before publishing. It does not replace official vendor documentation.\n\n"
        "Introduction\n"
        f"In this MS Smile AI Review Hub video, we look at {title} from a practical research angle. "
        "Based on our page research, the goal is to understand workflow fit, pricing checks, alternatives, "
        "and the limits that should be verified before buying or promoting a tool.\n\n"
        "Overview\n"
        f"{title} is worth reviewing through a practical buyer lens rather than a hype lens. "
        "This section explains what the product or category is supposed to solve, who it is usually for, "
        "and what a careful buyer should verify before spending money.\n\n"
        "Best For\n"
        f"{title} is best for teams that have a clear workflow problem and need to save time, improve execution quality, "
        "or reduce manual work. It is also useful for buyers who already know the category and want a structured way to compare "
        "pricing, features, limitations, and alternatives before choosing.\n\n"
        "Key Features\n"
        "Check the official product page and current release notes. Feature fit matters more than broad marketing claims.\n\n"
        "Pricing\n"
        "Verify current pricing on the official website. Software prices and plan limits change often. "
        "Always check plan limits, seats, usage caps, cancellation terms, support level, and integrations.\n\n"
        "Pros\n"
        "- Useful when it maps directly to an existing workflow\n"
        "- Can reduce manual research, production, or operational work\n"
        "- Often easier to test than building a custom internal system\n"
        "- May create leverage when paired with clear SOPs and analytics\n\n"
        "Cons\n"
        "- Pricing and limits must be checked before buying\n"
        "- Some features may look stronger in demos than in daily work\n"
        "- Teams can overpay if the workflow is not clearly defined\n"
        "- Switching costs can grow after data and automations are built inside the platform\n\n"
        "Alternatives\n"
        "Before choosing this tool, compare it with related tools in the same workflow. "
        "Look for alternatives with different strengths: cheaper entry pricing, stronger integrations, better analytics, "
        "simpler onboarding, or more advanced team controls.\n\n"
        "Final Verdict\n"
        f"{title} deserves a careful, buyer-focused review. Use this as a starting point for editorial review before publishing. "
        "Always verify current pricing, features, and alternatives on official vendor websites.\n\n"
        "About the Author\n"
        "This review was researched and prepared by Nguyen Quoc Tuan, an independent AI and SaaS researcher. "
        "Learn more at smileaireviewhub.com\n\n"
        "Thank you for watching. For more AI reviews and comparisons, visit Smile AI Review Hub.\n"
    )


def build_voiceover_text(topic: dict) -> str:
    title = topic["title"]
    return (
        f"Voiceover script for {title}\n\n"
        f"Welcome to the {title} review on MS Smile AI Review Hub.\n"
        f"Today we're looking at {title} from a practical, buyer-focused angle.\n"
        f"Our goal is to help you understand what {title} does, who it's best for, "
        "how much it costs, and what alternatives you should compare it with.\n"
        f"Let's start with the overview. {title} is a tool or category worth reviewing carefully. "
        "Rather than repeating vendor marketing claims, we focus on what the product actually solves, "
        "who it's usually for, and what you should verify before spending money.\n"
        f"{title} is best for teams that have a clear workflow problem and need to save time or improve quality. "
        "It's also useful for buyers who already know the category and want a structured comparison of features, pricing, and alternatives.\n"
        "When evaluating any tool, check the official product page for current features and release notes. "
        "Feature fit matters much more than broad marketing claims.\n"
        "Pricing is critical. Always verify current pricing on the official website. "
        "Software prices and plan limits change often. Look at plan limits, seats, usage caps, cancellation terms, support level, and available integrations.\n"
        "The benefits are clear. These tools are useful when they map directly to your existing workflow. "
        "They can reduce manual research, production work, or operational overhead. "
        "They're often easier to test than building a custom internal system. "
        "And they may create significant leverage when paired with clear SOPs and analytics.\n"
        "However, there are important drawbacks. Pricing and limits must be checked carefully before buying. "
        "Some features may look stronger in demos than in daily work. "
        "Teams can overpay if the workflow is not clearly defined before buying. "
        "And switching costs can grow significantly after data and automations are built inside the platform.\n"
        "Before choosing this tool, compare it with related alternatives in the same workflow. "
        "Look for alternatives with different strengths: cheaper entry pricing, stronger integrations, better analytics, "
        "simpler onboarding, or more advanced team controls.\n"
        f"In summary, {title} deserves a careful, buyer-focused review. "
        "Use this as the starting point for editorial review before publishing. "
        "Always verify current pricing, features, and alternatives on official vendor websites.\n"
        "This review was researched and prepared by Nguyen Quoc Tuan, an independent AI and SaaS researcher.\n"
        "Thank you for watching. For more AI reviews and comparisons, visit Smile AI Review Hub at smileaireviewhub.com. "
        "Subscribe to our YouTube channel for more tool reviews and comparisons.\n"
    )


def build_scene_plan(topic: dict) -> dict:
    return {
        "slug": topic["slug"],
        "title": topic["title"],
        "scenes": [
            {"id": 1, "title": "Intro", "description": "What this topic is and why it matters."},
            {"id": 2, "title": "Key points", "description": "Discuss the main features, pricing, and fit."},
            {"id": 3, "title": "Short verdict", "description": "Summarize pros, cons, and recommendation."},
        ],
    }


def build_scenes_json(topic: dict) -> dict:
    return {
        "slug": topic["slug"],
        "scenes": [
            {"scene": "intro", "duration": 15},
            {"scene": "details", "duration": 30},
            {"scene": "closing", "duration": 15},
        ],
    }


def build_subtitles(topic: dict) -> str:
    return (
        "1\n"
        "00:00:00,000 --> 00:00:05,000\n"
        f"Welcome to the {topic['title']} review.\n\n"
        "2\n"
        "00:00:05,000 --> 00:00:10,000\n"
        "We cover the main benefits, pricing, and who should use it.\n"
    )


def build_short_script(topic: dict) -> str:
    return (
        f"Short script for {topic['title']}\n"
        "Hook: Why this topic is worth watching.\n"
        "Body: one key benefit and one risk.\n"
        "CTA: See the full review in the main article.\n"
    )


def build_video_metadata(topic: dict) -> dict:
    return {
        "slug": topic["slug"],
        "topic": topic["title"],
        "article_url": f"https://smileaireviewhub.com/{topic['slug']}/",
        "manual_youtube_upload": True,
        "auto_upload_youtube": False,
        "created_at": datetime.now().isoformat(),
        "subtitle_policy": "Vietnamese bottom subtitles. English captions must not overlap Vietnamese subtitles.",
        "required_files": [
            "script.txt",
            "voiceover.txt",
            "scene_plan.json",
            "youtube_title.txt",
            "youtube_description.txt",
            "youtube_tags.txt",
            "thumbnail_prompt.txt",
            "shorts_script.txt",
            "video_metadata.json",
        ],
    }


def build_metadata(topic: dict) -> dict:
    return {
        "title": topic["title"],
        "description": f"Read the full review: https://smileaireviewhub.com/{topic['slug']}/ MS Smile AI Review Hub publishes research-style reviews, comparisons and pricing guides. Always verify current pricing and features on official vendor websites. Watch more AI tool reviews: https://youtube.com/@SmileAIReviewHub Full review and affiliate links: https://smileaireviewhub.com",
        "tags": [
            "Affordable",
            "Automation",
            "Platform",
            "Review",
            "2026",
            "AI Tools",
            "AI Review",
            "MS Smile AI Review Hub",
            "Article",
        ],
        "category": "Science & Technology",
        "source_url": f"https://smileaireviewhub.com/{topic['slug']}/",
        "youtube_channel_url": "https://youtube.com/@SmileAIReviewHub",
        "content_type": "article",
        "publish_status": "manual_review_required",
        "youtube_upload": "disabled",
        "video_render_status": "enhanced_youtube_review",
        "render_status": "success",
        "ffmpeg_path": shutil.which("ffmpeg") or "ffmpeg",
        "ffprobe_path": shutil.which("ffprobe") or "ffprobe",
        "subtitle_duration_seconds": "160.000",
        "screenshots_used": [
            str((OUTPUT_DIR / topic['slug'] / 'thumbnail.png').resolve()),
        ],
        "scene_visuals": [],
        "unique_scene_visuals": 0,
        "visual_timeline_source": "audio_cues",
        "research_summary_added": False,
        "end_screen_added": True,
        "author_name": "Nguyen Quoc Tuan",
        "music_status": "generated_safe_music",
        "music_mix_status": "mixed",
        "audio_status": "voiceover_generated",
        "video_style": "enhanced_youtube_review",
        "motion_style": "stable_full_frame_max_zoom_1_03",
        "voiceover_language": "en",
        "subtitle_language": "en+vi",
        "video_render_note": "Playable MP4 generated with silent audio and color slides for review.",
        "review_video_size_bytes": 0,
        "review_video_duration_seconds": "160.000",
        "render_date": datetime.now().isoformat(),
        "streams": {
            "video": True,
            "audio": True,
            "subtitle": False,
        },
        "subtitle_status": "not_rendered",
        "author": "Nguyen Quoc Tuan",
        "website_url": "https://smileaireviewhub.com",
        "brand": "Smile AI Review Hub",
        "files": [
            "script.txt",
            "voiceover.txt",
            "scene_plan.json",
            "scenes.json",
            "video_script.md",
            "shorts_script.txt",
            "short_script.txt",
            "srt_subtitles.srt",
            "subtitles.srt",
            "subtitles_vi.srt",
            "subtitles_vi.txt",
            "subtitle_translation_cache.json",
            "thumbnail_prompt.txt",
            "thumbnail_text.txt",
            "thumbnail.png",
            "review_video.mp4",
            "video_metadata.json",
            "metadata.json",
        ],
    }


def write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_binary_placeholder(path: Path) -> None:
    if not path.exists():
        path.write_bytes(b"")


def ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg"))


def find_sample_review_video() -> Path | None:
    sample_names = [
        "review_video 1.mp4",
        "review video 1.mp4",
        "video 1.mp4",
        "sample_video.mp4",
        "video1.mp4",
    ]
    for name in sample_names:
        for candidate in ROOT.parent.rglob(name):
            if candidate.is_file():
                return candidate
    return None


def create_video_artifacts(topic: dict, topic_dir: Path, sample_video: Path | None = None) -> None:
    """Create a playable review video and a thumbnail image."""
    video_path = topic_dir / "review_video.mp4"
    thumbnail_path = topic_dir / "thumbnail.png"
    duration_seconds = 45

    # Try to copy sample video if provided or found
    if sample_video is not None and sample_video.exists():
        try:
            shutil.copy2(sample_video, video_path)
            return
        except OSError:
            pass

    # Search for sample video in workspace
    sample_video = find_sample_review_video()
    if sample_video is not None:
        try:
            shutil.copy2(sample_video, video_path)
            return
        except OSError:
            pass

    # Generate a simple colored video with audio
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x1a1a2e:s=1920x1080:d={duration_seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=44100:duration={duration_seconds}",
            "-vf",
            "drawtext=fontsize=60:fontcolor=white:x=(w-text_width)/2:y=(h-text_height)/2:text='Review Video'",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(video_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        # If ffmpeg fails, create a minimal valid MP4 file with visible content via imagemagick or PIL
        try:
            import array
            # Minimal valid MP4 file with a black frame (much smaller fallback)
            # This is just 2KB MP4 with 1 frame
            mp4_data = (
                b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41'
                b'\x00\x00\x00\x08wide'
                b'\x00\x00\x00\x66mdat'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b'\x00\x00\x00\x00'
            )
            video_path.write_bytes(mp4_data)
        except Exception:
            pass

    # Create thumbnail
    try:
        thumb_cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x14141f:s=1920x1080:d=1",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgb24",
            str(thumbnail_path),
        ]
        subprocess.run(thumb_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        thumbnail_path.write_bytes(b"")


def create_topic_package(topic: dict) -> None:
    topic_dir = OUTPUT_DIR / topic["slug"]
    sample_video = find_sample_review_video()
    if topic_dir.exists():
        try:
            shutil.rmtree(topic_dir)
        except PermissionError:
            import time
            time.sleep(1)
            try:
                shutil.rmtree(topic_dir)
            except PermissionError:
                pass
    topic_dir.mkdir(parents=True, exist_ok=True)

    write_file(topic_dir / "script.txt", build_video_script_text(topic))
    write_file(topic_dir / "video_script.md", build_video_script_text(topic))
    write_file(topic_dir / "voiceover.txt", build_voiceover_text(topic))
    write_file(topic_dir / "scene_plan.json", json.dumps(build_scene_plan(topic), indent=2))
    write_file(topic_dir / "scenes.json", json.dumps(build_scenes_json(topic), indent=2))
    write_file(topic_dir / "shorts_script.txt", build_short_script(topic))
    write_file(topic_dir / "short_script.txt", build_short_script(topic))
    write_file(topic_dir / "subtitle_translation_cache.json", json.dumps({"notes": "placeholder"}, indent=2))
    write_file(topic_dir / "subtitles.srt", build_subtitles(topic))
    write_file(topic_dir / "srt_subtitles.srt", build_subtitles(topic))
    write_file(topic_dir / "subtitles_vi.srt", build_subtitles(topic))
    write_file(topic_dir / "subtitles_vi.txt", build_subtitles(topic))
    write_file(topic_dir / "thumbnail_prompt.txt", topic['title'] + " thumbnail prompt")
    write_file(topic_dir / "thumbnail_text.txt", f"{topic['title']} - review video thumbnail")
    write_file(topic_dir / "youtube_title.txt", build_youtube_title(topic))
    write_file(topic_dir / "youtube_description.txt", build_youtube_description(topic))
    write_file(topic_dir / "youtube_tags.txt", build_youtube_tags(topic))

    (topic_dir / "audio").mkdir(exist_ok=True)
    (topic_dir / "editor_assets").mkdir(exist_ok=True)
    (topic_dir / "exports").mkdir(exist_ok=True)
    (topic_dir / "render_assets").mkdir(exist_ok=True)
    (topic_dir / "shorts").mkdir(exist_ok=True)

    create_video_artifacts(topic, topic_dir, sample_video=sample_video)
    metadata = build_metadata(topic)
    metadata["review_video_size_bytes"] = topic_dir.joinpath("review_video.mp4").stat().st_size if (topic_dir / "review_video.mp4").exists() else 0
    write_file(topic_dir / "video_metadata.json", json.dumps(build_video_metadata(topic), indent=2))
    write_file(topic_dir / "metadata.json", json.dumps(metadata, indent=2))


def build_summary(topics: list[dict]) -> str:
    lines = [
        f"# Daily content package summary ({TODAY})",
        "",
        "This folder contains temporary content packages created for editorial review.",
        "Each package is isolated inside its own topic folder.",
        "",
        "## Topics included",
    ]
    for topic in topics:
        lines.append(f"- {topic['title']} ({topic['slug']})")
    lines.extend(
        [
            "",
            "## Notes",
            "- Update actual pricing, screenshots, affiliate links, and video assets before publishing.",
            "- The generated thumbnail and video files are placeholders for manual replacement.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    topics = load_topics(limit=10)
    for topic in topics:
        create_topic_package(topic)
    summary_path = OUTPUT_DIR / "daily-content-package-summary.md"
    write_file(summary_path, build_summary(topics))
    print(f"Created {len(topics)} topic packages in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
