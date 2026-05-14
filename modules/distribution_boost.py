from __future__ import annotations

import json
import re
from pathlib import Path

from config import settings


def generate_distribution_boost(title: str, article_url: str, content: str = "") -> dict[str, object]:
    topic = clean_title(title)
    excerpt = clean_excerpt(content, topic)
    return {
        "reddit_summary": reddit_summary(topic, article_url, excerpt),
        "medium_summary": medium_summary(topic, article_url, excerpt),
        "linkedin_article_snippet": linkedin_snippet(topic, article_url, excerpt),
        "faq_schema_suggestions": faq_suggestions(topic),
        "internal_link_suggestions": internal_link_suggestions(topic),
        "ai_overview_snippets": ai_overview_snippets(topic, excerpt),
    }


def save_distribution_boost(slug: str, title: str, article_url: str, content: str = "") -> Path:
    output_dir = settings.base_dir / "draft_output" / "distribution_boost"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{slug}.json"
    path.write_text(json.dumps(generate_distribution_boost(title, article_url, content), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def reddit_summary(topic: str, article_url: str, excerpt: str) -> str:
    return (
        f"I put together a practical research note on {topic}. "
        f"The main angle is workflow fit, pricing risk, and whether the tool is worth evaluating before buying. "
        f"Short takeaway: {excerpt}\n\n"
        f"Full note: {article_url}\n\n"
        "Disclosure: the page may contain affiliate links."
    )


def medium_summary(topic: str, article_url: str, excerpt: str) -> str:
    return (
        f"# {topic}: practical research notes\n\n"
        f"When evaluating {topic}, the useful question is not only what the product claims to do, but whether it fits a real workflow. "
        f"{excerpt}\n\n"
        f"Read the full version here: {article_url}\n\n"
        "Affiliate disclosure: some links may be affiliate links."
    )


def linkedin_snippet(topic: str, article_url: str, excerpt: str) -> str:
    return (
        f"{topic}\n\n"
        "For SaaS buyers and affiliate publishers, the safest review angle is research-first: use case, alternatives, switching cost, and pricing clarity.\n\n"
        f"Key note: {excerpt}\n\n"
        f"Full research page: {article_url}"
    )


def faq_suggestions(topic: str) -> list[str]:
    return [
        f"Is {topic} worth it for beginners?",
        f"What should buyers check before paying for {topic}?",
        f"What are the best alternatives to {topic}?",
        f"Does {topic} fit solo users or teams better?",
        f"How should affiliate publishers mention {topic} safely?",
    ]


def internal_link_suggestions(topic: str) -> list[str]:
    slug = slugify(topic)
    parts = [part for part in slug.split("-") if part not in {"review", "pricing", "vs", "best"}]
    base = "-".join(parts[:2]) if parts else slug
    return [
        f"/review/{base}/",
        f"/pricing/{base}/",
        "/category/ai-coding-tools/" if "coding" in slug or "cursor" in slug or "copilot" in slug else "/categories/",
        "/comparisons/",
    ]


def ai_overview_snippets(topic: str, excerpt: str) -> list[str]:
    return [
        f"{topic} is best evaluated by workflow fit, pricing clarity, alternatives, and real buyer constraints.",
        f"A safe recommendation for {topic} should mention who should use it, who should avoid it, and what to verify on the official website.",
        excerpt,
    ]


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", str(title or "AI tool review")).strip()


def clean_excerpt(content: str, fallback: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(content or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return f"{fallback} should be reviewed by use case, alternatives, and pricing risk."
    return text[:220].rstrip() + ("..." if len(text) > 220 else "")


def slugify(text: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "page"
