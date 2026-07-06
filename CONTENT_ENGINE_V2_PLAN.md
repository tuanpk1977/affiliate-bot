# Content Generation Engine V2 Plan

## Goal

Upgrade the current content generation engine to improve CTR, clicks, SEO quality, and affiliate conversion without publishing, deploying, or pushing anything. This plan is documentation-only for now and keeps the existing publish pipeline untouched.

## Safety constraints

- Do not publish.
- Do not deploy.
- Do not push.
- Do not modify docs/, site_output/, or production files under data/.
- Do not change build_site.py or the publish pipeline.
- Do not write new articles yet.
- Keep the work in a planning and test-first phase until the user explicitly approves implementation.

## Proposed modules

The V2 engine should be introduced as a staged, additive layer around the current generation flow. Proposed modules (not created yet):

1. modules/content_engine_v2_title_optimizer.py
   - CTR style title generation
   - curiosity gap support
   - year modifier support
   - buyer-intent language
   - tested/reviewed angle
   - comparison angle

2. modules/content_engine_v2_meta_optimizer.py
   - meta description generation
   - benefit-first phrasing
   - keyword match control
   - click-reason phrasing
   - max length enforcement

3. modules/content_engine_v2_intent_detector.py
   - classify content into review, comparison, pricing, alternatives, tutorial, use case, FAQ, or buying guide

4. modules/content_engine_v2_outline_builder.py
   - create article structure with hero intro, quick verdict, audience fit, avoid-it section, pros/cons, pricing, alternatives, comparison table, testing/experience section, FAQ, verdict, CTA, and internal links

5. modules/content_engine_v2_eeat_enhancer.py
   - add Last Updated, Tested by Smile AI Review Hub, evaluation criteria, limitations, transparent recommendation, and practical guidance

6. modules/content_engine_v2_schema_builder.py
   - generate Article, Review, FAQ, Breadcrumb, and SoftwareApplication schema hints where appropriate

7. modules/content_engine_v2_internal_link_planner.py
   - plan links to review, comparison, alternatives, pricing, and tutorial pages

8. modules/content_engine_v2_cta_optimizer.py
   - improve affiliate CTA quality with non-spammy wording and better placement

9. modules/content_engine_v2_orchestrator.py
   - coordinate the above modules into a single draft-generation workflow

## Files likely to change later

These are the existing files most likely to be touched when implementation begins:

- modules/content_growth_pipeline.py
- modules/ai_angle_generator.py
- modules/markdown_publisher.py
- modules/internal_linker.py
- modules/structured_data_upgrade.py
- modules/pre_publish_quality_gate.py
- scripts/run_daily_content_growth.py
- tests/test_content_quality_gate.py

## Current implementation baseline

The current pipeline already has useful anchors:

- content generation and article rendering live in modules/content_growth_pipeline.py
- title/meta generation is currently lightweight and not fully optimized for CTR
- schema generation already exists in modules/content_growth_pipeline.py and modules/structured_data_upgrade.py
- internal linking already exists in modules/internal_linker.py
- the report-only gate already exists in modules/pre_publish_quality_gate.py

The V2 work should extend these existing flows rather than replace them wholesale.

## Proposed tests to add

Tests should be added before implementation begins.

1. tests/test_content_engine_v2_titles.py
   - stronger title generation for comparison and review intent
   - inclusion of curiosity gap, year modifier, and tested/reviewed angle

2. tests/test_content_engine_v2_meta.py
   - meta description length control
   - benefit-first phrasing
   - keyword match behavior

3. tests/test_content_engine_v2_intent.py
   - correct intent classification for review/comparison/pricing/tutorial/FAQ/buying guide cases

4. tests/test_content_engine_v2_outline.py
   - section coverage for hero intro, quick verdict, pros/cons, pricing, alternatives, comparison table, FAQ, verdict, CTA, and internal links

5. tests/test_content_engine_v2_eeat.py
   - Last Updated, tested-by signal, transparency, limitations, and practical recommendation support

6. tests/test_content_engine_v2_schema.py
   - schema hint generation for Article, Review, FAQ, Breadcrumb, and SoftwareApplication cases

7. tests/test_content_engine_v2_quality_gate_integration.py
   - ensure the engine produces inputs that can be evaluated by modules/pre_publish_quality_gate.py
   - verify report-only mode and 85/100 target handling

## Implementation order

### Step 1 — Title and meta optimization (Low risk)

- Add title optimizer and meta optimizer modules.
- Keep them isolated from publish logic.
- Generate outputs as structured draft metadata instead of changing final pages directly.
- Risk: Low

### Step 2 — Search intent and outline builder (Medium risk)

- Add intent detection and outline construction.
- Ensure the new structure includes the required sections for stronger article quality.
- Keep the existing article renderer as the display layer.
- Risk: Medium

### Step 3 — E-E-A-T and CTA enhancement (Medium risk)

- Add tested-by wording, transparent limitations, and stronger CTA text.
- Keep wording non-spammy and buyer-intent focused.
- Risk: Medium

### Step 4 — Schema and internal linking support (Medium risk)

- Add schema bundle generation and internal-link planning.
- These changes should be additive and should not alter the publish workflow yet.
- Risk: Medium

### Step 5 — Quality gate integration (Medium risk)

- Feed generated article metadata into modules/pre_publish_quality_gate.py.
- Run in report-only mode.
- Minimum target score: 85/100.
- If below 85, report specific improvement areas rather than blocking publish.
- Risk: Medium

### Step 6 — Orchestrator and draft output integration (Medium risk)

- Wire the new modules into the existing draft-generation flow.
- Preserve the current publish pipeline as-is.
- Risk: Medium

## Risk level by step

| Step | Risk | Notes |
| --- | --- | --- |
| Title and meta optimization | Low | Mostly additive metadata generation |
| Intent detection and outline builder | Medium | Affects article structure and content quality |
| E-E-A-T and CTA enhancement | Medium | Risk of over-optimizing or sounding promotional |
| Schema and internal links | Medium | Must not break existing page rendering |
| Quality gate integration | Medium | Needs careful scoring calibration |
| Orchestrator integration | Medium | Must preserve backward compatibility |

## Rollback plan

If a later step causes regressions:

1. Revert the last implementation commit only.
2. Keep the previous content generation flow intact.
3. Restore the previous draft renderer behavior if needed.
4. Keep the report-only quality gate enabled so regressions are visible without blocking publish.
5. Avoid changing build_site.py, publish scripts, or deployment-related files during rollback.

## Checkpoint commit plan

Use small commits to keep the work reviewable.

- Checkpoint 1: title and meta optimizer modules + tests
- Checkpoint 2: intent detector + outline builder + tests
- Checkpoint 3: E-E-A-T enhancer + CTA optimizer + tests
- Checkpoint 4: schema + internal-link planner + tests
- Checkpoint 5: orchestrator + quality gate integration + tests

Each checkpoint should include:

- files changed
- tests run
- quality gate result
- whether publish remains safe

## Expected outcome

After implementation, the content engine should produce drafts that are more likely to:

- earn stronger click-through rates
- match search intent more closely
- support better SEO quality
- include stronger affiliate CTA and trust signals
- pass the report-only quality gate at or above 85/100
