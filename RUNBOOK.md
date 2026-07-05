# RUNBOOK

## Overview

## Safe refactor scope for this repository

The current safe refactor is limited to the decision-layer logic in `modules/content_strategy.py`. The change preserves existing output values and thresholds while making the branching easier to review and maintain.

This runbook now includes a protected scope for the current refactor phase. The objective is to improve decision and planning logic without touching production publishing or generated site output.

### Single source of truth for this phase

The following modules are the authoritative implementations for decision logic:

- `modules/topic_scorer.py` — scoring engine and weights
- `modules/content_strategy.py` — content-format decision logic
- `modules/topic_ranker.py` — ranking logic
- `modules/content_planner.py` — planning output logic
- `scripts/score_topics.py` — local scoring entrypoint

If a change is required, refactor these modules in place rather than creating duplicate logic.

### Files and folders explicitly protected

Do not modify the following during this phase:

- `build_site.py`
- `scripts/run_daily_publish_pipeline.py`
- `scripts/sync_site_output_to_docs.py`
- `docs/`
- `site_output/`
- `data/`

These paths are protected because they affect published output, deployment, or the existing repository state.

### Pre-refactor workflow

1. Review the relevant module and existing tests.
2. Run the local scoring flow without changing published files.
3. Add or update tests before modifying logic.
4. Keep the change backward compatible and local-only.
5. Do not write new articles, do not publish, and do not deploy.
6. Review results in reports or temporary local artifacts only.

### Forbidden actions during this phase

- Do not write new articles.
- Do not modify `build_site.py`.
- Do not modify the publish pipeline.
- Do not change `docs/`, `site_output/`, or `data/`.
- Do not deploy or trigger Cloudflare/GitHub Actions.

### Refactor checkpoint 1 completed

- Module: `modules/content_strategy.py`
- Status: completed
- Tests passed: `python -m unittest tests.test_topic_decision_engine -v`
- Files changed:
  - `modules/content_strategy.py`
  - `AI_DECISION_ENGINE.md`
  - `RUNBOOK.md`
- Rollback instruction: revert the changes in `modules/content_strategy.py` and remove the documentation notes in `AI_DECISION_ENGINE.md` and `RUNBOOK.md` if a future issue requires restoring the previous behavior.

This repository supports two related workflows:

- **New AI Affiliate Intelligence Platform**: `main.py`, `run_platform.bat`, and website output under `site_output/`.
- **Legacy affiliate research bot**: `src/main.py`, `runbot.bat`, and legacy output under `data/output/`.

The primary production deployment target is **Cloudflare Pages**.

## Prerequisites

- Python 3.11+ installed.
- A `.env` file based on `.env.example`.
- `BASE_SITE_URL` set in `.env`.
- Optional Cloudflare variables:
  - `CLOUDFLARE_API_TOKEN`
  - `CLOUDFLARE_PAGES_PROJECT`
  - `CLOUDFLARE_DEPLOY_COMMAND`

## Setup

```powershell
pip install -r requirements.txt
copy .env.example .env
```

## Primary operational workflows

### New platform build

1. Run the AI platform pipeline:
   ```powershell
   python main.py
   ```
2. If you want a local dashboard:
   ```powershell
   python -m streamlit run dashboard/app.py
   ```
3. The pipeline writes site output to `site_output/`, plus data and reports under `data/`.

### Daily content growth

1. Discover trending topics:
   ```powershell
   python scripts/discover_ai_trends.py --limit 10
   ```
2. Generate daily content, build, and optionally submit IndexNow:
   ```powershell
   python scripts/run_daily_content_growth.py --limit 10
   ```
3. For testing without build or IndexNow:
   ```powershell
   python scripts/run_daily_content_growth.py --limit 10 --no-build --no-indexnow
   ```

### Legacy affiliate discovery bot

1. Run legacy discovery and scoring:
   ```powershell
   python src/main.py
   ```
2. Or use the helper batch file:
   ```text
   runbot.bat
   ```
3. Outputs are written under `data/output/` and `landing_pages/`.

### Cloudflare deployment

1. Build or refresh `site_output/`.
2. Validate the site.
3. Deploy with Cloudflare:
   ```powershell
   python scripts/deploy_cloudflare.py --project-name YOUR_CLOUDFLARE_PAGES_PROJECT
   ```
4. Or use the helper batch file:
   ```text
   run_cloudflare_publish.bat
   ```

## Validation commands

- `python scripts/final_predeploy_check.py`
- `python scripts/validate_site.py`
- `python scripts/check_indexnow_status.py`
- `python scripts/test_indexnow.py --dry-run`

## Common file locations

- `site_output/` – generated static website.
- `site_output/sitemap.xml` – sitemap for deployed pages.
- `site_output/robots.txt` – robots policy.
- `site_output/indexnow-key.txt` – IndexNow key.
- `data/trending_topics.json` – discovered topics.
- `social_drafts/` – generated social draft files.
- `video_output/` – generated YouTube/video draft files.

## Troubleshooting

### Build issues

- Check `logs/app.log` for pipeline failures.
- Ensure `.env` values are present and valid.
- Ensure `BASE_SITE_URL` is set for any workflow writing `site_output/`.

### Site output missing

- If `site_output/robots.txt` or `site_output/sitemap.xml` is missing, rerun the build.
- If the site output is stale, run `python build_site.py` or `python main.py` depending on the workflow.

### IndexNow failures

- IndexNow failures do not invalidate Cloudflare deploys.
- Use `scripts/check_indexnow_status.py` to verify the production key is live.
- If `indexnow-key.txt` is missing, generate or copy a valid key into `site_output/` and redeploy.

### Social drafts not appearing

- Confirm `scripts/run_daily_content_growth.py` completed successfully.
- Check drafts under `social_drafts/YYYY-MM-DD/<slug>/`.

## Notes

- Do not delete or change production logic in code without a follow-up request.
- Do not deploy from this audit.
- Do not remove files.
