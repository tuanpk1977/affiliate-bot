"""Read-only comparison of legacy runtime settings and site-profile configuration."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from modules.platform.site_profile import PROFILE_DIRECTORY, SITE_ID_PATTERN


MATCH = "MATCH"
DIFFERENT = "DIFFERENT"
PROFILE_MISSING = "PROFILE_MISSING"
LEGACY_MISSING = "LEGACY_MISSING"
HARDCODED = "HARDCODED"
ENVIRONMENT_OVERRIDE = "ENVIRONMENT_OVERRIDE"
NOT_YET_INTEGRATED = "NOT_YET_INTEGRATED"
READ_ONLY_ADAPTER_INTEGRATED = "READ_ONLY_ADAPTER_INTEGRATED"
UNSAFE_TO_MIGRATE = "UNSAFE_TO_MIGRATE"

SAFE_NOW = "SAFE_NOW"
REQUIRES_ADAPTER = "REQUIRES_ADAPTER"
BLOCKED = "BLOCKED"
NOT_APPLICABLE = "NOT_APPLICABLE"

SECRET_MARKERS = ("api_key", "apikey", "token", "secret", "password", "credential")
SECRET_ENVIRONMENT_KEYS = (
    "BING_WEBMASTER_API_KEY",
    "GOOGLE_SEARCH_CONSOLE_CREDENTIALS_JSON",
    "INDEXNOW_KEY",
    "OPENAI_API_KEY",
)
PUBLIC_OVERRIDE_KEYS = ("BASE_SITE_URL", "SITE_DOMAIN", "SITE_NAME")

DEFAULT_SCAN_FILES = (
    "config.py",
    "runbot_menu.bat",
    "editorial_console.py",
    "modules/site_builder.py",
    "modules/canonical_routes.py",
    "modules/sitemap_generator.py",
    "modules/publishing_indexing.py",
    "modules/daily_editorial_workflow.py",
    "modules/social/draft_workflow.py",
    "modules/social/publisher_manager.py",
    "modules/seo_system.py",
    "scripts/build_selected_output.py",
    "scripts/post_deploy_indexing.py",
    "scripts/deploy_cloudflare.py",
    ".github/workflows/post-deploy-indexing.yml",
    "netlify.toml",
)
PRODUCTION_CRITICAL_FILES = {
    "modules/site_builder.py",
    "modules/canonical_routes.py",
    "modules/sitemap_generator.py",
    "modules/publishing_indexing.py",
    "modules/daily_editorial_workflow.py",
    "scripts/build_selected_output.py",
    "scripts/post_deploy_indexing.py",
    "scripts/deploy_cloudflare.py",
    ".github/workflows/post-deploy-indexing.yml",
}
HARDCODE_PATTERNS = (
    ("production_domain", re.compile(r"smileaireviewhub\.com", re.I)),
    ("brand_name", re.compile(r"(?:MS\s+)?Smile AI Review Hub", re.I)),
    ("legacy_affiliate_catalog", re.compile(r"affiliate_links\.csv", re.I)),
    ("site_output_path", re.compile(r"(?<![\w-])site_output(?:[/\\]|[\"'])", re.I)),
    ("production_output_path", re.compile(r"(?<![\w-])docs(?:[/\\]|[\"'])", re.I)),
    ("published_static_path", re.compile(r"published_static_pages", re.I)),
)


@dataclass(frozen=True)
class FieldComparison:
    key: str
    current: Any
    profile: Any
    current_source: str
    status: str
    severity: str
    recommendation: str


@dataclass(frozen=True)
class HardcodeFinding:
    file: str
    line: int
    key: str
    value: str
    classification: str
    severity: str
    recommendation: str


@dataclass(frozen=True)
class IntegrationStatus:
    component: str
    status: str
    evidence: str
    migration_readiness: str
    recommendation: str


@dataclass(frozen=True)
class DriftReport:
    site_id: str
    profile_path: str
    profile_valid: bool
    profile_validation_error: str
    field_comparison: tuple[FieldComparison, ...]
    hardcode_findings: tuple[HardcodeFinding, ...]
    integration_status: tuple[IntegrationStatus, ...]
    credential_presence: dict[str, str]

    @property
    def strict_failure(self) -> bool:
        return any(
            row.status == UNSAFE_TO_MIGRATE or row.severity == "critical"
            for row in self.field_comparison
        ) or any(
            item.classification == "production-critical hardcode"
            for item in self.hardcode_findings
        )

    def summary(self) -> dict[str, Any]:
        statuses = Counter(row.status for row in self.field_comparison)
        classifications = Counter(item.classification for item in self.hardcode_findings)
        return {
            "field_count": len(self.field_comparison),
            "hardcode_count": len(self.hardcode_findings),
            "integration_component_count": len(self.integration_status),
            "field_status_counts": dict(sorted(statuses.items())),
            "hardcode_classification_counts": dict(sorted(classifications.items())),
            "strict_failure": self.strict_failure,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "profile_path": self.profile_path,
            "profile_valid": self.profile_valid,
            "profile_validation_error": self.profile_validation_error,
            "summary": self.summary(),
            "field_comparison": [asdict(item) for item in self.field_comparison],
            "hardcode_findings": [asdict(item) for item in self.hardcode_findings],
            "integration_status": [asdict(item) for item in self.integration_status],
            "migration_readiness": {
                item.component: item.migration_readiness for item in self.integration_status
            },
            "credential_presence": dict(self.credential_presence),
        }


def _root(root: Path | None) -> Path:
    return Path(root) if root is not None else Path(__file__).resolve().parents[2]


def _is_secret_key(key: str) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return str(key).upper() in SECRET_ENVIRONMENT_KEYS or any(
        marker in normalized for marker in SECRET_MARKERS
    )


def redact_value(key: str, value: Any, *, override: bool = False) -> Any:
    """Redact secret-like values while retaining only presence information."""

    if not _is_secret_key(key):
        return value
    if override and value not in (None, "", False):
        return "OVERRIDE_PRESENT"
    return "PRESENT" if value not in (None, "", False) else "ABSENT"


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, f"File not found: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return {}, "Profile root must be a JSON object."
    return payload, ""


def _nested(mapping: Mapping[str, Any], path: str) -> Any:
    value: Any = mapping
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().rstrip("/") if value.startswith(("http://", "https://")) else value.strip()
    if isinstance(value, list):
        return tuple(value)
    return value


def _comparison(
    *,
    key: str,
    current: Any,
    profile: Any,
    source: str,
    source_kind: str = "configured",
    severity: str = "low",
    recommendation: str = "No action required.",
) -> FieldComparison:
    current = redact_value(key, current, override=source_kind == "environment")
    profile = redact_value(key, profile)
    if source_kind == "unsafe":
        status = UNSAFE_TO_MIGRATE
        severity = "critical"
    elif profile is None:
        status = PROFILE_MISSING
        severity = "high" if severity == "low" else severity
        recommendation = f"Add '{key}' to the profile contract before any migration."
    elif current is None:
        status = LEGACY_MISSING
        recommendation = "Keep the profile value; introduce it through an explicit compatibility adapter."
    elif source_kind == "environment":
        status = ENVIRONMENT_OVERRIDE
        recommendation = "Document and validate the environment override before profile integration."
    elif _normalize(current) != _normalize(profile):
        status = DIFFERENT
        severity = "high" if severity == "low" else severity
        recommendation = "Resolve the value difference explicitly; do not select one source automatically."
    elif source_kind == "hardcoded":
        status = HARDCODED
        recommendation = "Route this value through one compatibility adapter before changing runtime authority."
    else:
        status = MATCH
    return FieldComparison(
        key=key,
        current=current,
        profile=profile,
        current_source=source,
        status=status,
        severity=severity,
        recommendation=recommendation,
    )


def collect_current_configuration(
    root: Path,
    environ: Mapping[str, str],
) -> dict[str, tuple[Any, str, str]]:
    """Collect allowlisted effective legacy values without importing mutable workflows."""

    editorial, _ = _read_json(root / "config" / "editorial_system.json")
    base_override = str(environ.get("BASE_SITE_URL") or "").strip().rstrip("/")
    domain_override = str(environ.get("SITE_DOMAIN") or "").strip().rstrip("/")
    name_override = str(environ.get("SITE_NAME") or "").strip()
    effective_domain = base_override or domain_override or "https://smileaireviewhub.com"
    domain_source = (
        "environment BASE_SITE_URL"
        if base_override
        else "environment SITE_DOMAIN"
        if domain_override
        else "runtime fallback literals"
    )
    domain_kind = "environment" if base_override or domain_override else "hardcoded"
    site_name = name_override or "MS Smile AI Review Hub"
    name_source = "environment SITE_NAME" if name_override else "config.py Settings.site_name default"
    name_kind = "environment" if name_override else "configured"
    minimum_sources = _nested(
        editorial, "threshold_policy.initial_thresholds.minimum_usable_sources"
    )
    human_approval = _nested(editorial, "human_approval.required")
    return {
        "site_identity.site_name": (site_name, name_source, name_kind),
        "site_identity.brand_name": (
            "Smile AI Review Hub",
            "renderer/social hardcoded brand literals",
            "hardcoded",
        ),
        "site_identity.production_domain": (effective_domain, domain_source, domain_kind),
        "site_identity.default_language": ("en", "legacy content conventions", "hardcoded"),
        "site_identity.supported_languages": (
            ["en", "vi"],
            "legacy renderer/localization conventions",
            "hardcoded",
        ),
        "site_identity.niche": (
            "AI software, SaaS, automation, and productivity tools",
            "legacy content/renderer wording",
            "hardcoded",
        ),
        "site_identity.active": (None, "no centralized legacy field", "configured"),
        "content.categories": (None, "distributed content constants", "configured"),
        "content.content_types": (None, "distributed workflow classifiers", "configured"),
        "content.affiliate_disclosure": (
            "Some links may be affiliate links. We may earn a commission at no extra cost to you.",
            "renderer/social fallback literals",
            "hardcoded",
        ),
        "content.editorial.human_approval_required": (
            human_approval,
            "config/editorial_system.json human_approval.required",
            "configured",
        ),
        "content.source.minimum_usable_sources": (
            minimum_sources,
            "config/editorial_system.json threshold_policy",
            "configured",
        ),
        "content.seo.canonical_base_url": (
            effective_domain,
            "modules/canonical_routes.py BASE_URL",
            domain_kind,
        ),
        "paths.site_output": ("site_output", "config.py Settings.site_output_dir", "configured"),
        "paths.docs": ("docs", "publish/deployment workflow literals", "hardcoded"),
        "paths.published_static_pages": (
            "data/published_static_pages",
            "daily workflow literals",
            "hardcoded",
        ),
        "paths.upload": ("upload", "daily workflow self.upload_root", "hardcoded"),
        "paths.draft": (
            "data/production_article_drafts",
            "daily workflow literals",
            "hardcoded",
        ),
        "paths.sitemap": ("site_output/sitemap.xml", "sitemap/build literals", "hardcoded"),
        "paths.assets": ("site_output/assets", "renderer/build conventions", "hardcoded"),
        "affiliate.runtime_source": (
            "data/affiliate_links.csv",
            "config.py and modules/affiliate_links.py",
            "unsafe",
        ),
        "affiliate.profile_catalog": (
            "data/sites/smile_ai_review_hub/affiliate",
            "modules/platform/affiliate_data.py",
            "configured",
        ),
    }


PROFILE_FIELD_MAP = {
    "site_identity.site_name": "site_name",
    "site_identity.brand_name": "brand_name",
    "site_identity.production_domain": "domain",
    "site_identity.default_language": "default_language",
    "site_identity.supported_languages": "supported_languages",
    "site_identity.niche": "niche",
    "site_identity.active": "active",
    "content.categories": "categories",
    "content.content_types": "content_types",
    "content.affiliate_disclosure": "affiliate_disclosure",
    "content.editorial.human_approval_required": "editorial_settings.human_approval_required",
    "content.source.minimum_usable_sources": "source_policy.minimum_usable_sources",
    "content.seo.canonical_base_url": "seo_defaults.canonical_base_url",
    "paths.site_output": "output.site_output_dir",
    "paths.docs": "output.production_output_dir",
    "paths.published_static_pages": "output.published_static_pages_dir",
    "paths.upload": "output.upload_dir",
    "paths.draft": "output.draft_dir",
    "paths.sitemap": "output.sitemap_path",
    "paths.assets": "output.assets_dir",
    "affiliate.runtime_source": "affiliate.catalog_dir",
    "affiliate.profile_catalog": "affiliate.catalog_dir",
}


def build_field_comparisons(
    profile: Mapping[str, Any],
    current: Mapping[str, tuple[Any, str, str]],
) -> tuple[FieldComparison, ...]:
    rows: list[FieldComparison] = []
    for key, (value, source, source_kind) in current.items():
        profile_value = _nested(profile, PROFILE_FIELD_MAP[key])
        recommendation = "No action required."
        severity = "medium" if source_kind == "hardcoded" else "low"
        if key == "affiliate.runtime_source":
            recommendation = (
                "Do not auto-migrate legacy CSV records. Add a read-only adapter and require verified "
                "operator-owned links before catalog conversion."
            )
        rows.append(
            _comparison(
                key=key,
                current=value,
                profile=profile_value,
                source=source,
                source_kind=source_kind,
                severity=severity,
                recommendation=recommendation,
            )
        )
    return tuple(rows)


def classify_hardcode(path: Path, key: str) -> tuple[str, str, str]:
    """Classify one finding without changing or importing the target module."""

    rel = path.as_posix().lstrip("./")
    lower = rel.lower()
    if lower.startswith(("tests/", "test/")) or "/tests/" in lower:
        return "test fixture", "info", "Keep fixtures explicit and excluded from production drift."
    if lower.endswith(".md") or lower.startswith(("architecture/", "docs/")):
        return "documentation only", "info", "No runtime action required."
    if lower.startswith(("data/", "site_output/", "upload/")):
        return "generated artifact", "info", "Do not edit generated artifacts to resolve drift."
    if rel == "config.py":
        return (
            "intentional compatibility default",
            "low",
            "Retain until an adapter proves equivalent defaults for the active site.",
        )
    if rel in PRODUCTION_CRITICAL_FILES:
        return (
            "production-critical hardcode",
            "critical",
            "Replace only through a tested compatibility adapter; do not bulk-rewrite.",
        )
    if key == "legacy_affiliate_catalog":
        return (
            "unrelated legacy code",
            "medium",
            "Keep legacy catalog ownership explicit until verified-link migration is designed.",
        )
    return (
        "migration candidate",
        "medium",
        "Route through the future site-context adapter when this component is migrated.",
    )


def scan_hardcodes(
    root: Path,
    paths: Sequence[str | Path] | None = None,
) -> tuple[HardcodeFinding, ...]:
    findings: list[HardcodeFinding] = []
    for requested in paths or DEFAULT_SCAN_FILES:
        candidate = Path(requested)
        path = candidate if candidate.is_absolute() else root / candidate
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        try:
            rel_path = path.relative_to(root)
        except ValueError:
            rel_path = path
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//")):
                continue
            for key, pattern in HARDCODE_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                classification, severity, recommendation = classify_hardcode(rel_path, key)
                findings.append(
                    HardcodeFinding(
                        file=rel_path.as_posix(),
                        line=line_number,
                        key=key,
                        value=match.group(0),
                        classification=classification,
                        severity=severity,
                        recommendation=recommendation,
                    )
                )
    return tuple(findings)


def integration_statuses() -> tuple[IntegrationStatus, ...]:
    return (
        IntegrationStatus(
            "profile_loader",
            MATCH,
            "modules/platform/site_profile.py validates local profile JSON.",
            SAFE_NOW,
            "Keep the loader read-only.",
        ),
        IntegrationStatus(
            "renderer",
            READ_ONLY_ADAPTER_INTEGRATED,
            "modules/site_builder.py page_shell reads site_name through the immutable compatibility adapter; config.py remains authoritative.",
            SAFE_NOW,
            "Keep this integration limited to page_shell site-name rendering until another parity checkpoint is approved.",
        ),
        IntegrationStatus(
            "canonical",
            NOT_YET_INTEGRATED,
            "modules/canonical_routes.py defines BASE_URL from legacy settings/fallback.",
            REQUIRES_ADAPTER,
            "Resolve canonical base through the same site context as the renderer.",
        ),
        IntegrationStatus(
            "sitemap",
            NOT_YET_INTEGRATED,
            "modules/sitemap_generator.py uses legacy settings/fallback.",
            REQUIRES_ADAPTER,
            "Pass the selected profile domain explicitly after adapter parity tests.",
        ),
        IntegrationStatus(
            "social",
            NOT_YET_INTEGRATED,
            "modules/social/draft_workflow.py contains Smile-specific domain and brand literals.",
            REQUIRES_ADAPTER,
            "Add site context to source-package rendering without changing manual publication.",
        ),
        IntegrationStatus(
            "affiliate_resolver",
            NOT_YET_INTEGRATED,
            "The fail-closed resolver exists but no production CTA calls it.",
            BLOCKED,
            "First add a read-only legacy/catalog adapter; never auto-migrate URL records.",
        ),
        IntegrationStatus(
            "publish",
            NOT_YET_INTEGRATED,
            "Daily publishing stages fixed docs/site_output/data/upload paths.",
            BLOCKED,
            "Design an explicit per-site staging allowlist before runtime integration.",
        ),
        IntegrationStatus(
            "deployment",
            NOT_YET_INTEGRATED,
            "Cloudflare/GitHub flow and legacy netlify.toml use fixed publish roots.",
            BLOCKED,
            "Keep current production root unchanged until isolated deployment routing exists.",
        ),
        IntegrationStatus(
            "indexing",
            NOT_YET_INTEGRATED,
            "Indexing modules/workflow contain a fixed host and fixed docs/site_output roots.",
            BLOCKED,
            "Inject site identity only after publish/deployment output ownership is isolated.",
        ),
        IntegrationStatus(
            "dashboard_menu",
            NOT_YET_INTEGRATED,
            "Runbot and dashboards assume one Smile AI site and shared queues.",
            BLOCKED,
            "Do not add a site selector until queue/state namespaces are designed.",
        ),
    )


def _credential_presence(environ: Mapping[str, str]) -> dict[str, str]:
    return {
        key: redact_value(key, environ.get(key), override=bool(environ.get(key)))
        for key in SECRET_ENVIRONMENT_KEYS
    }


def analyze_site_profile_drift(
    site_id: str,
    *,
    root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    scan_paths: Sequence[str | Path] | None = None,
) -> DriftReport:
    """Build a local-only report; this function performs no writes and no network calls."""

    if not SITE_ID_PATTERN.fullmatch(str(site_id or "").strip()):
        raise ValueError("site_id must contain lowercase letters, numbers, and underscores only.")
    repository = _root(root)
    environment = environ if environ is not None else os.environ
    profile_path = repository / PROFILE_DIRECTORY / f"{site_id}.json"
    profile, load_error = _read_json(profile_path)
    validation_error = load_error
    if not validation_error:
        try:
            from modules.platform.site_profile import validate_site_profile

            validate_site_profile(profile)
        except ValueError as exc:
            validation_error = str(exc)
    current = collect_current_configuration(repository, environment)
    return DriftReport(
        site_id=site_id,
        profile_path=str(profile_path),
        profile_valid=not validation_error,
        profile_validation_error=validation_error,
        field_comparison=build_field_comparisons(profile, current),
        hardcode_findings=scan_hardcodes(repository, scan_paths),
        integration_status=integration_statuses(),
        credential_presence=_credential_presence(environment),
    )


def render_text_report(report: DriftReport) -> str:
    summary = report.summary()
    lines = [
        "SITE PROFILE CONFIGURATION DRIFT",
        f"Site: {report.site_id}",
        f"Profile: {report.profile_path}",
        f"Profile valid: {'YES' if report.profile_valid else 'NO'}",
    ]
    if report.profile_validation_error:
        lines.append(f"Profile validation: {report.profile_validation_error}")
    lines.extend(
        [
            "",
            "SUMMARY",
            f"Fields compared: {summary['field_count']}",
            f"Hardcode findings: {summary['hardcode_count']}",
            f"Strict failure: {'YES' if summary['strict_failure'] else 'NO'}",
        ]
    )
    for key, count in summary["field_status_counts"].items():
        lines.append(f"- {key}: {count}")
    lines.extend(["", "FIELD_COMPARISON"])
    for row in report.field_comparison:
        lines.extend(
            [
                f"- {row.key}",
                f"  current: {row.current!r}",
                f"  profile: {row.profile!r}",
                f"  current_source: {row.current_source}",
                f"  status: {row.status}",
                f"  severity: {row.severity}",
                f"  recommendation: {row.recommendation}",
            ]
        )
    lines.extend(["", "HARDCODE_FINDINGS"])
    if not report.hardcode_findings:
        lines.append("- none")
    for item in report.hardcode_findings:
        lines.append(
            f"- {item.file}:{item.line} | {item.key} | {item.classification} | "
            f"{item.severity} | {item.value!r} | {item.recommendation}"
        )
    lines.extend(["", "INTEGRATION_STATUS"])
    for item in report.integration_status:
        lines.append(
            f"- {item.component}: {item.status} | {item.evidence} | "
            f"readiness={item.migration_readiness} | {item.recommendation}"
        )
    lines.extend(["", "MIGRATION_READINESS"])
    for item in report.integration_status:
        lines.append(f"- {item.component}: {item.migration_readiness}")
    lines.extend(["", "CREDENTIAL_PRESENCE"])
    for key, status in report.credential_presence.items():
        lines.append(f"- {key}: {status}")
    return "\n".join(lines) + "\n"


def render_json_report(report: DriftReport) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n"
