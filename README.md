# Affiliate Research Bot / AI Affiliate Intelligence Platform

This repository contains two related automation stacks:

- **Legacy affiliate research bot**: `src/main.py`, `runbot.bat`, and the legacy `data/output/` workflow.
- **New AI Affiliate Intelligence Platform**: `main.py`, `run_platform.bat`, and the current `site_output/` website build.

Both stacks coexist in the repository, but they use different entrypoints and are intended for separate workflows.

## What this project does

1. **Affiliate research & scoring**
   - Collects affiliate program signals from candidate websites.
   - Scores offers for affiliate quality, ad readiness, and market potential.
   - Generates CSV reports, landing page plans, ROI summaries, and ad upload templates.

2. **AI content growth pipeline**
   - Discovers trending AI/SaaS topics.
   - Generates website article HTML, video draft assets, and social draft content.
   - Builds the static website output and optionally submits URLs to IndexNow.

3. **Static site build & SEO automation**
   - Builds website output in `site_output/`.
   - Generates `sitemap.xml` and `robots.txt`.
   - Applies SEO cleanup, structured data upgrades, bilingual pages, and internal linking.

4. **Cloudflare deploy + IndexNow**
   - Primary production deployment target is **Cloudflare Pages**.
   - `scripts/deploy_cloudflare.py` deploys `site_output/` and optionally runs IndexNow after success.
   - `scripts/submit_indexnow.py`, `scripts/check_indexnow_status.py`, and `scripts/post_deploy.py` support IndexNow.

5. **Social draft generation**
   - Creates manual drafts under `social_drafts/YYYY-MM-DD/<slug>/`.
   - Social output is intentionally draft/manual only.

## Important note

- The primary production workflow is **Cloudflare Pages**.
- `netlify.toml` and some Netlify-related docs are retained for compatibility only.
- Do not rely on legacy Netlify instructions unless you explicitly need that path.
- Do not commit `.env`.
- See `RUNBOOK.md` and `CONTENT_WORKFLOW.md` for operational runbooks and content workflow details.

## Quick start

```powershell
pip install -r requirements.txt
copy .env.example .env
```

Set `BASE_SITE_URL` in `.env` before running content/site build and deployment commands.

## Primary entrypoints

### New platform

- `python main.py`
- `run_platform.bat`
- `python scripts/generate_tool_screenshots.py`
- `python -m streamlit run dashboard/app.py`

### Daily content growth

- `python scripts/discover_ai_trends.py --limit 10`
- `python scripts/run_daily_content_growth.py --limit 10`
- `python scripts/run_daily_content_growth.py --discover --limit 10`
- `python scripts/run_daily_content_growth.py --limit 10 --dry-run`
- `python scripts/run_daily_content_growth.py --limit 10 --no-build --no-indexnow`

### Affiliate research bot (legacy)

- `python src/main.py`
- `runbot.bat`

### Deployment

- `python scripts/deploy_cloudflare.py --project-name YOUR_CLOUDFLARE_PAGES_PROJECT`
- `python scripts/deploy_cloudflare.py --dry-run`
- `run_cloudflare_publish.bat`
- `python scripts/check_indexnow_status.py`
- `python scripts/test_indexnow.py`

## Build and deploy workflow

1. Build website output:
   - `python main.py` for the new platform.
   - `python build_site.py` for incremental publish or full rebuild.

2. Validate the build:
   - `python scripts/final_predeploy_check.py`
   - `python scripts/validate_site.py`
   - `python scripts/check_indexnow_status.py`

3. Deploy to Cloudflare:
   - `run_cloudflare_publish.bat`
   - or `python scripts/deploy_cloudflare.py --project-name YOUR_CLOUDFLARE_PAGES_PROJECT`

4. Verify live site:
   - `https://<site>/`
   - `https://<site>/sitemap.xml`
   - `https://<site>/robots.txt`
   - `https://<site>/indexnow-key.txt`

5. Manual social/video follow-up:
   - Publish social drafts manually from `social_drafts/`.
   - Upload YouTube drafts manually and add URLs back with `scripts/update_youtube_links.py`.

## Outputs and key folders

- `site_output/`: static website output for deployment.
- `data/`: data sources, reports, tracking, and generated CSVs.
- `landing_pages/`: generated landing pages and templates.
- `social_drafts/`: manual social posting drafts.
- `video_output/`: YouTube draft scripts, metadata, transcripts, and scenes.
- `docs/`: docs sync target for website content.

## Key files and reports

- `data/offer_scores.csv`
- `data/market_insights.csv`
- `data/keywords.csv`
- `data/ads_google.csv`
- `data/ads_bing.csv`
- `data/roi_report.csv`
- `data/report_summary.md`
- `data/content_growth_reports/YYYY-MM-DD.md`
- `data/trending_topics.json`
- `data/content_growth_performance_log.csv`
- `data/published_static_pages/<slug>/index.html`
- `social_drafts/YYYY-MM-DD/<slug>/`
- `video_output/<slug>/`
- `site_output/sitemap.xml`
- `site_output/robots.txt`
- `site_output/indexnow-key.txt`

## Deploy and IndexNow support

- Public key: `site_output/indexnow-key.txt`
- IndexNow submitter: `scripts/submit_indexnow.py`
- Post-deploy runner: `scripts/post_deploy.py`
- Dry-run test: `scripts/test_indexnow.py`
- Live diagnostics: `scripts/check_indexnow_status.py`
- Cloudflare deploy: `scripts/deploy_cloudflare.py`

### Common deploy flags

```powershell
CLOUDFLARE_API_TOKEN=<token>
CLOUDFLARE_PAGES_PROJECT=<project>
CLOUDFLARE_DEPLOY_COMMAND=<optional existing deploy command>
AUTO_INDEXNOW_AFTER_DEPLOY=true
BASE_SITE_URL=https://smileaireviewhub.com
```

### IndexNow notes

- IndexNow expects a valid `indexnow-key.txt` file in `site_output/`.
- The key must be deployed and live at `https://<site>/indexnow-key.txt`.
- `scripts/check_indexnow_status.py` verifies local files and live availability.
- `scripts/submit_indexnow.py` can submit incremental changes or sitemap URLs.

## Social and content workflow notes

- Generated social content is draft-only and not auto-posted.
- Video and YouTube assets are created as manual drafts under `video_output/`.
- `AUTO_YOUTUBE_UPLOAD` and `AUTO_SOCIAL_POST` should remain false for safe workflow.
- `scripts/run_daily_content_growth.py` generates manual social and video files but does not publish them.

## Legacy notes

- `netlify.toml` and Netlify instructions are kept for compatibility only.
- Primary production deployment is Cloudflare Pages.
- `src/main.py` is a legacy affiliate research bot and is separate from `main.py`.

## How to add new affiliate candidates

- Edit `data/input/projects_seed.csv` for manual seeds.
- Edit `data/input/discovery_sources.csv` for automated discovery.
- Run `runbot.bat` or `python src/main.py` for the legacy affiliate discovery pipeline.

## How to add new content topics

- Run `python scripts/discover_ai_trends.py --limit 10` to refresh topic discovery.
- Run `python scripts/run_daily_content_growth.py --limit 10` to generate new pages, drafts, and site output.
- Use `--no-build` or `--no-indexnow` for safe local testing.

## Recommended validation commands

```powershell
python scripts/final_predeploy_check.py
python scripts/validate_site.py
python scripts/check_indexnow_status.py
python scripts/test_indexnow.py --dry-run
```

## When something is wrong

- If `site_output/robots.txt` or `site_output/sitemap.xml` is missing, rebuild before deployment.
- If IndexNow fails, the Cloudflare deployment can still be valid; fix the IndexNow configuration and retry later.
- If social drafts are not generated, check the daily content growth workflow output under `social_drafts/YYYY-MM-DD/` and verify `python scripts/run_daily_content_growth.py` completed successfully.
- If `main.py` or `build_site.py` exits with errors, inspect `logs/app.log` and the console output for missing dependencies or invalid `.env` values.

## Legacy affiliate bot setup

```powershell
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit seed and discovery sources before running the legacy affiliate discovery pipeline:

- `data/input/projects_seed.csv`
- `data/input/discovery_sources.csv`

## Legacy affiliate bot run

Double-click:

```text
runbot.bat
```

Manual run:

```powershell
python src/main.py
```

Outputs are written to:

- `data/output/projects_raw.csv`
- `data/output/projects_scored.csv`
- `data/output/top_report.txt`
- `data/output/decision_summary.txt`
- `data/output/discovered_projects.csv`
- `data/output/ad_launch_plan.csv`
- `data/output/google_ads_upload_template.csv`
- `data/output/microsoft_ads_upload_template.csv`
- `data/output/ads_manual_steps.txt`
- `data/output/landing_pages_index.csv`
- `data/output/roi_report.csv`
- `data/output/roi_summary.txt`
- `data/output/crypto_listing_watchlist.csv`
- `data/output/crypto_listing_summary.txt`
- `landing_pages/`
- `data/logs/bot.log`

For manual verification, use `data/input/manual_review_template.csv` as the review sheet format.

## Where to see results

- `data/output/decision_summary.txt`: easiest file to read first for affiliate opportunity status.
- `data/output/top_report.txt`: ranked list of affiliate leads.
- `data/output/projects_scored.csv`: full scored dataset with statuses and recommendations.
- `data/output/google_ads_upload_template.csv`: manual upload template for Google Ads.
- `data/output/microsoft_ads_upload_template.csv`: manual upload template for Microsoft/Bing Ads.
- `data/output/roi_report.csv`: ROI calculations and campaign recommendations.
- `data/output/roi_summary.txt`: Vietnamese ROI summary.
- `video_output/`: YouTube draft assets.
- `social_drafts/`: manual social posting drafts.

## Ads automation scope

The bot can automatically:

- Discover affiliate leads.
- Score and rank leads.
- Detect basic ads policy risks.
- Block high-risk leads from ad templates.
- Generate landing page guidance.
- Generate Google Ads and Microsoft/Bing Ads CSV templates.
- Calculate ROI from exported campaign results.
- Recommend `PAUSE`, `WATCH`, `OPTIMIZE`, or `SCALE`.

Manual steps remain required:

- Own the target domain and hosting.
- Publish landing pages to the live domain.
- Add affiliate disclosures, Privacy Policy, Terms, and Contact pages.
- Place affiliate links in the published landing page CTA.
- Verify paid search and brand bidding rules in affiliate terms.
- Keep campaigns paused until manual review is complete.
- Export or paste ad performance into `data/input/ad_results.csv` before ROI tracking.

## ROI tracking

After campaigns get traffic, export or enter results into:

```csv
campaign,cost,clicks,conversions,revenue,notes
My Campaign,25,100,2,60,first test
```

Then run:

```powershell
python src/main.py
```

Check:

- `data/output/roi_report.csv`
- `data/output/roi_summary.txt`

## Crypto listing watchlist

The legacy bot can monitor listing announcement pages and create a research watchlist.

Outputs:

- `data/output/crypto_listing_watchlist.csv`
- `data/output/crypto_listing_summary.txt`

This is research data only, not investment advice.

## How auto discovery works

The legacy bot reads `data/input/discovery_sources.csv`, extracts candidate project links from trusted sources, and evaluates them.

Change `DISCOVERY_LIMIT` in `.env` to control how many candidate sources the pipeline checks per run:

```env
DISCOVERY_LIMIT=25
```

## How to add projects

Edit `data/input/projects_seed.csv`:

```csv
brand_name,website,category,source,notes
Tool Name,https://example.com,saas,manual,short note
AI Product,https://example.ai,ai,twitter,found from post
```

Recommended categories:

- `ai`
- `saas`
- `devtools`
- `crypto`
- `finance`
- `marketing`
- `education`
- `ecommerce`

## Scoring meaning

- `affiliate_quality_score`: how strong and clear the affiliate program looks.
- `data_product_value_score`: how sellable this lead is as paid information.
- `ad_readiness_score`: how ready this project is for future ad testing.
- `total_score`: blended priority score used for ranking.
- `recommended_action`: what to do next before selling or advertising the lead.
- `review_status`: whether the lead is ready for verification, needs manual review, needs more research, or belongs in the watchlist.
- `sale_status`: whether this can be packaged after proof, must be verified before selling, is blocked, or should not be sold yet.
- `ads_status`: whether this can move toward ad testing after terms review.
- `verification_checklist`: the exact items to verify before selling the lead or running ads.

## Manual verification workflow

1. Run the affiliate bot and open `data/output/projects_scored.csv`.
2. Filter by `sale_status` and `review_status`.
3. Manually open `manual_review_url` or `affiliate_url`.
4. Confirm commission, cookie window, payout, allowed traffic sources, and program activity.
5. Capture proof before selling the information.
6. Only move a lead toward ads when `ads_status` is not `not_ready_for_ads` and traffic restrictions are confirmed.

## AI Trend Discovery

Run the daily topic discovery engine before generating articles:

```powershell
python scripts/discover_ai_trends.py
```

The engine reads public trend feeds and optional API-backed sources, filters topics already published in the site output, scores opportunities, and writes:

- `data/trending_topics.json`
- `data/trending_topics_daily_report.md`
- `data/trend_reports/YYYY-MM-DD.md`

It does not generate articles, videos, or deploy the website.

## Daily content growth workflow

Use `python scripts/run_daily_content_growth.py --limit 10` to generate site content, video drafts, social drafts, and optional IndexNow submission.

The content growth pipeline is intentionally website-first: it publishes HTML to `site_output/` and creates manual drafts for YouTube and social.

The engine reads public trend feeds and optional API-backed sources, filters topics already published in the site output, scores opportunities, and writes:

- `data/trending_topics.json`
- `data/trending_topics_daily_report.md`
- `data/trend_reports/YYYY-MM-DD.md`

It does not generate articles, videos, or deploy the website. X and YouTube discovery require `TWITTER_BEARER_TOKEN` and `YOUTUBE_API_KEY`. LinkedIn is reported as unavailable unless an approved discovery endpoint is configured.
