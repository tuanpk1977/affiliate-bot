from __future__ import annotations

import html
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .competitor_analysis import analyze_competitors
from .content_gap import analyze_gaps
from .internal_link_planner import plan_internal_links
from .keyword_clustering import build_clusters
from .keyword_research import collect_candidates
from .opportunity_scoring import score_opportunities


class SeoPipeline:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path(__file__).resolve().parents[2]).resolve()
        self.data_dir = self.root / "data" / "seo"
        self.config = self._read(self.root / "config" / "seo_engine.json", {})

    @staticmethod
    def _read(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, name: str, payload: Any) -> Path:
        path = self.data_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def existing_pages(self) -> list[dict[str, str]]:
        pages = []
        for base in (self.root / "docs", self.root / "data" / "production_article_drafts"):
            if not base.exists():
                continue
            for path in base.glob("*/index.html"):
                text = path.read_text(encoding="utf-8", errors="ignore")
                start, end = text.lower().find("<title>"), text.lower().find("</title>")
                pages.append({"slug": path.parent.name, "title": text[start + 7:end] if start >= 0 and end > start else path.parent.name})
        return list({row["slug"]: row for row in pages}.values())

    def import_keywords(self, seeds: list[str], imports: list[Path]) -> list[dict[str, Any]]:
        rows = collect_candidates(seeds, imports)
        self._write("keyword_candidates.json", rows)
        return rows

    def run(self, *, seeds: list[str] | None = None, imports: list[Path] | None = None) -> dict[str, Any]:
        candidates = self.import_keywords(seeds or list(self.config.get("seed_keywords", [])), imports or [])
        pages = self.existing_pages()
        slugs = {row["slug"] for row in pages}
        clusters = build_clusters(candidates, slugs)
        competitors = analyze_competitors(clusters)
        gaps = analyze_gaps(clusters, slugs)
        links = plan_internal_links(gaps, pages)
        opportunities = score_opportunities(gaps, clusters, self.config.get("scoring_weights"))
        files = {
            "clusters": self._write("keyword_clusters.json", clusters),
            "competitors": self._write("competitor_analysis.json", competitors),
            "gaps": self._write("content_gaps.json", gaps),
            "links": self._write("internal_link_plan.json", links),
            "opportunities": self._write("opportunities.json", opportunities),
        }
        report = {"generated_at": datetime.now(UTC).isoformat(), "mode": "offline_deterministic", "counts": {"candidates": len(candidates), "clusters": len(clusters), "gaps": len(gaps), "links": len(links), "opportunities": len(opportunities)}, "files": {key: str(value) for key, value in files.items()}, "limitations": ["No live SERP volume or competitor claims are generated without imported evidence."]}
        report_path = self._write("pipeline_report.json", report)
        report["dashboard"] = str(self.render_dashboard(opportunities))
        report["report_path"] = str(report_path)
        return report

    def render_dashboard(self, opportunities: list[dict[str, Any]] | None = None) -> Path:
        opportunities = opportunities if opportunities is not None else self._read(self.data_dir / "opportunities.json", [])
        rows = "".join(f"<tr data-intent='{html.escape(str(row['search_intent']))}' data-decision='{html.escape(str(row['decision']))}'><td>{html.escape(str(row['keyword']))}</td><td>{html.escape(str(row['search_intent']))}</td><td>{html.escape(str(row['decision']))}</td><td>{row['opportunity_score']}</td><td>{html.escape(str(row['slug']))}</td></tr>" for row in opportunities)
        body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SEO Opportunity Dashboard</title><style>body{{font:15px Arial;margin:0;color:#172033;background:#f5f7fa}}main{{max-width:1200px;margin:auto;padding:24px}}.kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.kpi,table{{background:#fff;border:1px solid #d8e0e8;border-radius:6px}}.kpi{{padding:16px}}table{{width:100%;border-collapse:collapse;margin-top:18px}}th,td{{padding:11px;border-bottom:1px solid #e6ebf0;text-align:left}}select{{padding:8px;margin-right:8px}}@media(max-width:700px){{.kpis{{grid-template-columns:1fr}}table{{display:block;overflow-x:auto}}}}</style></head><body><main><h1>SEO Opportunity Dashboard</h1><div class="kpis"><div class="kpi">Opportunities<br><strong>{len(opportunities)}</strong></div><div class="kpi">Create<br><strong>{sum(row['decision']=='create' for row in opportunities)}</strong></div><div class="kpi">Needs human review<br><strong>{sum(bool(row['requires_human_review']) for row in opportunities)}</strong></div></div><p><select id="intent"><option value="">All intents</option><option>commercial</option><option>informational</option><option>transactional</option><option>navigational</option></select><select id="decision"><option value="">All decisions</option><option>create</option><option>update</option><option>merge</option></select></p><table><thead><tr><th>Keyword</th><th>Intent</th><th>Decision</th><th>Score</th><th>Slug</th></tr></thead><tbody>{rows}</tbody></table></main><script>for(const id of ['intent','decision'])document.getElementById(id).onchange=()=>{{for(const row of document.querySelectorAll('tbody tr'))row.hidden=!!((intent.value&&row.dataset.intent!==intent.value)||(decision.value&&row.dataset.decision!==decision.value))}}</script></body></html>"""
        path = self.data_dir / "seo_dashboard.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def queue_opportunities(self, slugs: list[str], *, batch_date: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        opportunities = self._read(self.data_dir / "opportunities.json", [])
        selected = [row for row in opportunities if row.get("slug") in set(slugs)]
        if len(selected) != len(set(slugs)):
            raise ValueError("One or more opportunity slugs are unknown.")
        existing = {row["slug"] for row in self.existing_pages()}
        duplicates = [row["slug"] for row in selected if row["slug"] in existing or row.get("decision") != "create"]
        if duplicates:
            raise ValueError(f"Existing or non-create opportunities cannot be queued: {', '.join(duplicates)}")
        target_date = batch_date or date.today().isoformat()
        queue_path = self.root / "data" / "editorial_queue" / target_date / "topics.json"
        current = self._read(queue_path, {"generated_at": "", "date": target_date, "mode": "seo_engine", "count": 0, "topics": []})
        queued_slugs = {str(row.get("slug")) for row in current.get("topics", [])}
        additions = [{"keyword": row["keyword"], "slug": row["slug"], "search_intent": row["search_intent"], "content_type": row["suggested_content_type"], "status": "selected", "source": "seo_engine", "requires_human_approval": True, "opportunity_score": row["opportunity_score"]} for row in selected if row["slug"] not in queued_slugs]
        result = {"dry_run": dry_run, "date": target_date, "queue_path": str(queue_path), "queued": additions, "approval_changed": False, "published": False}
        if not dry_run:
            current["topics"] = list(current.get("topics", [])) + additions
            current["count"] = len(current["topics"])
            current["generated_at"] = datetime.now(UTC).isoformat()
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            queue_path.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return result
