from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from modules.revision_binding import binding_for_file
from .utils import PublishedArticle, extract_canonical, extract_meta, extract_title, read_json


class SocialDraftRootSelectionService:
    """Rank live articles and bind current-cycle Website roots to Social drafts."""

    def __init__(
        self,
        *,
        root: Path,
        data_dir: Path,
        draft_root: Path,
        article_from_live_row: Callable[[dict[str, Any]], PublishedArticle],
        social_batch_dates: Callable[[], list[str]],
        best_title: Callable[[str, str, str], str],
        looks_like_iso_date: Callable[[str], bool],
        week_start: Callable[[str], str],
        status_key: Callable[[Any], str],
        write_json: Callable[[Path, Any], None],
        now_iso: Callable[[], str],
        social_weekly_root_count: int,
        default_social_draft_count: int,
    ) -> None:
        self.root = root
        self.data_dir = data_dir
        self.draft_root = draft_root
        self.article_from_live_row = article_from_live_row
        self.social_batch_dates = social_batch_dates
        self.best_title = best_title
        self.looks_like_iso_date = looks_like_iso_date
        self.week_start = week_start
        self.status_key = status_key
        self.write_json = write_json
        self.now_iso = now_iso
        self.social_weekly_root_count = social_weekly_root_count
        self.default_social_draft_count = default_social_draft_count

    def _current_cycle_angle_history(
        self,
        *,
        batch_date: str,
        root_topic_id: str,
        platform: str,
    ) -> list[str]:
        """Read only same-root metadata in the requested Website cycle."""
        if not self.looks_like_iso_date(batch_date):
            return []
        start = date.fromisoformat(self.week_start(batch_date))
        end = date.fromisoformat(batch_date)
        angles: list[str] = []
        # Exclude the current batch so rerunning Menu F is idempotent instead of
        # treating its own unapproved drafts as prior-day history.
        for offset in range(max(0, (end - start).days)):
            day = (start + timedelta(days=offset)).isoformat()
            day_root = self.draft_root / day
            if not day_root.is_dir():
                continue
            for metadata_path in day_root.glob(f"*/{platform}/metadata.json"):
                metadata = read_json(metadata_path, {})
                if not isinstance(metadata, dict):
                    continue
                if str(metadata.get("root_topic_id") or "") != root_topic_id:
                    continue
                # A/B/C are internal components.  Consume one daily angle only
                # after the composed FINAL post is approved or published.
                if self.status_key(metadata.get("status")) not in {
                    "approved_for_copy", "pending_manual_publish", "published_manual"
                }:
                    continue
                angle = str(
                    metadata.get("today_social_angle")
                    or metadata.get("social_angle")
                    or ""
                )
                if angle:
                    angles.append(angle)
        return list(dict.fromkeys(angles))

    def _research_source_count(self, slug: str) -> int:
        research_dir = self.data_dir / "research" / slug
        if not research_dir.exists():
            return 0
        source_urls: set[str] = set()
        for path in research_dir.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            stack: list[Any] = [payload]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    for key, nested in value.items():
                        if key.lower() in {"url", "source_url", "link"} and isinstance(nested, str) and nested.startswith("http"):
                            source_urls.add(nested)
                        else:
                            stack.append(nested)
                elif isinstance(value, list):
                    stack.extend(value)
        return len(source_urls)

    def rank_articles(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        for row in rows:
            article = self.article_from_live_row(row)
            headings = article.headings or []
            key_points = article.key_points or []
            source_count = self._research_source_count(article.article_id)
            text = f"{article.title} {article.description} {' '.join(headings)}".lower()
            score = 0.0
            reasons: list[str] = []
            if article.description and len(article.description) >= 80:
                score += 12
                reasons.append("strong meta description")
            if len(headings) >= 4:
                score += 12
                reasons.append("clear article structure")
            if article.image:
                score += 8
                reasons.append("featured image available")
            if source_count >= 3:
                score += 16
                reasons.append(f"{source_count} research sources found")
            elif source_count >= 2:
                score += 10
                reasons.append(f"{source_count} research sources found")
            elif source_count == 1:
                score += 4
                reasons.append("one research source found")
            if any(word in text for word in ("pricing", "comparison", "alternatives", "buyer", "workflow", "platform", "software")):
                score += 16
                reasons.append("commercial or workflow intent")
            if any(word in text for word in ("how to", "challenges", "marketing", "automation", "tools", "business")):
                score += 12
                reasons.append("practical usefulness")
            if any(word in text for word in ("2026", "review")):
                score += 6
                reasons.append("evergreen review angle")
            if len(key_points) >= 4:
                score += 8
                reasons.append("multiple reusable takeaways")
            if "healthcare" in text or "financial" in text or "legal" in text:
                score -= 10
                reasons.append("higher review risk")
            ranked.append(
                {
                    "slug": article.article_id,
                    "title": article.title,
                    "url": article.url,
                    "score": round(score, 2),
                    "reason": "; ".join(reasons) or "basic live article metadata",
                    "selected": False,
                    "source_count": source_count,
                }
            )
        ranked.sort(key=lambda item: (-float(item["score"]), str(item["slug"])))
        for item in ranked[:self.default_social_draft_count]:
            item["selected"] = True
        return ranked

    def _weekly_social_roots_path(self, week_start: str) -> Path:
        return self.draft_root / "weeks" / f"{week_start}.json"

    def _website_weekly_roots(self, batch_date: str) -> list[dict[str, Any]]:
        """Load only the canonical Website roots for the requested content cycle."""
        if not self.looks_like_iso_date(batch_date):
            return []
        manifest = read_json(
            self.data_dir / "editorial_queue" / "weeks" / self.week_start(batch_date) / "week.json",
            {},
        )
        if not isinstance(manifest, dict) or str(manifest.get("lock_status") or "").lower() != "locked":
            return []
        roots = [row for row in list(manifest.get("topics") or []) if isinstance(row, dict)]
        return roots[:self.social_weekly_root_count]

    def _website_root_bindings(
        self,
        *,
        batch_date: str,
        roots: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Resolve source slugs from current-cycle queues without historical scans."""
        if not self.looks_like_iso_date(batch_date):
            return {}
        root_lookup: dict[str, dict[str, Any]] = {}
        for root in roots:
            root_id = str(root.get("root_topic_id") or root.get("parent_slug") or root.get("slug") or "")
            if root_id:
                root_lookup[root_id] = root
        bindings: dict[str, dict[str, Any]] = {}
        start = date.fromisoformat(self.week_start(batch_date))
        end = date.fromisoformat(batch_date)
        for offset in range(max(0, (end - start).days) + 1):
            day = (start + timedelta(days=offset)).isoformat()
            queue = read_json(self.data_dir / "editorial_queue" / day / "topics.json", {})
            for topic in list(queue.get("topics") or []) if isinstance(queue, dict) else []:
                if not isinstance(topic, dict):
                    continue
                slug = str(topic.get("slug") or "")
                root_id = str(topic.get("root_topic_id") or topic.get("parent_slug") or "")
                if not slug or root_id not in root_lookup:
                    continue
                root = root_lookup[root_id]
                bindings[slug] = {
                    "root_topic_id": root_id,
                    "root_title": str(root.get("root_title") or root.get("title") or ""),
                    "source_article_slug": slug,
                    "source_batch_date": day,
                    "social_angle": str(topic.get("daily_angle") or topic.get("suggested_article_angle") or "source_article_adaptation"),
                    "today_social_angle": str(topic.get("daily_angle") or topic.get("suggested_article_angle") or "source_article_adaptation"),
                    "content_relationship": "website_root_social_adaptation",
                    "content_origin": "WEBSITE_ROOT_BASED",
                    "social_mode": "SOURCE_BASED_SOCIAL",
                }
        for root_id, root in root_lookup.items():
            parent_slug = str(root.get("parent_slug") or root.get("slug") or root_id)
            bindings.setdefault(
                parent_slug,
                {
                    "root_topic_id": root_id,
                    "root_title": str(root.get("root_title") or root.get("title") or ""),
                    "source_article_slug": parent_slug,
                    "source_batch_date": self.week_start(batch_date),
                    "social_angle": "root_topic_adaptation",
                    "today_social_angle": "root_topic_adaptation",
                    "content_relationship": "website_root_social_adaptation",
                    "content_origin": "WEBSITE_ROOT_BASED",
                    "social_mode": "SOURCE_BASED_SOCIAL",
                },
            )
        return bindings

    def _source_binding(self, slug: str, context: dict[str, Any]) -> dict[str, Any]:
        metadata = read_json(self.data_dir / "production_article_drafts" / slug / "metadata.json", {})
        if not isinstance(metadata, dict):
            metadata = {}
        html_path = self.data_dir / "production_article_drafts" / slug / "index.html"
        current_hash = ""
        if html_path.is_file():
            current_hash = binding_for_file(html_path)["content_hash"]
        approval = metadata.get("human_approval") if isinstance(metadata.get("human_approval"), dict) else {}
        revision_id = str(
            metadata.get("revision_id")
            or approval.get("revision_id")
            or approval.get("approved_revision_id")
            or (f"website-revision-v1:{current_hash}" if current_hash else "")
        )
        research_dir = self.data_dir / "research" / slug
        research_reference = ""
        for name in ("FACT_LEDGER.json", "fact_ledger.json", "package.json"):
            candidate = research_dir / name
            if candidate.is_file():
                research_reference = str(candidate.relative_to(self.root)).replace("\\", "/")
                break
        enrichment = read_json(research_dir / "enrichment_report.json", {})
        if not isinstance(enrichment, dict):
            enrichment = {}
        research_blockers = list(enrichment.get("blockers") or [])
        research_status = str(enrichment.get("status") or "").upper()
        evidence_verified = bool(
            enrichment
            and not research_blockers
            and (
                enrichment.get("article_ready") is True
                or enrichment.get("draft_exportable") is True
                or research_status in {"ARTICLE_READY", "RESEARCH_GOOD", "RESEARCH_STRONG"}
            )
        )
        return {
            **context,
            "source_article_slug": slug,
            "source_revision_id": revision_id,
            "source_content_hash": current_hash,
            "source_evidence_reference": research_reference,
            "evidence_inheritance": (
                "VERIFIED_SOURCE_ARTICLE" if evidence_verified else "SOURCE_RESEARCH_REVIEW_REQUIRED"
            ),
            "source_research_state": "PASSED" if evidence_verified else "BLOCKED_OR_UNVERIFIED",
            "source_research_blockers": research_blockers,
        }

    def _read_weekly_social_roots(self, batch_date: str) -> dict[str, Any]:
        if not self.looks_like_iso_date(batch_date):
            return {}
        week_start = self.week_start(batch_date)
        path = self._weekly_social_roots_path(week_start)
        payload = read_json(path, {})
        if isinstance(payload, dict) and isinstance(payload.get("root_slugs"), list):
            return payload
        for existing_date in self.social_batch_dates():
            if existing_date >= batch_date or not self.looks_like_iso_date(existing_date) or self.week_start(existing_date) != week_start:
                continue
            manifest = read_json(self.draft_root / existing_date / "manifest.json", {})
            items = manifest.get("items") if isinstance(manifest, dict) else []
            if isinstance(items, list) and items:
                root_slugs = [str(item.get("slug") or "") for item in items if isinstance(item, dict) and item.get("slug")]
                if root_slugs:
                    return {
                        "schema_version": 1,
                        "social_week_start": week_start,
                        "root_slugs": root_slugs[:self.social_weekly_root_count],
                        "source_batch_date": existing_date,
                        "selection_policy": "derived_from_earliest_social_manifest",
                    }
        return {}

    def _write_weekly_social_roots(self, *, batch_date: str, ranking: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any]:
        week_start = self.week_start(batch_date)
        path = self._weekly_social_roots_path(week_start)
        root_slugs = [str(row.get("slug") or "") for row in selected if row.get("slug")]
        payload = {
            "schema_version": 1,
            "social_week_start": week_start,
            "root_slugs": root_slugs[:self.social_weekly_root_count],
            "source_batch_date": batch_date,
            "selection_policy": "monday_or_first_social_selection",
            "selection_count": len(root_slugs[:self.social_weekly_root_count]),
            "created_at": self.now_iso(),
            "ranking": ranking,
            "continuation_rule": "Tue-Sun social drafts must reuse these root slugs and add a distinct advanced angle plus next-post teaser.",
        }
        existing = read_json(path, {})
        if isinstance(existing, dict) and existing.get("created_at"):
            payload["created_at"] = existing["created_at"]
        self.write_json(path, payload)
        return payload

    def _live_row_for_weekly_root(self, slug: str, resolved: str, live_by_slug: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        if slug in live_by_slug:
            return live_by_slug[slug]
        html_path = self.root / "docs" / slug / "index.html"
        if not html_path.exists():
            return None
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        canonical = extract_canonical(html_text) or f"https://smileaireviewhub.com/{slug}/"
        title = extract_meta(html_text, "og:title") or extract_title(html_text) or slug.replace("-", " ").title()
        return {
            "slug": slug,
            "title": self.best_title(slug, title, title),
            "url": canonical,
            "batch_date": resolved,
            "source": "weekly_social_root_docs_fallback",
        }
