"""Load and validate site profiles without network or state mutation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


DEFAULT_SITE_ID = "smile_ai_review_hub"
PROFILE_DIRECTORY = Path("config") / "sites"
SITE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")
PROHIBITED_KEY_PARTS = ("api_key", "apikey", "access_token", "secret", "password")

REQUIRED_FIELDS = (
    "schema_version",
    "site_id",
    "site_name",
    "brand_name",
    "domain",
    "default_language",
    "supported_languages",
    "niche",
    "categories",
    "content_types",
    "affiliate_disclosure",
    "editorial_settings",
    "seo_defaults",
    "social_platform_settings",
    "source_policy",
    "output",
    "active",
    "production_enabled",
    "example",
)


class SiteProfileError(ValueError):
    """Raised when a site profile is missing, malformed, or unsafe."""


@dataclass(frozen=True)
class SiteProfile:
    """Validated site-level settings used by the shared engine foundation."""

    schema_version: int
    site_id: str
    site_name: str
    brand_name: str
    domain: str
    default_language: str
    supported_languages: tuple[str, ...]
    niche: str
    categories: tuple[str, ...]
    content_types: tuple[str, ...]
    affiliate_disclosure: str
    editorial_settings: dict[str, Any]
    seo_defaults: dict[str, Any]
    social_platform_settings: dict[str, Any]
    source_policy: dict[str, Any]
    output: dict[str, Any]
    active: bool
    production_enabled: bool
    example: bool

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable copy of the profile."""

        payload = asdict(self)
        for field in ("supported_languages", "categories", "content_types"):
            payload[field] = list(payload[field])
        return payload

    def output_path(self, repository_root: Path, key: str) -> Path:
        """Resolve one configured relative output path inside the repository."""

        value = str(self.output.get(key) or "").strip()
        if not value:
            raise SiteProfileError(f"Profile '{self.site_id}' has no output path named '{key}'.")
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise SiteProfileError(
                f"Profile '{self.site_id}' output.{key} must be a repository-relative path."
            )
        return repository_root / candidate


def _repository_root(root: Path | None = None) -> Path:
    return Path(root) if root is not None else Path(__file__).resolve().parents[2]


def _profile_path(site_id: str, root: Path | None = None) -> Path:
    normalized = str(site_id or "").strip()
    if not SITE_ID_PATTERN.fullmatch(normalized):
        raise SiteProfileError(
            f"Invalid site_id '{normalized}'. Use lowercase letters, numbers, and underscores only."
        )
    return _repository_root(root) / PROFILE_DIRECTORY / f"{normalized}.json"


def _require_nonempty_string(profile: Mapping[str, Any], field: str) -> str:
    value = profile.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SiteProfileError(f"Site profile field '{field}' must be a non-empty string.")
    return value.strip()


def _require_string_list(profile: Mapping[str, Any], field: str) -> tuple[str, ...]:
    value = profile.get(field)
    if not isinstance(value, list) or not value:
        raise SiteProfileError(f"Site profile field '{field}' must be a non-empty list.")
    normalized = tuple(str(item).strip() for item in value)
    if any(not item for item in normalized):
        raise SiteProfileError(f"Site profile field '{field}' cannot contain empty values.")
    if len(set(normalized)) != len(normalized):
        raise SiteProfileError(f"Site profile field '{field}' cannot contain duplicates.")
    return normalized


def _require_mapping(profile: Mapping[str, Any], field: str) -> dict[str, Any]:
    value = profile.get(field)
    if not isinstance(value, dict):
        raise SiteProfileError(f"Site profile field '{field}' must be an object.")
    return dict(value)


def _validate_public_url(value: str, field: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SiteProfileError(f"Site profile field '{field}' must be an HTTPS URL without credentials.")
    if parsed.query or parsed.fragment:
        raise SiteProfileError(f"Site profile field '{field}' cannot contain a query or fragment.")
    return value.rstrip("/")


def _validate_no_secrets(value: Any, path: str = "profile") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(marker in normalized for marker in PROHIBITED_KEY_PARTS):
                raise SiteProfileError(f"Secret-like field '{path}.{key}' is not allowed in a site profile.")
            _validate_no_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_no_secrets(child, f"{path}[{index}]")


def validate_site_profile(
    profile: Mapping[str, Any],
    *,
    for_production: bool = False,
) -> None:
    """Validate one raw profile and raise a clear error on the first unsafe value."""

    if not isinstance(profile, Mapping):
        raise SiteProfileError("Site profile must be a JSON object.")
    missing = [field for field in REQUIRED_FIELDS if field not in profile]
    if missing:
        raise SiteProfileError(f"Site profile is missing required fields: {', '.join(missing)}.")
    _validate_no_secrets(profile)

    if profile.get("schema_version") != 1:
        raise SiteProfileError("Site profile 'schema_version' must be 1.")
    site_id = _require_nonempty_string(profile, "site_id")
    if not SITE_ID_PATTERN.fullmatch(site_id):
        raise SiteProfileError("Site profile 'site_id' must use lowercase letters, numbers, and underscores.")

    for field in ("site_name", "brand_name", "niche", "affiliate_disclosure"):
        _require_nonempty_string(profile, field)
    domain = _validate_public_url(_require_nonempty_string(profile, "domain"), "domain")
    default_language = _require_nonempty_string(profile, "default_language")
    supported_languages = _require_string_list(profile, "supported_languages")
    if not LANGUAGE_PATTERN.fullmatch(default_language):
        raise SiteProfileError("Site profile 'default_language' is not a supported language code.")
    if any(not LANGUAGE_PATTERN.fullmatch(item) for item in supported_languages):
        raise SiteProfileError("Site profile 'supported_languages' contains an invalid language code.")
    if default_language not in supported_languages:
        raise SiteProfileError("'default_language' must be included in 'supported_languages'.")

    _require_string_list(profile, "categories")
    _require_string_list(profile, "content_types")
    editorial = _require_mapping(profile, "editorial_settings")
    seo = _require_mapping(profile, "seo_defaults")
    social = _require_mapping(profile, "social_platform_settings")
    source_policy = _require_mapping(profile, "source_policy")
    output = _require_mapping(profile, "output")

    if not isinstance(editorial.get("human_approval_required"), bool):
        raise SiteProfileError("'editorial_settings.human_approval_required' must be boolean.")
    if not isinstance(social.get("manual_publish_only"), bool):
        raise SiteProfileError("'social_platform_settings.manual_publish_only' must be boolean.")
    minimum_sources = source_policy.get("minimum_usable_sources")
    if not isinstance(minimum_sources, int) or isinstance(minimum_sources, bool) or minimum_sources < 1:
        raise SiteProfileError("'source_policy.minimum_usable_sources' must be an integer of at least 1.")
    canonical_base = _validate_public_url(
        str(seo.get("canonical_base_url") or "").strip(),
        "seo_defaults.canonical_base_url",
    )
    if canonical_base != domain:
        raise SiteProfileError("'seo_defaults.canonical_base_url' must match the profile domain.")
    for key in ("site_output_dir", "production_output_dir", "published_static_pages_dir"):
        value = str(output.get(key) or "").strip()
        path = Path(value)
        if not value or path.is_absolute() or ".." in path.parts:
            raise SiteProfileError(f"'output.{key}' must be a repository-relative path.")

    for field in ("active", "production_enabled", "example"):
        if not isinstance(profile.get(field), bool):
            raise SiteProfileError(f"Site profile field '{field}' must be boolean.")

    if for_production:
        hostname = (urlsplit(domain).hostname or "").lower()
        if not profile["active"]:
            raise SiteProfileError(f"Site profile '{site_id}' is inactive and cannot be used for production.")
        if not profile["production_enabled"]:
            raise SiteProfileError(
                f"Site profile '{site_id}' has production_enabled=false and cannot be used for production."
            )
        if profile["example"] or hostname.endswith((".invalid", ".example", ".test", ".localhost")):
            raise SiteProfileError(f"Example site profile '{site_id}' cannot be used for production.")
        if not editorial["human_approval_required"]:
            raise SiteProfileError("Production profiles must require explicit human approval.")
        if not social["manual_publish_only"]:
            raise SiteProfileError("Production profiles must keep social publishing manual.")


def _to_site_profile(profile: Mapping[str, Any]) -> SiteProfile:
    return SiteProfile(
        schema_version=int(profile["schema_version"]),
        site_id=str(profile["site_id"]),
        site_name=str(profile["site_name"]),
        brand_name=str(profile["brand_name"]),
        domain=str(profile["domain"]).rstrip("/"),
        default_language=str(profile["default_language"]),
        supported_languages=tuple(profile["supported_languages"]),
        niche=str(profile["niche"]),
        categories=tuple(profile["categories"]),
        content_types=tuple(profile["content_types"]),
        affiliate_disclosure=str(profile["affiliate_disclosure"]),
        editorial_settings=dict(profile["editorial_settings"]),
        seo_defaults=dict(profile["seo_defaults"]),
        social_platform_settings=dict(profile["social_platform_settings"]),
        source_policy=dict(profile["source_policy"]),
        output=dict(profile["output"]),
        active=bool(profile["active"]),
        production_enabled=bool(profile["production_enabled"]),
        example=bool(profile["example"]),
    )


def load_site_profile(
    site_id: str | None = None,
    *,
    root: Path | None = None,
    require_active: bool = False,
    for_production: bool = False,
) -> SiteProfile:
    """Load one profile by ID; omitted IDs resolve only to the explicit default."""

    requested = site_id or DEFAULT_SITE_ID
    path = _profile_path(requested, root)
    if not path.exists():
        raise SiteProfileError(f"Site profile '{requested}' was not found at '{path}'.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SiteProfileError(
            f"Site profile '{requested}' contains invalid JSON at line {exc.lineno}, column {exc.colno}."
        ) from exc
    validate_site_profile(raw, for_production=for_production)
    if raw["site_id"] != requested:
        raise SiteProfileError(
            f"Profile filename '{requested}.json' does not match site_id '{raw['site_id']}'."
        )
    if require_active and not raw["active"]:
        raise SiteProfileError(f"Site profile '{requested}' is inactive.")
    return _to_site_profile(raw)


def get_active_site_profile(
    site_id: str | None = None,
    *,
    root: Path | None = None,
    for_production: bool = False,
) -> SiteProfile:
    """Load the requested or default profile and require it to be active."""

    return load_site_profile(
        site_id,
        root=root,
        require_active=True,
        for_production=for_production,
    )


def list_site_profiles(*, root: Path | None = None) -> list[str]:
    """Return configured profile IDs without loading or modifying them."""

    directory = _repository_root(root) / PROFILE_DIRECTORY
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob("*.json") if path.is_file())
