"""Fail-closed affiliate link selection for validated repository data."""

from __future__ import annotations

from dataclasses import dataclass

from modules.platform.affiliate_data import ACTIVE_STATUS, AffiliateCatalog, AffiliateLink
from modules.platform.site_profile import SiteProfile


@dataclass(frozen=True)
class AffiliateResolution:
    """A safe resolution result that never fabricates or guesses a URL."""

    status: str
    reason: str
    site_id: str
    partner_id: str = ""
    product_id: str = ""
    category: str = ""
    affiliate_url: str = ""
    destination_domain: str = ""
    disclosure_required: bool = False
    disclosure_text: str = ""


def _country_eligible(country: str, link: AffiliateLink, partner_countries: tuple[str, ...]) -> bool:
    requested = country.strip().upper()
    if not requested:
        return True
    allowed = link.supported_countries or partner_countries
    return not allowed or requested in allowed


def resolve_affiliate_link(
    catalog: AffiliateCatalog,
    profile: SiteProfile,
    *,
    partner_id: str | None = None,
    product_id: str | None = None,
    category: str | None = None,
    country: str | None = None,
) -> AffiliateResolution:
    """Resolve one unambiguous active link, or return a non-eligible status."""

    if catalog.site_id != profile.site_id:
        return AffiliateResolution(
            status="invalid_site",
            reason="Affiliate catalog site_id does not match the selected site profile.",
            site_id=profile.site_id,
        )
    partners = {partner.partner_id: partner for partner in catalog.partners}
    products = {product.product_id: product for product in catalog.products}
    requested_partner = str(partner_id or "").strip()
    requested_product = str(product_id or "").strip()
    requested_category = str(category or "").strip().casefold()
    requested_country = str(country or "").strip()

    eligible: list[AffiliateLink] = []
    for link in catalog.links:
        partner = partners.get(link.partner_id)
        product = products.get(link.product_id) if link.product_id else None
        if link.status != ACTIVE_STATUS or partner is None or partner.status != ACTIVE_STATUS:
            continue
        if product is not None and product.status != ACTIVE_STATUS:
            continue
        if requested_partner and link.partner_id != requested_partner:
            continue
        if requested_product and link.product_id != requested_product:
            continue
        if requested_category and link.category.casefold() != requested_category:
            continue
        if not _country_eligible(requested_country, link, partner.supported_countries):
            continue
        eligible.append(link)

    if not eligible:
        return AffiliateResolution(
            status="no_eligible_affiliate_link",
            reason="No active affiliate link matches all requested constraints.",
            site_id=profile.site_id,
            partner_id=requested_partner,
            product_id=requested_product,
            category=str(category or "").strip(),
        )
    if len(eligible) > 1:
        return AffiliateResolution(
            status="ambiguous",
            reason="More than one active affiliate link matches; provide a partner_id or product_id.",
            site_id=profile.site_id,
            partner_id=requested_partner,
            product_id=requested_product,
            category=str(category or "").strip(),
        )

    selected = eligible[0]
    return AffiliateResolution(
        status="eligible",
        reason="One verified active affiliate link matched the requested constraints.",
        site_id=profile.site_id,
        partner_id=selected.partner_id,
        product_id=selected.product_id,
        category=selected.category,
        affiliate_url=selected.affiliate_url,
        destination_domain=selected.destination_domain,
        disclosure_required=selected.disclosure_required,
        disclosure_text=profile.affiliate_disclosure if selected.disclosure_required else "",
    )
