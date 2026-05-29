from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd

from modules.scheduler_runner import process_due_telegram_posts
from modules.telegram_publisher import escape_markdown, split_long_text


QUEUE_COLUMNS = [
    "queue_id",
    "post_id",
    "draft_id",
    "platform",
    "channel_type",
    "community_id",
    "community_name",
    "title",
    "content",
    "article_url",
    "target_url",
    "tracked_url",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "status",
    "scheduled_time",
    "approved_at",
    "published_at",
    "last_attempt",
    "attempts",
    "error",
    "policy_status",
    "policy_warnings",
    "manual_export_path",
    "published_url",
    "notes",
]


def queue_row(status: str = "approved", when: str | None = None) -> dict[str, str]:
    row = {column: "" for column in QUEUE_COLUMNS}
    row.update({
        "queue_id": "q1",
        "post_id": "p1",
        "platform": "telegram",
        "content": "Test Telegram content",
        "status": status,
        "scheduled_time": when or (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds"),
        "attempts": "0",
    })
    return row


class TelegramSchedulerTests(unittest.TestCase):
    def test_markdown_escape(self) -> None:
        escaped = escape_markdown("Hello _world_ [link](url)!")
        self.assertIn("\\_", escaped)
        self.assertIn("\\[", escaped)
        self.assertIn("\\!", escaped)

    def test_long_text_splits(self) -> None:
        parts = split_long_text("word " * 2000, max_chars=1000)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 1000 for part in parts))

    def test_scheduled_publish_updates_status(self) -> None:
        saved: dict[str, pd.DataFrame] = {}
        queue = pd.DataFrame([queue_row()])
        with patch("modules.scheduler_runner.load_queue", return_value=queue), \
             patch("modules.scheduler_runner.save_queue", side_effect=lambda df: saved.setdefault("df", df.copy())), \
             patch("modules.scheduler_runner.validate_telegram_config", return_value=(True, "ok")), \
             patch("modules.scheduler_runner.send_post", return_value={"ok": True, "message_ids": ["123"]}), \
             patch("modules.scheduler_runner.write_log"):
            result = process_due_telegram_posts()
        self.assertEqual(result["published"], 1)
        self.assertEqual(saved["df"].loc[0, "status"], "published")
        self.assertEqual(saved["df"].loc[0, "published_url"], "123")

    def test_failed_publish_updates_status(self) -> None:
        saved: dict[str, pd.DataFrame] = {}
        queue = pd.DataFrame([queue_row()])
        with patch("modules.scheduler_runner.load_queue", return_value=queue), \
             patch("modules.scheduler_runner.save_queue", side_effect=lambda df: saved.setdefault("df", df.copy())), \
             patch("modules.scheduler_runner.validate_telegram_config", return_value=(False, "missing token")), \
             patch("modules.scheduler_runner.write_log"):
            result = process_due_telegram_posts()
        self.assertEqual(result["failed"], 1)
        self.assertEqual(saved["df"].loc[0, "status"], "failed")
        self.assertIn("missing token", saved["df"].loc[0, "error"])

    def test_future_post_is_not_published(self) -> None:
        queue = pd.DataFrame([queue_row(when=(datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds"))])
        with patch("modules.scheduler_runner.load_queue", return_value=queue), \
             patch("modules.scheduler_runner.save_queue") as save_queue, \
             patch("modules.scheduler_runner.validate_telegram_config", return_value=(True, "ok")), \
             patch("modules.scheduler_runner.send_post") as send_post:
            result = process_due_telegram_posts()
        self.assertEqual(result["published"], 0)
        self.assertEqual(result["skipped"], 1)
        send_post.assert_not_called()
        save_queue.assert_called_once()


if __name__ == "__main__":
    unittest.main()
