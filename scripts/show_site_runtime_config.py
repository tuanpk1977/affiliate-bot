"""Print the immutable site runtime compatibility context."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.platform.site_profile import DEFAULT_SITE_ID  # noqa: E402
from modules.platform.site_runtime_config import (  # noqa: E402
    SiteRuntimeConfigError,
    build_site_runtime_config,
)


LEGACY_FIELD_SOURCES = {
    "site_id": "current owner compatibility default",
    "site_name": "config.py settings.site_name",
    "brand_name": "current owner compatibility default",
    "production_domain": "config.py settings.base_site_url/settings.site_domain",
    "canonical_base_url": "config.py settings.base_site_url/settings.site_domain",
    "default_language": "current owner compatibility default",
    "supported_languages": "current owner compatibility default",
    "niche": "current owner compatibility default",
    "affiliate_disclosure": "current owner compatibility default",
    "docs_output_path": "current production output convention",
    "site_output_path": "config.py settings.site_output_dir",
    "asset_path": "config.py settings.site_output_dir/assets",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show read-only site runtime compatibility.")
    parser.add_argument("--site", default=DEFAULT_SITE_ID)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        runtime = build_site_runtime_config(
            args.site,
            strict_profile_match=args.strict,
            root=args.root,
        )
    except SiteRuntimeConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    payload = runtime.as_dict()
    payload["field_sources"] = {
        key: {
            "effective": LEGACY_FIELD_SOURCES[key],
            "profile": f"config/sites/{args.site}.json (compatibility validation only)",
        }
        for key in runtime.field_statuses
    }
    payload["renderer_integration_status"] = "READ_ONLY_ADAPTER_INTEGRATED"
    payload["secret_handling"] = "NOT_READ"
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
