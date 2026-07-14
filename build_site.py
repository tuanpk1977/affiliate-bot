from __future__ import annotations

import argparse
import filecmp
import shutil
from pathlib import Path

from config import settings
from modules.content_approval import publish_static_draft
from modules.bilingual_site import add_bilingual_pages
from modules.facebook_meta import post_process_facebook_meta
from modules.sitemap_generator import generate_sitemap
from modules.trust_localization_upgrade import enhance_site
from modules.gsc_404_recovery import write_gsc_404_recovery_pages
from modules.homepage_crawl_sections import enrich_homepage_crawl_sections
from modules.internal_linker import post_process_internal_links
from modules.legacy_slug_normalizer import normalize_legacy_slugs
from modules.canonical_routes import apply_canonical_routing
from modules.seo_ai_search_upgrade import apply_seo_ai_search_upgrade
from modules.seo_title_optimizer import optimize_site_titles
from modules.seo_technical_cleanup import apply_technical_seo_cleanup
from modules.structured_data_upgrade import apply_structured_data_upgrade
from modules.topical_hubs import write_topical_hubs
from modules.site_verification_meta import apply_pinterest_domain_verification


def sync_root_verification_files() -> int:
    copied = 0
    root = Path(__file__).resolve().parent
    patterns = (
        "yandex_*.html",
        "*.txt",
        "sw.js",
    )
    excluded = {
        "requirements.txt",
    }
    for pattern in patterns:
        for source in root.glob(pattern):
            if source.name in excluded or source.name.endswith(".local-backup"):
                continue
            if copy_if_changed(source, settings.site_output_dir / source.name):
                copied += 1
    return copied


def copy_if_changed(source: Path, target: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and filecmp.cmp(source, target, shallow=False):
        return False
    shutil.copy2(source, target)
    return True


def sync_published_pages() -> dict[str, int]:
    source_root = settings.data_dir / "published_static_pages"
    changed = 0
    scanned = 0
    if not source_root.exists():
        return {"scanned": 0, "changed": 0}
    for source in sorted(source_root.glob("*/index.html")):
        scanned += 1
        slug = source.parent.name
        target = settings.site_output_dir / slug / "index.html"
        if copy_if_changed(source, target):
            changed += 1
    return {"scanned": scanned, "changed": changed}


def sync_article_visuals() -> int:
    source_root = Path(__file__).resolve().parent / "assets" / "article-visuals"
    if not source_root.exists():
        return 0
    changed = 0
    target_root = settings.site_output_dir / "assets" / "article-visuals"
    for source in sorted(source_root.glob("*")):
        if source.is_file() and copy_if_changed(source, target_root / source.name):
            changed += 1
    return changed


def sync_public_article_assets() -> int:
    source_root = Path(__file__).resolve().parent / "assets"
    changed = 0
    target_root = settings.site_output_dir / "assets"
    for name in ("article.css", "public-article.css"):
        source = source_root / name
        if source.exists() and copy_if_changed(source, target_root / name):
            changed += 1
    return changed


def incremental_build() -> dict[str, object]:
    settings.site_output_dir.mkdir(parents=True, exist_ok=True)
    verification_files_changed = sync_root_verification_files()
    sync_stats = sync_published_pages()
    article_visuals_changed = sync_article_visuals()
    public_article_assets_changed = sync_public_article_assets()
    technical_stats = apply_technical_seo_cleanup(settings.site_output_dir)
    add_bilingual_pages(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    final_technical_stats = apply_technical_seo_cleanup(settings.site_output_dir)
    technical_stats["review_pages_changed"] = technical_stats.get("review_pages_changed", 0) + final_technical_stats.get("review_pages_changed", 0)
    technical_stats["cloudflare_go_redirect_rules"] = final_technical_stats.get("cloudflare_go_redirect_rules", 0)
    write_gsc_404_recovery_pages(settings.site_output_dir)
    hub_stats = write_topical_hubs(settings.site_output_dir)
    enhance_site(settings.site_output_dir)
    homepage_stats = enrich_homepage_crawl_sections(settings.site_output_dir)
    internal_link_stats = post_process_internal_links(settings.site_output_dir)
    seo_ai_stats = apply_seo_ai_search_upgrade(settings.site_output_dir)
    facebook_stats = post_process_facebook_meta(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    title_stats = optimize_site_titles(settings.site_output_dir)
    legacy_slug_stats = normalize_legacy_slugs(settings.site_output_dir)
    schema_stats = apply_structured_data_upgrade(settings.site_output_dir)
    canonical_stats = apply_canonical_routing(settings.site_output_dir)
    pinterest_stats = apply_pinterest_domain_verification(settings.site_output_dir)
    sitemap_path = generate_sitemap(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    return {
        "mode": "incremental",
        "published_pages_scanned": sync_stats["scanned"],
        "published_pages_changed": sync_stats["changed"],
        "verification_files_changed": verification_files_changed,
        "article_visuals_changed": article_visuals_changed,
        "public_article_assets_changed": public_article_assets_changed,
        "sitemap": str(sitemap_path),
        "facebook_meta_pages": facebook_stats.get("pages", 0),
        "facebook_meta_changed": facebook_stats.get("changed", 0),
        "internal_link_pages": internal_link_stats.get("pages", 0),
        "internal_links_added": internal_link_stats.get("links_added", 0),
        "seo_ai_pages": seo_ai_stats.get("pages", 0),
        "seo_ai_changed": seo_ai_stats.get("changed", 0),
        "seo_ai_faq_schemas_added": seo_ai_stats.get("faq_schemas_added", 0),
        "seo_ai_breadcrumbs_added": seo_ai_stats.get("breadcrumbs_added", 0),
        "seo_titles_changed": title_stats.get("changed", 0),
        "seo_titles_remaining_long": title_stats.get("remaining_long", 0),
        "legacy_slug_pages_changed": legacy_slug_stats.get("changed", 0),
        "legacy_slug_replacements": legacy_slug_stats.get("replacements", 0),
        "structured_data_changed": schema_stats.get("changed", 0),
        "structured_data_review_pages": schema_stats.get("review_pages", 0),
        "structured_data_comparison_pages": schema_stats.get("comparison_pages", 0),
        "structured_data_video_pages": schema_stats.get("video_pages", 0),
        "canonical_pages": canonical_stats.get("canonical_pages", 0),
        "canonical_pages_changed": canonical_stats.get("canonical_pages_changed", 0),
        "canonical_redirect_rules": canonical_stats.get("canonical_redirect_rules", 0),
        "pinterest_meta_pages": pinterest_stats.get("scanned", 0),
        "pinterest_meta_changed": pinterest_stats.get("changed", 0),
        "public_review_pages_changed": technical_stats.get("review_pages_changed", 0),
        "cloudflare_go_redirect_rules": technical_stats.get("cloudflare_go_redirect_rules", 0),
        "topical_hubs_written": hub_stats.get("topical_hubs_written", 0),
        "homepage_crawl_sections": homepage_stats.get("homepage_crawl_sections", 0),
    }


def full_build() -> dict[str, object]:
    from main import main

    main()
    verification_files_changed = sync_root_verification_files()
    article_visuals_changed = sync_article_visuals()
    public_article_assets_changed = sync_public_article_assets()
    hub_stats = write_topical_hubs(settings.site_output_dir)
    homepage_stats = enrich_homepage_crawl_sections(settings.site_output_dir)
    internal_link_stats = post_process_internal_links(settings.site_output_dir)
    seo_ai_stats = apply_seo_ai_search_upgrade(settings.site_output_dir)
    title_stats = optimize_site_titles(settings.site_output_dir)
    legacy_slug_stats = normalize_legacy_slugs(settings.site_output_dir)
    schema_stats = apply_structured_data_upgrade(settings.site_output_dir)
    canonical_stats = apply_canonical_routing(settings.site_output_dir)
    pinterest_stats = apply_pinterest_domain_verification(settings.site_output_dir)
    sitemap_path = generate_sitemap(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    return {
        "mode": "full",
        "site_output": str(settings.site_output_dir),
        "verification_files_changed": verification_files_changed,
        "article_visuals_changed": article_visuals_changed,
        "public_article_assets_changed": public_article_assets_changed,
        "sitemap": str(sitemap_path),
        "internal_link_pages": internal_link_stats.get("pages", 0),
        "internal_links_added": internal_link_stats.get("links_added", 0),
        "seo_ai_pages": seo_ai_stats.get("pages", 0),
        "seo_ai_changed": seo_ai_stats.get("changed", 0),
        "seo_titles_changed": title_stats.get("changed", 0),
        "seo_titles_remaining_long": title_stats.get("remaining_long", 0),
        "legacy_slug_pages_changed": legacy_slug_stats.get("changed", 0),
        "legacy_slug_replacements": legacy_slug_stats.get("replacements", 0),
        "structured_data_changed": schema_stats.get("changed", 0),
        "canonical_pages": canonical_stats.get("canonical_pages", 0),
        "canonical_pages_changed": canonical_stats.get("canonical_pages_changed", 0),
        "canonical_redirect_rules": canonical_stats.get("canonical_redirect_rules", 0),
        "pinterest_meta_pages": pinterest_stats.get("scanned", 0),
        "pinterest_meta_changed": pinterest_stats.get("changed", 0),
        "topical_hubs_written": hub_stats.get("topical_hubs_written", 0),
        "homepage_crawl_sections": homepage_stats.get("homepage_crawl_sections", 0),
    }


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Build AI Tool Review Hub static output.")
    parser.add_argument("--full", action="store_true", help="Run the full legacy pipeline.")
    parser.add_argument("--publish-draft", default="", help="Publish one Approved draft id before syncing.")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting an existing slug when publishing a draft.")
    args = parser.parse_args()

    if args.full:
        result = full_build()
    else:
        if args.publish_draft:
            ok, message = publish_static_draft(args.publish_draft, overwrite=args.overwrite)
            print(f"publish_draft={args.publish_draft} ok={ok} message={message}")
            if not ok:
                raise SystemExit(1)
        result = incremental_build()

    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main_cli()
