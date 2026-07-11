# Five Module Boundaries

This document defines a safe boundary plan for Smile AI Review Hub without moving large parts of the repository in one checkpoint.

The supporting SEO Engine is documented separately in `architecture/SEO_ENGINE_BOUNDARY.md`. It may queue selected opportunities for AI Writer review, but it cannot approve, publish, deploy, or mutate the five production modules.

## Module Ownership

### 1. AI Writer

Owns trend discovery, research packages, planning, article body generation, SEO title/meta, FAQ content, product facts, and source-backed editorial claims.

Current files:

- `modules/ai_trend_discovery.py`
- `modules/research_intelligence.py`
- `modules/content_planning_engine.py`
- `modules/content_growth_pipeline.py` for drafting logic
- `modules/content_review.py`
- `modules/verified_source_acquisition.py`
- `modules/knowledge_registry.py`
- `data/research/`
- `data/research_cache/`

### 2. Website Builder

Owns public HTML rendering, templates, CSS, CTA rendering, table rendering, TOC, related research, footer, localization, and public render validation.

Current files:

- `modules/content_growth_pipeline.py` for canonical public article rendering
- `assets/article.css`
- `assets/public-article.css`
- `build_site.py`
- `modules/internal_linker.py`
- `modules/trust_localization_upgrade.py`
- `modules/structured_data_upgrade.py`
- `modules/publishing_indexing.py` for public page validation helpers

### 3. Publisher

Owns build, sync, smart validation, git add/commit/push orchestration, deploy verification, and indexing notification.

Current files:

- `modules/daily_editorial_workflow.py` for publish-ready orchestration
- `editorial_console.py`
- `scripts/sync_site_output_to_docs.py`
- `scripts/post_deploy_indexing.py`
- `scripts/submit_indexnow.py`
- `scripts/check_indexnow_status.py`
- `.github/workflows/post-deploy-indexing.yml`

### 4. Affiliate Manager

Owns merchant records, official URLs, affiliate links, redirect mappings, partner intake, CTA labels, and disclosure rules.

Current files:

- `modules/affiliate_links.py`
- `data/affiliate_links.csv`
- `data/partners/`
- partner intake paths in `modules/daily_editorial_workflow.py`
- `/go/` redirect generation in build and SEO cleanup scripts

### 5. Dashboard

Owns review queues, approvals, blocked reasons, publish controls, operator reports, and live status surfaces.

Current files:

- `modules/editorial_operations_console.py`
- `modules/daily_editorial_workflow.py` dashboard and queue methods
- `data/editorial_operations_console.*`
- `data/content_review_queue.json`
- `data/human_approval_queue.json`
- `data/publish_queue.json`
- `data/live_status_report.*`
- `runbot_menu.bat`

## Overlapping Files

- `modules/content_growth_pipeline.py`: AI Writer plus Website Builder. Keep the current public renderer as an adapter until a dedicated Website Builder module is extracted.
- `modules/daily_editorial_workflow.py`: Publisher plus Dashboard plus small Affiliate Manager entry points. Preserve CLI/menu behavior while extracting adapters.
- `build_site.py`: Website Builder plus Publisher build orchestration. Keep asset sync and page generation here until a publisher facade exists.
- `modules/internal_linker.py` and `modules/trust_localization_upgrade.py`: Website Builder post-process adapters. They must preserve canonical article markup.

## Adapter Boundaries

Use small adapters before moving files:

- `WebsiteBuilder.render_public_article(article_data) -> html`
- `WebsiteBuilder.validate_public_article(path) -> list[str]`
- `Publisher.publish_batch(batch_date, validation_mode) -> report`
- `AffiliateManager.resolve_cta(tool_or_brand) -> cta`
- `Dashboard.load_queue(batch_date) -> queue_state`

Adapters must call existing functions first. Do not duplicate publish logic or regenerate queue formats.

## Dependency Rules

- AI Writer may read Affiliate Manager data through an adapter, but must not write redirect files.
- Website Builder may render CTA URLs provided by Affiliate Manager, but must not approve affiliate links.
- Publisher may call Website Builder validation, but must not rewrite article content.
- Dashboard may request publish actions, but Publisher owns git/build/deploy side effects.
- Affiliate Manager may update merchant data, but must not edit public article HTML directly.

## Prohibited Cross-Module Access

- Public templates must not read internal queue statuses for display.
- Dashboard status labels must not leak into public HTML.
- AI Writer must not push GitHub or submit IndexNow.
- Website Builder must not approve human review states.
- Publisher must not invent affiliate links, pricing, traffic metrics, or social proof.

## Migration Phases

1. Stabilize contracts: keep existing files, add tests around renderer, validation, publish-ready, and indexing.
2. Extract Website Builder helpers from `modules/content_growth_pipeline.py` without changing public output.
3. Extract Publisher facade around build, sync, smart validation, git, and indexing.
4. Move Affiliate Manager partner and CTA resolution behind a small interface.
5. Split Dashboard queue/report rendering after menu option behavior is covered by tests.

## Suggested Future Folder Layout

```text
modules/
  ai_writer/
  website_builder/
  publisher/
  affiliate_manager/
  dashboard/
```

This is a target layout, not an instruction to move files now. Preserve `editorial_console.py`, `runbot_menu.bat`, option 8 smart publish, and option 11 strict audit throughout each phase.
