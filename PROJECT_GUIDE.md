# Smile AI Review Hub Project Guide

This guide documents the current repository behavior so Codex, Copilot, or another AI assistant can understand the project before changing it.

## Editorial Automation Platform

The repository now includes an AI Editorial Automation Platform layered on top of the existing site generators.

The system is designed around two repeating workflows:

- Weekly editorial intelligence
- Mandatory research packaging
- Daily scheduled production
- Weekly business intelligence

The rule for future work is:

- reuse stable engines
- prefer adapters over rewrites
- keep automatic publishing local-only unless explicitly enabled later

### Architecture

Core platform modules:

- `modules/ai_trend_discovery.py`: multi-source trend discovery and scoring.
- `modules/content_planning_engine.py`: keyword planning, intent, cluster, coverage, outline, and reasoning.
- `modules/content_growth_pipeline.py`: content generation, SEO metadata, local publish, and reusable content assets.
- `modules/editorial_automation.py`: weekly candidate collection, weekly ranking, editorial calendar generation, and daily scheduled execution.
- `modules/editorial_business_intelligence.py`: evergreen evaluation, affiliate opportunity scoring, lifecycle logging, history retention, gap analysis, affiliate coverage analysis, and weekly dashboards.
- `modules/research_intelligence.py`: pre-generation research packaging, keyword intelligence, entity extraction, FAQ building, competitor/source assembly, cache reuse, and research quality scoring.
- `modules/source_connectors.py`: offline-safe source connector framework with status labels for trusted-source discovery.
- `modules/competitor_snapshot_ingestion.py`: local competitor snapshot ingestion from JSON/CSV files.
- `modules/topic_cluster_engine.py`: topic clustering support.
- `scripts/validate_production_content_pipeline.py`: end-to-end production validation against real keywords.

Compatibility adapters:

- `modules/homepage_crawl_sections.py`
- `modules/topical_hubs.py`

These exist so the incremental build remains stable while the broader editorial system is assembled.

### Folder Structure

Editorial automation files:

- `data/weekly_topic_candidates.csv`
- `data/weekly_topic_candidates.json`
- `data/weekly_topic_history.jsonl`
- `data/weekly_topic_provider_status.json`
- `data/weekly_topics.csv`
- `data/weekly_topics.json`
- `data/editorial_calendar.csv`
- `data/editorial_calendar.json`
- `data/daily_editorial_report_<date>.json`
- `data/research/<slug>/keyword.json`
- `data/research/<slug>/keyword_intelligence.json`
- `data/research/<slug>/outline.json`
- `data/research/<slug>/faq.json`
- `data/research/<slug>/entities.json`
- `data/research/<slug>/competitors.json`
- `data/research/<slug>/sources.json`
- `data/research/<slug>/writing_plan.json`
- `data/research_cache/entities/*.json`
- `data/research_quality_report.json`
- `data/research_quality_report.csv`
- `data/research_quality_report.md`
- `data/research_enrichment_queue.json`
- `data/research_enrichment_queue.csv`
- `data/research_enrichment_history.jsonl`
- `data/research_enrichment_report.json`
- `data/research_enrichment_report.csv`
- `data/research_enrichment_report.md`
- `data/competitor_snapshots.json`
- `data/competitor_snapshots.csv`
- `data/evergreen_report.csv`
- `data/evergreen_report.json`
- `data/evergreen_report.md`
- `data/affiliate_opportunities.csv`
- `data/affiliate_opportunities.json`
- `data/content_gap_report.csv`
- `data/content_gap_report.json`
- `data/content_gap_report.md`
- `data/affiliate_coverage_report.csv`
- `data/affiliate_coverage_report.json`
- `data/affiliate_coverage_report.md`
- `data/weekly_dashboard.csv`
- `data/weekly_dashboard.json`
- `data/weekly_dashboard.md`
- `data/content_lifecycle.jsonl`
- `data/content_lifecycle_state.json`
- `data/weekly_history.jsonl`
- `data/content_growth_reports/production-pipeline-validation-*.json`
- `data/content_growth_reports/production-pipeline-validation-*.md`
- `data/content_growth_reports/production-pipeline-validation-*.csv`

Entry points:

- `scripts/run_weekly_editorial_cycle.py`
- `run_daily_content.py`
- `scripts/validate_production_content_pipeline.py`

### Weekly Workflow

The weekly workflow is:

```text
provider signals
  -> trend aggregation
  -> candidate scoring
  -> weekly topic ranking
  -> weekly_topics.csv/json
  -> editorial calendar expansion
  -> editorial_calendar.csv/json
  -> evergreen/opportunity/gap/coverage analysis
  -> weekly_dashboard.csv/json/md
```

Weekly outputs are generated without publishing articles. Every candidate topic is persisted so discovery history is never discarded.

### Evergreen Workflow

```text
published site_output pages
  -> evergreen scan
  -> freshness and issue classification
  -> evergreen_report.csv/json/md
```

Each scanned article stores publish date, last updated, last validation, topic, cluster, affiliate products, traffic estimate placeholder, and lifecycle status.

Statuses:

- Fresh
- Needs Review
- Needs Update
- Outdated
- Deprecated
- Broken

### Business Intelligence Workflow

```text
weekly topics + published articles + affiliate offer data
  -> affiliate opportunity scoring
  -> content gap analysis
  -> affiliate coverage analysis
  -> weekly history append
  -> weekly executive dashboard
```

### Lifecycle Workflow

```text
editorial calendar row
  -> planned
  -> research
  -> generated
  -> reviewed
  -> published
  -> evergreen status transitions when quality declines
```

### Research Workflow

```text
topic
  -> research_intelligence.build_research_package()
  -> keyword intelligence
  -> entities
  -> FAQ groups
  -> competitor analysis
  -> trusted sources
  -> writing plan
  -> research quality score
  -> cache reuse by entity/tool
```

Research becomes mandatory before planning and article generation. The writer should not start from only a keyword.

### Research Quality Gate

```text
research package
  -> quality score
  -> threshold check
  -> pass: planning and generation continue
  -> fail: topic enters enrichment queue
```

Low-quality topics are blocked from article generation unless config explicitly allows an override.

### Research Cache

Reusable knowledge lives in:

- `data/research/<slug>/`
- `data/research_cache/entities/*.json`

If another article targets the same tool or entity, the pipeline reuses cached entities and trusted sources instead of rebuilding from zero.

### Enrichment Queue

Failed research topics are added to:

- `data/research_enrichment_queue.json`
- `data/research_enrichment_queue.csv`
- `data/research_enrichment_history.jsonl`

Queue rows store topic, slug, missing source/competitor/entity signals, affiliate-data gaps, priority, reason, timestamps, and status.

### Source Connector Framework

The current source-connector layer is offline-safe and deterministic.

Supported connector types:

- `official_docs`
- `pricing_page`
- `product_page`
- `release_notes`
- `affiliate_program_page`
- `competitor_article`
- `api_docs`

Every source item is labeled as one of:

- `verified`
- `estimated`
- `missing`
- `needs_review`

### Competitor Snapshot Ingestion

Competitor coverage can be imported from:

- `data/competitor_snapshots.json`
- `data/competitor_snapshots.csv`

If no local snapshots exist, the system reports missing competitor coverage instead of fabricating profiles.

### Daily Workflow

The daily workflow is:

```text
editorial_calendar.json
  -> today's scheduled rows
  -> mandatory research package
  -> research quality gate
  -> planning
  -> generation
  -> SEO title/meta
  -> internal links
  -> FAQ/schema/html
  -> local publish
  -> optional local build
  -> daily report
```

`run_daily_content.py` reads the existing weekly calendar and generates only today’s scheduled content. It does not regenerate weekly topic selection.

Research packages are built automatically during article generation and saved under `data/research/`.

### Sequence Diagram

```text
Weekly cycle
  scripts/run_weekly_editorial_cycle.py
    -> WeeklyTrendIntelligenceEngine.collect_candidates()
    -> WeeklyTrendIntelligenceEngine.rank_topics()
    -> WeeklyTrendIntelligenceEngine.generate_editorial_calendar()
    -> EditorialBusinessIntelligence.run_weekly_intelligence()

Daily cycle
  python run_daily_content.py
    -> load editorial_calendar.json
    -> ResearchIntelligencePlatform.build_research_package()
    -> ResearchIntelligencePlatform.evaluate_quality_gate()
    -> content_growth_pipeline.generate_topic_package()
      -> ContentPlanningEngine.create_plan()
      -> render article + assets
    -> ContentLifecycleManager.record_transition()
    -> optional build_site.incremental_build()

Monday cycle
  -> weekly trend discovery
  -> top 10 weekly topics
  -> research packages
  -> verified source acquisition from source_registry
  -> verified source gate
  -> quality gate
  -> schedule only approved topics

Tuesday-Sunday cycle
  -> continue approved deep-dive articles
  -> queue failed topics for enrichment
  -> run verified source acquisition first
  -> run offline enrichment and recheck quality
```

### Data Flow

```text
external/local trend providers
  -> TopicCandidate records
  -> CandidateTopicRecord snapshots
  -> WeeklyTopicRecord shortlist
  -> EditorialCalendarEntry schedule
  -> ResearchPackage outputs
  -> Evergreen / opportunity / gap / coverage reports
  -> Weekly dashboard
  -> GeneratedPage outputs
  -> validation reports
```

### Commands

Weekly intelligence:

```powershell
python scripts/run_weekly_editorial_cycle.py
```

Weekly intelligence with overrides:

```powershell
python scripts/run_weekly_editorial_cycle.py --candidate-limit 200 --top-topics 10 --max-per-source 40
```

Generate today’s scheduled content only:

```powershell
python run_daily_content.py
```

Generate today’s scheduled content and run a local incremental build:

```powershell
python run_daily_content.py --build
```

Run end-to-end production validation:

```powershell
python scripts/validate_production_content_pipeline.py
```

Generate weekly intelligence and business-intelligence reports:

```powershell
python scripts/run_weekly_editorial_cycle.py
```

Run research enrichment:

```powershell
python scripts/run_research_enrichment.py
```

Normalize the verified source registry and generate source reports:

```powershell
python scripts/import_verified_sources.py
```

Run the full test suite:

```powershell
python -m pytest
```

### Validation

### Autonomous Content Agency

- `data/source_registry.json` and `data/source_registry.csv` are the curated local registry for official docs, pricing pages, affiliate program pages, release notes, competitor articles, API docs, and product pages.
- `modules/verified_source_acquisition.py` matches local entity signals against the registry and attaches `verified_sources`, `missing_verified_sources`, `source_confidence`, `source_status`, and per-source trust scores to each research package.
- `modules/knowledge_registry.py` is the long-term governance layer. It normalizes records, computes freshness and trust, detects duplicates, assigns canonical sources, and maintains version history in `data/source_registry_history.jsonl`.
- `modules/source_review.py` creates and updates `data/source_review_queue.json` plus `data/source_review_report.{json,csv,md}` so pending, duplicate, expired, and rejected sources can be reviewed without changing the generation pipeline.
- `modules/knowledge_dashboard.py` writes `data/knowledge_dashboard.{json,csv,md}` with verified %, pending %, expired %, duplicate %, average trust, average freshness, missing source-type coverage, and top weak topics.
- `ResearchIntelligencePlatform.evaluate_quality_gate()` now checks both research quality and the verified source gate configured in `config/editorial_system.json`.
- `scripts/run_research_enrichment.py` reuses the same verified-source-first flow before retrying queued topics.
- `scripts/import_verified_sources.py` now upgrades raw registry rows into governed records, refreshes the review queue, and rebuilds the knowledge dashboard.

Governance flow:

```text
Verified Source Acquisition
  -> Knowledge Registry
  -> Knowledge Review Queue
  -> Knowledge Health Dashboard
  -> Research Package
  -> Research Quality Gate
  -> AI Content Review
  -> Human Approval (optional)
  -> Publish Gate
  -> Local publish only
  -> Analytics feedback
  -> Self-optimization
```

Key governance config in `config/editorial_system.json`:

- `knowledge_review.freshness_threshold`
- `knowledge_review.review_after_days`
- `knowledge_review.expire_after_days`
- `knowledge_review.minimum_verified_sources`
- `knowledge_review.minimum_official_sources`
- `knowledge_review.minimum_trust_score`
- `knowledge_review.minimum_freshness`
- `knowledge_review.duplicate_similarity`

Review workflow:

- `modules/content_review.py` evaluates factual quality, source quality, SEO title/meta quality, affiliate disclosure, internal links, duplicate content risk, readability, word count, business value, and publish readiness.
- Review artifacts are written to `data/content_review_queue.json` and `data/content_review_report.{json,csv,md}`.
- `modules/human_approval.py` maintains `data/human_approval_queue.json`. Human approval is optional by config, but supported as a first-class gate.
- Content is not considered publishable unless AI review passes. If human approval is required, the publish path remains blocked until a human marks the item approved.

Publish gate workflow:

- `modules/publish_gate.py` checks research quality, verified source score, knowledge freshness, AI review status, optional human approval, broken links, duplicate title/meta, affiliate disclosure, business score, and readability.
- Publish artifacts are written to `data/publish_queue.json` and `data/publish_gate_report.{json,csv,md}`.
- Blocked content does not reach the local publish step.
- Auto deploy remains disabled. No GitHub push, no live deploy, and no IndexNow behavior was enabled by these checkpoints.

Analytics and self-optimization workflow:

- `modules/content_analytics.py` builds `data/content_performance.json`, `data/content_performance.csv`, and appends `data/topic_feedback_history.jsonl` from local tracking data only.
- `modules/self_optimization.py` creates `data/optimization_report.{json,csv,md}` and feeds score adjustments back into weekly topic ranking.
- Recommended actions include:
  `write new article`, `update old article`, `improve affiliate section`, `refresh pricing`, `add comparison table`, `add internal links`, `hold / do nothing`.

Operational flow:

```text
Monday
  trend discovery
  -> top 10 topics
  -> research
  -> source verification
  -> knowledge review
  -> AI review gate
  -> schedule approved topics

Tuesday to Sunday
  generate deeper articles only from approved topics
  -> optional human approval
  -> publish gate
  -> local publish only
  -> analytics feedback
```

Manual approval rule:

- If `content_review.require_human_approval` or `publish_gate.require_human_approval` is true, a page must remain in `needs_human_review` until a human changes it to `human_approved`.

Production validation checks:

- planning metadata
- outline presence
- SEO title
- meta description
- canonical URL
- heading structure
- internal links
- related keywords
- broken links
- duplicate titles
- duplicate descriptions

Business-intelligence checks include:

- research quality score
- knowledge cache reuse
- keyword/entity/source completeness
- source connector status labels
- competitor snapshot coverage
- evergreen freshness and update status
- affiliate opportunity score and monetization priority
- missing content gaps
- affiliate disclosure, link, and CTA coverage
- lifecycle transition logging
- weekly trend history retention

Reports are written in:

- JSON
- Markdown
- CSV

Current report families include:

- research quality and enrichment reports
- source registry, source review, and knowledge dashboard reports
- content review and human approval queues
- publish gate queue and publish gate reports
- content performance and optimization reports

Current commands:

- `python scripts/run_weekly_editorial_cycle.py`
- `python scripts/import_verified_sources.py`
- `python scripts/run_research_enrichment.py`
- `python run_daily_content.py`
- `python run_daily_content.py --build`
- `python scripts/validate_production_content_pipeline.py`
- `python -m pytest`

Remaining blockers:

- Verified source and knowledge governance are operational, but production value still depends on richer curated registry coverage.
- Human approval is supported locally, but there is not yet a dedicated editor UI or inbox workflow.
- Publish gate is local-only and intentionally does not trigger deployment.
- Analytics are based on local/mock tracking until a future checkpoint adds real data connectors safely.

Recommended Checkpoint 21:

- Add a local-safe source change detection and editorial operations console that can diff registry versions, surface top review blockers, and orchestrate approval/publish decisions from one operational dashboard.

### Troubleshooting

- If `build_site.py` fails on missing editorial helper modules, confirm the compatibility adapters still exist.
- If weekly discovery returns too few topics, increase `EDITORIAL_MAX_PER_SOURCE` or `EDITORIAL_CANDIDATE_LIMIT`.
- If daily generation returns zero pages, check `data/editorial_calendar.json` and confirm there are rows for today’s date.
- If validation reports broken links, inspect `suggested_internal_links` for the generated topic and verify the referenced local pages exist.

### Configuration

Editorial automation values now live in config:

- `config/editorial_system.json`
- `EDITORIAL_CANDIDATE_LIMIT`
- `EDITORIAL_MAX_PER_SOURCE`
- `EDITORIAL_TOP_TOPICS`
- `EDITORIAL_CALENDAR_DAYS`
- `EDITORIAL_VALIDATION_KEYWORDS`

Business-intelligence thresholds also live in `config/editorial_system.json` under:

- `business_intelligence.evergreen`
- `business_intelligence.affiliate_opportunity`
- `business_intelligence.content_gap`
- `business_intelligence.affiliate_coverage`

Research thresholds and limits also live there under:

- `research_intelligence`

The autonomous content agency roadmap for the current repo is:

- research package
- quality gate
- enrichment queue
- offline source connectors
- competitor snapshots
- approved-topic scheduling

### Future Roadmap

Planned follow-up work:

- parallel article generation
- retry/resume support for interrupted runs
- richer research adapters before drafting
- stronger article-level validation before local publish
- clean interfaces for future git push, deploy, sitemap ping, and indexing automation

### Updated Summary

The repository is no longer only a set of separate article scripts. It now has a weekly-to-daily editorial automation layer that can:

- collect and persist candidate topics
- rank weekly topics
- expand those topics into an editorial calendar
- generate only today’s scheduled content
- validate production output end to end

- score evergreen health of published pages
- log lifecycle transitions
- estimate affiliate opportunity by weekly topic
- detect content gaps and coverage issues
- generate a weekly executive dashboard

- build a mandatory research package before planning
- block low-quality research from article generation
- route failed topics into an enrichment loop
- reuse cached research across shared tools/entities
- score research completeness before article generation

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

IndexNow support is implemented through:

```text
scripts/submit_indexnow.py
scripts/check_indexnow_status.py
site_output/indexnow-key.txt
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
- Read URLs from `site_output/sitemap.xml`.
- Use `site_output/indexnow-key.txt` for the key file.
- Do not crash the build if IndexNow submission fails.

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

1. Run `python scripts/run_weekly_editorial_cycle.py`.
2. Discover and rank 10 hottrend topics for the current week.
3. Build research packages, verified source checks, and quality-gate decisions for those topics.
4. Create the weekly editorial calendar only from approved topics.
5. For Monday only, run `python run_daily_content.py --date YYYY-MM-DD` using the Monday date of the current week.
6. Generate up to 10 Monday hottrend articles through:
   - research
   - planning
   - article generation
   - SEO title/meta
   - internal links
   - AI review
   - human approval if required
   - publish gate
7. Publish locally only when all gates pass.
8. Do not publish topics in `needs_enrichment`, `needs_revision`, `needs_human_review`, `rejected`, or `blocked` states.
9. Rebuild the local operational dashboards:
   - `python scripts/build_ceo_dashboard.py`
   - `data/daily_ceo_dashboard.html`
   - `data/master_dashboard.xlsx`
Current cluster storage in this repo is represented by the cluster outputs under:

```text
data/content_clusters.csv
data/content_clusters.json
```

If a separate weekly cluster file is added later, the Monday selection should be recorded there as well. For now, treat the existing cluster outputs as the weekly cluster record.

### Tuesday through Sunday workflow

Do not discover a new weekly cluster on these days.

1. Read the current week’s approved topic set from the weekly cluster output files and editorial calendar.
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
4. Run only the scheduled day through research, planning, generation, AI review, optional human approval, and the publish gate.
5. Publish locally only if all gates pass.
6. Send failures to the correct queue:
   - `data/research_enrichment_queue.json`
   - `data/content_review_queue.json`
   - `data/human_approval_queue.json`
   - `data/publish_queue.json`
7. Do not deploy, push, or submit IndexNow from this workflow.

### Required checks after each publish batch

After every publish batch, the bot must also:

1. Add internal links between each new article and its original review article.
2. Check for duplicate title and duplicate meta description issues before finalizing.
3. Report:
   - locally published URLs
   - queued or rejected topics
   - any errors or warnings

### Practical rule for future runs

- If the article already exists, treat the task as `REFRESH`, not `CREATE`.
- If the article does not exist, treat the task as `CREATE`.
- Never show the same slug as both `CREATE` and `REFRESH`.
- Human approval is required for affiliate review, pricing, comparison, and product recommendation articles.
- Informational and tutorial articles can publish automatically if all gates pass.
- Do not publish failed, rejected, blocked, or `needs_enrichment` topics.
- No auto deploy is allowed until explicitly enabled in a future workflow.

This daily instruction block is the first thing the bot should read before doing daily content work.

### Editorial Operations Console

Human approval already exists through:

- `data/content_review_queue.json`
- `data/human_approval_queue.json`
- `data/publish_queue.json`

Use the local operator console to review and move drafts without deploy, push, or IndexNow:

- Open the review preview:
  - `data/production_article_drafts/<slug>/index.html`
- Open the source markdown:
  - `data/production_article_drafts/<slug>/article.md`
- Open the operator dashboard:
  - `data/editorial_operations_console.html`
- Use the built-in console action buttons:
  - `Open Draft`
  - `Open HTML Preview`
  - `Open Review Summary`
  - `Open Metadata`
  - `Open Social Drafts`
  - `Open All Social Drafts`
  - `Copy Facebook Draft`
  - `Copy Quora Draft`
  - `Copy LinkedIn Draft`
  - `Copy X Draft`
  - `Approve`
  - `Reject`
  - `Publish`
  - `Publish All Approved`
  - `Preview Website`

The console now has:

- a top-level article list
- a same-page detail panel for the selected article
- author/byline metadata visibility
- social draft visibility
- local launcher buttons for approve, reject, publish, and copy-to-clipboard social drafts

Commands:

```bash
python scripts/editorial_console.py --list
python scripts/editorial_console.py --build
python scripts/editorial_console.py --approve best-ai-productivity-software
python scripts/editorial_console.py --reject best-ai-productivity-software --reason "Needs pricing fix"
python scripts/editorial_console.py --publish best-ai-productivity-software
python scripts/editorial_console.py --publish-all
python scripts/editorial_console.py --request-topic "best AI tools for small business" --category "AI Tools" --intent "commercial"
```

### Simplest Morning Workflow

For the current local operator flow, the easiest daily path is:

```text
1. Run one morning command
2. Open one dashboard
3. Review each article
4. Approve or reject each row
5. Publish the batch only after every row is approved
```

Use this command to start the weekly batch on Monday, or on the first day you begin a new week:

```powershell
python editorial_console.py morning --count 10
```

If you want the daily review dashboard to open immediately after generation:

```powershell
python editorial_console.py morning --count 10 --open
```

`--open` now starts the local interactive review dashboard. This is the easiest operator mode because you can:

- open an article inside the same dashboard
- approve it
- reject it
- return to the list automatically
- continue until the full batch is done
- publish the batch from the same dashboard when every row is approved

On the first run of a week, this command now does all of the following:

- discovers trending topics
- scores and selects the batch
- freezes one weekly batch of 10 core topics for the full week
- runs research and quality gates
- generates the day-one drafts
- builds the daily review dashboard
- copies review and upload-ready files into `upload/YYYY-MM-DD/`
- refreshes `upload/dashboard.html`

From Tuesday to Sunday, do not discover a new weekly batch. Reuse the same 10 weekly topics and generate follow-up articles with:

```powershell
python editorial_console.py morning --count 10 --mode advanced
python editorial_console.py morning --count 10 --mode advanced --open
```

`advanced` mode reuses the same weekly topic batch and rotates the angle by day:

- Tuesday: pricing
- Wednesday: alternatives
- Thursday: comparison
- Friday: tutorial
- Saturday: best-for-use-case
- Sunday: review/deep-dive

After the morning command finishes, use one of these files:

- Daily review dashboard:
  `site_output/review/YYYY-MM-DD/index.html`
- Upload master dashboard:
  `upload/dashboard.html`
- Operator console:
  `data/editorial_operations_console.html`

The `upload/YYYY-MM-DD/` folder now contains helper files so you do not need to remember long commands:

- `open_dashboard.cmd`
- `publish_approved.cmd`
- `status.cmd`

You can also ask the CLI to show or open the current dashboards:

```powershell
python editorial_console.py open
python editorial_console.py open --master
python editorial_console.py open --operator
python editorial_console.py open --run
python editorial_console.py serve --open
```

Practical operator sequence:

```text
Morning
  -> python editorial_console.py morning --count 10 --open
  -> browser opens the interactive local dashboard
  -> click Xem nội dung
  -> read the article inside the dashboard
  -> click Approve or Reject
  -> dashboard returns to the list and continues to the next article
  -> click Publish Ready Articles to publish only rows that already passed every gate
```

Current daily operator diagram:

One-click BAT files:

```text
runbot_menu.bat
  -> main non-technical launcher
  -> opens a simple numbered menu
  -> 1 = week start batch
  -> 2 = Tue-Sun advanced follow-up batch
  -> 3 = custom topic
  -> 4 = open dashboard
  -> 5 = status
  -> 6 = check live status
  -> 7 = publish approved + push GitHub
  -> 8 = exit

runbot_week_start.bat
  -> use on the first working day of the week
  -> runs python editorial_console.py morning --count 10 --mode standard --open
  -> opens the interactive review dashboard and the operator console

runbot_tue_to_sun.bat
  -> use on Tuesday to Sunday
  -> runs python editorial_console.py morning --count 10 --mode advanced --open
  -> reuses the same 10 weekly topics and creates deep-dive follow-up drafts

runbot_custom_topic.bat
  -> asks for a custom topic
  -> optionally asks for an official/source URL
  -> runs python editorial_console.py request-topic ... --open
  -> opens the operator console for review
```

```text
python editorial_console.py morning --count 10
  -> trend discovery
  -> topic scoring
  -> top 10 selection
  -> research package
  -> quality gates
  -> draft generation
  -> daily review dashboard
  -> upload/YYYY-MM-DD/
  -> upload/dashboard.html

operator opens dashboard
  -> preview each article
  -> approve or reject each slug

articles that pass publish gate
  -> python editorial_console.py publish-ready --date YYYY-MM-DD
  -> copy final pages into site_output/<slug>/index.html
  -> sync site_output/ into docs/ with scripts/sync_site_output_to_docs.py
  -> copy final pages into upload/YYYY-MM-DD/published/<slug>/index.html
  -> validate site_output/ and docs/
  -> git add docs site_output data upload
  -> git commit -m "Publish ready daily articles YYYY-MM-DD"
  -> git push origin main
  -> write upload/YYYY-MM-DD/publish_report.md

strict full-batch mode if needed
  -> python editorial_console.py publish --date YYYY-MM-DD
  -> blocks unless every topic in the batch is ready for publish
```

Most useful commands right now:

```powershell
python editorial_console.py morning --count 10
python editorial_console.py morning --count 10 --open
python editorial_console.py status
python editorial_console.py approve --slug <slug>
python editorial_console.py reject --slug <slug> --reason "Need revision"
python editorial_console.py publish-ready
python editorial_console.py publish
python editorial_console.py request-topic --topic "UGCVideo AI review" --category "AI Video Tools" --intent "commercial research" --open
python editorial_console.py open --run
python editorial_console.py serve --open
```

Simplest daily operating method:

```text
Double-click runbot_menu.bat
  -> easiest entrypoint for normal operation
  -> choose option 1 on the first working day of the week
  -> choose option 2 on Tuesday to Sunday
  -> choose option 3 when you want one custom affiliate article
  -> choose option 4 to reopen the dashboard
  -> choose option 6 to check live status
  -> choose option 7 to open only blocked reasons
  -> choose option 8 to publish approved rows and push GitHub
  -> when choosing option 8, enter the batch date if you want to publish an older day such as 2026-07-07
  -> leave it blank to publish today's approved batch
  -> option 7 rebuilds the live report and opens only blocked rows with reason + fix suggestion
  -> after option 8 finishes, the bot now prints OK/ERROR and opens the live-status report automatically
  -> while option 8 is running, it prints the current step and a heartbeat every 60 seconds
  -> after 5 minutes it prints a progress reminder
  -> after 10 minutes it prints a long-running warning
  -> after git push, it waits through short checkpoints and checks the real domain automatically
  -> it now reports either "GitHub push OK nhưng Pages chưa cập nhật" or "Website live OK"
  -> when Website live OK is detected, it prints the final live URLs directly in the terminal
  -> it also saves live-link history into:
     - data/published_live_urls.jsonl
     - data/published_live_urls_latest.json
  -> when creating a new weekly batch, it compares new topics against data/published_live_urls.jsonl
  -> if slug, keyword, or URL path is near-duplicate with an already-live article, it prints a warning immediately
  -> duplicate warnings are saved into the weekly manifest and daily queue before drafting
  -> near-duplicate topics also get a small score penalty so fresh topics float higher automatically

Double-click runbot_week_start.bat
  -> on the first day of the week

Double-click runbot_tue_to_sun.bat
  -> on Tuesday to Sunday

Double-click runbot_custom_topic.bat
  -> when you want to create a custom affiliate article outside the weekly batch
  -> enter topic
  -> enter link if you have one
  -> the system creates research + draft + opens review console

Browser dashboard opens
  -> read article
  -> approve or reject
  -> click Publish Ready Articles

Only articles already in ready_for_publish can go live that day.
Blocked rows stay in review or enrichment until fixed.
```

Exact daily click workflow:

```text
1. Double-click runbot_menu.bat
2. Pick:
   - 1 for the first working day of the week
   - 2 for Tue-Sun deep-dive follow-up articles
   - 3 for a manual/custom affiliate topic
   - 4 to reopen the dashboard
   - 6 to open the live-status report
   - 7 to open only blocked reasons
   - 8 to publish approved rows and push GitHub
   - when choosing 8, type the batch date you want to publish, or leave it blank for today
   - after publishing, review the auto-opened live-status report
3. Wait for the browser dashboard to open
4. Use the filters:
   - Ready to publish
   - Blocked
   - Needs revision
   - Published
5. Click Xem nội dung on each row
6. Read the article in the right-side preview panel
7. Click Approve or Reject
8. Continue until the list is fully reviewed
9. Click Publish Ready Articles
10. The system will:
    - build site_output
    - sync site_output into docs
    - validate site_output and docs
    - git add docs site_output data upload
    - create a git commit
    - git push origin main
11. Open upload/dashboard.html to verify the publish report and copied files
```

Live status check:

```powershell
python editorial_console.py check-live
python editorial_console.py check-live --all
python editorial_console.py check-live --open
```

This report tells you clearly:

- which article is only local
- which article is already synced into `docs/`
- which article is already included in git / `origin/main`
- which article returns `200`, `404`, or `unknown` on the real domain

Operator rules:

- Review the draft HTML before approving.
- Use `data/editorial_operations_console.html` as the default operator surface for non-technical review.
- Review `metadata.json`, `review_summary.md`, and `publish_readiness_report.md` in the same draft folder when the article is affiliate, pricing, comparison, review, or product recommendation content.
- Review author/byline fields before approving:
  - `author_name`
  - `author_profile_url`
  - `author_bio`
  - `reviewed_by`
  - `last_updated`
  - `editorial_policy_url`
  - `affiliate_disclosure_url`
- Social drafts are manual-only. The console can open or copy them, but it must not auto-post to Facebook, Quora, LinkedIn, X, Reddit, DEV.to, Product Hunt, Qiita, or any other network.
- Human approval is required for affiliate review, pricing, comparison, and product recommendation articles.
- Informational and tutorial articles can move forward automatically only when every gate passes.
- Do not publish failed, rejected, blocked, or `needs_enrichment` topics.
- `serve --open` intentionally keeps the PowerShell window busy because it is running the local dashboard server.
- Open a second PowerShell window for `status`, `approve`, `reject`, or `publish-ready`.
- `publish-ready` is the default operator command because it publishes only rows that already passed every gate.
- `publish-ready --validation-mode smart` là chế độ publish hằng ngày nên dùng mặc định.
  - Chỉ kiểm tra các bài đang được publish trong batch hôm đó.
  - Không để các trang cũ lỗi ở chỗ khác chặn cả batch.
  - Bài nào fail validation sẽ bị skip riêng, các bài còn lại vẫn có thể push.
- `publish-ready --validation-mode strict` là chế độ audit/publish nghiêm ngặt.
  - Quét toàn bộ `site_output/` và `docs/`.
  - Chỉ dùng khi bạn muốn kiểm tra toàn site, không nên dùng cho publish nhanh mỗi ngày.
- `validate-batch --mode smart` dùng để kiểm tra trước khi push.
- `validate-batch --mode strict` dùng để audit toàn site trước các đợt cleanup lớn.
- `autofix-batch` sẽ tự sửa các lỗi đơn giản trước khi publish:
  - thiếu CTA cuối bài
  - thiếu FAQ schema khi đã có FAQ hiển thị
  - thiếu meta description
  - CTA đang đi thẳng ra official URL thay vì route `/go/` nếu hệ thống đã biết affiliate mapping
  - còn sót marker nội bộ như `Research package snapshot`, `Content planning snapshot`, `Affiliate placeholder fields`, `{{`, `}}`
- Nếu bài bị skip trong bước smart validation:
  - mở `data/live_status_report.html`
  - xem cột `Block reason`
  - sửa đúng lỗi được ghi
  - chạy lại `python editorial_console.py autofix-batch --date YYYY-MM-DD`
  - sau đó chạy lại `python editorial_console.py publish-ready --date YYYY-MM-DD --validation-mode smart`
- `publish` is strict full-batch mode and blocks if even one row still fails the publish gate.
- `--publish-all` publishes only rows already in `approved_for_publish`. It never approves drafts automatically.
- `request-topic` is for off-calendar requests. It builds a research package, runs source and research gates, generates a draft only if the topic passes, and then sends the result into the normal review / approval / publish workflow.
- The console shows status colors:
  - red = blocked
  - yellow = waiting
  - green = approved
  - blue = published

Monday or week-start workflow:

1. Discover 10 hottrend topics.
2. Freeze those 10 topics as the active weekly batch.
3. Run research, verified source checks, AI review, and human approval routing.
4. Approve only valid day-one drafts.
5. Publish locally only the approved day-one articles.

Tuesday-Sunday workflow:

1. Reuse the same weekly batch of 10 topics created at week start.
2. Generate one deeper follow-up article per topic for that day.
3. Route failures to enrichment, review, human approval, or publish queues.
4. Publish locally only after all gates pass and required human approval is complete.

Lệnh publish/validation nên dùng:

```powershell
python editorial_console.py autofix-batch --date YYYY-MM-DD
python editorial_console.py validate-batch --date YYYY-MM-DD --mode smart
python editorial_console.py publish-ready --date YYYY-MM-DD --validation-mode smart
python editorial_console.py validate-batch --date YYYY-MM-DD --mode strict
python editorial_console.py publish-ready --date YYYY-MM-DD --validation-mode strict
```

Giải thích nhanh:

1. `autofix-batch`:
   sửa lỗi HTML đơn giản trước.
2. `validate-batch --mode smart`:
   kiểm tra riêng batch hôm nay, chưa push.
3. `publish-ready --validation-mode smart`:
   publish các bài hợp lệ và push GitHub nếu các bài được chọn đều ổn.
4. `validate-batch --mode strict`:
   audit toàn site.
5. `publish-ready --validation-mode strict`:
   chỉ dùng khi bạn muốn bắt luôn cả lỗi cũ trên site.

Custom affiliate site or brand workflow:

Use this when you want to create an article for a website or tool that is not part of the current weekly batch.

```powershell
python editorial_console.py request-topic --topic "UGCVideo AI review" --official-url "https://ugcvideo.ai" --affiliate-url "https://ugcvideo.ai/affiliates" --pricing-url "https://ugcvideo.ai/pricing" --category "AI Video Tools" --intent "commercial research" --count 1 --open
```

What this does:

1. Creates a research package for the requested topic.
2. Runs the research and source quality gates.
3. Generates a draft only if the topic passes.
4. Saves the request into `data/custom_topic_history.json`.
5. Adds the draft into the daily review dashboard and copies files into `upload/YYYY-MM-DD/`.
6. Rebuilds the operator console.
7. Opens `data/editorial_operations_console.html` when `--open` is used.

If you do not have all URLs yet, you can leave `--affiliate-url` or `--pricing-url` empty.

New affiliate partner workflow:

Use this when you have a new affiliate partner and want a whole content cluster, not just one article.

```powershell
python editorial_console.py partner-intake --name "UGCVideo.ai" --official-url "https://ugcvideo.ai" --affiliate-url "https://ugcvideo.ai/affiliates" --pricing-url "https://ugcvideo.ai/pricing" --contact-note "Reached out by email" --commission-note "Use verified commission terms only" --payout-note "Add payout schedule if known" --count 8 --open
```

What this does:

1. Saves partner profile into `data/partners/<partner-slug>/partner.json`.
2. Appends a row into `data/partner_intake_history.json`.
3. Creates a research package from official/pricing/affiliate URLs plus notes.
4. Builds a content cluster such as review, pricing, alternatives, tutorial, affiliate program, comparison, and FAQ.
5. Runs research, planning, AI review, and publish gate for each draft.
6. Adds all drafts into the daily review dashboard.
7. Copies partner outputs into `upload/YYYY-MM-DD/<partner-slug>/`.
8. Does not push GitHub automatically.

How to publish a custom affiliate article:

1. Run `request-topic`.
2. Open the preview in the operator console.
3. Approve the article.
4. Publish it only if the publish gate shows ready.

Affiliate link management:

1. Update `data/affiliate_links.csv` when you receive a real affiliate URL.
2. Keep `official_url` filled even if `affiliate_url` is empty.
3. If `approved=true` and `affiliate_url` exists, the article CTA can use the affiliate URL.
4. If no approved affiliate URL exists, the CTA falls back to the official website safely.

Runbot menu workflow (Vietnamese):

1. `runbot_menu.bat`
   - `1`: đầu tuần, chọn 10 chủ đề tuần và tạo draft.
   - `2`: Tue-Sun, tạo bài chuyên sâu tiếp theo từ 10 chủ đề tuần đó.
   - `3`: Custom topic, nhập topic + official/affiliate/pricing URL.
   - `4`: mở dashboard duyệt bài.
   - `5`: xem trạng thái batch hiện tại.
   - `6`: check live status.
   - `7`: chỉ xem các bài bị block và cách sửa.
   - `8`: publish các bài đã approved rồi build/sync docs/commit/push GitHub.
   - `9`: New Affiliate Partner, nhập một brand/tool để bot tạo cả cụm bài.
   - `10`: thoát menu.

Ví dụ UGCVideo.ai:

1. Chạy `runbot_menu.bat`
2. Chọn `9`
3. Nhập:
   - Partner/Product name: `UGCVideo.ai`
   - Official website URL: `https://ugcvideo.ai`
   - Affiliate program URL: `https://ugcvideo.ai/affiliates`
   - Pricing page URL: `https://ugcvideo.ai/pricing`
4. Bot sẽ tạo cluster bài và đưa tất cả vào dashboard để duyệt.
5. Chỉ sau khi approve xong mới quay lại menu và chọn `8` để publish + push GitHub.

Recommended topic patterns for a new affiliate partner:

- `<brand> review`
- `<brand> pricing`
- `<brand> alternatives`
- `<brand> comparison`
- `best <brand> for small business`
- `how to use <brand>`

Rules for custom affiliate articles:

- never invent commission numbers, discounts, or pricing
- if terms are unclear, keep the article informational until verified
- use official URLs as fallback when no affiliate link is configured
- do not publish if verified-source, AI review, or publish gates still fail

## 12B. CONTENT QUALITY FIRST WORKFLOW

This section defines the required quality-first workflow for future Codex/Copilot runs before any new article is written or published.

### Mandatory reading before content work

Before writing or publishing new articles, the assistant must read:

- [PROJECT_GUIDE.md](PROJECT_GUIDE.md)
- [PROJECT_MAP.md](PROJECT_MAP.md)
- [RUNBOOK.md](RUNBOOK.md)
- [reports/REPO_HEALTH.md](reports/REPO_HEALTH.md)
- [SERP_WINNING_RULEBOOK.md](SERP_WINNING_RULEBOOK.md)

Before any future content generation, Codex/Copilot must read:

- [PROJECT_GUIDE.md](PROJECT_GUIDE.md)
- [SERP_WINNING_RULEBOOK.md](SERP_WINNING_RULEBOOK.md)
- [CONTENT_ENGINE_V2_PLAN.md](CONTENT_ENGINE_V2_PLAN.md)
- [CONTENT_ENGINE_V3_BLUEPRINT.md](CONTENT_ENGINE_V3_BLUEPRINT.md)
- [CTR_ENGINE_DESIGN.md](CTR_ENGINE_DESIGN.md)
- [EEAT_ENGINE_DESIGN.md](EEAT_ENGINE_DESIGN.md)
- [INTERNAL_LINK_ENGINE_DESIGN.md](INTERNAL_LINK_ENGINE_DESIGN.md)
- [SEO_AUTONOMOUS_WRITER.md](SEO_AUTONOMOUS_WRITER.md)

### Guardrails for every content run

1. Do not refactor more unless explicitly requested.
2. For low CTR or low click performance, improve the content engine first rather than changing publish flow:
   - stronger title
   - stronger meta description
   - better search intent match
   - FAQ section
   - pros/cons
   - comparison table
   - alternatives section
   - verdict section
   - internal links
   - Review/FAQ/Breadcrumb schema
   - E-E-A-T signals
   - Last Updated
   - Tested by Smile AI Review Hub
   - affiliate CTA quality
3. Use [modules/pre_publish_quality_gate.py](modules/pre_publish_quality_gate.py) in report-only mode before publishing.
   - Minimum target score: 85/100.
   - If the score is below 85, report the issues and improve the draft or generator.
   - Do not block publish yet unless the user explicitly enables blocking mode.
4. Daily content workflow must be:
   - select topics from the dashboard/cluster
   - generate drafts first
   - run the quality gate
   - improve drafts or the generator until the score is at least 85
   - publish only after user approval
5. Do not modify:
   - [build_site.py](build_site.py)
   - the publish pipeline
   - Cloudflare scripts
   - GitHub Actions
   - [docs/](docs/)
   - [site_output/](site_output/)
   - production files under [data/](data/)
unless the user explicitly asks.
6. Do not deploy, push, submit IndexNow, or publish to social platforms unless the user explicitly asks.
7. After any change, report:
   - files changed
   - tests run
   - quality gate result
   - whether publish is safe

### Default operating rule

If a run is not explicitly approved for publishing, the assistant should stay in report-only mode, improve quality first, and avoid any production-side changes.

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

## 15. Canonical Public Article Renderer

Public article rendering now follows this source-first flow:

```text
research package + article data
  -> modules/content_growth_pipeline.render_article()
  -> public presentation boundary / sanitize_public_article_html()
  -> data/production_article_drafts/<slug>/index.html
  -> data/published_static_pages/<slug>/index.html
  -> build_site.py copies pages and /assets/article.css into site_output/
  -> scripts/sync_site_output_to_docs.py copies site_output/ into docs/
  -> editorial_console.py publish-ready --validation-mode smart
  -> git commit / push
  -> Cloudflare Pages
```

`docs/` remains generated deployment output. Fix public article layout in the renderer, CSS asset, validators, or post-process adapters first; do not hand-patch only `docs/`.

Canonical article pages load:

```html
<link rel="stylesheet" href="/assets/article.css">
```

`assets/public-article.css` remains as a compatibility alias. The build copies both article stylesheets into `site_output/assets/`, and sync copies them into `docs/assets/`.

Public English articles must use public labels only. Vietnamese labels belong under `/vi/`. Internal workflow states such as `needs_human_review`, `human_approved`, `published_local`, `approved_for_publish`, `needs_revision`, `needs_enrichment`, `research_score`, `source_confidence`, and planning/debug snapshots must never appear in public HTML. Public reviewer wording should be `Reviewed by: Editorial Team` or equivalent safe editorial wording.

Canonical article markup uses:

- `.site-header`
- `.site-nav`
- `.breadcrumbs`
- `.article-layout`
- `.article-container`
- `.article-hero`
- `.article-card`
- `.article-section`
- `.author-card`
- `.disclosure-card`
- `.toc-links`
- `.table-wrapper`
- `.article-table`
- `.cta-group`
- `.cta-button`
- `.cta-button-secondary`
- `.related-grid`
- `.related-card`
- `.faq-list`
- `.source-list`
- `.site-footer`

Tables must use `<div class="table-wrapper"><table class="article-table">...</table></div>` with header scope attributes where practical. CTA links must use button classes. Affiliate redirect links under `/go/<merchant>/` must include `rel="sponsored noopener noreferrer"`; external non-affiliate links use `rel="noopener noreferrer"`.

Related research must be deterministic, deduplicated, limited to six cards, exclude the current URL, and avoid mixing `/vi/` pages into English cards.

## 16. Smart vs Strict Public Validation

Daily publish uses smart validation:

```powershell
python editorial_console.py validate-batch --date YYYY-MM-DD --mode smart
python editorial_console.py publish-ready --date YYYY-MM-DD --validation-mode smart
```

Smart mode validates only approved or publishable articles in the current batch plus required assets. If one approved article fails, it is skipped and reported; unrelated legacy pages must not block the batch.

Strict mode remains the full-site audit path:

```powershell
python editorial_console.py validate-batch --date YYYY-MM-DD --mode strict
```

Runbot option 8 must continue to publish approved content with smart validation. Runbot option 11 is reserved for strict full-site audit.

## 17. Indexing Policy

Website deploy success is independent from search-engine indexing success. `scripts/post_deploy_indexing.py` writes reports and warnings when preflight, live validation, IndexNow, Bing, or Google submission fails. Non-strict indexing exits 0 so a successful website deployment is not marked broken. Strict indexing may exit nonzero only when explicitly enabled:

```powershell
$env:STRICT_INDEXING="true"
python scripts/post_deploy_indexing.py --strict-indexing
```

The GitHub Actions post-deploy indexing workflow runs in non-strict mode by default. Missing IndexNow, Bing, Yandex, Google, or live-propagation prerequisites must produce a warning plus `logs/indexing/` and `reports/` artifacts, not a failed website deployment. Strict mode is reserved for explicit audits:

```powershell
python scripts/post_deploy_indexing.py --strict
```

Every indexing run should print:

- indexing mode
- changed URLs detected
- URLs validated
- URLs submitted
- URLs skipped
- warning count
- report path

If no public URLs changed, the expected result is success with `No new public URLs require submission.`

## 17A. Canonical Public Footer, Community Signals, and Hero Images

The canonical public article template must include the complete semantic footer generated by `modules/content_growth_pipeline.render_site_footer()`. Footer links must not be concatenated, and the footer must include:

- Brand
- Explore
- Company
- Follow

The footer source is the renderer, not manual patches in `docs/`.

Canonical public articles may include `Our Community Signals` from configured public values in `config/siteStats.json`. Only public platform links are allowed. Do not expose private analytics, internal dashboards, or unsupported traffic claims. The required note is:

```text
Metrics reflect public content activity and are updated periodically. They are not website visitor claims.
```

Hero images are optional. The renderer may output `.article-hero-image` only when the local image file exists in the source/build output. A public page must not ship an empty, placeholder, or broken hero image. Valid hero images must include `src`, `alt`, `width`, `height`, and `decoding="async"`.

## 18. Five-Module Architecture Direction

Do not migrate the whole repository at once. Use adapters and clear boundaries:

- AI Writer: research packages, outlines, article content, SEO title/meta, FAQ, product facts.
- Website Builder: HTML templates, public layout, article CSS, table/CTA/TOC/related rendering, public-safe author/reviewer output, render validation.
- Publisher: build, sync, smart validation, git add/commit/push, deploy status, indexing notification.
- Affiliate Manager: merchant records, official URLs, affiliate redirects, CTA labels, disclosure policy.
- Dashboard: queues, approvals, publish actions, blocked reasons, status reports.

Current ownership mapping:

- `modules/content_growth_pipeline.py`: AI Writer plus current canonical Website Builder adapter.
- `build_site.py`: Website Builder build orchestration and public asset copy.
- `modules/internal_linker.py`, `modules/trust_localization_upgrade.py`, `modules/structured_data_upgrade.py`: Website Builder post-process adapters. They must preserve canonical article markup.
- `modules/daily_editorial_workflow.py` and `editorial_console.py`: Publisher and Dashboard orchestration.
- `modules/affiliate_links.py` and `data/affiliate_links.csv`: Affiliate Manager data boundary.
- `scripts/post_deploy_indexing.py`, `scripts/submit_indexnow.py`, `scripts/check_indexnow_status.py`: Publisher indexing boundary.

Future migration should first extract a dedicated Website Builder interface around the canonical renderer and public validation, then move AI Writer and Publisher responsibilities behind adapters. Preserve the existing operator menu and commands during each phase.

Detailed boundary documentation lives outside public deployment output:

- `architecture/FIVE_MODULE_BOUNDARIES.md`
