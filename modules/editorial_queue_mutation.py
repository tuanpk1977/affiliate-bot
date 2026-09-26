from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import shutil
from typing import Any, Callable


class EditorialQueueMutation:
    """Own queue persistence, request conversion, and carry-forward materialization."""

    def __init__(
        self,
        *,
        data_dir: Path,
        review_root: Path,
        queue_dir: Callable[[str], Path],
        load_queue: Callable[[str], dict[str, Any]],
        save_queue: Callable[[str, dict[str, Any]], None],
        week_start: Callable[[str], str],
        copy_review_preview: Callable[..., Path],
        load_metadata: Callable[[str], dict[str, Any]],
        classify_content_type: Callable[[str], str],
        score_search_intent: Callable[[str], float],
        now_iso: Callable[[], str],
        read_json: Callable[[Path, Any], Any],
        write_json: Callable[[Path, Any], Path],
    ) -> None:
        self.data_dir = data_dir
        self.review_root = review_root
        self.queue_dir = queue_dir
        self.load_queue = load_queue
        self.save_queue_callback = save_queue
        self.week_start = week_start
        self.copy_review_preview_callback = copy_review_preview
        self.load_metadata = load_metadata
        self.classify_content_type = classify_content_type
        self.score_search_intent = score_search_intent
        self.now_iso = now_iso
        self.read_json = read_json
        self.write_json = write_json

    def save_queue(self, batch_date: str, payload: dict[str, Any]) -> None:
        self.write_json(self.queue_dir(batch_date) / "topics.json", payload)

    def batch_item(self, *, batch_date: str, slug: str) -> dict[str, Any]:
        payload = self.load_queue(batch_date)
        for item in payload.get("topics", []):
            if str(item.get("slug") or "") == slug:
                return dict(item)
        raise ValueError(f"Unknown batch slug: {slug}")

    def publish_row(self, slug: str) -> dict[str, Any]:
        for row in self.read_json(self.data_dir / "publish_queue.json", []):
            if str(row.get("slug") or "") == slug:
                return dict(row)
        return {}

    def copy_review_preview(self, *, slug: str, batch_date: str) -> Path:
        source = self.data_dir / "production_article_drafts" / slug / "index.html"
        if not source.exists():
            raise FileNotFoundError(f"Draft preview missing for {slug}: {source}")
        target = self.review_root / batch_date / slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def update_batch_status(
        self,
        *,
        batch_date: str,
        slug: str,
        status: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = self.load_queue(batch_date)
        for item in payload.get("topics", []):
            if str(item.get("slug") or "") != slug:
                continue
            item["status"] = status
            if extra:
                item.update(extra)
            break
        self.save_queue_callback(batch_date, payload)

    def update_batch_status_if_present(
        self,
        *,
        batch_date: str,
        slug: str,
        status: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        try:
            payload = self.load_queue(batch_date)
        except FileNotFoundError:
            return
        for item in payload.get("topics", []):
            if str(item.get("slug") or "") != slug:
                continue
            if status is not None:
                item["status"] = status
            if extra:
                item.update(extra)
            self.save_queue_callback(batch_date, payload)
            return

    def upsert_topics_into_batch(
        self,
        *,
        batch_date: str,
        topics: list[dict[str, Any]],
        mode: str,
    ) -> dict[str, Any]:
        try:
            payload = self.load_queue(batch_date)
        except FileNotFoundError:
            week_start = self.week_start(batch_date)
            payload = {
                "generated_at": self.now_iso(),
                "date": batch_date,
                "week_start": week_start,
                "week_end": (date.fromisoformat(week_start) + timedelta(days=6)).isoformat(),
                "mode": mode,
                "count": 0,
                "topics": [],
            }
        existing = {str(item.get("slug") or ""): item for item in payload.get("topics", [])}
        for topic in topics:
            existing[str(topic.get("slug") or "")] = topic
        merged = list(existing.values())
        payload["generated_at"] = self.now_iso()
        payload["mode"] = mode
        payload["count"] = len(merged)
        payload["topics"] = merged
        self.save_queue_callback(batch_date, payload)
        return payload

    def queue_entry_from_request_result(
        self,
        *,
        keyword: str,
        slug: str,
        result: dict[str, Any],
        batch_date: str,
        category: str,
        intent: str,
        content_type: str,
        source_type: str,
        partner_name: str,
        official_url: str,
        affiliate_url: str,
        pricing_url: str,
        cluster_article_number: int,
        cluster_article_total: int,
        suggested_article_angle: str,
    ) -> dict[str, Any]:
        drafted = bool(result.get("draft"))
        normalized_intent = intent.strip() or "commercial research"
        entry = {
            "keyword": keyword,
            "slug": slug,
            "title": keyword,
            "content_type": content_type,
            "search_intent": normalized_intent,
            "search_intent_score": self.score_search_intent(normalized_intent),
            "category": category.strip(),
            "source_type": source_type,
            "partner_name": partner_name.strip(),
            "official_url": official_url.strip(),
            "affiliate_url": affiliate_url.strip(),
            "pricing_url": pricing_url.strip(),
            "cluster_article_number": int(cluster_article_number or 1),
            "cluster_article_total": int(cluster_article_total or 1),
            "suggested_article_angle": suggested_article_angle,
            "status": "drafted" if drafted else "needs_enrichment",
            "batch_date": batch_date,
            "week_start": self.week_start(batch_date),
            "mode": source_type,
            "source_urls": [
                url
                for url in [official_url.strip(), affiliate_url.strip(), pricing_url.strip()]
                if url
            ],
            "draft_dir": str(self.data_dir / "production_article_drafts" / slug) if drafted else "",
            "review_preview": "",
            "research_quality_gate": dict(result.get("quality_gate") or {}),
            "error": "" if drafted else "Research/source quality gate blocked draft generation.",
        }
        if drafted:
            try:
                preview_path = self.copy_review_preview_callback(slug=slug, batch_date=batch_date)
                entry["review_preview"] = str(preview_path)
                entry["draft_file"] = str(self.data_dir / "production_article_drafts" / slug / "index.html")
                entry["metadata_file"] = str(
                    self.data_dir / "production_article_drafts" / slug / "metadata.json"
                )
            except FileNotFoundError:
                pass
        return entry

    def build_custom_topic_requests(
        self,
        *,
        topic_name: str,
        category: str,
        intent: str,
        count: int,
    ) -> list[dict[str, str]]:
        normalized = topic_name.strip()
        if not normalized:
            return []
        if int(count or 1) <= 1:
            return [
                {
                    "topic": normalized,
                    "content_type": self.classify_content_type(normalized),
                    "suggested_article_angle": f"Custom topic request for {normalized}",
                    "category": category.strip(),
                    "intent": intent.strip(),
                }
            ]
        templates = [
            ("review", f"{normalized} review 2026"),
            ("pricing", f"{normalized} pricing"),
            ("alternatives", f"{normalized} alternatives"),
            ("pros_cons", f"{normalized} pros and cons"),
            ("tutorial", f"how to use {normalized}"),
            ("comparison", f"{normalized} vs competitors"),
            ("affiliate_program", f"{normalized} affiliate program"),
            ("faq", f"{normalized} faq"),
        ]
        requests: list[dict[str, str]] = []
        for content_type, topic in templates[: max(1, int(count or 1))]:
            requests.append(
                {
                    "topic": topic,
                    "content_type": content_type,
                    "suggested_article_angle": (
                        f"Custom cluster article for {normalized}: {content_type}"
                    ),
                    "category": category.strip(),
                    "intent": intent.strip(),
                }
            )
        return requests

    @staticmethod
    def build_partner_cluster_topics(*, partner_name: str, count: int) -> list[dict[str, str]]:
        templates = [
            ("review", f"{partner_name} Review 2026"),
            ("pricing", f"{partner_name} Pricing"),
            ("alternatives", f"{partner_name} Alternatives"),
            ("pros_cons", f"{partner_name} Pros and Cons"),
            ("tutorial", f"How to Use {partner_name}"),
            ("affiliate_program", f"{partner_name} Affiliate Program"),
            ("comparison", f"{partner_name} vs top competitor"),
            ("faq", f"{partner_name} FAQ"),
        ]
        return [
            {
                "topic": topic,
                "content_type": content_type,
                "suggested_article_angle": (
                    f"Affiliate partner cluster for {partner_name}: {content_type}"
                ),
                "category": "Affiliate Partner",
            }
            for content_type, topic in templates[: max(1, int(count or 8))]
        ]

    def carry_forward_publish_candidates(
        self,
        *,
        batch_date: str,
        topics: list[dict[str, Any]],
        publish_rows: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        known_slugs = {str(item.get("slug") or "") for item in topics}
        carry_forward: list[dict[str, Any]] = []
        for row in publish_rows.values():
            slug = str(row.get("slug") or "")
            if not slug or slug in known_slugs:
                continue
            status = str(row.get("status") or "")
            if status not in {"approved_for_publish", "published_local"}:
                continue
            metadata = self.load_metadata(slug)
            carry_forward.append(
                {
                    "keyword": str(metadata.get("title") or row.get("title") or slug.replace("-", " ")),
                    "slug": slug,
                    "status": "approved" if status == "approved_for_publish" else "published",
                    "carry_forward": True,
                    "batch_date": batch_date,
                }
            )
        return carry_forward

    @staticmethod
    def upsert_affiliate_partner_record(partner_profile: dict[str, Any]) -> None:
        try:
            from modules.affiliate_links import upsert_affiliate_link
        except Exception:
            return
        upsert_affiliate_link(
            {
                "brand": str(partner_profile.get("name") or ""),
                "slug": str(partner_profile.get("slug") or ""),
                "official_url": str(partner_profile.get("official_url") or ""),
                "affiliate_url": str(partner_profile.get("affiliate_url") or ""),
                "status": (
                    "approved"
                    if str(partner_profile.get("affiliate_url") or "").strip()
                    else "official_only"
                ),
                "affiliate_status": (
                    "approved"
                    if str(partner_profile.get("affiliate_url") or "").strip()
                    else "official_only"
                ),
                "notes": str(partner_profile.get("contact_note") or ""),
                "commission_note": str(partner_profile.get("commission_note") or ""),
                "network": str(partner_profile.get("payout_note") or "Direct"),
                "approved": bool(str(partner_profile.get("affiliate_url") or "").strip()),
            }
        )
