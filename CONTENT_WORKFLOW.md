# CONTENT_WORKFLOW

## Purpose

This document describes the daily content generation workflow for the AI content growth pipeline.
It focuses on website article generation, social draft generation, and IndexNow support.

## Workflow overview

1. **Discover trending topics**.
2. **Select the best topics for the day**.
3. **Generate article HTML and save it to `site_output/` and `data/published_static_pages/`**.
4. **Create manual social draft files under `social_drafts/`**.
5. **Create manual video draft assets under `video_output/`**.
6. **Build and sync the website output**.
7. **Optionally submit generated URLs to IndexNow**.

## Key scripts

- `python scripts/discover_ai_trends.py --limit 10`
- `python scripts/run_daily_content_growth.py --limit 10`
- `python scripts/run_daily_content_growth.py --discover --limit 10`
- `python scripts/run_daily_content_growth.py --limit 10 --dry-run`
- `python scripts/run_daily_content_growth.py --limit 10 --no-build --no-indexnow`

## Data flow

### Discovery

- `scripts/discover_ai_trends.py` runs the trend discovery engine.
- It writes discovered topics and reports into `data/trending_topics.json` and `data/trending_topics_daily_report.md`.
- If `data/trending_topics.json` exists and `--discover` is not used, the content workflow loads existing topics.

### Topic selection

- The workflow loads topics and normalizes scores.
- It selects top topics while avoiding duplicates and avoiding content already published.
- It limits similar content types and spreads coverage across formats.

### Article generation

- For each selected topic, the pipeline renders full HTML with article structure, schema, and meta tags.
- Articles are saved to:
  - `data/published_static_pages/<slug>/index.html`
  - `site_output/<slug>/index.html`
- The generated HTML includes:
  - canonical URLs
  - robots metadata
  - FAQ schema
  - internal link suggestions
  - affiliate disclosure section

### Social and video drafts

- Social drafts are written to `social_drafts/YYYY-MM-DD/<slug>/`.
- Video draft assets are written to `video_output/<slug>/`.
- Draft files are intentionally manual content for human review and platform posting.

## Build and sync

- Generated website HTML is placed in `site_output/` for deployment.
- The workflow may run `python build_site.py` to ensure the site is built and output is valid.
- It also syncs `site_output/` to `docs/` via `scripts/sync_site_output_to_docs.py`.

## IndexNow integration

- When enabled, the workflow submits generated URLs to IndexNow.
- `scripts/run_daily_content_growth.py` uses `submit_generated_urls()` if `--no-indexnow` is not present.
- The workflow keeps IndexNow submission optional for local testing.

## Safety settings

The content workflow intentionally avoids automated external publishing:

- `AUTO_YOUTUBE_UPLOAD=false`
- `AUTO_SOCIAL_POST=false`
- `CONTENT_GROWTH_AUTO_PUBLISH_WEBSITE=true`
- `CONTENT_GROWTH_VIDEO_DRAFTS_ONLY=true`
- `CONTENT_GROWTH_SOCIAL_DRAFTS_ONLY=true`

The workflow raises an error if `AUTO_YOUTUBE_UPLOAD` or `AUTO_SOCIAL_POST` is enabled.

## Output paths

- `data/trending_topics.json`
- `data/content_growth_reports/YYYY-MM-DD.md`
- `data/published_static_pages/<slug>/index.html`
- `site_output/<slug>/index.html`
- `video_output/<slug>/`
- `social_drafts/YYYY-MM-DD/<slug>/`
- `data/content_growth_performance_log.csv`

## Manual review

After generation, review the following manually before final promotion:

- Generated article content for vendor facts and pricing accuracy.
- Social draft tone and platform suitability.
- Video draft scripts and call-to-actions.
- IndexNow submission status and live `robots.txt`/`sitemap.xml` availability.

## Notes

- The content workflow is a website-first generator.
- Social and video drafts are not auto-posted.
- The workflow supports manual publishing of social and video content after review.
