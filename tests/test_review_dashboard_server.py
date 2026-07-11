from __future__ import annotations

import http.client
import csv
import json
import re
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse

from modules.daily_editorial_workflow import DailyEditorialWorkflow
from modules.review_dashboard_server import ReviewDashboardServer


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _seed_workflow(root: Path) -> DailyEditorialWorkflow:
    data_dir = root / "data"
    slug = "review-me"
    draft_dir = data_dir / "production_article_drafts" / slug
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "index.html").write_text("<!doctype html><html><body>Draft</body></html>", encoding="utf-8")
    (draft_dir / "metadata.json").write_text(json.dumps({"title": "Review Me", "url": "https://example.com/review-me/"}), encoding="utf-8")
    _write_json(
        data_dir / "editorial_queue" / "2026-07-10" / "topics.json",
        {
            "generated_at": "",
            "date": "2026-07-10",
            "mode": "standard",
            "count": 1,
            "topics": [
                {
                    "keyword": "review me",
                    "slug": slug,
                    "status": "drafted",
                    "draft_file": str(draft_dir / "index.html"),
                    "review_preview": str(draft_dir / "index.html"),
                }
            ],
        },
    )
    _write_json(data_dir / "content_review_queue.json", [{"slug": slug, "status": "needs_human_review", "publishable": True}])
    _write_json(data_dir / "human_approval_queue.json", [{"slug": slug, "status": "needs_human_review"}])
    _write_json(data_dir / "publish_queue.json", [{"slug": slug, "status": "blocked", "failures": ["human approval missing"]}])
    return DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")


class ReviewDashboardServerTests(unittest.TestCase):
    def test_approve_handles_mixed_report_fields_and_renders_success_notice(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            workflow.data_dir.joinpath("content_review_queue.json").write_text(
                json.dumps([
                    {"slug": "older-row", "status": "needs_human_review"},
                    {"slug": "review-me", "status": "needs_human_review", "publishable": True},
                ]),
                encoding="utf-8",
            )
            result = workflow.approve(slug="review-me", batch_date="2026-07-10")
            self.assertEqual(result["result"]["human_approval"]["status"], "human_approved")
            with workflow.data_dir.joinpath("content_review_report.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            rendered = workflow.render_interactive_dashboard(
                batch_date="2026-07-10", selected_slug="review-me", message="Article approved successfully"
            )
            self.assertIn("role='status'", rendered)
            self.assertIn("Article approved successfully", rendered)

    def test_error_notice_is_visually_distinct(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            rendered = workflow.render_interactive_dashboard(
                batch_date="2026-07-10", selected_slug="review-me", message="Error: invalid review data"
            )
            self.assertIn("class='notice error'", rendered)

    def test_approve_uses_post_and_redirects_back_to_dashboard(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            httpd = ReviewDashboardServer(workflow=workflow).serve(batch_date="2026-07-10", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                conn = http.client.HTTPConnection(host, port, timeout=5)
                conn.request("GET", "/?date=2026-07-10&slug=review-me&filter=blocked")
                response = conn.getresponse()
                html = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                token_match = re.search(r'name="csrf_token" value="([^"]+)"', html)
                self.assertIsNotNone(token_match)
                token = token_match.group(1)

                body = f"date=2026-07-10&slug=review-me&filter=blocked&anchor=row-review-me&csrf_token={token}"
                conn.request("POST", "/approve", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                post_response = conn.getresponse()
                post_response.read()

                self.assertEqual(post_response.status, 303)
                location = post_response.getheader("Location") or ""
                parsed = urlparse(location)
                params = parse_qs(parsed.query)
                self.assertEqual(parsed.path, "/")
                self.assertEqual(params["date"], ["2026-07-10"])
                self.assertEqual(params["slug"], ["review-me"])
                self.assertEqual(params["filter"], ["blocked"])
                self.assertEqual(params["message"], ["Article approved successfully"])
                self.assertEqual(parsed.fragment, "row-review-me")

                queue = json.loads((workflow.data_dir / "editorial_queue" / "2026-07-10" / "topics.json").read_text(encoding="utf-8"))
                self.assertEqual(queue["topics"][0]["status"], "approved")
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_reject_uses_post_and_redirects_back_to_dashboard(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            httpd = ReviewDashboardServer(workflow=workflow).serve(batch_date="2026-07-10", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                conn = http.client.HTTPConnection(host, port, timeout=5)
                conn.request("GET", "/?date=2026-07-10&slug=review-me")
                response = conn.getresponse()
                html = response.read().decode("utf-8")
                token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

                body = f"date=2026-07-10&slug=review-me&reason=Needs+fix&anchor=row-review-me&csrf_token={token}"
                conn.request("POST", "/reject", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                post_response = conn.getresponse()
                post_response.read()

                self.assertEqual(post_response.status, 303)
                self.assertIn("Article+rejected+successfully", post_response.getheader("Location") or "")
                queue = json.loads((workflow.data_dir / "editorial_queue" / "2026-07-10" / "topics.json").read_text(encoding="utf-8"))
                self.assertEqual(queue["topics"][0]["status"], "rejected")
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
