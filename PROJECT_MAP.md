# Project Map

## 1. Folder structure

### Root files
- README.md — high-level overview of the repository and deployment posture.
- PROJECT_GUIDE.md — detailed project guide for AI assistants and contributors.
- AI_DECISION_ENGINE.md — decision-engine scope and safety rules.
- RUNBOOK.md — operational runbook for local and deployment workflows.
- main.py — primary orchestration entrypoint for the new platform workflow.
- build_site.py — incremental/full site build entrypoint for static output.
- requirements.txt — Python dependencies.
- config.py — shared configuration, directory setup, and logging helpers.

### Core folders
- modules/ — reusable Python modules for content generation, SEO, schema, affiliate logic, publishing, and site generation.
- scripts/ — CLI entrypoints for discovery, scoring, publishing, validation, and deployment.
- data/ — runtime data, report outputs, generated article snapshots, topic scores, and tracking files.
- docs/ — Cloudflare Pages publish target.
- site_output/ — generated static website output.
- landing_pages/ — landing page source and generated output.
- social_drafts/ — manual social-posting drafts.
- video_output/ — generated video draft assets and metadata.
- draft_output/ — draft and preview artifacts.
- tests/ — unit and integration tests.
- reports/ — audit and planning reports.

## 2. Entry points

### Primary application entrypoints
- main.py — orchestrates the full new-platform workflow.
- build_site.py — builds or refreshes the static site output.
- run_daily_content_growth.py — wrapper for daily content-generation workflow.
- scripts/run_daily_publish_pipeline.py — publishing workflow for selected articles.

### Legacy entrypoints
- src/main.py — legacy affiliate research bot entrypoint.
- runbot.bat — legacy batch wrapper.
- run_platform.bat — newer platform batch wrapper.

### CLI utilities
- scripts/discover_ai_trends.py
- scripts/score_topics.py
- scripts/run_daily_content_growth.py
- scripts/generate_video_assets.py
- scripts/sync_site_output_to_docs.py
- scripts/submit_indexnow.py
- scripts/check_indexnow_status.py
- scripts/deploy_cloudflare.py
- scripts/validate_site.py
- scripts/final_predeploy_check.py

## 3. Build pipeline

### Main build flow
1. main.py loads offers and source data.
2. It runs market, keyword, compliance, ROI, and content-generation modules.
3. It generates landing pages and site output via modules.site_builder.build_site_output.
4. It runs SEO, internal-link, schema, sitemap, and metadata post-processing.
5. It writes data and report artifacts under data/.

### build_site.py flow
- build_site.py supports incremental and full builds.
- Incremental mode copies published article snapshots from data/published_static_pages into site_output/.
- It then runs SEO cleanup, multilingual pages, internal linking, metadata rewrite, canonical routing, schema upgrade, social metadata post-processing, and sitemap generation.
- Full mode calls main.py first and then applies the same post-processing steps.

## 4. Publish pipeline

### Current publish model
- The production workflow is Cloudflare Pages through docs/.
- build_site.py creates site_output/.
- scripts/sync_site_output_to_docs.py copies the generated site into docs/.
- GitHub push then triggers Cloudflare Pages deployment.

### Important boundaries
- The repository is allowed to generate and prepare publish files locally.
- Manual deployment and production pipeline changes are out of scope for this documentation-only task.

## 5. Content generation flow

### Content generation stages
1. Discover topics using scripts/discover_ai_trends.py.
2. Score and rank topics using scripts/score_topics.py and modules/topic_scorer.py.
3. Create article drafts and related assets through the content-growth pipeline.
4. Publish selected drafts into data/published_static_pages and later into site_output/.
5. Generate social drafts and video assets as manual drafts rather than auto-publishing.

### Content-related modules
- modules/content_growth_pipeline.py
- modules/content_planner.py
- modules/content_strategy.py
- modules/topic_scorer.py
- modules/topic_ranker.py
- modules/video_priority.py
- modules/social_score.py
- modules.content_approval.py
- modules.markdown_publisher.py

## 6. SEO flow

### SEO responsibilities
- Canonical routing: modules/canonical_routes.py
- Sitemap generation: modules/sitemap_generator.py
- Technical cleanup: modules/seo_technical_cleanup.py
- Title optimization: modules/seo_title_optimizer.py
- Duplicate metadata cleanup: modules/seo_metadata_uniqueness.py
- AI-search upgrade: modules/seo_ai_search_upgrade.py
- Internal linking: modules/internal_linker.py

### SEO pipeline stages
- Post-process generated HTML in site_output/.
- Rewrite titles and metadata for clarity and uniqueness.
- Apply canonical routing and technical cleanup.
- Add internal links and topical hubs.
- Regenerate sitemap and verify SEO output.

## 7. Schema flow

### Schema responsibilities
- modules/structured_data_upgrade.py applies structured data upgrades.
- The schema layer is used after content generation and site rendering.
- Schema improvements are applied as a post-processing step over generated pages.

### Schema coverage targets
- Article
- Review
- FAQ
- Breadcrumb
- Organization
- Person
- Product
- SoftwareApplication
- VideoObject
- WebPage

## 8. AI workflow

### AI-related capabilities
- Topic discovery from trend and search signals.
- Topic scoring and prioritization.
- Draft generation and planning.
- SEO and schema enhancement.
- Social and video asset generation.

### Main AI workflow modules
- modules/ai_trend_discovery.py
- modules/topic_scorer.py
- modules/content_strategy.py
- modules/topic_ranker.py
- modules/content_planner.py
- modules/ai_angle_generator.py
- modules/social_content_generator.py
- modules/video_package_generator.py
- modules.seo_system.py

## 9. Module dependencies

### High-level dependency clusters
- Orchestration layer: main.py, build_site.py
- Content generation: modules/content_*.py, modules/markdown_publisher.py
- SEO and schema: modules/seo_*.py, modules/structured_data_upgrade.py, modules/internal_linker.py
- Affiliate and market intelligence: modules/offer_*.py, modules/market_analyzer.py, modules/roi_tracker.py
- Social/video: modules/social_*.py, modules/video_*.py

### Important runtime dependency examples
- main.py depends on modules such as offer_loader, offer_scorer, landing_page_generator, site_builder, seo_system, and structured_data_upgrade.
- build_site.py depends on canonical routing, internal linking, SEO cleanup, metadata rewrite, schema upgrade, sitemap generation, and topical hubs.
- scripts/score_topics.py depends on modules/topic_scorer.py, topic_ranker.py, content_strategy.py, and content_planner.py.

## 10. Legacy modules

### Clearly legacy or separate
- src/main.py — older affiliate research bot entrypoint.
- modules/legacy_slug_normalizer.py — compatibility layer for older URL patterns.
- runbot.bat and related legacy batch commands.
- Netlify-related artifacts are retained for compatibility but are not the primary deployment path.

### Legacy vs current
- The new platform is centered around main.py and build_site.py.
- The legacy workflow remains available for older affiliate research tasks and historical compatibility.

## 11. Duplicate modules

### Likely overlap areas
- Multiple SEO-related modules perform related post-processing tasks; several modules could overlap in title, metadata, canonical, and schema work.
- The repository contains both older and newer content-generation paths, which may lead to duplicate logic across legacy and current modules.
- Several modules in modules/ appear to cover similar concerns (for example, content planning, content strategy, and scoring) and may share logic that should be consolidated during refactor.

### Refactor risk note
- Duplicate logic is likely concentrated around content planning, site post-processing, SEO cleanup, and metadata generation.

## 12. Safe-to-refactor modules

These are the safest candidates for isolated refactor work because they are closer to decision logic and local generation than to deployment or published output:

- modules/topic_scorer.py
- modules/content_strategy.py
- modules/topic_ranker.py
- modules/content_planner.py
- modules/social_score.py
- modules/video_priority.py
- scripts/score_topics.py

These modules can be inspected and refactored locally without changing published site output, docs/, or deployment behavior.

## Safe operating rules reflected in this document

- Do not modify build_site.py.
- Do not modify publish pipeline or deployment scripts.
- Do not modify docs/, site_output/, or data/ as part of this documentation-only task.
- Do not write new articles.
- Do not deploy.
