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

    def preview(self, article: PublishedArticle) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "title": article.title,
            "description": article.description,
            "image": article.image,
            "url": article.url,
            "tags": article.tags,
        }

    def publish(self, article: PublishedArticle) -> PublishResult:
        validation = self.validate()
        if not validation.success:
            return validation
        return PublishResult(
            platform=self.platform,
            status="not_implemented",
            url=article.url,
            error="publisher integration is not implemented yet",
        )

