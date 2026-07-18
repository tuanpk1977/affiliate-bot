"""Reusable, repository-local platform configuration interfaces."""

from modules.platform.affiliate_data import (
    AffiliateCatalog,
    AffiliateLink,
    AffiliatePartner,
    AffiliateProduct,
    AffiliateValidationError,
    load_affiliate_catalog,
)
from modules.platform.affiliate_resolver import AffiliateResolution, resolve_affiliate_link
from modules.platform.site_profile import (
    DEFAULT_SITE_ID,
    SiteProfile,
    SiteProfileError,
    get_active_site_profile,
    list_site_profiles,
    load_site_profile,
    validate_site_profile,
)

__all__ = [
    "AffiliateCatalog",
    "AffiliateLink",
    "AffiliatePartner",
    "AffiliateProduct",
    "AffiliateResolution",
    "AffiliateValidationError",
    "DEFAULT_SITE_ID",
    "SiteProfile",
    "SiteProfileError",
    "get_active_site_profile",
    "list_site_profiles",
    "load_affiliate_catalog",
    "load_site_profile",
    "resolve_affiliate_link",
    "validate_site_profile",
]
