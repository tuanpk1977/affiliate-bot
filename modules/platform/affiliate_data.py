"""Validated affiliate partner, product, and link data contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from modules.platform.site_profile import SITE_ID_PATTERN, load_site_profile


ACTIVE_STATUS = "active"
ALLOWED_STATUSES = {"active", "inactive", "pending", "rejected", "expired"}
AFFILIATE_DIRECTORY = Path("data") / "sites"


class AffiliateValidationError(ValueError):
    """Raised when repository affiliate data is malformed or inconsistent."""


@dataclass(frozen=True)
class AffiliatePartner:
    partner_id: str
    company_name: str
    site_id: str
    category: str
    program_name: str
    affiliate_url: str
    destination_domain: str
    supported_countries: tuple[str, ...]
    commission_note: str
    cookie_duration_note: str
    disclosure_required: bool
    status: str
    last_verified_at: str
    operator_notes: str


@dataclass(frozen=True)
class AffiliateProduct:
    product_id: str
    partner_id: str
    product_name: str
    category: str
    destination_url: str
    affiliate_url: str
    coupon: str
    price_note: str
    currency: str
    availability_note: str
    status: str
    last_verified_at: str


@dataclass(frozen=True)
class AffiliateLink:
    link_id: str
    site_id: str
    partner_id: str
    product_id: str
    category: str
    affiliate_url: str
    destination_url: str
    destination_domain: str
    supported_countries: tuple[str, ...]
    disclosure_required: bool
    status: str
    last_verified_at: str
    operator_notes: str


@dataclass(frozen=True)
class AffiliateCatalog:
    site_id: str
    partners: tuple[AffiliatePartner, ...]
    products: tuple[AffiliateProduct, ...]
    links: tuple[AffiliateLink, ...]


PARTNER_FIELDS = (
    "partner_id",
    "company_name",
    "site_id",
    "category",
    "program_name",
    "affiliate_url",
    "destination_domain",
    "supported_countries",
    "commission_note",
    "cookie_duration_note",
    "disclosure_required",
    "status",
    "last_verified_at",
    "operator_notes",
)
PRODUCT_FIELDS = (
    "product_id",
    "partner_id",
    "product_name",
    "category",
    "destination_url",
    "affiliate_url",
    "coupon",
    "price_note",
    "currency",
    "availability_note",
    "status",
    "last_verified_at",
)
LINK_FIELDS = (
    "link_id",
    "site_id",
    "partner_id",
    "product_id",
    "category",
    "affiliate_url",
    "destination_url",
    "destination_domain",
    "supported_countries",
    "disclosure_required",
    "status",
    "last_verified_at",
    "operator_notes",
)


def _repository_root(root: Path | None = None) -> Path:
    return Path(root) if root is not None else Path(__file__).resolve().parents[2]


def _string(record: Mapping[str, Any], field: str, context: str, *, allow_empty: bool = False) -> str:
    value = record.get(field)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise AffiliateValidationError(f"{context}.{field} must be {qualifier}.")
    return value.strip()


def _status(record: Mapping[str, Any], context: str) -> str:
    value = _string(record, "status", context).lower()
    if value not in ALLOWED_STATUSES:
        raise AffiliateValidationError(
            f"{context}.status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}."
        )
    return value


def _countries(record: Mapping[str, Any], context: str) -> tuple[str, ...]:
    value = record.get("supported_countries")
    if not isinstance(value, list):
        raise AffiliateValidationError(f"{context}.supported_countries must be a list.")
    countries = tuple(str(item).strip().upper() for item in value)
    if any(not country or len(country) not in {2, 3} for country in countries):
        raise AffiliateValidationError(
            f"{context}.supported_countries must contain ISO-like 2 or 3 letter country codes."
        )
    if len(set(countries)) != len(countries):
        raise AffiliateValidationError(f"{context}.supported_countries cannot contain duplicates.")
    return countries


def _boolean(record: Mapping[str, Any], field: str, context: str) -> bool:
    value = record.get(field)
    if not isinstance(value, bool):
        raise AffiliateValidationError(f"{context}.{field} must be boolean.")
    return value


def _https_url(value: str, field: str, context: str, *, allow_empty: bool = False) -> str:
    if not value and allow_empty:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AffiliateValidationError(
            f"{context}.{field} must be an HTTPS URL without embedded credentials."
        )
    return value


def _domain(value: str, context: str) -> str:
    normalized = value.lower().strip().rstrip(".")
    if "://" in normalized or "/" in normalized or not normalized or "." not in normalized:
        raise AffiliateValidationError(f"{context}.destination_domain must be a hostname.")
    return normalized.removeprefix("www.")


def _host_matches_domain(url: str, destination_domain: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return host == destination_domain or host.endswith(f".{destination_domain}")


def _require_fields(record: Mapping[str, Any], fields: tuple[str, ...], context: str) -> None:
    if not isinstance(record, Mapping):
        raise AffiliateValidationError(f"{context} must be an object.")
    missing = [field for field in fields if field not in record]
    if missing:
        raise AffiliateValidationError(f"{context} is missing fields: {', '.join(missing)}.")


def validate_affiliate_partner(record: Mapping[str, Any]) -> AffiliatePartner:
    """Validate and normalize one partner record."""

    context = "partner"
    _require_fields(record, PARTNER_FIELDS, context)
    status = _status(record, context)
    affiliate_url = _https_url(
        _string(record, "affiliate_url", context, allow_empty=True),
        "affiliate_url",
        context,
        allow_empty=status != ACTIVE_STATUS,
    )
    if status == ACTIVE_STATUS and not affiliate_url:
        raise AffiliateValidationError("partner.affiliate_url is required when status is active.")
    site_id = _string(record, "site_id", context)
    if not SITE_ID_PATTERN.fullmatch(site_id):
        raise AffiliateValidationError("partner.site_id is invalid.")
    return AffiliatePartner(
        partner_id=_string(record, "partner_id", context),
        company_name=_string(record, "company_name", context),
        site_id=site_id,
        category=_string(record, "category", context),
        program_name=_string(record, "program_name", context),
        affiliate_url=affiliate_url,
        destination_domain=_domain(_string(record, "destination_domain", context), context),
        supported_countries=_countries(record, context),
        commission_note=_string(record, "commission_note", context, allow_empty=True),
        cookie_duration_note=_string(record, "cookie_duration_note", context, allow_empty=True),
        disclosure_required=_boolean(record, "disclosure_required", context),
        status=status,
        last_verified_at=_string(record, "last_verified_at", context, allow_empty=True),
        operator_notes=_string(record, "operator_notes", context, allow_empty=True),
    )


def validate_affiliate_product(record: Mapping[str, Any]) -> AffiliateProduct:
    """Validate and normalize one product record."""

    context = "product"
    _require_fields(record, PRODUCT_FIELDS, context)
    status = _status(record, context)
    destination_url = _https_url(
        _string(record, "destination_url", context, allow_empty=True),
        "destination_url",
        context,
        allow_empty=status != ACTIVE_STATUS,
    )
    if status == ACTIVE_STATUS and not destination_url:
        raise AffiliateValidationError("product.destination_url is required when status is active.")
    affiliate_url = _https_url(
        _string(record, "affiliate_url", context, allow_empty=True),
        "affiliate_url",
        context,
        allow_empty=True,
    )
    return AffiliateProduct(
        product_id=_string(record, "product_id", context),
        partner_id=_string(record, "partner_id", context),
        product_name=_string(record, "product_name", context),
        category=_string(record, "category", context),
        destination_url=destination_url,
        affiliate_url=affiliate_url,
        coupon=_string(record, "coupon", context, allow_empty=True),
        price_note=_string(record, "price_note", context, allow_empty=True),
        currency=_string(record, "currency", context, allow_empty=True),
        availability_note=_string(record, "availability_note", context, allow_empty=True),
        status=status,
        last_verified_at=_string(record, "last_verified_at", context, allow_empty=True),
    )


def validate_affiliate_link(record: Mapping[str, Any]) -> AffiliateLink:
    """Validate and normalize one independently selectable affiliate link."""

    context = "link"
    _require_fields(record, LINK_FIELDS, context)
    status = _status(record, context)
    affiliate_url = _https_url(
        _string(record, "affiliate_url", context, allow_empty=True),
        "affiliate_url",
        context,
        allow_empty=status != ACTIVE_STATUS,
    )
    destination_url = _https_url(
        _string(record, "destination_url", context, allow_empty=True),
        "destination_url",
        context,
        allow_empty=status != ACTIVE_STATUS,
    )
    if status == ACTIVE_STATUS and (not affiliate_url or not destination_url):
        raise AffiliateValidationError(
            "link.affiliate_url and link.destination_url are required when status is active."
        )
    destination_domain = _domain(_string(record, "destination_domain", context), context)
    if destination_url and not _host_matches_domain(destination_url, destination_domain):
        raise AffiliateValidationError(
            "link.destination_url host does not match link.destination_domain."
        )
    site_id = _string(record, "site_id", context)
    if not SITE_ID_PATTERN.fullmatch(site_id):
        raise AffiliateValidationError("link.site_id is invalid.")
    return AffiliateLink(
        link_id=_string(record, "link_id", context),
        site_id=site_id,
        partner_id=_string(record, "partner_id", context),
        product_id=_string(record, "product_id", context, allow_empty=True),
        category=_string(record, "category", context),
        affiliate_url=affiliate_url,
        destination_url=destination_url,
        destination_domain=destination_domain,
        supported_countries=_countries(record, context),
        disclosure_required=_boolean(record, "disclosure_required", context),
        status=status,
        last_verified_at=_string(record, "last_verified_at", context, allow_empty=True),
        operator_notes=_string(record, "operator_notes", context, allow_empty=True),
    )


def _load_collection(path: Path, site_id: str, key: str) -> list[Mapping[str, Any]]:
    if not path.exists():
        raise AffiliateValidationError(f"Affiliate data file is missing: '{path}'.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AffiliateValidationError(
            f"Affiliate data '{path}' contains invalid JSON at line {exc.lineno}, column {exc.colno}."
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise AffiliateValidationError(f"Affiliate data '{path}' must use schema_version 1.")
    if payload.get("site_id") != site_id:
        raise AffiliateValidationError(f"Affiliate data '{path}' has the wrong site_id.")
    records = payload.get(key)
    if not isinstance(records, list):
        raise AffiliateValidationError(f"Affiliate data '{path}' must contain a '{key}' list.")
    return records


def load_affiliate_catalog(
    site_id: str,
    *,
    root: Path | None = None,
) -> AffiliateCatalog:
    """Load one site's affiliate catalog; no legacy data is silently imported."""

    load_site_profile(site_id, root=root)
    directory = _repository_root(root) / AFFILIATE_DIRECTORY / site_id / "affiliate"
    partners = tuple(
        validate_affiliate_partner(item)
        for item in _load_collection(directory / "partners.json", site_id, "partners")
    )
    products = tuple(
        validate_affiliate_product(item)
        for item in _load_collection(directory / "products.json", site_id, "products")
    )
    links = tuple(
        validate_affiliate_link(item)
        for item in _load_collection(directory / "links.json", site_id, "links")
    )

    partner_ids = [partner.partner_id for partner in partners]
    product_ids = [product.product_id for product in products]
    link_ids = [link.link_id for link in links]
    for label, identifiers in (
        ("partner", partner_ids),
        ("product", product_ids),
        ("link", link_ids),
    ):
        if len(identifiers) != len(set(identifiers)):
            raise AffiliateValidationError(f"Affiliate catalog contains duplicate {label}_id values.")

    partner_map = {partner.partner_id: partner for partner in partners}
    product_map = {product.product_id: product for product in products}
    for partner in partners:
        if partner.site_id != site_id:
            raise AffiliateValidationError(
                f"Partner '{partner.partner_id}' belongs to site '{partner.site_id}', not '{site_id}'."
            )
    for product in products:
        partner = partner_map.get(product.partner_id)
        if partner is None:
            raise AffiliateValidationError(
                f"Product '{product.product_id}' references unknown partner '{product.partner_id}'."
            )
        if product.destination_url and not _host_matches_domain(
            product.destination_url,
            partner.destination_domain,
        ):
            raise AffiliateValidationError(
                f"Product '{product.product_id}' destination does not match partner destination_domain."
            )
    for link in links:
        if link.site_id != site_id:
            raise AffiliateValidationError(
                f"Link '{link.link_id}' belongs to site '{link.site_id}', not '{site_id}'."
            )
        if link.partner_id not in partner_map:
            raise AffiliateValidationError(
                f"Link '{link.link_id}' references unknown partner '{link.partner_id}'."
            )
        if link.product_id and link.product_id not in product_map:
            raise AffiliateValidationError(
                f"Link '{link.link_id}' references unknown product '{link.product_id}'."
            )
    return AffiliateCatalog(site_id=site_id, partners=partners, products=products, links=links)
