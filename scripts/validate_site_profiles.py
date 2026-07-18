"""Read-only validation for all repository site profiles."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.platform.site_profile import (  # noqa: E402
    SiteProfileError,
    list_site_profiles,
    load_site_profile,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate site profiles without writing repository state.")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument(
        "--production-check",
        action="store_true",
        help="Also require active production-enabled profiles to pass production safety checks.",
    )
    args = parser.parse_args(argv)

    site_ids = list_site_profiles(root=args.root)
    if not site_ids:
        print("ERROR: no site profiles were found.", file=sys.stderr)
        return 1

    failures = 0
    for site_id in site_ids:
        try:
            profile = load_site_profile(site_id, root=args.root)
            if args.production_check and profile.production_enabled:
                load_site_profile(site_id, root=args.root, for_production=True)
            mode = "production" if profile.production_enabled else "example/inactive"
            print(f"PASS {site_id}: active={str(profile.active).lower()} mode={mode}")
        except SiteProfileError as exc:
            failures += 1
            print(f"FAIL {site_id}: {exc}", file=sys.stderr)
    print(f"Validated profiles: {len(site_ids)}; failed: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
