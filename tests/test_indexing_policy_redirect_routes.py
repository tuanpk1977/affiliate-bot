from modules.indexing_policy import REDIRECT_ROBOTS_META, robots_meta_for_path, should_include_in_sitemap


REDIRECT_ROUTES = (
    "/surfer-seo-pricing-2026/",
    "/vi/surfer-seo-pricing-2026/",
    "/vi/marketing-software-review/",
    "/vi/crm-alternatives/",
)


def test_legacy_redirect_routes_remain_noindex_and_out_of_sitemap():
    for route in REDIRECT_ROUTES:
        assert robots_meta_for_path(route) == REDIRECT_ROBOTS_META
        assert should_include_in_sitemap(route) is False
