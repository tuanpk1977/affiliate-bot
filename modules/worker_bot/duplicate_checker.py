from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import WorkerBotConfig
from .data_loader import TopicCandidate, load_topic_history
from .utils import jaccard_similarity, normalize_topic, slugify


@dataclass(frozen=True)
class DuplicateResult:
    is_duplicate: bool
    reason: str
    matched: str = ""
    similarity: float = 0.0


class DuplicateChecker:
    def __init__(self, config: WorkerBotConfig) -> None:
        self.config = config
        self.existing_slugs: set[str] = set()
        self.existing_topics: list[str] = []
        self._load_existing_articles()
        self._load_existing_videos()
        self._load_topic_history()

    def _add_slug(self, value: str) -> None:
        slug = slugify(value)
        if slug:
            self.existing_slugs.add(slug)
            self.existing_topics.append(slug.replace("-", " "))

    def _load_existing_articles(self) -> None:
        for root in self.config.existing_article_roots:
            if not root.exists():
                continue
            for index_file in root.rglob("index.html"):
                rel = index_file.parent.relative_to(root)
                if str(rel) not in (".", ""):
                    self._add_slug(rel.as_posix().split("/")[-1])
            for html_file in root.glob("*.html"):
                if html_file.name.lower() != "index.html":
                    self._add_slug(html_file.stem)

    def _load_existing_videos(self) -> None:
        root = self.config.existing_video_root
        if not root.exists():
            return
        for child in root.iterdir():
            if child.is_dir():
                self._add_slug(child.name)

    def _load_topic_history(self) -> None:
        for row in load_topic_history(self.config):
            status = " ".join(str(row.get(key, "")) for key in ("status", "content_decision", "article_url")).lower()
            if "publish" in status or "http" in status:
                self._add_slug(row.get("slug") or row.get("topic") or "")

    def check(self, candidate: TopicCandidate, selected_topics: list[str] | None = None) -> DuplicateResult:
        if candidate.slug in self.existing_slugs:
            return DuplicateResult(True, "slug already exists in articles, videos, or published history", candidate.slug, 1.0)

        topic_norm = normalize_topic(candidate.topic)
        for existing in self.existing_topics:
            similarity = jaccard_similarity(topic_norm, existing)
            if similarity >= self.config.maximum_similarity:
                return DuplicateResult(True, "very similar to existing content", existing, similarity)

        for selected in selected_topics or []:
            similarity = jaccard_similarity(candidate.topic, selected)
            if similarity >= self.config.maximum_similarity:
                return DuplicateResult(True, "very similar to another selected topic", selected, similarity)

        return DuplicateResult(False, "unique enough")
