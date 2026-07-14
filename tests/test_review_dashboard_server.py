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
    (draft_dir / "article.md").write_text("# Review Me\n\nFull draft body.", encoding="utf-8")
    (draft_dir / "index.html").write_text("<!doctype html><html><body>Draft</body></html>", encoding="utf-8")
    (draft_dir / "review_summary.md").write_text("Review summary", encoding="utf-8")
    (draft_dir / "publish_readiness_report.md").write_text("AI report", encoding="utf-8")
    (draft_dir / "metadata.json").write_text(json.dumps({"title": "Review Me", "url": "https://example.com/review-me/"}), encoding="utf-8")
    research_dir = data_dir / "research" / slug
    research_dir.mkdir(parents=True, exist_ok=True)
    (research_dir / "sources.json").write_text(json.dumps({"verified_sources": [{"url": "https://example.com/source"}]}), encoding="utf-8")
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
    def test_get_dashboard_returns_200_and_csrf_token(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            httpd = ReviewDashboardServer(workflow=workflow).serve(batch_date="2026-07-10", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                conn = http.client.HTTPConnection(host, port, timeout=5)
                conn.request("GET", "/?date=2026-07-10")
                response = conn.getresponse()
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn('name="csrf_token"', body)
                self.assertIn("Requested date: 2026-07-10", body)
                self.assertIn("Resolved batch date: 2026-07-10", body)
                self.assertIn("Draft count: 1", body)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_missing_requested_date_resolves_to_latest_valid_batch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            _write_json(
                workflow.data_dir / "editorial_queue" / "2026-07-11" / "topics.json",
                {"date": "2026-07-11", "topics": [{"slug": "empty-topic", "status": "selected"}]},
            )
            placeholder_draft = workflow.data_dir / "production_article_drafts" / "placeholder"
            placeholder_draft.mkdir(parents=True, exist_ok=True)
            (placeholder_draft / "index.html").write_text("<html></html>", encoding="utf-8")
            _write_json(
                workflow.data_dir / "editorial_queue" / "YYYY-MM-DD" / "topics.json",
                {"date": "YYYY-MM-DD", "topics": [{"slug": "placeholder", "status": "drafted", "draft_file": str(placeholder_draft / "index.html")}]},
            )
            httpd = ReviewDashboardServer(workflow=workflow).serve(batch_date="latest", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                conn = http.client.HTTPConnection(host, port, timeout=5)
                conn.request("GET", "/?date=2026-07-14")
                response = conn.getresponse()
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn("Requested date: 2026-07-14", body)
                self.assertIn("Resolved batch date: 2026-07-10", body)
                self.assertIn("Draft count: 1", body)
                self.assertIn("review-me", body)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_latest_resolution_does_not_reuse_old_dashboard_without_drafts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = _seed_workflow(root)
            _write_json(
                workflow.data_dir / "editorial_queue" / "2026-07-12" / "topics.json",
                {"date": "2026-07-12", "topics": [{"slug": "queue-only", "status": "research_ready"}]},
            )
            old_dashboard = workflow.site_output_dir / "review" / "2026-07-12" / "index.html"
            old_dashboard.parent.mkdir(parents=True, exist_ok=True)
            old_dashboard.write_text("<html>old dashboard</html>", encoding="utf-8")

            resolved = ReviewDashboardServer._resolve_batch_date_for_workflow(workflow, "latest", default_date="latest")

            self.assertEqual(resolved["resolved_date"], "2026-07-10")
            self.assertEqual(resolved["draft_count"], 1)
            self.assertEqual(resolved["latest_batch_detection"], "latest draft-ready batch")

    def test_latest_date_reads_seven_reviewable_drafts_fixture(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = _seed_workflow(root)
            topics = []
            for index in range(7):
                slug = f"codex-draft-{index + 1}"
                draft_dir = workflow.data_dir / "production_article_drafts" / slug
                draft_dir.mkdir(parents=True, exist_ok=True)
                (draft_dir / "index.html").write_text(f"<!doctype html><html><body>Draft {index + 1}</body></html>", encoding="utf-8")
                topics.append({"keyword": f"codex draft {index + 1}", "slug": slug, "status": "drafted", "draft_file": str(draft_dir / "index.html")})
            _write_json(workflow.data_dir / "editorial_queue" / "2026-07-13" / "topics.json", {"date": "2026-07-13", "topics": topics})
            httpd = ReviewDashboardServer(workflow=workflow).serve(batch_date="latest", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                conn = http.client.HTTPConnection(host, port, timeout=5)
                conn.request("GET", "/?date=latest")
                response = conn.getresponse()
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn("Resolved batch date: 2026-07-13", body)
                self.assertIn("Draft count: 7", body)
                self.assertIn("codex-draft-7", body)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_render_exception_returns_http_500_not_empty_response(self) -> None:
        class BrokenWorkflow(DailyEditorialWorkflow):
            def render_interactive_dashboard(self, **kwargs: object) -> str:  # type: ignore[override]
                raise NameError("csrf_token")

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = BrokenWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            _write_json(workflow.data_dir / "editorial_queue" / "2026-07-10" / "topics.json", {"date": "2026-07-10", "topics": []})
            httpd = ReviewDashboardServer(workflow=workflow).serve(batch_date="2026-07-10", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                conn = http.client.HTTPConnection(host, port, timeout=5)
                conn.request("GET", "/?date=2026-07-10")
                response = conn.getresponse()
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 500)
                self.assertIn("Dashboard render failed", body)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_post_missing_csrf_token_is_rejected_without_state_change(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            httpd = ReviewDashboardServer(workflow=workflow).serve(batch_date="2026-07-10", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                conn = http.client.HTTPConnection(host, port, timeout=5)
                body = "date=2026-07-10&slug=review-me&filter=blocked&anchor=row-review-me"
                conn.request("POST", "/approve", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                post_response = conn.getresponse()
                post_response.read()
                self.assertEqual(post_response.status, 303)
                self.assertIn("Security+token+expired", post_response.getheader("Location") or "")
                queue = json.loads((workflow.data_dir / "editorial_queue" / "2026-07-10" / "topics.json").read_text(encoding="utf-8"))
                self.assertEqual(queue["topics"][0]["status"], "drafted")
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

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

    def test_server_detail_exposes_reviewable_artifacts_and_reject_confirmation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            rendered = workflow.render_interactive_dashboard(batch_date="2026-07-10", selected_slug="review-me")
            self.assertIn('/artifact?date=2026-07-10&amp;slug=review-me&amp;type=draft', rendered)
            self.assertIn('/artifact?date=2026-07-10&amp;slug=review-me&amp;type=html', rendered)
            self.assertIn('/artifact?date=2026-07-10&amp;slug=review-me&amp;type=source-review', rendered)
            self.assertIn('onsubmit="return confirm(', rendered)

    def test_server_artifact_endpoint_serves_draft_content(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            httpd = ReviewDashboardServer(workflow=workflow).serve(batch_date="2026-07-10", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = httpd.server_address
                conn = http.client.HTTPConnection(host, port, timeout=5)
                conn.request("GET", "/artifact?date=2026-07-10&slug=review-me&type=draft")
                response = conn.getresponse()
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), "text/plain; charset=utf-8")
                self.assertIn("Full draft body", body)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=2)

    def test_static_dashboard_disables_backend_actions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            result = workflow.build_review_dashboard(batch_date="2026-07-10")
            rendered = Path(result["dashboard_file"]).read_text(encoding="utf-8")
            self.assertIn("Open Local Review Server", rendered)
            self.assertIn("python editorial_console.py serve --date 2026-07-10 --open", rendered)
            self.assertIn("Approve in server", rendered)
            self.assertIn("Reject in server", rendered)
            self.assertNotIn("actions/approve-review-me.cmd", rendered)
            self.assertNotIn("actions/reject-review-me.cmd", rendered)
            self.assertNotIn("Publish Ready Articles", rendered)

    def test_blocked_topic_without_preview_has_no_enabled_server_action(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workflow = _seed_workflow(Path(temp_dir))
            queue_path = workflow.data_dir / "editorial_queue" / "2026-07-10" / "topics.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["topics"].append(
                {
                    "keyword": "blocked",
                    "slug": "blocked-topic",
                    "status": "needs_enrichment",
                    "error": "Research quality gate blocked draft generation: competitor coverage is limited",
                }
            )
            queue_path.write_text(json.dumps(queue, indent=2), encoding="utf-8")
            rendered = workflow.render_interactive_dashboard(batch_date="2026-07-10", selected_slug="blocked-topic")
            self.assertIn("No draft preview yet.", rendered)
            self.assertIn('<button class="button success" disabled>Approve</button>', rendered)
            self.assertIn('<button class="button danger" disabled>Reject</button>', rendered)


if __name__ == "__main__":
    unittest.main()
