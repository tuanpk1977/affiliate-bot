# Self Validation Engine

Every AI writer must review its own output before reporting completion.

## SEO Validation

- title present
- H1 present
- meta description planned or present
- canonical planned or present
- primary keyword used naturally
- slug lowercase and stable

## EEAT Validation

- methodology exists
- source limits are disclosed
- unsupported claims are caveated or removed
- affiliate disclosure exists
- practical buyer checks are present

## HTML Validation

- no broken tags in generated HTML
- no workflow markers in public sections
- no local paths exposed
- no raw debug JSON
- tables are readable

## CTA Validation

- CTA is editorial, not manipulative
- CTA points to full review, official verification, or checklist
- no fake affiliate destination

## FAQ Validation

- at least three useful questions when FAQ exists
- answers do not duplicate main sections word-for-word
- FAQ schema can be generated from visible FAQ

## Style Validation

- no forbidden phrases
- no duplicate paragraphs
- no duplicate headings
- no repetitive conclusions
- paragraph rhythm matches `ARTICLE_FINGERPRINT.md`

## Hallucination Detection

Reject or revise when a claim cannot be traced to a prepared source or common safe operational advice.

## Fingerprint Matching

Compare article structure to `ARTICLE_FINGERPRINT.md`. If major sections are missing, revise before saving.
