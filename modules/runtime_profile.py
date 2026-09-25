from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


PROFILE_ENV = "AFFILIATE_BOT_RUNTIME_PROFILE"
FULL_COMPATIBILITY = "FULL_COMPATIBILITY"
LITE_DAILY = "LITE_DAILY"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "runtime_profiles.json"


class RuntimeProfileError(ValueError):
    """Raised when a requested profile cannot be resolved exactly."""


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    description: str
    manifest: str
    menu_choices: tuple[str, ...]
    features: tuple[str, ...]
    excluded_features: tuple[str, ...]
    compatibility_escape_hatch: str | None

    def allows_menu_choice(self, choice: str) -> bool:
        normalized = str(choice or "").strip().upper()
        return "*" in self.menu_choices or normalized in self.menu_choices

    def allows_feature(self, feature: str) -> bool:
        normalized = str(feature or "").strip()
        return "*" in self.features or normalized in self.features


def load_runtime_profile_registry(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeProfileError(f"Runtime profile registry is missing: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeProfileError(f"Runtime profile registry is invalid: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "runtime_profiles_v1":
        raise RuntimeProfileError("Runtime profile registry must use schema runtime_profiles_v1")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise RuntimeProfileError("Runtime profile registry has no profiles")
    default = str(payload.get("default_profile") or "").strip().upper()
    if default != FULL_COMPATIBILITY:
        raise RuntimeProfileError("FULL_COMPATIBILITY must remain the default profile")
    for required in (FULL_COMPATIBILITY, LITE_DAILY):
        if required not in profiles or not isinstance(profiles[required], dict):
            raise RuntimeProfileError(f"Required runtime profile is missing: {required}")
    return payload


def resolve_runtime_profile(
    requested: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    registry_path: Path = DEFAULT_CONFIG_PATH,
) -> RuntimeProfile:
    registry = load_runtime_profile_registry(registry_path)
    environment = os.environ if environ is None else environ
    raw = requested if requested is not None else environment.get(PROFILE_ENV)
    name = str(raw or registry["default_profile"]).strip().upper()
    profiles = registry["profiles"]
    if name not in profiles:
        allowed = ", ".join(sorted(profiles))
        raise RuntimeProfileError(
            f"Unknown runtime profile {name!r}. Expected exactly one of: {allowed}. No fallback was applied."
        )
    row = profiles[name]
    menu_choices = row.get("menu_choices")
    features = row.get("features")
    excluded = row.get("excluded_features", [])
    if not isinstance(menu_choices, list) or not all(isinstance(item, str) for item in menu_choices):
        raise RuntimeProfileError(f"Profile {name} has invalid menu_choices")
    if not isinstance(features, list) or not all(isinstance(item, str) for item in features):
        raise RuntimeProfileError(f"Profile {name} has invalid features")
    if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
        raise RuntimeProfileError(f"Profile {name} has invalid excluded_features")
    manifest = str(row.get("manifest") or "").strip()
    if not manifest:
        raise RuntimeProfileError(f"Profile {name} has no manifest")
    return RuntimeProfile(
        name=name,
        description=str(row.get("description") or ""),
        manifest=manifest,
        menu_choices=tuple(item.upper() for item in menu_choices),
        features=tuple(features),
        excluded_features=tuple(excluded),
        compatibility_escape_hatch=(
            str(row["compatibility_escape_hatch"])
            if row.get("compatibility_escape_hatch")
            else None
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve the Affiliate Bot runtime profile without side effects.")
    parser.add_argument("command", choices=("show", "validate", "check-menu"))
    parser.add_argument("--profile", default=None)
    parser.add_argument("--choice", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = resolve_runtime_profile(args.profile)
    except RuntimeProfileError as exc:
        print(f"RUNTIME_PROFILE_ERROR: {exc}")
        return 2
    if args.command == "show":
        print(f"RUNTIME_PROFILE={profile.name}")
        print(f"RUNTIME_MANIFEST={profile.manifest}")
        if profile.compatibility_escape_hatch:
            print(f"FULL_COMPATIBILITY_ESCAPE_HATCH={profile.compatibility_escape_hatch}")
        return 0
    if args.command == "check-menu":
        allowed = profile.allows_menu_choice(args.choice)
        print(f"MENU_CHOICE_ALLOWED={'YES' if allowed else 'NO'}")
        return 0 if allowed else 3
    print(f"VALID_RUNTIME_PROFILE={profile.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
