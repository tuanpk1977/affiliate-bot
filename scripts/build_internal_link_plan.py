from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.performance_tracking import DATA_DIR, build_content_lifecycle, numeric, write_csv


FIELDS = ["source_slug", "source_url", "target_slug", "target_url", "anchor_text", "buyer_journey_stage", "affiliate_intent", "reason", "score"]


def tokens(slug: str) -> set[str]:
    stop = {"review", "reviews", "2026", "best", "ai", "software", "tool", "tools"}
    return {part for part in str(slug).split("-") if part and part not in stop}


def buyer_stage(source: dict[str, object], target: dict[str, object]) -> str:
    text = f"{source.get('slug')} {target.get('slug')}".lower()
    if "pricing" in text:
        return "pricing validation"
    if "alternative" in text or "vs" in text or "compare" in text:
        return "comparison"
    if "review" in text:
        return "review consideration"
    return "topic discovery"


def affiliate_intent(target: dict[str, object]) -> str:
    text = f"{target.get('slug')} {target.get('topic')}".lower()
    if any(term in text for term in ("pricing", "review", "alternative", "vs", "best")):
        return "high"
    return "medium"


def build_plan() -> list[dict[str, object]]:
    lifecycle = build_content_lifecycle()
    candidates: dict[str, list[dict[str, object]]] = defaultdict(list)
    for source in lifecycle:
        source_tokens = tokens(str(source.get("slug", "")))
        for target in lifecycle:
            if source.get("slug") == target.get("slug"):
                continue
            target_tokens = tokens(str(target.get("slug", "")))
            overlap = source_tokens & target_tokens
            if not overlap:
                continue
            intent_bonus = 15 if affiliate_intent(target) == "high" else 5
            score = len(overlap) * 20 + intent_bonus + min(20, numeric(target.get("google_clicks")) / 5)
            candidates[str(source.get("slug"))].append(
                {
                    "source_slug": source.get("slug", ""),
                    "source_url": source.get("article_url", ""),
                    "target_slug": target.get("slug", ""),
                    "target_url": target.get("article_url", ""),
                    "anchor_text": target.get("topic", ""),
                    "buyer_journey_stage": buyer_stage(source, target),
                    "affiliate_intent": affiliate_intent(target),
                    "reason": f"Topic similarity: {', '.join(sorted(overlap))}",
                    "score": round(score, 1),
                }
            )
    rows: list[dict[str, object]] = []
    for source_slug, links in candidates.items():
        selected = sorted(links, key=lambda row: numeric(row.get("score")), reverse=True)[:10]
        rows.extend(selected[: max(5, min(10, len(selected)))])
    return sorted(rows, key=lambda row: (str(row.get("source_slug")), -numeric(row.get("score"))))


def main() -> int:
    rows = build_plan()
    write_csv(DATA_DIR / "internal_link_plan.csv", rows, FIELDS)
    print(f"Internal link plan rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
