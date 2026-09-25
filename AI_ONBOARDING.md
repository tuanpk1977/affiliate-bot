# AI Onboarding for Smile AI Review Hub

This repository must be understandable by a new AI with no prior chat history. Start here before writing, editing, reviewing, publishing, or changing architecture.

## Operating Contract

The project is an editorial automation system for Smile AI Review Hub. It prepares topic queues and research packages, writes source-backed article drafts, routes drafts through review and mandatory human approval, publishes approved articles through Git/GitHub, deploys through the existing static-site pipeline, and prepares manual social publishing drafts.

The system is model agnostic. Do not assume a specific model, vendor, IDE, hosted agent, or API. The repository-local writing workflow must work with any capable AI that can read and write files in this repo.

## Read First

Before generating an article, read these files in order:

1. `AI_WRITER_INSTRUCTIONS.md`
2. `EDITORIAL_MEMORY.md`
3. `WRITING_DNA.md`
4. `STRUCTURE_DNA.md`
5. `VOICE_DNA.md`
6. `ARTICLE_FINGERPRINT.md`
7. `DECISION_ENGINE.md`
8. `STYLE_ENGINE.md`
9. `ARTICLE_BLUEPRINT_ENGINE.md`
10. `SELF_VALIDATION_ENGINE.md`
11. `QUALITY_SCORE_ENGINE.md`
12. `MODEL_CONSISTENCY_TEST.md`
13. `docs/editorial/UNIVERSAL_EDITORIAL_ENGINE.md`
14. `docs/editorial/EDITORIAL_ENGINE.md`
15. `docs/editorial/CONTENT_BLUEPRINT.md`
16. `docs/editorial/STYLE_GUIDE.md`
17. `docs/editorial/ARTICLE_TEMPLATE.md`
18. `docs/editorial/QUALITY_CHECKLIST.md`
19. `docs/prompts/MASTER_SYSTEM_PROMPT.md`
20. `docs/prompts/MASTER_WRITER_PROMPT.md`

For review, research, QA, social, or development tasks, also read the matching role guide and playbook in `docs/editorial/`.

## Daily Workflow

Menu 1 prepares weekly foundation root topics and research. It should not publish or approve anything. Monday selection is quality-limited and capped at 5 roots. If only 1-4 topics pass source/readiness checks, those valid roots are still the complete weekly foundation set. Do not invent replacements to reach 5.

Menu 2 prepares daily deep-dive queues only from the locked Monday root topic set. It should not open the review dashboard, invent topics outside the weekly set, import another week, or replace a weak/finished root with a new hot topic. Every Menu 2 item must preserve a valid `root_topic_id`, scheduled `daily_angle`, same-root differentiation contract, and next-article bridge.

Midweek discoveries that are not part of the Monday root set belong in watchlist, research monitoring, social-only consideration, rejection, or explicit human override review. They do not enter website production automatically. Unconfirmed hot news must stay in `SOCIAL_HOT_UNCONFIRMED` or an equivalent social/watchlist state. Officially confirmed news may become `OFFICIAL_NEWS_STANDALONE`, but it must not replace the locked foundation roots.

The repository AI writer reads `data/codex_tasks/CURRENT_TASK.md`, follows the referenced instruction file, writes drafts into `data/production_article_drafts/<slug>/`, updates review/publish queues through existing workflow code, and regenerates the local review dashboard.

Menu 4 is the review dashboard. The editor manually approves or rejects.

Menu 8 publishes only explicitly human-approved articles that pass the publish gate. It builds selected output, syncs `site_output` to `docs`, commits scoped files, pushes to `origin/main`, and lets the existing deployment pipeline run.

Social has two separate contracts. Website article distribution uses Menu F to prepare source packages for exactly two live HTTP 200 articles; the AI writes platform-specific drafts, Menu G reviews them, and Menu E copies only approved drafts for manual publishing. Hot-news monitoring uses `SOCIAL_HOT_UNCONFIRMED` packages before a website article exists; those packages preserve source URLs and discovery timestamps, use cautious language, contain no fabricated Smile AI Review Hub URL, do not create website drafts, and do not modify weekly roots.

Menu H is the AI News Editor, not a website topic selector. It uses the dedicated `SOCIAL_HOT_NEWS_V2` profile: event clustering first, Tier A major/official news first, Tier B secondary stories second, then diversity as a soft cap. Its hard gates are limited to a valid source URL, title, determinable date, enough evidence for safe wording, duplicate-event protection, and project scope/safety. Menu H may select zero to three items and only prepares `SOCIAL_HOT_DRAFT` packages plus a repository AI task.

Menu I is offline Editorial Intelligence. It analyzes manually exported CSV files, repository HTML, article relationships, and already-generated AI output files. It produces recommendations and reports only. It never edits an article, changes a queue, approves, publishes, deploys, indexes, commits, or pushes.

Repository AI tasks use `data/ai_tasks/CURRENT_AI_TASK.md` and the schema in `data/ai_tasks/AI_TASK_SCHEMA.json`. Legacy `data/codex_tasks/CURRENT_TASK.md` remains a compatibility pointer; the task contract is model-neutral and does not authorize a model API.

## Non-Negotiable Safety Rules

- Never auto-approve an article.
- Never publish without explicit human approval.
- Never bypass hard blockers.
- Never call paid APIs unless the task explicitly authorizes them.
- Never invent sources, pricing, credentials, claims, benchmarks, or product facts.
- Never edit queue/state/generated files casually.
- Never push, deploy, index, or publish unless explicitly requested.
- Never treat warnings as blockers unless the current publish gate says they are hard blockers.

## Repository Map

- `editorial_console.py`: main CLI entry point behind menu actions.
- `runbot_menu.bat`: Windows operator menu.
- `modules/daily_editorial_workflow.py`: queue, batch, dashboard, publish workflow orchestration.
- `modules/codex_writer_workflow.py`: repository-local article writing integration.
- `modules/content_growth_pipeline.py`: article rendering, public HTML, schema, CSS, sanitization.
- `modules/content_review.py`: editorial review, quality scoring, warnings and blockers.
- `modules/publish_gate.py`: final publish eligibility normalization.
- `scripts/codex_instruction_prompt.py`: creates model-agnostic handoff task files.
- `scripts/codex_write_daily_articles.py`: CLI for writing queued drafts.
- `data/editorial_queue/`: prepared topic queues and weekly manifests.
- `data/production_article_drafts/`: draft source of truth for generated articles.
- `data/content_review_queue.json`: review queue.
- `data/human_approval_queue.json`: human approval state.
- `data/publish_queue.json`: publish state.
- `data/published_static_pages/`: generated public article HTML.
- `site_output/`: local static build output.
- `docs/`: production deployment root.
- `upload/`: batch artifacts and reports.
- `data/social_drafts/`: social source packages and platform drafts.
- `data/ai_tasks/`: model-neutral repository AI task handoffs.
- `modules/performance_engine/`: CSV-only performance recommendations and editorial-memory extraction.
- `modules/knowledge_graph/`: deterministic article relationship, orphan, duplicate, gap, and link analysis.
- `editorial_intelligence_console.py`: Menu I report-only CLI.

## Current Limitations

Some legacy class names, scripts, and folders still use the word `codex` because they were introduced as local handoff utilities. Treat those as repository-local AI workflow names, not as a dependency on any hosted model or API.

The safest future migration is a compatibility rename that preserves CLI entry points while adding neutral aliases.

## Universal External Writer

Routine website and social writing uses the model-neutral queue in
`data/write_queue/`. ChatGPT Web/Desktop is the primary operator-selected writer,
but the returned ZIP contract is not model-specific.

The AI receives a self-contained Menu X ZIP. It must obey `TASK.json`,
`PROMPT.md`, the supplied source allowlist, the output contract, and validation
rules. It must return one `completed_drafts.zip`; it must not approve, publish,
deploy, index, call repository APIs, or invent sources.

Menu W is the only supported universal registration boundary. Never ask the
operator to extract or manually move output folders. Imported website drafts go
to Menu 4; social drafts go to Menu G. Human approval remains mandatory.

See:

- `docs/editorial/EXTERNAL_WRITER_WORKFLOW.md`
- `docs/editorial/EXTERNAL_WRITER_ZIP_CONTRACT.md`
- `docs/editorial/EXTERNAL_WRITER_IMPORT_SECURITY.md`

## Zero-Human Generation Standard

Any future LLM must produce articles by executing the repository instructions, not by relying on private chat history or model-specific habits. The DNA files define style, structure, voice, measurable fingerprint, decision trees, self-validation, and quality scoring.
