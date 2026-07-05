from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import shutil
from typing import Any

from .article_generator import generate_article
from .config import WorkerBotConfig, load_config
from .data_loader import TopicCandidate, load_topic_candidates
from .duplicate_checker import DuplicateChecker
from .logger import WorkerLogger
from .topic_selector import select_topics, topic_to_json
from .utils import content_hash, read_json, write_json, write_text
from .video_generator import create_draft_video
from .youtube_generator import generate_youtube_package


def _internal_links() -> list[str]:
    return [
        "https://smileaireviewhub.com/reviews/",
        "https://smileaireviewhub.com/comparisons/",
        "https://smileaireviewhub.com/best-ai-seo-tools-2026/",
        "https://smileaireviewhub.com/best-website-builder-2026/",
    ]


def _legacy_scenes(candidate: TopicCandidate, duration: int = 45) -> list[dict[str, str]]:
    titles = ["Intro", "Overview", "Key Features", "Pricing", "Pros and Cons", "Final Verdict"]
    scene_len = max(5, duration // len(titles))
    scenes: list[dict[str, str]] = []
    start = 0
    for title in titles:
        end = min(duration, start + scene_len)
        scenes.append({"time": f"{start}-{end}", "type": title.lower().replace(" ", "-"), "title": title})
        start = end
    if scenes:
        scenes[-1]["time"] = scenes[-1]["time"].split("-")[0] + f"-{duration}"
    return scenes


def _ensure_video_output_shape(folder: Path) -> None:
    for relative in [
        "audio",
        "editor_assets/article_sections",
        "exports",
        "render_assets",
        "shorts/short-1",
        "shorts/short-2",
        "shorts/short-3",
    ]:
        (folder / relative).mkdir(parents=True, exist_ok=True)


def _copy_youtube_compat_files(folder: Path, youtube: dict[str, str]) -> None:
    mapping = {
        "youtube-title.txt": "youtube_title.txt",
        "youtube-description.txt": "youtube_description.txt",
        "youtube-tags.txt": "youtube_tags.txt",
        "thumbnail-prompt.txt": "thumbnail_prompt.txt",
        "thumbnail-text.txt": "thumbnail_text.txt",
        "video-script.txt": "script.txt",
    }
    for source, target in mapping.items():
        if source in youtube:
            write_text(folder / target, youtube[source].rstrip() + "\n")
    write_text(
        folder / "pinned_comment.txt",
        "Read the full guide and compare related tools on Smile AI Review Hub: https://smileaireviewhub.com\n",
    )
    for index in range(1, 4):
        short_dir = folder / "shorts" / f"short-{index}"
        write_text(short_dir / "script.txt", youtube.get("video-script.txt", "").rstrip() + "\n")
        write_text(short_dir / "title.txt", youtube.get("shorts-title.txt", "").rstrip() + "\n")


def _write_topic_folder(
    candidate: TopicCandidate,
    folder: Path,
    config: WorkerBotConfig,
    logger: WorkerLogger,
    skip_video: bool = False,
) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    _ensure_video_output_shape(folder)
    started = datetime.now()
    article, meta, image_prompts = generate_article(candidate, _internal_links())
    youtube = generate_youtube_package(candidate)
    topic_payload = topic_to_json(candidate)
    topic_payload["article_metadata"] = meta
    draft_hash = content_hash({"topic": topic_payload, "article": article, "youtube": youtube})

    write_json(folder / "topic.json", topic_payload)
    write_text(folder / "article.md", article)
    write_json(
        folder / "article-score.json",
        {
            "topic": candidate.topic,
            "slug": candidate.slug,
            "score": candidate.score,
            "source": candidate.source,
            "content_hash": draft_hash,
            "generated_at": started.isoformat(timespec="seconds"),
        },
    )
    write_text(folder / "image-prompts.txt", image_prompts + "\n")
    write_text(folder / "feature_image_prompt.txt", image_prompts.splitlines()[0].replace("Hero image: ", "").rstrip() + "\n")

    for filename, value in youtube.items():
        path = folder / filename
        if filename.endswith(".json"):
            write_text(path, value)
        else:
            write_text(path, value.rstrip() + "\n")
    _copy_youtube_compat_files(folder, youtube)

    # Compatibility files mirror the established video_output folder shape while staying draft-only.
    write_json(folder / "scenes.json", _legacy_scenes(candidate, config.video_duration_seconds))

    video_ok = False
    video_message = "video skipped"
    video_details: dict[str, Any] = {}
    if not skip_video:
        video_ok, video_message, video_details = create_draft_video(candidate, folder / "draft-video.mp4", config)
        if video_ok:
            shutil.copyfile(folder / "draft-video.mp4", folder / "review_video.mp4")
            shutil.copyfile(folder / "draft-video.mp4", folder / "exports" / "review_video.mp4")

    write_json(
        folder / "metadata.json",
        {
            "title": youtube["youtube-title.txt"],
            "description": youtube["youtube-description.txt"],
            "tags": [tag.strip() for tag in youtube["youtube-tags.txt"].split(",") if tag.strip()],
            "category": meta["category"],
            "source_url": meta["url"],
            "website_url": "https://smileaireviewhub.com",
            "author": "Nguyen Quoc Tuan",
            "author_name": "Nguyen Quoc Tuan",
            "brand": "Smile AI Review Hub",
            "content_type": "draft_review",
            "publish_status": "draft_only_codex_review_required",
            "youtube_upload": "disabled",
            "worker_bot": True,
            "video_render_status": "worker_draft_youtube_review",
            "render_status": "success" if video_ok else "warning",
            "audio_status": video_details.get("voice_status", "not_rendered"),
            "music_status": "not_added_worker_draft",
            "video_style": "article_section_review_draft",
            "subtitle_language": "en+vi",
            "subtitle_status": "bilingual_burned_and_srt" if video_ok else "not_rendered",
            "motion_style": "multi_scene_static_article_sections",
            "scene_visuals": video_details.get("scene_visuals", []),
            "unique_scene_visuals": len(video_details.get("scene_visuals", [])),
            "review_video_duration_seconds": video_details.get("duration_seconds", 0),
            "review_video_size_bytes": (folder / "review_video.mp4").stat().st_size if (folder / "review_video.mp4").exists() else 0,
            "streams": {
                "video": video_ok,
                "audio": bool(video_details.get("audio_stream")),
                "subtitles": (folder / "subtitles.srt").exists() and (folder / "subtitles_vi.srt").exists(),
            },
            "safety": {
                "published": False,
                "deployed": False,
                "youtube_uploaded": False,
                "social_posted": False,
                "indexnow_submitted": False,
            },
        },
    )

    status = {
        "status": "draft_ready",
        "topic": candidate.topic,
        "slug": candidate.slug,
        "score": candidate.score,
        "article_file": "article.md",
        "draft_video": "draft-video.mp4" if video_ok else "",
        "video_status": "ok" if video_ok else "warning",
        "video_message": video_message,
        "video_details": video_details,
        "warnings": ["voiceover_missing"] if video_details.get("voice_status") == "voiceover_missing" else [],
        "published": False,
        "deployment": "not_allowed_for_worker_bot",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_json(folder / "status.json", status)
    write_text(
        folder / "generation-log.txt",
        "\n".join(
            [
                f"Topic: {candidate.topic}",
                f"Slug: {candidate.slug}",
                f"Score: {candidate.score}",
                f"Source: {candidate.source}",
                f"Video: {video_message}",
                "Safety: draft only; no publish, deploy, YouTube upload, or social post.",
            ]
        )
        + "\n",
    )
    logger.log(f"Generated draft for {candidate.slug}: video={video_message}")
    return status


def run_worker_bot(
    config_path: str | Path | None = None,
    limit: int | None = None,
    run_date: str | None = None,
    skip_video: bool = False,
    force_one_test: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path or None) if config_path else load_config()
    day = run_date or date.today().isoformat()
    output_root = config.output_folder / day
    output_root.mkdir(parents=True, exist_ok=True)
    logger = WorkerLogger(output_root / "worker-bot.log")
    logger.log("Content Assistant Bot started")
    logger.log("Safety mode: draft output only")

    candidates = load_topic_candidates(config)
    checker = DuplicateChecker(config)
    selected, rejected = select_topics(candidates, config, checker, limit=limit, force_one_test=force_one_test)

    write_json(output_root / "selected-topics.json", [topic_to_json(item) for item in selected])
    write_json(output_root / "rejected-topics.json", rejected)
    logger.log(f"Loaded candidates={len(candidates)} selected={len(selected)} rejected={len(rejected)}")
    for item in rejected[:25]:
        logger.log(f"Rejected {item.get('slug')}: {item.get('reason')}")
    if force_one_test:
        logger.log("force-one-test enabled: one duplicate topic may be generated for smoke testing only")

    statuses: list[dict[str, Any]] = []
    for candidate in selected:
        statuses.append(_write_topic_folder(candidate, output_root / candidate.slug, config, logger, skip_video=skip_video))

    cache = read_json(config.cache_file, {})
    cache[day] = {"selected": [item.slug for item in selected], "generated_at": datetime.now().isoformat(timespec="seconds")}
    write_json(config.cache_file, cache)

    summary = {
        "run_date": day,
        "output_root": str(output_root),
        "candidates": len(candidates),
        "selected": len(selected),
        "rejected": len(rejected),
        "generated": len(statuses),
        "topics": [item["slug"] for item in statuses],
        "safety": {
            "published": False,
            "deployed": False,
            "youtube_uploaded": False,
            "social_posted": False,
            "indexnow_submitted": False,
        },
        "force_one_test": force_one_test,
    }
    write_json(output_root / "run-summary.json", summary)
    logger.log("Content Assistant Bot finished")
    return summary
