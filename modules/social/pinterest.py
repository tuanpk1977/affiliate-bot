from __future__ import annotations

from .base_publisher import BasePublisher, PublishResult
from .utils import PublishedArticle


BOARD_KEYWORDS = [
    ("coding", "AI Coding"),
    ("agent", "AI Agents"),
    ("vibe", "Vibe Coding"),
    ("automation", "AI Automation"),
    ("openai", "OpenAI"),
    ("claude", "Claude AI"),
    ("cursor", "Cursor AI"),
    ("windsurf", "Windsurf IDE"),
    ("comparison", "AI Tools Comparison"),
    ("alternative", "AI Tools Comparison"),
]


class PinterestPublisher(BasePublisher):
    platform = "pinterest"

    def board_for(self, article: PublishedArticle) -> str:
        text = f"{article.title} {article.description} {' '.join(article.tags)}".lower()
        for keyword, board in BOARD_KEYWORDS:
            if keyword in text:
                return board
        return "AI Reviews"

    def preview(self, article: PublishedArticle) -> dict[str, str | list[str]]:
        payload = super().preview(article)
        payload["board"] = self.board_for(article)
        payload["canonical_url"] = article.url
        return payload

    def publish(self, article: PublishedArticle) -> PublishResult:
        validation = self.validate()
        if not validation.success:
            return validation
        payload = self.preview(article)
        mode = str(self.config.get("mode") or "browser_hook")
        return PublishResult(
            platform=self.platform,
            status="prepared_browser_hook" if mode == "browser_hook" else "prepared",
            url=article.url,
            success=False,
            error="Pinterest API credentials/browser automation are not configured; prepared payload only.",
            metadata=payload,
        )

