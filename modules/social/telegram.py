from __future__ import annotations

from .base_publisher import BasePublisher


class TelegramPublisher(BasePublisher):
    platform = "telegram"

