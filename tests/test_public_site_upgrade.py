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
    base_css,
    community_proof_html,
    footer_html,
    legal_pages,
    newsletter_html,
    page_shell,
    popular_tools_this_week_html,
    write_about_page,
    write_index,
    write_legal_pages,
    write_og_images,
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


def test_public_preview_css_contains_responsive_overflow_guards() -> None:
    css = base_css()
    required = (
        "html,body{max-width:100%;overflow-x:hidden}",
        ".cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))",
        "@media(max-width:1024px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}",
        "@media(max-width:640px){.cards,.social-proof-grid{grid-template-columns:1fr}",
        ".content-card img,.card img{display:block;width:100%;max-width:100%;height:auto;aspect-ratio:16/9;object-fit:cover",
        "min-width:0;overflow:hidden",
        "white-space:normal;text-align:center",
        "a,a:visited{color:var(--link-color)}",
        "a:focus-visible{outline:3px solid var(--focus-ring);outline-offset:3px}",
        ".content-hub-section.single-card .cards{grid-template-columns:minmax(0,760px)}",
        ".content-hub-section.single-card .content-card{display:grid",
        ".author-box{border-left:4px solid #0f766e",
    )
    for snippet in required:
        assert snippet in css
    assert "language-switcher" not in css


def test_homepage_public_brand_claims_and_contact_are_safe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BASE_SITE_URL", BASE)
    (tmp_path / "assets" / "og").mkdir(parents=True)
    (tmp_path / "assets" / "og" / "home.svg").write_text("<svg/>", encoding="utf-8")
    published_root = tmp_path / "published"
    published_root.mkdir()
    article = published_root / "top-10-marketing-automation-software-platforms-for-businesses-in-2026"
    article.mkdir()
    (article / "index.html").write_text(
        f"""<!doctype html><html><head><title>Top 10 Marketing Automation Software Platforms</title>
        <meta name='description' content='A practical software buying guide.'>
        <link rel='canonical' href='{BASE}/top-10-marketing-automation-software-platforms-for-businesses-in-2026/'>
        </head><body><h1>Top 10 Marketing Automation Software Platforms</h1>
        <p>A practical software buying guide for small business teams.</p></body></html>""",
        encoding="utf-8",
    )

    write_index(tmp_path, [], published_root=published_root)
    rendered = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert "Smile AI Review Hub" in rendered
    assert "MS Smile AI Review Hub" not in rendered
    assert "Most Popular AI Tools This Week" not in rendered
    assert "Featured AI Tools" in rendered
    assert "75,000" not in rendered
    assert "language-switcher" not in rendered
    assert "?lang=" not in rendered
    assert "contact@smileaireviewhub.com" not in rendered
    assert "admin@smileaireviewhub.com" not in rendered
    assert "Â" not in rendered
    assert "Review pages</h2><div class=\"cards\"></div>" not in rendered
    assert "Latest Reviews</h2><div class=\"cards\"></div>" not in rendered


def test_footer_uses_canonical_trust_routes_without_unverified_email() -> None:
    rendered = footer_html()
    for route in (
        "/about/",
        "/editorial-policy/",
        "/how-we-review/",
        "/affiliate-disclosure/",
        "/contact/",
        "/privacy-policy/",
        "/terms/",
    ):
        assert f'href="{route}"' in rendered
    for legacy_or_unverified in (
        "/privacy/",
        "/disclosure/",
        "/testing-methodology/",
        "/author-profile/",
        "contact@smileaireviewhub.com",
        "admin@smileaireviewhub.com",
        "MS Smile AI Review Hub",
    ):
        assert legacy_or_unverified not in rendered


def test_featured_tools_are_backed_by_published_records_without_popularity_claim() -> None:
    rendered = popular_tools_this_week_html(
        [
            _record(
                "top-10-marketing-automation-software-platforms-for-businesses-in-2026",
                content_type="buying_guide",
                category="marketing_automation",
            )
        ]
    )
    assert "Featured AI Tools" in rendered
    assert "Most Popular" not in rendered
    assert f"{BASE}/top-10-marketing-automation-software-platforms-for-businesses-in-2026/" in rendered


def test_generated_og_fallback_assets_use_public_brand(tmp_path: Path) -> None:
    write_og_images(tmp_path, [])
    for relative in ("assets/og/home.svg", "assets/og/site.svg", "assets/og/blog.svg"):
        rendered = (tmp_path / relative).read_text(encoding="utf-8")
        assert "Smile AI Review Hub" in rendered
        assert "MS Smile AI Review Hub" not in rendered


def test_article_pages_include_real_author_box_and_author_schema(monkeypatch) -> None:
    monkeypatch.setenv("BASE_SITE_URL", BASE)
    rendered = page_shell(
        "AI Workflow Review",
        "A practical review.",
        "<h1>AI Workflow Review</h1><p>Useful source-backed review content.</p>",
        "/ai-workflow-review/",
    )
    assert "author-box" in rendered
    assert "Written by" in rendered
    assert "Nguyen Quoc Tuan" in rendered
    assert "/about-author/" in rendered
    assert "/author-profile/" not in rendered
    assert "Independent AI and SaaS researcher" in rendered
    scripts = [
        part.split("</script>", 1)[0]
        for part in rendered.split('<script type="application/ld+json">')[1:]
    ]
    article = next(json.loads(value) for value in scripts if json.loads(value).get("@type") == "Article")
    assert article["author"]["name"] == "Nguyen Quoc Tuan"
    assert article["author"]["url"].endswith("/about-author/")


def test_public_social_blocks_use_only_real_configured_links() -> None:
    combined = community_proof_html() + footer_html() + newsletter_html()
    assert "Follow Our Public Channels" in combined
    assert "Our Community Signals" not in combined
    assert "Metrics are based on public content activity" not in combined
    assert "href=\"#\"" not in combined
    assert "javascript:" not in combined.lower()
    assert "rel=\"me noopener noreferrer\"" in combined or "rel='me noopener noreferrer'" in combined
    assert "Blogger" not in combined
    assert "Pinterest" not in combined


def test_newsletter_block_does_not_render_fake_subscription_form() -> None:
    rendered = newsletter_html()
    assert "<form" not in rendered
    assert "type='email'" not in rendered
    assert 'type="email"' not in rendered
    assert "Subscribe" not in rendered
    assert "Newsletter integration coming soon." not in rendered
    assert "newsletter-links" in rendered


def test_single_item_homepage_sections_are_marked_for_featured_layout() -> None:
    rendered = render_homepage_content_hub(
        [_record("how-to-test-ai-tools", content_type="tutorial")],
        base_url=BASE,
    )
    assert "content-hub-section single-card" in rendered


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
