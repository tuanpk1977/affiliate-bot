# Public Content Hub and Trust Layer

## Status

This document describes source support added for the Smile AI Review Hub public
content hub. The source changes have not rebuilt, published, deployed, or indexed
production output.

Smile AI Review Hub remains the only production-enabled site. The example health,
sports, and consumer-goods profiles remain inactive, use `.invalid` domains, keep
production disabled, and have empty affiliate catalogs.

## Homepage

`modules/site_builder.py` builds the homepage from two local inputs:

1. existing builder page records; and
2. HTML under `data/published_static_pages/<slug>/index.html`.

`modules/public_content_hub.py` normalizes and deduplicates those records by
canonical URL. It classifies local published content and renders non-empty sections:

- Featured Reviews
- Best AI Tools
- Latest Comparisons
- Practical Tutorials
- Buying Guides
- Recently Published

Category navigation is shown only when the published records contain a matching
category. No draft, review-dashboard, or queue record is treated as published
content.

## Trust Pages

The source renderer supports these public routes:

- `/about/`
- `/editorial-policy/`
- `/how-we-review/`
- `/affiliate-disclosure/`
- `/contact/`
- `/privacy-policy/`
- `/terms/`

`/how-we-review-tools/` remains as a legacy route and points readers to the current
methodology. Trust copy distinguishes hands-on checks, source-based research,
official documentation review, and pricing or feature verification. It does not
claim that every product was bought or tested.

Contact remains static and uses the existing configured public email when present.
No contact API, database, Gmail account, paid service, or new secret is required.

## Internal Linking

`resolve_related_content()` is a deterministic, read-only resolver. It:

- accepts published content records only;
- excludes the current canonical URL;
- deduplicates targets;
- scores topic and category overlap;
- limits output to five links; and
- never inserts affiliate links or changes canonical URLs.

`page_shell()` exposes an opt-in `related_candidates` argument. Existing callers
remain unchanged unless they explicitly provide published candidates. This avoids
a bulk rewrite of historical production HTML.

## Metadata and Structured Data

`modules/public_page_metadata.py` provides:

- canonical-preserving Open Graph metadata;
- `og:url` and `og:site_name`;
- Twitter title, description, card, and optional image metadata;
- image omission when the referenced local asset does not exist;
- homepage `WebSite` and `Organization` JSON-LD;
- article `Article` and `BreadcrumbList` JSON-LD; and
- explicit FAQ JSON-LD only when visible question-and-answer data is supplied.

The helpers do not generate ratings, prices, credentials, or unverifiable review
claims.

## Content Health Report

Run:

```powershell
python scripts/report_content_health.py
python scripts/report_content_health.py --json
```

Optional arguments:

```powershell
python scripts/report_content_health.py --root site_output --sitemap site_output/sitemap.xml
python scripts/report_content_health.py --strict
```

The report reads local static HTML and sitemap data. It reports metadata, structured
data, local internal-link, related-content, duplicate-title, thin-content, trust-page,
homepage-section, and sitemap-membership findings. It does not call the network,
Analytics, Search Console, an LLM, or a paid API. Sitemap membership is not presented
as proof of Google indexing.

## Workflow Boundaries

This source upgrade does not modify:

- Menu 1, 2, 4, 8, F, or G;
- editorial queues or article state;
- approval or publishing gates;
- social drafting or review;
- Cloudflare or GitHub deployment;
- canonical authority; or
- indexing behavior.

Blogger and social channels remain distribution channels. The canonical source
remains `https://smileaireviewhub.com/`.

## Deployment State

No production build has been run for this work. Generated copies in `docs/`,
`site_output/`, dashboards, queues, reports, and article output must not be staged
as part of this source checkpoint. A later controlled build checkpoint is required
before these source changes can appear on the live site.
