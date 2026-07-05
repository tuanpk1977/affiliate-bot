# Content Assistant Bot

## Overview

The Content Assistant Bot is a draft-only worker for Smile AI Review Hub. It does not replace Codex and it does not publish anything. Its job is to prepare reviewable article drafts, YouTube metadata, video scripts, and simple draft videos so Codex can review, improve, and publish through the existing project workflow.

## Safety Rules

The worker bot only writes to `draft-output/` and its cache file in `data/`. It does not deploy, commit, push, submit IndexNow, upload YouTube videos, post social content, or modify production publishing logic.

## Folder Structure

Daily output is created here:

```text
draft-output/
  YYYY-MM-DD/
    selected-topics.json
    rejected-topics.json
    run-summary.json
    worker-bot.log
    topic-slug/
      topic.json
      article.md
      article-score.json
      youtube-title.txt
      youtube-description.txt
      youtube-tags.txt
      youtube-chapters.txt
      thumbnail-prompt.txt
      image-prompts.txt
      video-script.txt
      video-outline.json
      draft-video.mp4
      status.json
      generation-log.txt
```

## Configuration

Edit:

```text
config/content_assistant_bot.json
```

Important settings:

- `topics_per_day`: default number of topics to select.
- `minimum_score`: minimum topic score to generate.
- `maximum_similarity`: duplicate similarity threshold.
- `output_folder`: draft output root.
- `video_duration_seconds`: draft MP4 duration.
- `topic_scores_path`: primary scored topic input.
- `topic_dashboard_path`: fallback topic dashboard input.
- `trending_topics_path`: fallback trend input.
- `existing_article_roots`: folders used for duplicate detection.
- `existing_video_root`: existing videos used for duplicate detection.

## How To Run

Daily draft run:

```powershell
python scripts/run_content_assistant_bot.py --limit 10 --dry-run
```

Fast article/package-only run:

```powershell
python scripts/run_content_assistant_bot.py --limit 10 --dry-run --skip-video
```

One-topic smoke test:

```powershell
python scripts/run_content_assistant_bot.py --limit 1 --dry-run
```

If all current hottrend topics already exist and the normal duplicate checker selects zero topics, run a safe smoke test:

```powershell
python scripts/run_content_assistant_bot.py --force-one-test --limit 1
```

This writes one duplicate draft to `draft-output/` for testing only. It still does not publish, deploy, upload, or submit anything.

`--dry-run` is a safety label. The worker always writes draft files only.

## Daily Workflow

1. Read scored topics from `data/topic_scores.json`.
2. Fall back to `data/topic_dashboard.json` or `data/trending_topics.json` if needed.
3. Check for duplicate topics against existing articles, existing videos, and published topic history.
4. Select the best topics by score.
5. Generate article drafts, YouTube packages, image prompts, scripts, outlines, and simple draft videos.
6. Save everything under `draft-output/YYYY-MM-DD/`.
7. Codex reviews and improves the selected draft before any publishing work happens.

## Troubleshooting

- If no topics are generated, check `data/topic_scores.json` and the `minimum_score` setting.
- If topics are rejected, open `draft-output/YYYY-MM-DD/rejected-topics.json`.
- If `draft-video.mp4` is missing, check `generation-log.txt`; ffmpeg may be unavailable.
- If a topic is skipped as duplicate, the reason is recorded in `rejected-topics.json`.

## Codex Review Workflow

After the worker finishes, Codex should review:

- `article.md` for accuracy, specificity, SEO, readability, internal links, and schema.
- `image-prompts.txt` for suitable article visuals.
- YouTube files for title, description, chapters, tags, and thumbnail direction.
- `draft-video.mp4` only as a basic draft, not a final upload-ready video.

## Future Improvements

The worker is modular so it can later support:

- 20-100 article drafts per day.
- Multiple websites.
- Multiple languages.
- Multiple YouTube channels.
- Multiple AI providers.
- Better draft video rendering with real voiceover and subtitles.
