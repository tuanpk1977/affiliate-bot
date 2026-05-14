from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "20"))
    discovery_limit: int = int(os.getenv("DISCOVERY_LIMIT", "40"))
    user_agent: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 AffiliateResearchBot/1.0"
    )


settings = Settings()
