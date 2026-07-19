from __future__ import annotations

import json
from pathlib import Path

from modules.public_content_hub import (
    PublishedContent,
    discover_published_content,
    render_homepage_content_hub,
    resolve_related_content,
)
from modules.public_page_metadata import (
    article_structured_data,
    faq_structured_data,
    homepage_structured_data,
    render_social_metadata,
)
from modules.site_builder import (
    legal_pages,
    page_shell,
    write_about_page,
    write_index,
    write_legal_pages,
    write_trust_pages,
)


BASE = "https://smileaireviewhub.com"


def _record(
    slug: str,
    *,
    content_type: str = "review",
    category: str = "ai_tools",
) -> PublishedContent:
    return PublishedContent(
        title=slug.replace("-", " ").title(),
        url=f"{BASE}/{slug}/",
        excerpt=f"Evidence-based notes about {slug}.",
        content_type=content_type,
        category=category,
        published_date="2026-07-19",
    )


def test_homepage_hub_has_required_sections_without_empty_categories(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BASE_SITE_URL", BASE)
    (tmp_path / "assets" / "og").mkdir(parents=True)
    (tmp_path / "assets" / "og" / "home.svg").write_text("<svg/>", encoding="utf-8")
    pages = [
        {
            "slug": "marketing-automation-review",
            "brand_name": "Marketing Automation Review",
            "description": "A practical marketing automation review.",
            "niche": "Marketing Automation",
            "score": "80",
            "risk": "LOW",
            "url_path": "/marketing-automation-review/",
        },
        {
            "slug": "make-vs-zapier",
            "brand_name": "Make vs Zapier",
            "description": "A workflow comparison.",
            "niche": "Automation",
            "score": "78",
            "risk": "LOW",
            "url_path": "/make-vs-zapier/",
        },
        {
            "slug": "how-to-test-ai-tools",
            "brand_name": "How to Test AI Tools",
            "description": "A practical tutorial.",
            "niche": "AI",
            "score": "76",
            "risk": "LOW",
            "url_path": "/how-to-test-ai-tools/",
        },
        {
            "slug": "best-ai-tools-buying-guide",
            "brand_name": "Best AI Tools Buying Guide",
            "description": "A buyer-focused guide.",
            "niche": "AI",
            "score": "75",
            "risk": "LOW",
            "url_path": "/best-ai-tools-buying-guide/",
        },
    ]
    published_root = tmp_path / "published"
    published_root.mkdir()
    write_index(tmp_path, pages, published_root=published_root)
    rendered = (tmp_path / "index.html").read_text(encoding="utf-8")

    for heading in (
        "Featured Reviews",
        "Best AI Tools",
        "Latest Comparisons",
        "Practical Tutorials",
        "Buying Guides",
        "Recently Published",
    ):
        assert f"<h2>{heading}</h2>" in rendered
    assert "/how-we-review/" in rendered
    assert "AI Video Tools" not in rendered
    assert 'href="/review/' not in rendered
    assert '<meta charset="utf-8">' in rendered
    assert "og:url" in rendered
    assert "twitter:title" in rendered


def test_seven_required_trust_pages_are_generated_safely(tmp_path: Path) -> None:
    write_about_page(tmp_path)
    write_trust_pages(tmp_path)
    write_legal_pages(tmp_path)
    routes = (
        "about",
        "editorial-policy",
        "how-we-review",
        "affiliate-disclosure",
        "contact",
        "privacy-policy",
        "terms",
    )
    combined = ""
    for route in routes:
        path = tmp_path / route / "index.html"
        assert path.is_file(), route
        text = path.read_text(encoding="utf-8")
        assert "D:\\" not in text
        assert "API_KEY" not in text
        combined += text
    assert "We do not claim every product has been purchased or tested." in combined
    assert "does not add a separate charge" in combined
    assert "Affiliate commission does not change the price paid by the buyer." not in combined


def test_related_resolver_is_published_only_deduplicated_and_bounded() -> None:
    current = _record("marketing-automation-review", category="marketing_automation")
    candidates = [
        current,
        _record("marketing-automation-vs-crm", content_type="comparison", category="marketing_automation"),
        _record("marketing-automation-tutorial", content_type="tutorial", category="marketing_automation"),
        _record("marketing-automation-buying-guide", content_type="buying_guide", category="marketing_automation"),
        _record("marketing-automation-pricing", content_type="buying_guide", category="marketing_automation"),
        _record("marketing-automation-alternatives", content_type="comparison", category="marketing_automation"),
        _record("marketing-automation-alternatives", content_type="comparison", category="marketing_automation"),
    ]
    resolved = resolve_related_content(current.url, candidates, max_links=99)
    assert len(resolved) == 5
    assert current not in resolved
    assert len({item.url for item in resolved}) == len(resolved)
    assert resolved == resolve_related_content(current.url, candidates, max_links=99)


def test_related_resolver_returns_empty_for_missing_topic_match() -> None:
    resolved = resolve_related_content(
        f"{BASE}/unrelated-page/",
        [_record("video-generation-review", category="ai_video")],
    )
    assert resolved == []


def test_social_metadata_uses_valid_image_and_keeps_canonical(tmp_path: Path) -> None:
    image = tmp_path / "hero.webp"
    image.write_bytes(b"webp")
    canonical = f"{BASE}/example/"
    rendered = render_social_metadata(
        title="Example",
        description="Example description",
        canonical=canonical,
        site_name="Smile AI Review Hub",
        page_type="article",
        image_url=f"{BASE}/assets/hero.webp",
        image_path=image,
    )
    assert f'content="{canonical}"' in rendered
    assert "og:url" in rendered
    assert "og:site_name" in rendered
    assert "twitter:title" in rendered
    assert "twitter:description" in rendered
    assert "twitter:image" in rendered
    assert rendered.count("og:title") == 1

    without_image = render_social_metadata(
        title="Example",
        description="Example description",
        canonical=canonical,
        site_name="Smile AI Review Hub",
        page_type="article",
        image_url=f"{BASE}/assets/missing.webp",
        image_path=tmp_path / "missing.webp",
    )
    assert "og:image" not in without_image
    assert "twitter:image" not in without_image
    assert 'twitter:card" content="summary"' in without_image


def test_structured_data_is_valid_and_contains_no_fake_rating() -> None:
    homepage = homepage_structured_data(
        site_name="Smile AI Review Hub",
        canonical=f"{BASE}/",
    )
    article = article_structured_data(
        title="AI Tool Review",
        description="A practical review.",
        canonical=f"{BASE}/ai-tool-review/",
        site_name="Smile AI Review Hub",
        author_name="Nguyen Quoc Tuan",
    )
    for item in [*homepage, *article]:
        reparsed = json.loads(json.dumps(item))
        assert reparsed["@context"] == "https://schema.org"
        assert "AggregateRating" not in json.dumps(item)
        assert "ratingValue" not in json.dumps(item)
    assert {item["@type"] for item in homepage} == {"Organization", "WebSite"}
    assert {item["@type"] for item in article} == {"Article", "BreadcrumbList"}


def test_faq_schema_requires_visible_explicit_items() -> None:
    assert faq_structured_data([]) is None
    schema = faq_structured_data([("What is checked?", "Pricing and workflow fit.")])
    assert schema is not None
    assert schema["@type"] == "FAQPage"
    assert len(schema["mainEntity"]) == 1


def test_page_shell_opt_in_related_content_and_safe_schema(monkeypatch) -> None:
    monkeypatch.setenv("BASE_SITE_URL", BASE)
    current = f"{BASE}/marketing-automation-review/"
    related = [
        _record("marketing-automation-comparison", content_type="comparison", category="marketing_automation")
    ]
    rendered = page_shell(
        "Marketing Automation Review",
        "A practical review.",
        "<h1>Marketing Automation Review</h1>",
        "/marketing-automation-review/",
        related_candidates=related,
    )
    assert "Related reading" in rendered
    assert "Related Comparison" in rendered
    assert current in rendered
    scripts = [
        part.split("</script>", 1)[0]
        for part in rendered.split('<script type="application/ld+json">')[1:]
    ]
    parsed = [json.loads(value) for value in scripts]
    assert {item["@type"] for item in parsed} == {"Article", "BreadcrumbList"}


def test_discovery_rejects_noncanonical_hosts(tmp_path: Path) -> None:
    valid = tmp_path / "valid"
    invalid = tmp_path / "invalid"
    valid.mkdir()
    invalid.mkdir()
    (valid / "index.html").write_text(
        f"<title>Valid</title><h1>Valid</h1><link rel='canonical' href='{BASE}/valid/'>",
        encoding="utf-8",
    )
    (invalid / "index.html").write_text(
        "<title>Invalid</title><h1>Invalid</h1><link rel='canonical' href='https://example.invalid/invalid/'>",
        encoding="utf-8",
    )
    records = discover_published_content(tmp_path, base_url=BASE)
    assert [item.url for item in records] == [f"{BASE}/valid/"]


def test_menu_entry_points_remain_present_and_unmodified_by_renderer_work() -> None:
    text = Path("runbot_menu.bat").read_text(encoding="utf-8", errors="replace")
    for entry in (
        "1. Week start",
        "2. Tue-Sun",
        "4. Open dashboard",
        "8. Publish approved",
        "F.",
        "G.",
    ):
        assert entry in text


def test_legal_page_source_has_no_absolute_price_claim() -> None:
    disclosure = legal_pages()["affiliate-disclosure"][1]
    assert "does not change the price paid by the buyer" not in disclosure
    assert "Partner terms vary" in disclosure
