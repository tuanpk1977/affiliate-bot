# Smile AI Review Hub Project Guide

This guide documents the current repository behavior so Codex, Copilot, or another AI assistant can understand the project before changing it.

## 1. Project overview

Smile AI Review Hub is an AI affiliate and content automation project for `https://smileaireviewhub.com`.

The project currently supports:

- AI/SaaS affiliate content generation.
- Static website generation.
- AI trend discovery.
- Topic scoring and daily content planning.
- YouTube review asset generation.
- SEO cleanup, schema upgrades, canonical routing, sitemap generation, and IndexNow submission.
- Cloudflare Pages publishing through the `docs/` folder and GitHub.

Important workflow boundaries:

- The bot can write articles and build website output.
- The bot can publish website files into the Cloudflare Pages publish folder.
- The bot can generate YouTube video files and metadata locally.
- The bot does not upload videos to YouTube automatically.
- The bot does not auto-post to Facebook, Quora, Reddit, DEV, Hashnode, LinkedIn, X, or other social platforms.
- Social content, when generated, is only a draft for manual posting.

### Quick start for article publishing

If you only need to publish today's articles, read this section first and ignore the rest of the repo.

Recommended daily article flow:

```powershell
python scripts/run_daily_publish_pipeline.py --limit 5 --publish --skip-discover
python build_site.py
python scripts/sync_site_output_to_docs.py
git add docs data/published_static_pages data/published_today.csv data/published_today.json data/website_publish_report.csv data/website_publish_report.json data/article_draft_report.csv data/article_draft_report.json
git commit -m "Publish daily articles"
git push origin main
```

What this does:

- selects the top topics already prepared in `data/today_selected_topics.csv`
- writes the article source pages into `data/published_static_pages/<slug>/index.html`
- builds the public static site into `site_output/`
- copies the final publish output into `docs/`
- pushes the updated website to GitHub so Cloudflare Pages can redeploy

Where to inspect the result:

- article source snapshots: `data/published_static_pages/<slug>/index.html`
- public build output: `site_output/<slug>/index.html`
- deployed publish folder: `docs/<slug>/index.html`
- publish reports: `data/published_today.csv`, `data/website_publish_report.csv`, `data/article_draft_report.csv`

If the user asks for "the 5 newest/trendiest topics", use the first five rows from `data/today_selected_topics.csv`.

## 2. Main folder structure

### `data/`

Holds project data, reports, generated article source snapshots, scoring outputs, CSV indexes, and batch reports.

Important files include:

- `data/trending_topics.json`: raw selected topics from AI trend discovery.
- `data/trending_topics_daily_report.md`: readable report explaining selected trend topics.
- `data/topic_scores.json`: production topic scoring output. This is the main file to inspect for detailed topic scores.
- `data/topic_dashboard.json`: dashboard-style aggregate view of scored topics.
- `data/topic_plan.json`: daily planning output from the topic scoring engine.
- `data/topic_scoring_rules.json`: scoring weights/rules.
- `data/published_static_pages/`: generated article HTML snapshots used by the incremental site build.
- `data/content_growth_reports/`: daily content generation reports.
- `data/video_article_index.csv`: article index used by video rendering discovery.

### `modules/`

Contains reusable Python modules for the site and automation system.

Examples:

- `modules/content_growth_pipeline.py`: daily content growth pipeline.
- `modules/ai_trend_discovery.py`: trend discovery engine.
- `modules/topic_scorer.py`, `modules/topic_ranker.py`, `modules/content_strategy.py`, `modules/content_planner.py`: topic scoring and planning logic.
- `modules/video_priority.py`, `modules/social_score.py`: video/social priority scoring.
- `modules/sitemap_generator.py`: sitemap generation.
- `modules/canonical_routes.py`: canonical URL and redirect generation.
- `modules/seo_technical_cleanup.py`: technical SEO cleanup.
- `modules/structured_data_upgrade.py`: structured data post-processing.
- `modules/internal_linker.py`: internal linking pass.

### `scripts/`

Contains CLI scripts for project operations.

Important scripts:

- `scripts/discover_ai_trends.py`: discovers trending AI/SaaS topics and writes `data/trending_topics.json`.
- `scripts/score_topics.py`: scores trend topics and writes `data/topic_scores.json`, `data/topic_dashboard.json`, and `data/topic_plan.json`.
- `scripts/update_hottrend_tracking.py`: appends scored hottrend topics to persistent daily history, weekly/monthly summaries, latest dashboard CSV, and an optional Excel workbook.
- `scripts/run_daily_content_growth.py`: daily content generation CLI wrapper.
- `scripts/generate_video_assets.py`: creates YouTube scripts, subtitles, thumbnails, and renders videos.
- `scripts/sync_site_output_to_docs.py`: copies `site_output/` into `docs/` for Cloudflare Pages publishing.
- `scripts/submit_indexnow.py`: submits URLs to IndexNow.
- `scripts/check_indexnow_status.py`: checks IndexNow key, sitemap, robots, and diagnostics.
- `scripts/update_youtube_links.py`: reads YouTube links from CSV and updates website video sections/status files.

### `docs/`

Current Cloudflare Pages publish folder.

After build and sync, this folder contains the static website files that are pushed to GitHub. Cloudflare Pages deploys from this folder.

Do not manually edit generated HTML in `docs/` unless there is an emergency. Prefer changing the source/generator and rebuilding.

### `draft_output/`

Generated drafts, admin previews, dashboards, and temporary review outputs. This is not the main public publish folder.

### `landing_pages/`

Landing page source/output area. Some generated landing page output appears under `landing_pages/output/`.

### `site_output/`

Primary generated static site output.

`build_site.py` writes or updates this folder. Then `scripts/sync_site_output_to_docs.py` copies it into `docs/`.

### `tests/`

Python unit tests and validation tests.

Examples:

- `tests/test_ai_trend_discovery.py`
- `tests/test_topic_decision_engine.py`
- `tests/test_structured_data_upgrade.py`
- `tests/test_review_page_builder.py`
- `tests/test_faq_schema_integrity.py`

### Root scripts

- `build_site.py`: builds or post-processes the static website into `site_output/`.
- `run_daily_content_growth.py`: root wrapper for `scripts/run_daily_content_growth.py`.
- `main.py`: older/full site generation entry point used by full build mode.

## 3. Current website publishing workflow

The current website publishing flow is:

```powershell
python build_site.py
python scripts/sync_site_output_to_docs.py
git add docs
git commit -m "Update website"
git push origin main
```

Cloudflare Pages deploys from the GitHub repository after `main` is pushed.

### Mandatory pre-publish health gate

After building and syncing `site_output/` to `docs/`, run:

```powershell
python scripts/pre_publish_gate.py --urls-file data/published_today.json --repair
```

The gate validates only the current batch as a blocking check and also writes the full-site diagnostics to `reports/`. Do not run `git push` when this command returns a non-zero exit code.

Generated operational reports:

- `reports/health-report.md`
- `reports/dashboard.json`
- `reports/dashboard.md`
- `reports/content-qa.md`
- `reports/internal-link-map.md`

After Cloudflare deploys, `.github/workflows/post-deploy-indexing.yml` waits for the changed URLs, performs smart live validation, submits only changed URLs to IndexNow, submits the sitemap to Bing at most once per day, optionally submits it through the Google Search Console API, and writes:

- `reports/deployment-report.md`
- `reports/indexing-report.md`
- `logs/indexing/<date>/publishing-report-<time>.json`

The daily health workflow runs at 06:00 Asia/Bangkok and stores the generated reports as a GitHub Actions artifact.

## Operational Rules

- Never publish or deploy if preflight fails.
- Never submit IndexNow before the deployed URL returns HTTP 200 and its canonical is valid.
- Never include invalid, redirected, parameterized, draft, preview, or `/go/` URLs in the sitemap.
- Update `lastmod` only when page content changes.
- Submit only URLs changed by the current Git diff unless a full submission is explicitly requested.
- Submit the Bing sitemap at most once per UTC day.
- Do not use the retired unauthenticated Google sitemap ping endpoint. Use Search Console API credentials when configured; otherwise rely on the updated sitemap.
- Every article must contain an Author, visible FAQ with matching FAQ schema, Breadcrumb schema, at least two internal links, an external authority reference, and an image with useful ALT text.
- Generate health, QA, deployment, and indexing reports after every deployment.
- If validation fails, stop immediately and state the failed checks.
- Attempt deterministic repairs first: exact duplicate paragraphs, invalid canonical, invalid schema author, missing image ALT, and a missing image fallback.
- Never silently ignore unresolved broken links, missing media, invalid schema, or orphan pages.
- Deployment recovery checks use 1, 3, 10, and 30 minute delays, then stop and report. GitHub Actions concurrency prevents duplicate deployment checks.

Safe daily sequence:

```powershell
python scripts/run_daily_publish_pipeline.py --limit 10 --publish
python build_site.py
python scripts/sync_site_output_to_docs.py
python scripts/generate_sitemap.py --publish-root docs --mirror-to site_output --updated-urls-file data/published_today.json
python scripts/pre_publish_gate.py --urls-file data/published_today.json --repair
git add docs data reports
git commit -m "Publish daily articles"
git push origin main
```

The final push triggers Cloudflare Pages and post-deploy indexing automatically.

Notes:

- `site_output/` is the generated site output.
- `docs/` is the Cloudflare publish folder.
- `netlify.toml` may exist, but the active workflow described in this project is Cloudflare Pages through `docs/`.
- Do not use `wrangler login` unless the deployment method is explicitly changed. The observed workflow has been GitHub push to Cloudflare Pages.

## 4. Daily trend discovery and topic scoring

Run trend discovery:

```powershell
python scripts/discover_ai_trends.py --limit 10 --max-per-source 40
```

This writes:

- `data/trending_topics.json`
- `data/trending_topics_daily_report.md`

Run production topic scoring:

```powershell
python scripts/score_topics.py --input data/trending_topics.json --output data/topic_scores.json --dashboard-output data/topic_dashboard.json --plan-output data/topic_plan.json --rules data/topic_scoring_rules.json
```

This writes:

- `data/topic_scores.json`
- `data/topic_dashboard.json`
- `data/topic_plan.json`

Run production topic scoring and update hottrend history in one command:

```powershell
python scripts/score_topics.py --input data/trending_topics.json --output data/topic_scores.json --dashboard-output data/topic_dashboard.json --plan-output data/topic_plan.json --rules data/topic_scoring_rules.json --update-history
```

To inspect the detailed scores after running hottrend, open:

```text
data/topic_scores.json
```

That file contains per-topic scores such as total score, traffic score, revenue score, SEO score, recommendation, content decision, video priority, and social scores.

For a human-readable explanation of why trend topics were selected, open:

```text
data/trending_topics_daily_report.md
```

### Hottrend tracking history

The persistent hottrend tracker records topic performance every time scored topics are saved.

Manual tracker command:

```powershell
python scripts/update_hottrend_tracking.py --scores data/topic_scores.json
```

This writes:

- `data/hottrend_topic_history.csv`: full daily history. Use this to track first seen date, last seen date, times seen, score changes, and rank changes.
- `data/hottrend_latest_dashboard.csv`: latest run only, sorted for day-to-day review.
- `data/hottrend_weekly_summary.csv`: weekly grouped score and recommendation summary.
- `data/hottrend_monthly_summary.csv`: monthly grouped score and recommendation summary.
- `data/hottrend_topic_history.xlsx`: Excel workbook if `openpyxl` is available.
- `data/master_dashboard.xlsx`: master workbook with latest, history, weekly/monthly, rising/declining, article/video, affiliate, index, and YouTube status sheets.
- `data/hottrend_dashboard.html`: local HTML dashboard for quick review. This is not published to the website.

Excel workbook sheets:

- `Latest Dashboard`: current run topics and recommended action.
- `Full History`: every tracked topic row over time.
- `Weekly Summary`: average, best, latest score, recommendation trend, and video priority trend by week.
- `Monthly Summary`: same summary by month.
- `Rising Topics`: latest topics with positive score change.
- `Declining Topics`: latest topics with negative score change.
- `Video Candidates`: latest topics recommended for video.
- `Article Candidates`: latest topics recommended for article work.
- `Monitor - Skip`: topics that should be watched or skipped.

Safe daily hottrend workflow:

```powershell
python scripts/discover_ai_trends.py --limit 10 --max-per-source 40
python scripts/score_topics.py --input data/trending_topics.json --output data/topic_scores.json --dashboard-output data/topic_dashboard.json --plan-output data/topic_plan.json --rules data/topic_scoring_rules.json --update-history
```

Open `data/hottrend_topic_history.xlsx` for Excel analysis, or open the CSV files directly if Excel output is skipped.

### How to run hottrend scoring and open the dashboard

Recommended daily command sequence:

```powershell
python scripts/discover_ai_trends.py --limit 10 --max-per-source 40
python scripts/score_topics.py --input data/trending_topics.json --output data/topic_scores.json --dashboard-output data/topic_dashboard.json --plan-output data/topic_plan.json --rules data/topic_scoring_rules.json --update-history
```

After the second command finishes, review:

```text
data/master_dashboard.xlsx
data/hottrend_latest_dashboard.csv
data/hottrend_topic_history.csv
data/hottrend_weekly_summary.csv
data/hottrend_monthly_summary.csv
data/hottrend_dashboard.html
data/topic_scores.json
```

Score grades:

- `Excellent`: 85-100
- `Strong`: 75-84
- `Good`: 65-74
- `Monitor`: 50-64
- `Skip`: below 50

The scoring model prioritizes buyer intent first, then SEO opportunity, traffic potential, affiliate/revenue intent, video potential, social discussion potential, and freshness. Commercial review, comparison, pricing, alternatives, discount/coupon, pros/cons, tutorial, guide, and SaaS/software topics receive a controlled boost when buyer intent and revenue/SEO fit are present. News-only topics such as funding, launches, announcements, stock movement, and press releases are penalized and should rarely become daily winners.

Daily recommendation grades:

- `Excellent`: 90-100, plan Website + YouTube + Social.
- `Strong`: 80-89, plan Website + YouTube.
- `Good`: 70-79, plan Website.
- `Watch`: 60-69, manual review only.
- `Skip`: below 60, ignore.

The 6:00 AM hottrend workflow is planning-only. It must not generate articles, website pages, YouTube videos, social posts, deploys, git pushes, Cloudflare publishes, or IndexNow submissions.

Manual one-time daily planner run:

```powershell
python scripts/run_hottrend_daily_planner.py
```

Long-running local scheduler, daily at 06:00 local time:

```powershell
python scripts/run_hottrend_daily_planner.py --schedule --hour 6 --minute 0
```

This scheduler only runs:

- `scripts/discover_ai_trends.py`
- `scripts/score_topics.py --update-history`
- hottrend CSV/Excel/HTML dashboard generation

Only after manually reviewing the dashboard should content generation be run separately with `run_daily_content_growth.py`.

## 5. Daily content generation workflow

Generate articles from the current trend data:

```powershell
python run_daily_content_growth.py --limit 10 --no-indexnow
```

Current behavior:

- Reads topic data from `data/trending_topics.json`.
- Avoids already-published slugs.
- Writes article snapshots to `data/published_static_pages/`.
- Writes generated pages to `site_output/`.
- Writes video draft assets to `video_output/<slug>/`.
- Writes social draft assets to `social_drafts/<slug>/`.
- Builds and syncs the site unless `--no-build` is used.
- Does not upload YouTube videos.
- Does not post social content.

Dry run example:

```powershell
python run_daily_content_growth.py --limit 1 --dry-run --no-build --no-indexnow
```

Dry-run topic scoring integration:

```powershell
python run_daily_content_growth.py --limit 1 --dry-run --no-build --no-indexnow --score-topics
```

## 5A. Performance, revenue, and lifecycle tracking

The project has a reporting-only business intelligence layer. It does not publish, deploy, upload YouTube videos, or post to social platforms.

Main output files:

- `data/content_lifecycle.csv` and `data/content_lifecycle.json`: topic/article/video/revenue lifecycle view.
- `data/revenue_dashboard.csv` and `data/revenue_dashboard.json`: estimated affiliate/revenue opportunity dashboard.
- `data/gsc_performance_pages.csv`: imported page-level Google Search Console data.
- `data/gsc_performance_queries.csv`: imported query-level Google Search Console data.
- `data/youtube_analytics.csv`: imported YouTube analytics data.
- `data/social_analytics.csv`: manual social performance tracking template.
- `data/social_analytics_dashboard.csv`: social summary by platform.
- `data/content_refresh_recommendations.csv` and `.json`: refresh recommendations.
- `data/competitor_targets.csv`: manual competitor input template.
- `data/competitor_gap_analysis.csv`: competitor gap output.
- `data/internal_link_recommendations.csv`: dry-run internal link recommendations.
- `data/daily_executive_dashboard.html` and `.json`: local executive dashboard.
- `data/master_dashboard.xlsx`: Excel workbook with hottrend, lifecycle, revenue, YouTube, social, refresh, competitor, and internal link sheets when `openpyxl` is available.

Safe reporting commands:

```powershell
python scripts/update_content_lifecycle.py
python scripts/import_gsc_performance.py --input path\to\gsc_export.csv
python scripts/import_youtube_analytics.py --input path\to\youtube_export.csv
python scripts/update_social_analytics.py
python scripts/recommend_content_refresh.py
python scripts/competitor_gap_analysis.py
python scripts/recommend_internal_links.py
python scripts/build_executive_dashboard.py
```

The GSC and YouTube import scripts accept manual CSV exports. If no input file is provided, they only create/verify the expected template files.

The internal link recommendation script is dry-run by default. `--apply` is currently intentionally non-mutating in the safe reporting layer.

When hottrend scoring is run with `--update-history`, the system updates hottrend history and then refreshes lifecycle, revenue, refresh, competitor, social, and internal link dashboard sheets:

```powershell
python scripts/score_topics.py --input data/trending_topics.json --output data/topic_scores.json --dashboard-output data/topic_dashboard.json --plan-output data/topic_plan.json --rules data/topic_scoring_rules.json --update-history
```

Open these files first after a hottrend run:

```text
data/topic_scores.json
data/topic_plan.json
data/hottrend_latest_dashboard.csv
data/master_dashboard.xlsx
data/daily_executive_dashboard.html
```

Topic priority decisions:

- `TOP 1: Write now`: strongest current topic.
- `TOP 2-3: Write today`: next best topics for the same day.
- `Video candidate`: topic has strong YouTube potential.
- `Evergreen candidate`: topic has durable long-term value.
- `Watch`: monitor before writing.
- `Skip`: low priority or poor fit.

## 5B. AI CEO Dashboard workflow

The AI CEO Dashboard is a recommendation-only operating dashboard. It answers what to write, what not to write, what to refresh, what video to create, where competitors are ahead, which keywords are missing, and which pages have revenue potential.

It does not write articles, render videos, deploy, submit IndexNow, upload YouTube videos, or post social content.

Main files:

- `modules/opportunity_forecast.py`: calculates Money Score, estimated monthly traffic, estimated affiliate clicks, estimated revenue, difficulty, ranking speed, and confidence.
- `scripts/update_opportunity_forecast.py`: writes `data/opportunity_forecast.csv` and `data/opportunity_forecast.json`.
- `scripts/competitor_watch.py`: reads `data/competitor_targets.csv` and writes `data/competitor_watch.csv/json`.
- `scripts/keyword_gap_analysis.py`: compares competitor target keywords against current lifecycle/content data and writes `data/keyword_gap.csv/json`.
- `scripts/build_internal_link_plan.py`: creates `data/internal_link_plan.csv` with 5-10 recommended internal links per source page when possible.
- `scripts/build_ceo_dashboard.py`: writes `data/daily_ceo_dashboard.html/json` and updates `data/master_dashboard.xlsx`.

Money Score decisions:

- `WRITE NOW`: strongest money/topic fit.
- `WRITE THIS WEEK`: good money/topic fit, but not urgent enough for top slot.
- `WATCH`: monitor until more signal appears.
- `REFRESH`: existing page should be improved before writing a new page.
- `DELETE`: weak candidate to avoid or prune from future plans; this does not delete files automatically.

Manual CEO dashboard command:

```powershell
python scripts/build_ceo_dashboard.py
```

Daily 06:00 recommendation-only planner:

```powershell
python scripts/run_hottrend_daily_planner.py --schedule --hour 6 --minute 0
```

The scheduled planner runs discovery, scoring, hottrend history, opportunity forecast, competitor watch, keyword gap, internal link recommendation, and the CEO dashboard. It remains recommendation-only.

Open these first every morning:

```text
data/daily_ceo_dashboard.html
data/master_dashboard.xlsx
data/opportunity_forecast.csv
data/competitor_watch.csv
data/keyword_gap.csv
data/internal_link_plan.csv
```

## 6. YouTube video workflow

Video files are generated locally under:

```text
video_output/<slug>/
```

Typical folder contents include:

- `review_video.mp4`
- `metadata.json`
- `script.txt` or `video_script.txt`
- `voiceover.txt` or `transcript.txt`
- `subtitles.srt`
- `subtitles_vi.srt` or `subtitles_vi.txt`
- `thumbnail.png`
- `thumbnail_text.txt`
- `youtube_title.txt`
- `youtube_description.txt`
- `youtube_tags.txt`
- `pinned_comment.txt`

Render one video:

```powershell
python scripts/generate_video_assets.py --render --slug example-slug --skip-shorts --force
```

The video renderer discovers pages through CSV indexes such as:

```text
data/video_article_index.csv
```

If a newly generated article is not rendered, check that its slug and URL exist in `data/video_article_index.csv`.

Important:

- The project does not upload to YouTube automatically.
- After manual upload, paste the YouTube URL into the upload links CSV and run the YouTube link update workflow.

## 7. YouTube link website update workflow

YouTube links are managed through CSV files such as:

```text
video_output/upload_links.csv
data/upload_links.csv
```

Depending on the current workflow, the update script reads upload link rows and injects or updates video sections in matching website pages.

Common command:

```powershell
python scripts/update_youtube_links.py
```

Expected behavior:

- Read rows with YouTube URLs.
- Update matching article/video status records.
- Add a "Watch the video review" section where supported.
- Rebuild the site.
- Sync output to `docs/`.

Verify the script source before changing CSV location assumptions, because both `video_output/upload_links.csv` and `data/upload_links.csv` have been used in project history.

## 8. IndexNow workflow

IndexNow and sitemap submission support is implemented through:

```text
scripts/submit_indexnow.py
scripts/check_indexnow_status.py
scripts/validate_publishing_batch.py
scripts/post_deploy_indexing.py
modules/publishing_indexing.py
modules/search_engine_submission.py
docs/indexnow-key.txt
.github/workflows/post-deploy-indexing.yml
```

Manual submission:

```powershell
python scripts/submit_indexnow.py --latest 100
```

Diagnostics:

```powershell
python scripts/check_indexnow_status.py
```

Current intended behavior:

- Submit only valid `https://smileaireviewhub.com` URLs.
- Avoid localhost, preview, draft, and off-domain URLs.
- Read the production sitemap from `docs/sitemap.xml`.
- Use `docs/indexnow-key.txt` for the key file.
- Run local validation before a content commit is pushed.
- After GitHub push, wait for every new URL and the sitemap to be live on Cloudflare.
- Submit each new batch to IndexNow only after all safety checks pass.
- Submit the sitemap to Bing at most once per UTC day when `BING_WEBMASTER_API_KEY` is configured.
- Submit the sitemap through the Google Search Console API at most once per UTC day when credentials are configured.
- If Google credentials are absent, record natural sitemap discovery instead of calling the retired ping endpoint.

Safe daily sequence:

```powershell
python scripts/generate_sitemap.py --publish-root docs --mirror-to site_output --updated-urls-file data/published_today.json
python scripts/validate_publishing_batch.py --urls-file data/published_today.json
git add docs site_output/sitemap.xml data/published_today.json
git commit -m "Publish daily content batch"
git push origin main
```

The push triggers `.github/workflows/post-deploy-indexing.yml`. It performs:

```text
wait for Cloudflare deployment
-> HTTP 200 check for every newly added page
-> live sitemap XML and membership check
-> IndexNow submission
-> Bing sitemap submission (daily limit)
-> Google Search Console sitemap submission or natural-discovery log
-> indexing report artifact
```

Persistent local logs are written under `logs/indexing/`. GitHub Actions uploads the same directory as
an artifact retained for 90 days. Do not commit API keys or service-account JSON files.

## 9. Sitemap, robots, canonical, and SEO post-processing

`build_site.py` runs multiple post-processing passes, including:

- Technical SEO cleanup.
- Bilingual page generation.
- GSC 404 recovery page generation.
- Trust/localization enhancements.
- Internal linking.
- AI search/FAQ enhancements.
- Facebook/OpenGraph metadata post-processing.
- SEO title optimization.
- Legacy slug normalization.
- Structured data upgrades.
- Canonical route generation.
- Sitemap generation.

The sitemap is generated at:

```text
site_output/sitemap.xml
docs/sitemap.xml
```

After syncing, Cloudflare serves:

```text
https://smileaireviewhub.com/sitemap.xml
```

## 10. 404 and redirect handling

Known recovery and routing modules include:

- `modules/gsc_404_recovery.py`
- `modules/canonical_routes.py`
- `modules/legacy_slug_normalizer.py`
- `modules/seo_technical_cleanup.py`
- `modules/site_builder.py`

When fixing 404s:

1. Check whether a real generated page exists in `site_output/` and `docs/`.
2. Check whether the URL appears in `sitemap.xml`.
3. Check whether `_redirects` is overriding the URL.
4. Fix the generator/source module, not only the generated `docs/_redirects`.
5. Rebuild and sync before testing live.

## 11. Tests and targeted validation

Targeted tests for trend scoring:

```powershell
python -m unittest tests.test_topic_decision_engine -v
```

Trend scoring direct test:

```powershell
python scripts/score_topics.py --input data/trending_topics.json --output data/topic_scores.json --dashboard-output data/topic_dashboard.json --plan-output data/topic_plan.json --rules data/topic_scoring_rules.json
```

Hottrend tracking targeted test:

```powershell
python -m unittest tests.test_hottrend_tracking -v
```

Content Intelligence targeted test:

```powershell
python -m unittest tests.test_content_intelligence -v
```

## 11A. AI Content Intelligence Platform

The AI Content Intelligence layer is recommendation-only. It does not write articles,
generate videos, deploy, submit IndexNow, upload YouTube videos, or post to social
platforms.

Main outputs:

```text
data/google_trends.csv
data/google_news.csv
data/youtube_trends.csv
data/reddit_intelligence.csv
data/producthunt_dashboard.csv
data/x_trends.csv
data/linkedin_trends.csv
data/newsletter_intelligence.csv
data/intelligence_topics.csv
data/ai_memory.csv
data/auto_priority_engine.csv
data/content_intelligence_dashboard.html
data/content_intelligence_summary.json
data/master_dashboard.xlsx
```

Safe collector commands:

```powershell
python scripts/import_google_trends.py
python scripts/import_google_news.py --rss data/google_news_sample.xml
python scripts/import_youtube_trends.py --input data/youtube_trends_input.csv
python scripts/import_reddit_intelligence.py --input data/reddit_input.csv
python scripts/import_producthunt_intelligence.py --input data/producthunt_input.csv
python scripts/import_x_trends.py --input data/x_input.csv
python scripts/import_linkedin_trends.py --input data/linkedin_input.csv
python scripts/newsletter_import.py --input data/newsletter_input.csv
```

Build the reporting dashboard only:

```powershell
python scripts/build_content_intelligence_dashboard.py
```

Daily recommendation workflow:

```powershell
python scripts/run_hottrend_daily_planner.py
```

This workflow runs discovery, topic scoring, hottrend tracking, the CEO dashboard,
and the Content Intelligence dashboard. It is still planning-only.

The AI CEO Dashboard answers:

- What to write.
- What not to write.
- What to refresh.
- What video to create.
- Which competitor topics are worth monitoring.
- Which keywords are missing.
- Which pages can make money.
- Estimated traffic and affiliate revenue.
- Estimated difficulty and daily priority.

The spreadsheet `data/master_dashboard.xlsx` is the main file to open in Excel.
Important sheets include `Executive Summary`, `Auto Priority`, `AI Memory`,
`Google Trends`, `YouTube Trends`, `Competitor Watch`, `Keyword Gap`,
`Revenue Forecast`, and `Video Ideas`.

The newer AI Content Operations layer adds these planning-only sheets:

- `Today Write Plan`: the short daily action list, including write today, backup topics, videos, refreshes, and content gaps.
- `Money Ranking`: buyer-intent and affiliate-fit ranking for current scored topics.
- `Publishing Queue`: status planning only; it does not publish.
- `Duplicate Risk`: merge, refresh, skip, or new-topic risk checks.
- `Authority Score`: cluster-level authority and content gap score.
- `Content Gap`: missing review, pricing, alternatives, comparison, tutorial, FAQ, or video assets.
- `Content Clusters`: pillar/review/comparison/pricing/tutorial/alternatives grouping.
- `Internal Link Cluster Plan`: recommended internal links by cluster.
- `AI Auto Editor Report`: records non-invasive draft optimization runs.

Planning-only AI CEO command:

```powershell
python scripts/run_today_write_plan.py
```

This reads existing scoring/content data and writes CSV, JSON, and Excel sheets.
It does not write articles, create videos, build the website, deploy, commit, push,
submit IndexNow, upload YouTube, or post social content.

Daily 6:00 AM recommendation workflow:

```powershell
python scripts/run_hottrend_daily_planner.py --schedule --hour 6 --minute 0
```

One-time morning run:

```powershell
python scripts/run_hottrend_daily_planner.py
python scripts/validate_excel_workbook.py
```

After validation passes, open `data/master_dashboard.xlsx`, start with
`Today Write Plan`, then check `Money Ranking`, `Duplicate Risk`, and
`Content Gap` before asking Codex to write or refresh anything.

Individual planning commands:

```powershell
python scripts/check_duplicate_topics.py
python scripts/build_money_ranking.py
python scripts/update_publishing_queue.py
python scripts/build_content_clusters.py
python scripts/run_auto_editor.py --input draft_output/example.html --output draft_output/example.optimized.html
python scripts/generate_article_drafts.py --limit 10
```

These commands are safe analysis/reporting commands only.

### AI Content Publishing Engine

The Content Operations layer is recommendation-first. It does not publish.
It upgrades hottrend output into a publishing plan with these files:

```text
data/ai_priority_dashboard.csv
data/revenue_opportunity.csv
data/daily_publishing_schedule.csv
data/website_publishing_queue.csv
data/today_write_plan.csv
data/master_dashboard.xlsx
```

Important behavior:

- Existing articles should appear as `REFRESH`, not `CREATE`.
- New article opportunities should appear as `CREATE`.
- The same slug should not appear as both `CREATE` and `REFRESH`.
- Video work is a recommendation column, not an upload action.
- Website Publishing Queue stops at `READY_FOR_REVIEW`.

The final priority score is configurable in:

```text
data/ai_priority_formula.json
```

It combines money, trend, affiliate, competition, content gap, internal link,
Google impression, CTR, YouTube, and social scores.

Draft-only article generation:

```powershell
python scripts/run_today_write_plan.py
python scripts/generate_article_drafts.py --limit 10
```

Drafts are written to `draft_output/*.md` with status `READY_FOR_REVIEW`.
They are not added to the website, not built, not deployed, and not submitted
to IndexNow.

### How to safely regenerate `master_dashboard.xlsx`

Close Microsoft Excel before regenerating the workbook. If Excel has
`data/master_dashboard.xlsx` open, the dashboard writer will not overwrite it.
Instead, it writes a pending file such as:

```text
data/master_dashboard.pending_YYYYMMDD_HHMMSS.xlsx
```

Safe workflow:

```powershell
python scripts/run_hottrend_daily_planner.py
python scripts/validate_excel_workbook.py
```

Open `data/master_dashboard.xlsx` only after the validator prints `PASS`.
The writer saves through a temporary workbook first, validates it with
`openpyxl`, backs up the previous workbook under `data/backups/`, and then
replaces the master workbook atomically. This reduces the chance of Excel
showing a recovery warning.

IndexNow diagnostics:

```powershell
python scripts/check_indexnow_status.py
```

Build-only validation:

```powershell
python build_site.py
python scripts/sync_site_output_to_docs.py
```

Do not deploy from tests unless the user explicitly asks.

## 12. Daily AI Content Factory

This workflow turns scored hottrend data into local recommendations, article drafts, optional local website source pages, and manual YouTube video packages.

Safe planning command:

```powershell
python scripts/run_daily_publish_pipeline.py --limit 10
```

Full local content factory command:

```powershell
python scripts/run_daily_publish_pipeline.py --limit 10 --publish --generate-video-packages
```

Important behavior:

- `--publish` writes local source pages into `data/published_static_pages/`.
- It does not build `site_output/` or `docs/`.
- It does not deploy Cloudflare Pages.
- It does not commit, push, upload YouTube, post social content, or submit IndexNow.
- Video package files are created under `video_output/<slug>/` for manual YouTube upload.

Main outputs:

- `data/today_selected_topics.csv`
- `data/today_selected_topics.json`
- `data/title_tests.csv`
- `data/topical_authority.csv`
- `data/internal_link_insertions.csv`
- `data/refresh_queue.csv`
- `data/website_publish_report.csv`
- `data/video_package_report.csv`
- `draft_output/articles/<slug>.md`
- `draft_output/articles/<slug>.json`
- `video_output/<slug>/video_script.md`
- `video_output/<slug>/youtube_title.txt`
- `video_output/<slug>/youtube_description.txt`
- `video_output/<slug>/youtube_tags.txt`
- `video_output/<slug>/thumbnail_prompt.txt`
- `video_output/<slug>/short_script.txt`
- `video_output/<slug>/srt_subtitles.srt`
- `video_output/<slug>/scenes.json`
- `video_output/<slug>/voiceover.txt`

The decision engine uses:

- `WRITE_NOW` for new topics worth creating.
- `REFRESH_EXISTING` for topics where an article already exists.
- `VIDEO_ONLY` when the article exists and the main opportunity is video.
- `WATCH` for topics to monitor.
- `SKIP` for weak or risky topics.

Refresh-only queue:

```powershell
python scripts/run_refresh_existing_articles.py --limit 10
```

## 12A. HƯỚNG DẪN LÀM VIỆC HẰNG NGÀY CỦA BOT NỘI DUNG

When the user says something like:

```text
Vào phần hướng dẫn xem rồi viết 10 bài, push lên GitHub và website.
```

the bot should treat that as the default daily content workflow below, using the local date in `Asia/Bangkok` and the current week boundary starting on Monday.

### Monday workflow

Use `data/master_dashboard.xlsx` as the source of truth for the day.

1. Open the master dashboard and select the 10 strongest AI topics available that day.
2. Write 10 main review articles for those topics.
3. Publish the articles through the existing website workflow.
4. Refresh sitemap and submit index after the publish step.
5. Push the updated website to GitHub so Cloudflare Pages can redeploy from `docs/`.
6. Save the 10 selected topics as the week’s `Weekly Topic Cluster`.

Current cluster storage in this repo is represented by the cluster outputs under:

```text
data/content_clusters.csv
data/content_clusters.json
```

If a separate weekly cluster file is added later, the Monday selection should be recorded there as well. For now, treat the existing cluster outputs as the weekly cluster record.

### Tuesday through Sunday workflow

Do not pull new topics from `master-dashboard.xlsx` on these days.

1. Read the current week’s `Weekly Topic Cluster` from the cluster output files.
2. For each topic in that cluster, write one deeper article that has not already been covered.
3. Choose the deeper angle from:
   - pricing
   - alternatives
   - comparison
   - tutorial
   - use cases
   - FAQ
   - pros and cons
   - integration
4. Publish the 10 articles through the existing website workflow.
5. Refresh sitemap and submit index after publish.
6. Push the updated website to GitHub.

### Required checks after each publish batch

After every publish batch, the bot must also:

1. Add internal links between each new article and its original review article.
2. Check for duplicate title and duplicate meta description issues before finalizing.
3. Report:
   - the 10 new URLs
   - the commit hash
   - any errors or warnings

### Practical rule for future runs

- If the article already exists, treat the task as `REFRESH`, not `CREATE`.
- If the article does not exist, treat the task as `CREATE`.
- Never show the same slug as both `CREATE` and `REFRESH`.
- Use the existing publish workflow:

```powershell
python build_site.py
python scripts/sync_site_output_to_docs.py
git add docs
git commit -m "Update website"
git push origin main
```

This daily instruction block is the first thing the bot should read before doing daily content work.

## 13. Safe-change rules for AI assistants

Before editing:

- Inspect the relevant script/module first.
- Prefer small, reversible changes.
- Do not modify deployment logic unless explicitly requested.
- Do not modify Cloudflare scripts unless explicitly requested.
- Do not modify IndexNow scripts unless explicitly requested.
- Do not auto-upload YouTube videos.
- Do not auto-post social content.
- Do not delete old content or user changes.

When editing generated pages:

- Prefer fixing source generators under `modules/` or `scripts/`.
- Rebuild `site_output/`.
- Sync to `docs/`.
- Verify the output HTML.

When committing:

- Stage only relevant files.
- Be careful because this repository often has many unrelated dirty files.
- Do not commit secrets.
- Do not commit deployment credentials.

## 14. Current video status for the latest trend batch

The latest trend batch videos are expected under:

```text
video_output/openmontage-review-2026/
video_output/superpowers-review-2026/
video_output/ui-tars-desktop-review-2026/
video_output/rlm-review-2026/
video_output/8-best-generative-ai-software-stocks-to-buy-in-june-2026/
video_output/ai-search-software-comparison/
video_output/ai-video-software-comparison/
video_output/ai-voice-software-comparison/
video_output/ai-writing-software-comparison/
video_output/trex-an-ai-code-reviewer-that-runs-your-code/
```

Each folder should contain `review_video.mp4` plus supporting metadata/subtitle files.

## 15. Competitor trend discovery

The competitor scanner is a topic-discovery input only. It never copies article
content and never publishes pages.

Configuration:

```text
data/competitors.json
```

Manual scan:

```powershell
python scripts/scan_competitor_trends.py --max-items 12 --delay 1.0
```

Outputs:

```text
reports/competitor-trends.md
reports/competitor-trends.json
data/competitor_topic_candidates.json
```

Only candidates with a trend score of at least 70, clear commercial intent, and
an action of `create` or `refresh` are written to the daily candidate file.
The existing daily selector may read this file, but its duplicate checks still
decide whether the topic becomes a new article or a refresh.

The scanner prefers RSS and sitemap data, checks `robots.txt`, caches each
host's robots policy during a run, waits between requests, and records failed
requests in the report. Competitor pages are used only for titles, headings,
metadata, and topic signals.

## 16. Operational health and content growth reports

Generate the current health, QA, cluster, refresh, and linking reports with:

```powershell
python scripts/generate_operational_reports.py --publish-root docs
```

To validate and repair only a known batch of newly generated URLs:

```powershell
python scripts/generate_operational_reports.py --publish-root docs --urls-file data/published_today.csv --repair
```

Key outputs:

```text
reports/health-report.md
reports/dashboard.md
reports/dashboard.json
reports/content-qa.md
reports/internal-link-map.md
reports/topic-clusters.md
reports/topic-clusters.json
reports/content-refresh-queue.md
reports/auto-repair-report.md
reports/auto-repair-report.json
reports/history/
reports/social-posts/
```

Safe repairs are deliberately limited to deterministic changes such as a
canonical mismatch, a missing valid author object, a missing breadcrumb schema,
an obvious broken-link replacement, and missing image metadata/fallbacks.
Ambiguous links, weak content, duplicate intent, or missing FAQs remain in the
report for editorial review. Do not mass-rewrite healthy pages to make a report
number reach zero.
