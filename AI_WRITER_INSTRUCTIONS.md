# AI Writer Instructions

Use these instructions for article generation tasks prepared by Menu 1 or Menu 2.

Before writing, load `WRITING_DNA.md`, `STRUCTURE_DNA.md`, `VOICE_DNA.md`, `ARTICLE_FINGERPRINT.md`, `DECISION_ENGINE.md`, `SELF_VALIDATION_ENGINE.md`, `QUALITY_SCORE_ENGINE.md`, and `docs/editorial/UNIVERSAL_EDITORIAL_ENGINE.md`.

## Inputs

Read the task file referenced by `data/codex_tasks/CURRENT_TASK.md`. Then inspect:

- `data/editorial_queue/<date>/topics.json`
- any weekly manifest referenced by `data/editorial_queue/current_week.json`
- topic source packages and research metadata
- existing drafts under `data/production_article_drafts/<slug>/`
- same-root topic history for daily deep dives
- current renderer/review/publish code before assuming output shape

## Selection

Write only topics already present in the prepared queue. Do not replace, invent, or broaden the topic set.

For Menu 1, write every selected foundation root topic that has sufficient valid sources and no hard blocker. The weekly root set is capped at 5. It is valid to write fewer than 5 if fewer than 5 pass source readiness. Do not invent replacement roots.

For Menu 2, write only daily angles derived from the locked Monday weekly root manifest. Every Menu 2 draft must preserve the exact `root_topic_id`, immutable root title, `sequence_number`, and `daily_angle` from the queue. If the queue item has no valid `root_topic_id`, uses a root absent from the weekly manifest, changes the root title, or appears to introduce a new root topic, hold it and report the blocker.

The Monday root set is authoritative for website articles until the next Monday. Tuesday-through-Sunday work must not replace a weak root with a new hot topic. New hot topics belong in watchlist, monitoring, social-only, or human override review; they do not become website root topics automatically. Unconfirmed hot news must remain `SOCIAL_HOT_UNCONFIRMED` or an equivalent social-only state. Officially confirmed news may be handled as `OFFICIAL_NEWS_STANDALONE`, not as a foundation-root replacement.

`SOCIAL_HOT_UNCONFIRMED` is not a website article assignment. If a task uses that lane, write only cautious social monitoring copy from preserved source URLs and discovery timestamps. Do not create `data/production_article_drafts/`, a canonical URL, a Smile AI Review Hub article link, a weekly root, or a next-article bridge.

## Advanced Series Rules

Menu 2 articles under the same root must be genuinely different. Do not write another article if the only change is title wording or a paraphrased outline.

Each same-root article needs a unique:

- daily angle
- primary search intent
- reader question
- thesis
- reader stage
- evidence emphasis
- section architecture
- table purpose
- FAQ set
- CTA intent
- conclusion
- next-article bridge

Use `weekly_article_history`, `reader_question`, `unique_thesis`, `required_evidence`, `prohibited_overlap`, and `next_article_bridge` from the task package as authoritative data. Do not infer missing series data.

For a non-final advanced article, end with a natural bridge to the actual next scheduled same-root angle. If `next_article_bridge.state` is `NEXT_SCHEDULED_NOT_LIVE`, mention the next angle without linking or claiming it is published. If it is `NEXT_LIVE`, link only the verified canonical URL. If it is `SERIES_COMPLETE`, `SERIES_PAUSED`, or `NEXT_UNKNOWN`, do not fabricate a successor.

## Draft Requirements

Every draft must include:

- title
- slug
- search intent
- outline
- body
- source URLs
- claim/source mapping where available
- warnings
- hard blockers
- publishing confidence
- review status
- internal link suggestions
- entity coverage notes

Use the existing workflow to save drafts under `data/production_article_drafts/<slug>/` and update the dashboard queues.

Before reporting completion, run the self-validation checklist and assign a quality score using `QUALITY_SCORE_ENGINE.md`.

## Public Writing Rules

- Natural English unless the topic is explicitly Vietnamese.
- No Vietnamese mojibake.
- No workflow markers in public HTML.
- No unsupported factual claims.
- No fabricated pricing or feature claims.
- No duplicate paragraphs or headings.
- No thin sections.
- No generic AI-style filler.
- No automatic approval, publishing, pushing, deployment, or indexing.

## Stop Conditions

Hold the topic instead of writing if:

- usable sources are zero
- sources are about a different entity
- topic collides with a live, queued, archived, or drafted slug
- required research package is missing
- no trustworthy source supports the core claim
- renderer or validation fails in a way that could leak broken public output
