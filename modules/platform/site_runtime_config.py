"""Immutable compatibility context for one bounded site renderer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from config import settings
from modules.platform.site_profile import (
    DEFAULT_SITE_ID,
    SiteProfile,
    SiteProfileError,
    load_site_profile,
)


MATCH = "MATCH"
LEGACY_ONLY = "LEGACY_ONLY"
PROFILE_ONLY_NOT_ACTIVE = "PROFILE_ONLY_NOT_ACTIVE"
COMPATIBLE = "COMPATIBLE"
INCOMPATIBLE = "INCOMPATIBLE"
FALLBACK_TO_LEGACY = "FALLBACK_TO_LEGACY"


class SiteRuntimeConfigError(ValueError):
    """Raised when strict compatibility cannot be established."""


@dataclass(frozen=True)
class SiteRuntimeConfig:
    """Effective values owned by legacy settings plus profile compatibility evidence."""

    site_id: str
    site_name: str
    brand_name: str
    production_domain: str
    canonical_base_url: str
    default_language: str
    supported_languages: tuple[str, ...]
    niche: str
    affiliate_disclosure: str
    docs_output_path: Path
    site_output_path: Path
    asset_path: Path
    compatibility_status: str
    field_statuses: Mapping[str, str]
    profile_active: bool
    profile_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "site_name": self.site_name,
            "brand_name": self.brand_name,
            "production_domain": self.production_domain,
            "canonical_base_url": self.canonical_base_url,
            "default_language": self.default_language,
            "supported_languages": list(self.supported_languages),
            "niche": self.niche,
            "affiliate_disclosure": self.affiliate_disclosure,
            "docs_output_path": str(self.docs_output_path),
            "site_output_path": str(self.site_output_path),
            "asset_path": str(self.asset_path),
            "compatibility_status": self.compatibility_status,
            "field_statuses": dict(self.field_statuses),
            "profile_active": self.profile_active,
            "profile_error": self.profile_error,
        }


def _repository_root(root: Path | None) -> Path:
    return Path(root) if root is not None else Path(__file__).resolve().parents[2]


def _setting(source: Any, name: str, default: Any = "") -> Any:
    try:
        return getattr(source, name)
    except (AttributeError, OSError, ValueError):
        return default


def _absolute_path(root: Path, value: Any, fallback: str) -> Path:
    candidate = Path(value) if value not in (None, "") else Path(fallback)
    return candidate if candidate.is_absolute() else root / candidate


def _legacy_values(root: Path, source: Any) -> dict[str, Any]:
    base_url = str(_setting(source, "base_site_url") or "").strip().rstrip("/")
    site_domain = str(_setting(source, "site_domain") or "").strip().rstrip("/")
    production_domain = base_url or site_domain or "https://yourdomain.com"
    site_output_path = _absolute_path(
        root,
        _setting(source, "site_output_dir", root / "site_output"),
        "site_output",
    )
    return {
        "site_id": DEFAULT_SITE_ID,
        "site_name": str(_setting(source, "site_name", "MS Smile AI Review Hub") or "MS Smile AI Review Hub").strip(),
        "brand_name": "Smile AI Review Hub",
        "production_domain": production_domain,
        "canonical_base_url": production_domain,
        "default_language": "en",
        "supported_languages": ("en", "vi"),
        "niche": "AI software, SaaS, automation, and productivity tools",
        "affiliate_disclosure": (
            "Some links may be affiliate links. We may earn a commission at no extra cost to you."
        ),
        "docs_output_path": root / "docs",
        "site_output_path": site_output_path,
        "asset_path": site_output_path / "assets",
    }


def _profile_values(root: Path, profile: SiteProfile) -> dict[str, Any]:
    site_output_path = profile.output_path(root, "site_output_dir")
    return {
        "site_id": profile.site_id,
        "site_name": profile.site_name,
        "brand_name": profile.brand_name,
        "production_domain": profile.domain,
        "canonical_base_url": str(profile.seo_defaults.get("canonical_base_url") or "").rstrip("/"),
        "default_language": profile.default_language,
        "supported_languages": profile.supported_languages,
        "niche": profile.niche,
        "affiliate_disclosure": profile.affiliate_disclosure,
        "docs_output_path": profile.output_path(root, "production_output_dir"),
        "site_output_path": site_output_path,
        "asset_path": site_output_path / "assets",
    }


def _normalized(value: Any) -> Any:
    if isinstance(value, Path):
        return value.resolve()
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value.rstrip("/")
    return value


def _compare(legacy: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for key, legacy_value in legacy.items():
        if key not in profile or profile[key] in (None, ""):
            statuses[key] = LEGACY_ONLY
        elif _normalized(legacy_value) == _normalized(profile[key]):
            statuses[key] = MATCH
        else:
            statuses[key] = INCOMPATIBLE
    return statuses


def _runtime(
    legacy: Mapping[str, Any],
    *,
    site_id: str,
    compatibility_status: str,
    field_statuses: Mapping[str, str],
    profile_active: bool,
    profile_error: str = "",
) -> SiteRuntimeConfig:
    return SiteRuntimeConfig(
        site_id=site_id,
        site_name=str(legacy["site_name"]),
        brand_name=str(legacy["brand_name"]),
        production_domain=str(legacy["production_domain"]),
        canonical_base_url=str(legacy["canonical_base_url"]),
        default_language=str(legacy["default_language"]),
        supported_languages=tuple(legacy["supported_languages"]),
        niche=str(legacy["niche"]),
        affiliate_disclosure=str(legacy["affiliate_disclosure"]),
        docs_output_path=Path(legacy["docs_output_path"]),
        site_output_path=Path(legacy["site_output_path"]),
        asset_path=Path(legacy["asset_path"]),
        compatibility_status=compatibility_status,
        field_statuses=MappingProxyType(dict(field_statuses)),
        profile_active=profile_active,
        profile_error=profile_error,
    )


def build_site_runtime_config(
    site_id: str = DEFAULT_SITE_ID,
    strict_profile_match: bool = False,
    *,
    root: Path | None = None,
    settings_source: Any = settings,
) -> SiteRuntimeConfig:
    """Build a read-only runtime context while retaining legacy value authority."""

    repository_root = _repository_root(root)
    legacy = _legacy_values(repository_root, settings_source)
    try:
        profile = load_site_profile(site_id, root=repository_root)
    except SiteProfileError as exc:
        if strict_profile_match:
            raise SiteRuntimeConfigError(str(exc)) from exc
        return _runtime(
            legacy,
            site_id=site_id,
            compatibility_status=FALLBACK_TO_LEGACY,
            field_statuses={key: LEGACY_ONLY for key in legacy},
            profile_active=False,
            profile_error=str(exc),
        )

    profile_values = _profile_values(repository_root, profile)
    field_statuses = _compare(legacy, profile_values)
    inactive = not profile.active or not profile.production_enabled or profile.example
    incompatible = any(status == INCOMPATIBLE for status in field_statuses.values())
    if inactive:
        status = PROFILE_ONLY_NOT_ACTIVE
        error = f"Site profile '{site_id}' is not active for production."
    elif incompatible:
        status = FALLBACK_TO_LEGACY
        error = "Profile values do not match the authoritative legacy runtime settings."
    elif any(value == LEGACY_ONLY for value in field_statuses.values()):
        status = COMPATIBLE
        error = ""
    else:
        status = MATCH
        error = ""

    if strict_profile_match and (inactive or incompatible):
        raise SiteRuntimeConfigError(error)
    return _runtime(
        legacy,
        site_id=site_id,
        compatibility_status=status,
        field_statuses=field_statuses,
        profile_active=profile.active and profile.production_enabled and not profile.example,
        profile_error=error,
    )
