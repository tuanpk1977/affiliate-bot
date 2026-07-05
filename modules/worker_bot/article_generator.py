from __future__ import annotations

import json
from typing import Any

from .data_loader import TopicCandidate
from .utils import BASE_URL, clean_words


def _title_case(value: str) -> str:
    return " ".join(word.upper() if word.lower() in {"ai", "seo", "saas"} else word.capitalize() for word in value.split())


def _category(topic: str) -> str:
    lowered = topic.lower()
    if "seo" in lowered:
        return "SEO Tools"
    if "video" in lowered:
        return "Video AI"
    if "design" in lowered or "image" in lowered:
        return "Design AI"
    if "coding" in lowered or "engineering" in lowered:
        return "AI Coding"
    if "automation" in lowered or "meeting" in lowered:
        return "Automation"
    return "AI Software"


def article_metadata(candidate: TopicCandidate) -> dict[str, Any]:
    topic = candidate.topic
    display_topic = _title_case(topic)
    title = f"{display_topic} Review 2026"
    category = _category(topic)
    keywords = [topic.lower(), f"{topic.lower()} review", f"{topic.lower()} pricing", f"{topic.lower()} alternatives"]
    return {
        "seo_title": title,
        "slug": candidate.slug,
        "url": f"{BASE_URL}/{candidate.slug}/",
        "meta_description": clean_words(
            f"Independent {topic} review with features, pricing checks, pros, cons, alternatives, and practical buyer fit.",
            154,
        ),
        "keywords": keywords,
        "category": category,
        "tags": sorted({category, "AI tools", "SaaS review", "Buyer guide"}),
    }


def _schemas(meta: dict[str, Any], topic: str) -> tuple[dict[str, Any], dict[str, Any]]:
    article_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": meta["seo_title"],
        "description": meta["meta_description"],
        "author": {"@type": "Person", "name": "Tuan Nguyen Quoc"},
        "publisher": {"@type": "Organization", "name": "Smile AI Review Hub"},
        "mainEntityOfPage": meta["url"],
        "dateModified": "2026-06-25T08:00:00+07:00",
    }
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f"What is {topic} best for?",
                "acceptedAnswer": {"@type": "Answer", "text": f"{topic} is best evaluated for workflow fit, pricing clarity, and implementation risk."},
            },
            {
                "@type": "Question",
                "name": f"How should buyers verify {topic} pricing?",
                "acceptedAnswer": {"@type": "Answer", "text": "Check the official website before buying because SaaS plans, limits, and promotions change frequently."},
            },
        ],
    }
    return article_schema, faq_schema


def generate_article(candidate: TopicCandidate, internal_links: list[str]) -> tuple[str, dict[str, Any], str]:
    meta = article_metadata(candidate)
    topic = candidate.topic
    display_topic = _title_case(topic)
    official_hint = "Official website: add the product URL here after Codex verifies the correct destination. Use /go/ tracking only after affiliate approval."
    article_schema, faq_schema = _schemas(meta, topic)
    image_prompts = "\n".join(
        [
            f"Hero image: editorial SaaS dashboard mockup for {display_topic}, teal top bar, clean comparison cards, no vendor logo.",
            f"Pricing image: realistic pricing verification checklist for {display_topic}, plan limits, billing terms, trial checks.",
            f"Comparison image: {display_topic} versus alternatives with columns for features, pricing, best use case, and risk.",
        ]
    )
    related_links = "\n".join(f"- {link}" for link in internal_links) if internal_links else "- Add related review and comparison links during Codex review."
    article = f"""---
title: "{meta['seo_title']}"
slug: "{meta['slug']}"
description: "{meta['meta_description']}"
category: "{meta['category']}"
tags: {json.dumps(meta['tags'])}
keywords: {json.dumps(meta['keywords'])}
status: draft_for_codex_review
last_updated: "June 2026"
author: "Nguyen Quoc Tuan"
---

# {meta['seo_title']}

> Draft prepared by the Content Assistant Bot. Codex should fact-check product details, add official screenshots, verify pricing, and improve final editorial judgment before publishing.

## Watch the Video Review

YouTube embed placeholder. Add the final YouTube URL after upload. Keep this section near the top of the article, matching the existing Smile AI Review Hub review layout.

## Affiliate Disclosure

Some links may become affiliate links after editorial review. Smile AI Review Hub may earn a commission at no extra cost to readers. This does not change the evaluation method.

## Table of Contents

- Quick Verdict
- Official Website
- Overview
- How We Evaluated
- Key Features
- Pricing
- Pros and Cons
- Best Use Cases
- Not Best For
- Alternatives
- Implementation Checklist
- Final Verdict
- FAQ
- Author Note

## Quick Verdict

{display_topic} is worth considering if it solves a clear workflow, has pricing that matches your budget, and can be tested without major switching costs. The best buyers should verify the official website, compare alternatives, and avoid choosing any tool based only on hype.

## Official Website

{official_hint}

## Overview

{display_topic} should be reviewed as a practical business tool, not just as a trending keyword. A useful review needs to answer whether the software improves a measurable workflow, reduces manual effort, or helps a buyer make a better decision.

For most AI and SaaS tools, the buying decision depends on five questions: what job the tool completes, how fast a user can get value, what limits appear on lower plans, how well it integrates with the existing stack, and whether support is strong enough for long-term use.

## How We Evaluated {display_topic}

This draft uses a buyer-focused evaluation framework:

| Evaluation Area | What to Verify | Why It Matters |
|---|---|---|
| Workflow fit | Does {display_topic} solve a real day-to-day problem? | Tools that do not save time are hard to justify. |
| Pricing clarity | Are plan limits, trials, and billing rules clear? | Hidden limits can change the total cost. |
| Integrations | Does it connect with the buyer's current stack? | Integration gaps create manual work. |
| Team use | Are roles, seats, and collaboration controls available? | Solo tools may not scale to teams. |
| Export and lock-in | Can users export important data? | Buyers should avoid unnecessary lock-in. |
| Support | Are docs, support channels, and onboarding clear? | Support affects implementation speed. |

## Key Features to Check

The published version should explain the exact features after hands-on review or official documentation checks. For now, Codex should verify:

- Core workflow and primary use case.
- Setup process and learning curve.
- Collaboration, roles, and permissions.
- Reporting, analytics, or output quality.
- Export options and data portability.
- Security, privacy, and account management.
- Integration with popular tools in the same category.

## Pricing

Do not rely on old pricing screenshots or outdated summaries. Before publishing this review, verify current pricing on the official website. Check plan limits, free trial availability, billing cycle, usage caps, refund terms, and whether important features require higher-tier plans.

Suggested safe wording: "Verify current pricing on the official website." This keeps the article accurate even if the vendor changes pricing later.

## Pros and Cons

| Pros | Cons |
|---|---|
| Useful if it solves a specific workflow. | Needs current pricing verification. |
| Good candidate for a practical review article and YouTube explainer. | Vendor claims must be fact-checked. |
| Can be compared against alternatives for buyer fit. | Screenshots and hands-on notes should be added before publishing. |
| May support commercial search intent. | Affiliate availability must be confirmed. |

## Best Use Cases

{display_topic} is most useful for buyers who know the workflow they want to improve. It may be a good fit for small teams, creators, marketers, founders, or operators who need a practical software decision rather than a broad list of generic tools.

## Not Best For

This tool may not be the best fit if the buyer needs a free-only solution, requires official enterprise procurement support, or cannot verify whether the software fits the current workflow.

## Alternatives

Compare {display_topic} with at least three alternatives before making a recommendation. The alternatives section should explain which option is better for beginners, lower budgets, enterprise workflows, integrations, and specific use cases.

| Alternative Angle | What to Compare |
|---|---|
| Lower-cost option | Price, trial rules, and feature limits. |
| Enterprise option | Security, roles, support, and procurement. |
| Beginner option | Setup time and ease of use. |
| Integration-first option | Native integrations and API support. |

## Implementation Checklist

Before recommending {display_topic}, verify:

- Official URL and pricing page.
- Current plan limits and free trial rules.
- Product screenshots or official UI references.
- Main competitors.
- Affiliate program availability.
- Internal links to related reviews and comparisons.
- YouTube video embed after upload.

## Internal Link Suggestions

{related_links}

## Image Prompts

{image_prompts}

## Final Verdict

{display_topic} is a promising review topic, but the published version should include current product details, official URL, screenshots, pricing verification, and stronger editorial judgment. Codex should refine this draft into a specific buyer-focused article before it goes live.

## FAQ

### Is {display_topic} worth it in 2026?

It may be worth it if it solves a specific workflow and the current pricing fits your budget. Verify plan limits and alternatives before buying.

### Does {display_topic} have a free trial?

Check the official website for the latest free trial or free plan details. Trial rules can change quickly.

### Who should use {topic}?

The best users are teams or individuals with a clear workflow problem, a realistic budget, and time to test the tool before fully switching.

### What should I compare before buying?

Compare pricing, integrations, collaboration features, export options, support, and workflow fit.

### What is the biggest risk?

The biggest risk is choosing a tool based on hype or outdated pricing instead of hands-on workflow fit.

## Author Note

Written for Smile AI Review Hub by Nguyen Quoc Tuan. Final publication should include a last updated date, affiliate disclosure, verified product links, and related internal links.

```json
{json.dumps(article_schema, ensure_ascii=False, indent=2)}
```

```json
{json.dumps(faq_schema, ensure_ascii=False, indent=2)}
```
"""
    return article, meta, image_prompts
