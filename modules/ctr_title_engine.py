from __future__ import annotations

from typing import Any

from modules.performance_tracking import DATA_DIR, numeric, slugify, update_master_workbook, write_csv, write_json


TITLE_TEST_FIELDS = [
    "topic",
    "slug",
    "variant_type",
    "title",
    "predicted_ctr_score",
    "reason",
]


def _clean_topic(topic: str) -> str:
    return " ".join(str(topic or "").split())


def _score_title(title: str, variant_type: str) -> int:
    score = 55
    lowered = title.lower()
    if "2026" in lowered:
        score += 8
    if any(term in lowered for term in ("review", "pricing", "alternatives", " vs ", "best")):
        score += 10
    if variant_type in {"buyer_intent", "comparison"}:
        score += 8
    if 40 <= len(title) <= 60:
        score += 10
    elif len(title) > 70:
        score -= 12
    return max(0, min(100, score))


def generate_title_variants(topic: str, slug: str = "", article_type: str = "") -> list[dict[str, Any]]:
    topic = _clean_topic(topic)
    slug = slugify(slug or topic)
    base = topic.rstrip(" .")
    variants = [
        ("seo_safe", f"{base}: Practical 2026 Guide"),
        ("curiosity", f"Is {base} Worth It in 2026?"),
        ("comparison", f"{base} vs Alternatives: Which Should You Choose?"),
        ("buyer_intent", f"{base} Pricing, Pros, Cons and Best Use Cases"),
        ("youtube", f"{base} Review 2026 | What Buyers Should Know"),
    ]
    rows: list[dict[str, Any]] = []
    for variant_type, title in variants:
        rows.append(
            {
                "topic": topic,
                "slug": slug,
                "variant_type": variant_type,
                "title": title,
                "predicted_ctr_score": _score_title(title, variant_type),
                "reason": f"{variant_type} variant for {article_type or 'content'} intent.",
            }
        )
    return rows


def build_title_tests(selected_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for selected in selected_rows:
        rows.extend(
            generate_title_variants(
                str(selected.get("topic", "")),
                str(selected.get("slug", "")),
                str(selected.get("article_type", "")),
            )
        )
    return sorted(rows, key=lambda row: (str(row.get("slug", "")), -numeric(row.get("predicted_ctr_score"))))


def write_title_tests(selected_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = build_title_tests(selected_rows)
    write_csv(DATA_DIR / "title_tests.csv", rows, TITLE_TEST_FIELDS)
    write_json(DATA_DIR / "title_tests.json", rows)
    update_master_workbook({"CTR Title Tests": (rows, TITLE_TEST_FIELDS)})
    return {"title_tests": len(rows)}
