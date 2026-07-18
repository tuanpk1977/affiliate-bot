"""Display one validated site profile without changing state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.platform.site_profile import (  # noqa: E402
    DEFAULT_SITE_ID,
    SiteProfileError,
    load_site_profile,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show a validated repository site profile.")
    parser.add_argument("--site", default=DEFAULT_SITE_ID)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument(
        "--production-check",
        action="store_true",
        help="Require the selected profile to be safe and enabled for production.",
    )
    args = parser.parse_args(argv)
    try:
        profile = load_site_profile(
            args.site,
            root=args.root,
            for_production=args.production_check,
        )
    except SiteProfileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(profile.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
