import unittest

from modules.content_operations import build_publishing_queue


class PublishingQueueTests(unittest.TestCase):
    def test_write_now_candidate_gets_video_status(self):
        money = [{"topic": "Tool Review", "slug": "tool-review", "decision": "WRITE NOW", "money_score": 90}]
        rows = build_publishing_queue(money, inventory=[])
        self.assertEqual(rows[0]["article_status"], "Candidate")
        self.assertEqual(rows[0]["video_status"], "Needs video")


if __name__ == "__main__":
    unittest.main()
