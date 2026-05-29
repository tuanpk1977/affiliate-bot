from __future__ import annotations

import json
import unittest

import pandas as pd

from config import settings
from modules.social_policy_checker import split_x_thread, validate_post
from modules.social_publisher import EXTENDED_QUEUE_COLUMNS, ensure_social_accounts_config, load_queue, rewrite_for_platform


class SocialPublisherSafetyTests(unittest.TestCase):
    def test_social_accounts_do_not_store_passwords(self) -> None:
        accounts = ensure_social_accounts_config()
        serialized = json.dumps(accounts).lower()
        self.assertNotIn('"password"', serialized)

    def test_x_thread_parts_stay_under_limit(self) -> None:
        content = " ".join(["This is a practical AI coding workflow sentence." for _ in range(30)])
        parts = split_x_thread(content)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 260 for part in parts))

    def test_policy_requires_utm(self) -> None:
        row = {
            "platform": "linkedin",
            "content": "Useful workflow note",
            "tracked_url": "https://review.mssmileenglish.com/blog/chatgpt-prompts-for-windsurf/",
        }
        result = validate_post(row, queue=pd.DataFrame())
        self.assertFalse(result.valid)
        self.assertIn("missing_utm", result.errors)

    def test_queue_has_required_columns_when_present(self) -> None:
        queue_path = settings.data_dir / "social_publish_queue.csv"
        if not queue_path.exists():
            self.skipTest("social_publish_queue.csv has not been generated yet")
        queue = load_queue()
        for column in EXTENDED_QUEUE_COLUMNS:
            self.assertIn(column, queue.columns)

    def test_platform_rewrites_are_native_and_distinct(self) -> None:
        kwargs = {
            "base_content": "I use ChatGPT to plan prompts, Windsurf for a first build, and Codex for repair.",
            "title": "ChatGPT prompts for Windsurf",
            "tracked_url": "https://review.mssmileenglish.com/blog/chatgpt-prompts-for-windsurf/",
            "keyword": "ChatGPT prompts for Windsurf",
            "topic": "ChatGPT Windsurf Codex workflow",
        }
        facebook = rewrite_for_platform(platform="facebook", **kwargs)
        telegram = rewrite_for_platform(platform="telegram", **kwargs)
        linkedin = rewrite_for_platform(platform="linkedin", **kwargs)
        twitter = rewrite_for_platform(platform="twitter", **kwargs)

        self.assertNotEqual(facebook["content"], telegram["content"])
        self.assertNotEqual(linkedin["content"], twitter["content"])
        self.assertNotEqual(facebook["cta"], telegram["cta"])
        self.assertNotEqual(linkedin["cta"], twitter["cta"])
        self.assertNotEqual(facebook["hook"], linkedin["hook"])
        self.assertNotEqual(telegram["hook"], twitter["hook"])
        self.assertNotEqual(facebook["hook_style"], linkedin["hook_style"])
        self.assertNotEqual(telegram["tone_profile"], twitter["tone_profile"])

        facebook_paragraphs = [part for part in facebook["content"].split("\n\n") if part.strip()]
        linkedin_paragraphs = [part for part in linkedin["content"].split("\n\n") if part.strip()]
        telegram_lines = [part for part in telegram["content"].splitlines() if part.strip()]
        twitter_lines = [part for part in twitter["content"].splitlines() if part.strip()]
        self.assertGreaterEqual(len(facebook_paragraphs), 4)
        self.assertGreaterEqual(len(linkedin_paragraphs), 3)
        self.assertGreater(len(telegram_lines), len(twitter_lines))

    def test_twitter_rewrite_is_short(self) -> None:
        result = rewrite_for_platform(
            base_content="Long practical note about AI coding workflow " * 20,
            platform="twitter",
            title="Cursor vs Windsurf workflow",
            tracked_url="https://review.mssmileenglish.com/comparisons/cursor-vs-windsurf/",
            keyword="cursor vs windsurf",
            topic="AI coding workflow",
        )
        self.assertLessEqual(len(result["content"]), 280)

    def test_telegram_rewrite_has_no_export_metadata(self) -> None:
        result = rewrite_for_platform(
            base_content="A practical note about using ChatGPT before Windsurf.",
            platform="telegram",
            title="ChatGPT prompts for Windsurf",
            tracked_url="https://review.mssmileenglish.com/blog/chatgpt-prompts-for-windsurf/",
            keyword="ChatGPT prompts for Windsurf",
            topic="AI coding workflow",
        )
        blocked = ["Platform:", "Post ID:", "Image path:", "Tracked URL:"]
        for phrase in blocked:
            self.assertNotIn(phrase, result["content"])

    def test_codex_openclaw_platform_rewrites_are_not_light_paraphrases(self) -> None:
        kwargs = {
            "base_content": "Codex is useful for cleanup and OpenClaw is useful for quick prototype exploration.",
            "title": "Codex vs OpenClaw",
            "tracked_url": "https://review.mssmileenglish.com/comparisons/codex-vs-openclaw/",
            "keyword": "Codex vs OpenClaw",
            "topic": "AI coding workflow",
        }
        facebook = rewrite_for_platform(platform="facebook", **kwargs)
        linkedin = rewrite_for_platform(platform="linkedin", **kwargs)
        telegram = rewrite_for_platform(platform="telegram", **kwargs)
        twitter = rewrite_for_platform(platform="twitter", **kwargs)

        self.assertNotEqual(facebook["content"].splitlines()[0], linkedin["content"].splitlines()[0])
        self.assertNotEqual(telegram["content"].splitlines()[0], twitter["content"].splitlines()[0])
        self.assertNotEqual(facebook["cta"], linkedin["cta"])
        self.assertNotEqual(telegram["cta"], twitter["cta"])
        self.assertLessEqual(len(twitter["content"]), 280)

    def test_reddit_rewrite_is_native_and_non_hype(self) -> None:
        kwargs = {
            "base_content": "Codex is useful for cleanup and OpenClaw is useful for quick prototype exploration.",
            "title": "Codex vs OpenClaw",
            "tracked_url": "https://review.mssmileenglish.com/comparisons/codex-vs-openclaw/",
            "keyword": "Codex vs OpenClaw",
            "topic": "AI coding workflow",
        }
        reddit = rewrite_for_platform(platform="reddit", **kwargs)
        linkedin = rewrite_for_platform(platform="linkedin", **kwargs)
        facebook = rewrite_for_platform(platform="facebook", **kwargs)
        self.assertNotEqual(reddit["content"], linkedin["content"])
        self.assertNotEqual(reddit["content"], facebook["content"])
        lowered = reddit["content"].lower()
        for banned in ["best ai tool", "game changer", "must read", "check this out"]:
            self.assertNotIn(banned, lowered)
        self.assertIn("deeper breakdown here if useful", lowered)
        self.assertIn("discussion", reddit["tone_profile"].lower())

    def test_facebook_group_rewrite_is_vietnamese_and_no_link_by_default_option(self) -> None:
        result = rewrite_for_platform(
            base_content="Codex vs OpenClaw workflow note",
            platform="facebook_group",
            title="Codex vs OpenClaw",
            tracked_url="https://review.mssmileenglish.com/comparisons/codex-vs-openclaw/",
            keyword="codex vs openclaw",
            topic="AI coding workflow",
            include_link=False,
            facebook_variant="experience",
        )
        content = result["content"]
        self.assertIn("Chắc nhiều anh em", content)
        self.assertIn("BỐI CẢNH:", content)
        self.assertIn("ĐIỂM MẠNH:", content)
        self.assertIn("Không biết anh em", content)
        self.assertNotIn("https://", content)
        for banned in ["Read/check", "practical breakdown", "buying guide"]:
            self.assertNotIn(banned, content)

    def test_facebook_rewrite_differs_from_other_platforms_and_has_final_question(self) -> None:
        kwargs = {
            "base_content": "I use ChatGPT to plan prompts, Windsurf for a first build, and Codex for repair.",
            "title": "Cursor vs Windsurf",
            "tracked_url": "https://review.mssmileenglish.com/comparisons/cursor-vs-windsurf/",
            "keyword": "cursor vs windsurf",
            "topic": "AI coding workflow",
        }
        facebook = rewrite_for_platform(platform="facebook_group", include_link=False, facebook_variant="tool_comparison", **kwargs)
        telegram = rewrite_for_platform(platform="telegram", **kwargs)
        linkedin = rewrite_for_platform(platform="linkedin", **kwargs)
        twitter = rewrite_for_platform(platform="twitter", **kwargs)

        self.assertNotEqual(facebook["content"], telegram["content"])
        self.assertNotEqual(facebook["content"], linkedin["content"])
        self.assertNotEqual(facebook["content"], twitter["content"])
        self.assertTrue(
            "Anh em dùng thực tế thấy bên nào ổn hơn?" in facebook["content"]
            or "Không biết anh em ở đây đang nghiêng về bên nào hơn?" in facebook["content"]
        )
        self.assertIn("#AI", facebook["content"])


if __name__ == "__main__":
    unittest.main()
