from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .utils import PublishedArticle


@dataclass
class PublishResult:
    platform: str
    status: str
    url: str
    success: bool = False
    error: str = ""
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class SocialPublisher(Protocol):
    platform: str

    def validate(self) -> PublishResult:
        ...

    def preview(self, article: PublishedArticle) -> dict[str, Any]:
        ...

    def publish(self, article: PublishedArticle) -> PublishResult:
        ...


class BasePublisher:
    platform = "base"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    def validate(self) -> PublishResult:
        if not self.enabled():
            return PublishResult(platform=self.platform, status="disabled", url="", error="platform disabled")
        return PublishResult(platform=self.platform, status="ready", url="", success=True)

    def _hashtags(self, article: PublishedArticle, limit: int = 5) -> list[str]:
        return [f"#{tag.replace(' ', '')}" for tag in article.tags[:limit]]

    def _key_points(self, article: PublishedArticle, limit: int = 5) -> list[str]:
        points = list(article.key_points or article.headings or [])
        if not points and article.description:
            points = [article.description]
        return points[:limit]

    def _long_excerpt(self, article: PublishedArticle) -> str:
        source = article.summary or article.description
        if not source:
            source = "This guide compares practical fit, pricing considerations, trade-offs, and implementation notes."
        words = source.split()
        excerpt_words = words[: max(80, min(220, int(len(words) * 0.45)))]
        excerpt = " ".join(excerpt_words).strip()
        points = self._key_points(article, 4)
        point_lines = "\n".join(f"- {point}" for point in points)
        disclosure = f"\n\nDisclosure: {article.affiliate_disclosure}" if article.affiliate_disclosure else ""
        return (
            f"{excerpt}\n\n"
            f"Key sections:\n{point_lines}\n\n"
            f"Read the full original guide: {article.url}\n"
            f"Canonical URL for republishing: {article.canonical_url or article.url}"
            f"{disclosure}"
        )

    def _post_text(self, article: PublishedArticle) -> tuple[str, str]:
        points = self._key_points(article, 5)
        hashtags = " ".join(self._hashtags(article, 5))
        url = article.url
        if self.platform == "facebook":
            lines = [
                f"{article.title}",
                "",
                "A practical guide for teams comparing AI tools before they commit budget or workflow time.",
                "",
                "Key points:",
                *[f"- {point}" for point in points[:5]],
                "",
                f"Read the full guide: {url}",
                hashtags,
            ]
            return "\n".join(line for line in lines if line != ""), "Read the full guide"
        if self.platform == "linkedin":
            lines = [
                f"{article.title}",
                "",
                "For small teams, the right AI tool decision usually comes down to workflow fit, risk, and total operating cost.",
                "",
                "Useful checks from the guide:",
                *[f"- {point}" for point in points[:5]],
                "",
                f"Full breakdown: {url}",
                hashtags,
            ]
            return "\n".join(line for line in lines if line != ""), "Read the full breakdown"
        if self.platform == "twitter":
            insight = points[0] if points else article.description
            text = f"{insight}\n\nFull guide: {url}"
            tags = " ".join(self._hashtags(article, 2))
            if len(f"{text}\n{tags}") <= 280:
                text = f"{text}\n{tags}"
            return text[:280], "Read the guide"
        if self.platform in {"bluesky", "threads"}:
            insight = points[0] if points else article.description
            text = f"{article.title}\n\n{insight}\n\n{url}"
            tags = " ".join(self._hashtags(article, 2))
            return f"{text}\n{tags}".strip(), "Read the guide"
        if self.platform == "telegram":
            text = f"{article.title}\n\n{article.description}\n\n{url}"
            if article.image:
                text = f"{text}\n\nImage: {article.image}"
            return text, "Open the guide"
        if self.platform in {"devto", "medium", "hashnode", "blogger"}:
            return self._long_excerpt(article), "Read the full original guide"
        post_text = f"{article.title}\n\n{article.description}\n\nRead the full guide: {url}"
        if hashtags:
            post_text = f"{post_text}\n\n{hashtags}"
        return post_text, "Read the full guide"

    def preview(self, article: PublishedArticle) -> dict[str, Any]:
        hashtags = self._hashtags(article, 5)
        post_text, cta = self._post_text(article)
        return {
            "platform": self.platform,
            "title": article.og_title or article.title,
            "post_text": post_text,
            "description": article.og_description or article.description,
            "cta": cta,
            "image": article.og_image or article.image,
            "image_url": article.og_image or article.image,
            "url": article.url,
            "canonical_url": article.canonical_url or article.url,
            "tags": article.tags,
            "hashtags": hashtags,
            "affiliate_disclosure": article.affiliate_disclosure,
            "headings": article.headings or [],
            "key_points": article.key_points or [],
            "publish_date": article.publish_date,
            "character_count": len(post_text),
        }

    def publish(self, article: PublishedArticle) -> PublishResult:
        validation = self.validate()
        if not validation.success:
            return validation
        payload = self.preview(article)
        return PublishResult(
            platform=self.platform,
            status="prepared_manual",
            url=article.url,
            success=False,
            error="Manual publishing required. Copy the prepared content, publish on the platform, then confirm the result.",
            metadata=payload,
        )
