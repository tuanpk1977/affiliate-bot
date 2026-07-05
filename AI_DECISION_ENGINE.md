# AI Decision Engine

## Safety and governance for refactor work

This document defines the safe scope for the decision engine work. The goal is to improve scoring, planning, and recommendations without touching production publishing or generated site output.

### Single source of truth (authoritative modules)

For this phase, the following modules are the authoritative sources for decision logic:

- `modules/topic_scorer.py` — single source of truth for topic scoring logic and score weights.
- `modules/content_strategy.py` — single source of truth for content-type decision logic.
- `modules/topic_ranker.py` — single source of truth for ranking order.
- `modules/content_planner.py` — single source of truth for daily/weekly planning output.
- `scripts/score_topics.py` — the allowed entrypoint for local scoring runs and report generation.

Do not create parallel versions of these modules. If a change is needed, refactor the existing module in place.

### Files that must not be modified

The following files and folders are explicitly out of scope for this phase:

- `build_site.py`
- `scripts/run_daily_publish_pipeline.py`
- `scripts/sync_site_output_to_docs.py`
- `docs/`
- `site_output/`
- `data/`

These paths are protected to avoid any impact on production output, deployment, or published content.

### Pre-refactor process

Before changing any logic, follow this order:

1. Read the existing module and its tests.
2. Confirm the existing behavior with a local dry run only.
3. Add or update tests before changing logic.
4. Keep all changes local and backward compatible.
5. Do not write new articles, do not publish, and do not deploy.
6. Review the output in reports or temporary local artifacts only.

### Hard guardrails

- Do not write new articles.
- Do not modify `build_site.py`.
- Do not modify the publish pipeline.
- Do not modify `docs/`, `site_output/`, or `data/`.
- Do not deploy or trigger Cloudflare/GitHub Actions.
- If a change is risky, keep it disabled by default and validate it locally first.

## Architecture

The AI Decision Engine is designed as an isolated decision layer for affiliate and content automation.
It does not modify production workflows or deploy code.

### Current safe refactor note

The content strategy decision logic in `modules/content_strategy.py` was refactored to centralize threshold-based branching while preserving the existing output strings and decision thresholds. This change is intentionally limited to the decision layer and does not alter publish, build, or deployment behavior.

### Core modules

- `modules/topic_scorer.py`
  - Scores topics from 0-100 using 20 evaluation factors.
  - Computes traffic, revenue, and SEO sub-scores.
  - Produces recommendation labels and reasoning.
- `modules/content_strategy.py`
  - Decides between content formats: Website, YouTube, Shorts, Social, or Skip.
- `modules/topic_ranker.py`
  - Sorts topics and produces top 10/20/50 groups.
- `modules/content_planner.py`
  - Builds a weekly publishing plan from ranked topics.
- `modules/social_score.py`
  - Estimates social engagement across nine platforms.
- `modules/video_priority.py`
  - Prioritizes video format: No video, Short, Long review, Comparison, Tutorial, or Demo.

### Integration-ready design

All modules use simple interfaces and can be extended with adapters to connect to external data sources later:

- Google Trends
- Google Search Console
- Google Keyword Planner
- Bing Webmaster
- YouTube
- Reddit
- Quora
- PartnerStack
- Impact
- ShareASale
- CJ
- Amazon

The architecture keeps the decision engine isolated from production logic and existing pipelines.

## Workflow

1. Load raw topic feature inputs.
2. Score each topic with `TopicScorer`.
3. Estimate content strategy with `ContentStrategyEngine`.
4. Prioritize video opportunities with `VideoPriorityEngine`.
5. Estimate platform engagement in `SocialValueEstimator`.
6. Rank topics and produce top topic groups.
7. Generate a daily publishing plan.
8. Emit JSON outputs for dashboard consumption.

## Files created

- `modules/topic_scorer.py`
- `modules/content_strategy.py`
- `modules/topic_ranker.py`
- `modules/content_planner.py`
- `modules/social_score.py`
- `modules/video_priority.py`
- `data/topic_scoring_rules.json`
- `scripts/score_topics.py`
- `AI_DECISION_ENGINE.md`

## Future integrations

### Data adapters

Create adapter classes to fetch real signals from:

- Google Trends trends and breakout queries
- Google Search Console impression and CTR data
- Google Keyword Planner CPC and volume
- Bing Webmaster search and query data
- YouTube search and view potential
- Reddit topic engagement
- Quora question volume and topic demand

### Extension points

- `TopicScorer.load_rules()` accepts a JSON rule file.
- `ContentStrategyEngine` can accept an external scoring model.
- `VideoPriorityEngine` can be replaced by a learned classifier.
- `SocialValueEstimator` can be connected to real social network signals.

## Configuration

- `data/topic_scoring_rules.json` contains scoring weights and thresholds.
- `scripts/score_topics.py` uses `data/topic_inputs.json` as default input and writes `data/topic_scores.json`.

### Sample command

```powershell
python scripts/score_topics.py --input data/topic_inputs.json --output data/topic_scores.json --rules data/topic_scoring_rules.json
```

## Dashboard-ready outputs

The scoring script emits JSON output suitable for dashboard ingestion:

- `data/topic_scores.json`

Future dashboard modules can parse this file to show:

- Today's Best Topics
- Top Revenue Topics
- Highest SEO Score
- Highest Social Score
- Video Candidates
- Skipped Topics

## Demo and validation

To validate the decision engine without production impact:

1. Create a small topic input JSON file.
2. Run `scripts/score_topics.py`.
3. Review the scored JSON output.
4. Confirm content recommendations and daily plan logic match business rules.
