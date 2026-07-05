from __future__ import annotations

import json

from .data_loader import TopicCandidate
from .utils import clean_words


def _title_case(value: str) -> str:
    return " ".join(word.upper() if word.lower() in {"ai", "seo", "saas"} else word.capitalize() for word in value.split())


def generate_youtube_package(candidate: TopicCandidate) -> dict[str, str]:
    topic = candidate.topic
    display_topic = _title_case(topic)
    title = clean_words(f"{display_topic} Review: Features, Pricing, Pros and Cons", 95)
    chapters = "\n".join(
        [
            "00:00 Intro",
            "00:20 What the tool does",
            "00:55 Feature checklist",
            "01:35 Pricing notes",
            "02:10 Pros and cons",
            "02:45 Alternatives",
            "03:20 Final verdict",
        ]
    )
    description = f"""In this draft video package, we review {display_topic} from a practical buyer perspective.

We cover what it does, who it is best for, pricing checks, pros and cons, alternatives, and what to verify before buying.

Read full reviews and comparisons:
https://smileaireviewhub.com

Note: verify current pricing and plan limits on the official website before buying.
"""
    tags = ", ".join(
        [
            topic.lower(),
            f"{topic.lower()} review",
            "ai tools",
            "saas review",
            "software comparison",
            "pricing",
            "alternatives",
        ]
    )
    script = f"""Hook: If you are researching {display_topic}, do not start with the hype. Start with the workflow.

Section 1: What it does.
{display_topic} should be evaluated by the job it helps you finish, the time it saves, and the business risk it reduces.

Section 2: Feature checklist.
Check the core workflow, pricing limits, integrations, collaboration controls, export options, and support.

Section 3: Pricing.
Always verify current pricing on the official website. SaaS plans, usage limits, and trials change often.

Section 4: Pros and cons.
The main upside is practical workflow improvement. The main risk is buying based on outdated claims or screenshots.

Section 5: Alternatives.
Compare at least three tools before choosing. Look for lower-cost, enterprise, beginner-friendly, and integration-focused options.

Final CTA:
Read the full review on Smile AI Review Hub at smileaireviewhub.com.
"""
    outline = {
        "topic": display_topic,
        "style": "draft review video",
        "duration_seconds": 45,
        "scenes": [
            {"title": "Intro", "visual": "brand title card", "voiceover": f"Researching {display_topic}? Start with workflow fit."},
            {"title": "Feature checklist", "visual": "checklist slide", "voiceover": "Check features, integrations, pricing limits, and support."},
            {"title": "Pricing", "visual": "pricing verification card", "voiceover": "Verify current pricing on the official website."},
            {"title": "Pros and cons", "visual": "two-column table", "voiceover": "Compare upside, limits, and switching risk."},
            {"title": "Verdict", "visual": "CTA card", "voiceover": "Read the full review on Smile AI Review Hub."},
        ],
    }
    return {
        "youtube-title.txt": title,
        "youtube-description.txt": description,
        "youtube-tags.txt": tags,
        "youtube-chapters.txt": chapters,
        "thumbnail-prompt.txt": f"Clean YouTube thumbnail for {display_topic}, bold readable text, SaaS dashboard style, teal and white, no vendor logo.",
        "thumbnail-text.txt": clean_words(display_topic, 35),
        "shorts-title.txt": clean_words(f"Should you try {display_topic}?", 70),
        "shorts-description.txt": f"Quick buyer checklist for {display_topic}. Full review draft prepared for Smile AI Review Hub.",
        "video-script.txt": script,
        "video-outline.json": json.dumps(outline, ensure_ascii=False, indent=2) + "\n",
    }
