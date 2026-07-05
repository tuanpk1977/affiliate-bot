from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .config import WorkerBotConfig
from .data_loader import TopicCandidate
from .duplicate_checker import DuplicateChecker


def select_topics(
    candidates: list[TopicCandidate],
    config: WorkerBotConfig,
    checker: DuplicateChecker,
    limit: int | None = None,
    force_one_test: bool = False,
) -> tuple[list[TopicCandidate], list[dict[str, Any]]]:
    selected: list[TopicCandidate] = []
    rejected: list[dict[str, Any]] = []
    selected_topic_names: list[str] = []
    max_topics = limit or config.topics_per_day

    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        if len(selected) >= max_topics:
            rejected.append({"topic": candidate.topic, "slug": candidate.slug, "reason": "over daily limit"})
            continue
        if candidate.score < config.minimum_score:
            rejected.append({"topic": candidate.topic, "slug": candidate.slug, "reason": "below minimum score"})
            continue
        duplicate = checker.check(candidate, selected_topic_names)
        if duplicate.is_duplicate:
            rejected.append(
                {
                    "topic": candidate.topic,
                    "slug": candidate.slug,
                    "reason": duplicate.reason,
                    "matched": duplicate.matched,
                    "similarity": round(duplicate.similarity, 3),
                }
            )
            continue
        selected.append(candidate)
        selected_topic_names.append(candidate.topic)

    if force_one_test and not selected and candidates:
        forced = sorted(candidates, key=lambda item: item.score, reverse=True)[0]
        selected.append(forced)
        rejected = [
            item
            for item in rejected
            if item.get("slug") != forced.slug
        ]
        rejected.append(
            {
                "topic": forced.topic,
                "slug": forced.slug,
                "reason": "force-one-test selected this duplicate candidate for draft smoke test only",
                "score": forced.score,
            }
        )

    return selected, rejected


def topic_to_json(candidate: TopicCandidate) -> dict[str, Any]:
    payload = asdict(candidate)
    payload["raw"] = candidate.raw
    return payload
