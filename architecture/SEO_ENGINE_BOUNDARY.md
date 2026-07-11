# SEO Engine Boundary

The SEO Engine discovers and ranks editorial opportunities. It supports, but does not replace, the five production modules.

## Ownership

- Keyword import, normalization, deduplication, clustering, intent classification, gap analysis, internal-link suggestions, and transparent scoring.
- Offline reports and the local dashboard under `data/seo/`.
- Creating `selected` editorial queue entries only after an explicit operator command.

## Inputs and Evidence

- Manual seeds and operator-provided JSON, CSV, or text files.
- Local pages in `docs/` and drafts in `data/production_article_drafts/`.
- Existing editorial queues for duplicate protection.

External metrics are `verified` only when supplied by an imported source. Missing SERP, volume, competitor, or backlink evidence is `unavailable`; deterministic classifications are `inferred`.

## Prohibited Actions

- No article generation, approval, rejection, publishing, Git operations, deployment, indexing submission, or affiliate-link invention.
- No paid API dependency and no fabricated search volume, rankings, competitors, traffic, or revenue.
- No mutation of scoring thresholds owned by the Publisher or review gates.

## Editorial Contract

`queue-opportunity` and `queue-top` default to dry-run. With `--apply`, new rows use `status: selected`, `source: seo_engine`, and `requires_human_approval: true`. Existing pages and non-create decisions are rejected as duplicates.
