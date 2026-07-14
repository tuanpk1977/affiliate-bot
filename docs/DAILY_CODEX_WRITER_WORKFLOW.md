# Daily Codex Writer Workflow

This workflow keeps the current editorial architecture and publish pipeline. It only changes who writes the draft content after topics and research are prepared.

## Operator Flow

1. Open `runbot_menu.bat`.
2. Choose menu `1` for week-start topics or menu `2` for Tue-Sun advanced topics.
3. The menu previews topics, asks for confirmation, creates the dated topic queue, prepares research packages, and opens the dashboard.
4. Open Codex in this repository and ask it to write the daily articles, or run:

```powershell
python scripts\codex_write_daily_articles.py --count 10 --depth deep
```

5. Codex reads the current `data/editorial_queue/<date>/topics.json` queue and `data/research/<slug>/package.json` packages.
6. Codex selects up to 10 source-ready topics, writes drafts directly into `data/production_article_drafts/<slug>/`, updates the existing review queues, and refreshes the current dashboard.
7. The editor opens menu `4`, reads each draft, and manually approves or rejects.
8. Only after manual approval, menu `8` uses the existing publish-ready workflow to publish approved articles and push GitHub.

## Safety Rules

The Codex writer must not:

- call the OpenAI API;
- call `gpt-4o-mini`;
- use heuristic fallback;
- approve articles;
- publish articles;
- push GitHub;
- deploy;
- index URLs.

Every generated draft stores writer metadata:

```json
{
  "writer": {
    "provider": "codex",
    "mode": "interactive_repository_writer",
    "api_call_used": false,
    "openai_api_used": false,
    "heuristic_fallback_used": false
  }
}
```

## Data Contract

The writer uses the existing stores:

- topic queue: `data/editorial_queue/<date>/topics.json`
- research package: `data/research/<slug>/package.json`
- draft output: `data/production_article_drafts/<slug>/`
- content review queue: `data/content_review_queue.json`
- human approval queue: `data/human_approval_queue.json`
- publish gate queue: `data/publish_queue.json`
- review dashboard: `site_output/review/<date>/index.html`
- upload dashboard copies: `upload/<date>/`

The writer does not create a separate import/export task. Codex runs inside the repository and writes the normal dashboard-readable artifacts directly.

## Commands

Preview writer selection without writing files:

```powershell
python scripts\codex_write_daily_articles.py --count 10 --depth deep --dry-run
```

Write drafts for the current date:

```powershell
python scripts\codex_write_daily_articles.py --count 10 --depth deep
```

Write drafts for a specific date:

```powershell
python scripts\codex_write_daily_articles.py --date 2026-07-13 --count 10 --depth deep
```

Equivalent CLI command:

```powershell
python editorial_console.py codex-write --date 2026-07-13 --count 10 --depth deep
```

## Approval and Publishing

Human approval remains mandatory. A Codex-written draft enters the normal review queue with `needs_human_review` when no hard blocker is present. If a draft is rewritten after approval, the approval record is replaced with a new `needs_human_review` entry, so the article must be reviewed again.

Menu `8` is unchanged. It publishes only articles whose normalized final gate is exactly `Ready for Publish`.
