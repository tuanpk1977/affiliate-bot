from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
import json
import re

from modules.operational_health import HealthAudit, PageHealth


CLUSTERS = {
    "AI Coding Tools": {"coding", "code", "developer", "github", "cursor", "copilot", "ide"},
    "AI Agents": {"agent", "agents", "agentic", "autonomous"},
    "AI Search": {"search", "perplexity", "gemini", "retrieval"},
    "AI Video Tools": {"video", "synthesia", "pictory", "runway"},
    "AI Writing Tools": {"writing", "writer", "copy", "grammar", "jasper"},
    "AI Design Tools": {"design", "image", "canva", "framer", "webflow"},
    "AI Automation": {"automation", "workflow", "zapier", "make"},
    "AI Productivity": {"productivity", "meeting", "notion", "assistant"},
    "AI Business Tools": {"business", "marketing", "crm", "sales", "email", "seo"},
}


def tokens(page: PageHealth) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9]+", f"{page.title} {page.url}".casefold()))


def assign_cluster(page: PageHealth) -> str:
    page_tokens = tokens(page)
    ranked = [(len(page_tokens & keywords), name) for name, keywords in CLUSTERS.items()]
    score, name = max(ranked)
    return name if score else "AI Business Tools"


def topic_cluster_rows(audit: HealthAudit) -> list[dict[str, object]]:
    grouped: dict[str, list[PageHealth]] = defaultdict(list)
    for page in audit.indexable_pages:
        grouped[assign_cluster(page)].append(page)
    rows = []
    for cluster, pages in sorted(grouped.items()):
        hub = next((page.url for page in pages if any(value in page.url for value in ("/category/", "/hub", "/best-"))), "")
        for page in pages:
            candidates = []
            source_tokens = tokens(page)
            for target in pages:
                if target.url == page.url:
                    continue
                overlap = len(source_tokens & tokens(target))
                candidates.append((overlap, target.url))
            related = [url for _, url in sorted(candidates, reverse=True)[:5]]
            rows.append(
                {
                    "cluster": cluster,
                    "url": page.url,
                    "title": page.title,
                    "hub_url": hub,
                    "hub_status": "existing" if hub else "recommended",
                    "related_links": related,
                }
            )
    return rows


def write_topic_clusters(audit: HealthAudit, report_dir: Path) -> tuple[Path, Path]:
    rows = topic_cluster_rows(audit)
    json_path = report_dir / "topic-clusters.json"
    json_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    lines = ["# Topic Clusters", ""]
    current = ""
    for row in rows:
        if row["cluster"] != current:
            current = str(row["cluster"])
            lines.extend([f"## {current}", f"- Hub: {row['hub_url'] or 'Create a cluster hub page'}"])
        lines.append(f"- [{row['title']}]({row['url']})")
        lines.extend(f"  - Related: {url}" for url in row["related_links"])
    md_path = report_dir / "topic-clusters.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def refresh_queue(audit: HealthAudit) -> list[dict[str, object]]:
    duplicate_title_urls = {url for urls in audit.duplicate_titles.values() for url in urls}
    duplicate_h1_urls = {url for urls in audit.duplicate_h1.values() for url in urls}
    rows = []
    for page in audit.indexable_pages:
        if not any(value in page.schema_types for value in ("Article", "BlogPosting", "Review")):
            continue
        reasons = []
        if not page.faq_ok:
            reasons.append("missing FAQ")
        if not page.author_ok:
            reasons.append("missing or invalid author")
        if not page.breadcrumb_ok:
            reasons.append("missing breadcrumb")
        if page.word_count < 900:
            reasons.append("low word count")
        if len(page.internal_links) < 2:
            reasons.append("weak internal links")
        if not page.external_links:
            reasons.append("missing authority reference")
        if page.url in duplicate_title_urls:
            reasons.append("duplicate title")
        if page.url in duplicate_h1_urls:
            reasons.append("duplicate H1")
        if reasons:
            score = min(100, 25 + len(reasons) * 12 + (20 if "missing or invalid author" in reasons else 0))
            rows.append({"priority": score, "url": page.url, "title": page.title, "reasons": reasons})
    return sorted(rows, key=lambda row: int(row["priority"]), reverse=True)


def write_refresh_queue(audit: HealthAudit, report_dir: Path) -> Path:
    rows = refresh_queue(audit)
    path = report_dir / "content-refresh-queue.md"
    lines = ["# Content Refresh Queue", "", f"Pages queued: {len(rows)}", ""]
    for row in rows:
        lines.extend(
            [
                f"## {row['title']}",
                f"- URL: {row['url']}",
                f"- Priority: {row['priority']}",
                f"- Reasons: {', '.join(row['reasons'])}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_social_drafts(pages: list[PageHealth], report_dir: Path) -> Path:
    target = report_dir / "social-posts" / date.today().isoformat()
    target.mkdir(parents=True, exist_ok=True)
    for page in pages:
        slug = page.url.rstrip("/").rsplit("/", 1)[-1] or "home"
        title = page.title
        posts = {
            "facebook-en": f"{title}\n\nA practical buyer-focused guide with limitations, alternatives, and verification steps.\n\nRead: {page.url}\n\n#AITools #SaaS",
            "facebook-vi": f"{title}\n\nBài phân tích thực tế về tính phù hợp, hạn chế và các lựa chọn thay thế.\n\nXem bài: {page.url}\n\n#CongCuAI #SaaS",
            "linkedin": f"{title}\n\nA buyer-focused breakdown of workflow fit, tradeoffs, and what to verify before adopting the tool.\n\n{page.url}\n\n#ArtificialIntelligence #Software",
            "x": f"{title}\nPractical fit, limitations, and alternatives: {page.url} #AITools #SaaS",
            "quora": f"When evaluating this topic, start with workflow fit rather than feature count. This guide covers the main tradeoffs and verification steps: {page.url}",
            "devto": f"# {title}\n\nA concise practical guide for developers and software buyers. Read the full analysis: {page.url}",
        }
        for platform, body in posts.items():
            (target / f"{slug}-{platform}.txt").write_text(body + "\n", encoding="utf-8")
    return target


def write_auto_repair_report(
    before: dict[str, object],
    repair: dict[str, object],
    after: dict[str, object],
    report_dir: Path,
) -> tuple[Path, Path]:
    payload = {"before": before, "repair": repair, "after": after}
    json_path = report_dir / "auto-repair-report.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# SEO Auto-Repair Report",
        "",
        f"- Issues before: {before}",
        f"- Files/URLs repaired: {len(repair.get('repaired', []))}",
        f"- Issues remaining: {after}",
        f"- Validation: {'PASS' if after.get('status') == 'PASS' else 'NEEDS REVIEW'}",
        "",
        "## Repaired URLs",
        *[f"- {url}" for url in repair.get("repaired", [])],
        "",
        "## Unresolved",
    ]
    for url, errors in repair.get("unresolved", {}).items():
        lines.append(f"- {url}: {'; '.join(errors)}")
    md_path = report_dir / "auto-repair-report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path
