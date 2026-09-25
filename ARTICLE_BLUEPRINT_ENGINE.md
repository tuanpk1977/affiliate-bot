# Article Blueprint Engine

Use this file to convert a prepared topic into a publishable article draft.

For exact structure, measurable fingerprint, and decision trees, also load `STRUCTURE_DNA.md`, `ARTICLE_FINGERPRINT.md`, and `DECISION_ENGINE.md`.

## Required Input Fields

- `title`
- `slug`
- `search_intent`
- `primary_keyword`
- `sources` or `usable_sources`
- `daily_angle` when present
- `root_topic_id` when present
- competitor/entity/source metadata when available

## Article Flow

1. H1/title
2. short buyer-focused introduction
3. affiliate disclosure
4. byline/editorial review note
5. quick verdict
6. methodology or how we evaluated
7. shortlist or key options when appropriate
8. comparison table when multiple tools are discussed
9. product/workflow sections
10. pricing considerations
11. pros and cons
12. alternatives
13. common mistakes
14. FAQ
15. final recommendation
16. disclosure/footer

## Output Contract

Use the repository workflow to create:

- `data/production_article_drafts/<slug>/article.md`
- `data/production_article_drafts/<slug>/index.html`
- review metadata consumed by `data/content_review_queue.json`
- human approval queue entry
- publish queue entry
- dashboard preview for Menu 4

Do not create public `docs/<slug>/index.html` unless the publish workflow is explicitly running.

## Quality Target

A reviewable draft may have warnings. It must not have hard blockers. Hard blockers prevent review or publishing; warnings must be visible to the human editor.
