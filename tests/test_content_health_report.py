from __future__ import annotations

import hashlib
import json
from pathlib import Path

from modules.content_health_report import (
    HOMEPAGE_SECTIONS,
    TRUST_ROUTES,
    audit_content_health,
    format_content_health,
)
from scripts.report_content_health import main


BASE = "https://smileaireviewhub.com"


def _write_page(
    root: Path,
    route: str,
    *,
    title: str,
    description: str = "A useful description.",
    canonical: str | None = None,
    links: str = "",
    related: bool = True,
    schema: bool = True,
    og: bool = True,
    words: int = 520,
) -> None:
    folder = root / route.strip("/")
    folder.mkdir(parents=True, exist_ok=True)
    canonical = canonical if canonical is not None else f"{BASE}/{route.strip('/')}/"
    og_html = (
        f"<meta property='og:title' content='{title}'><meta property='og:description' content='{description}'>"
        f"<meta property='og:type' content='article'><meta property='og:url' content='{canonical}'>"
        if og
        else ""
    )
    schema_html = (
        '<script type="application/ld+json">'
        + json.dumps({"@context": "https://schema.org", "@type": "Article", "headline": title})
        + "</script>"
        if schema
        else ""
    )
    related_html = "<section class='related-content'>Related</section>" if related else ""
    body = " ".join(["evidence"] * words)
    html = (
        f"<html><head><title>{title}</title><meta name='description' content='{description}'>"
        f"<link rel='canonical' href='{canonical}'>{og_html}{schema_html}</head>"
        f"<body><h1>{title}</h1><p>{body}</p>{links}{related_html}</body></html>"
    )
    (folder / "index.html").write_text(html, encoding="utf-8")


def _write_required_shell(root: Path) -> None:
    headings = "".join(f"<h2>{heading}</h2>" for heading in HOMEPAGE_SECTIONS)
    (root / "index.html").write_text(
        f"<html><head><title>Home</title></head><body>{headings} affiliate disclosure</body></html>",
        encoding="utf-8",
    )
    for route in TRUST_ROUTES:
        folder = root / route.strip("/")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(
            f"<html><head><title>{route}</title></head><body><h1>{route}</h1></body></html>",
            encoding="utf-8",
        )


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_content_health_reports_missing_metadata_and_broken_links(tmp_path: Path) -> None:
    _write_required_shell(tmp_path)
    _write_page(
        tmp_path,
        "good-review",
        title="Good Review",
        links="<a href='/missing-target/'>Missing</a>",
    )
    _write_page(
        tmp_path,
        "metadata-gap",
        title="Metadata Gap",
        description="",
        og=False,
        schema=False,
        related=False,
        words=20,
    )
    sitemap = (
        "<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        f"<url><loc>{BASE}/good-review/</loc></url></urlset>"
    )
    (tmp_path / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    report = audit_content_health(tmp_path, base_url=BASE)
    assert report["summary"]["published_article_count"] == 2
    assert report["summary"]["broken_local_internal_link_count"] == 1
    assert report["summary"]["missing_description_count"] == 1
    assert report["summary"]["missing_open_graph_count"] == 1
    assert report["summary"]["missing_structured_data_count"] == 1
    assert report["summary"]["no_related_content_count"] == 1
    assert report["summary"]["thin_content_warning_count"] == 1
    assert report["summary"]["sitemap_listed_count"] == 1
    assert report["summary"]["sitemap_not_listed_count"] == 1
    assert all(report["trust_pages"].values())
    assert all(report["homepage_sections"].values())
    assert report["affiliate_disclosure_present"] is True


def test_content_health_is_read_only(tmp_path: Path) -> None:
    _write_required_shell(tmp_path)
    _write_page(tmp_path, "product-review", title="Review")
    before = _tree_hash(tmp_path)
    report = audit_content_health(tmp_path, base_url=BASE)
    after = _tree_hash(tmp_path)
    assert report["read_only"] is True
    assert before == after


def test_content_health_json_cli_and_human_output(tmp_path: Path, capsys) -> None:
    _write_required_shell(tmp_path)
    _write_page(tmp_path, "product-review", title="Review")
    assert main(["--root", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["read_only"] is True
    assert payload["summary"]["published_article_count"] == 1

    assert main(["--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "Content Health Report" in output
    assert "Read-only: YES" in output


def test_content_health_format_does_not_claim_google_indexing(tmp_path: Path) -> None:
    _write_required_shell(tmp_path)
    _write_page(tmp_path, "review", title="Review")
    output = format_content_health(audit_content_health(tmp_path, base_url=BASE))
    assert "indexed by Google" not in output
    assert "Sitemap listed" in output
