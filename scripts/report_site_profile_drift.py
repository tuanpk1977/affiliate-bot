"""Print a read-only site-profile compatibility report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.platform.config_drift import (  # noqa: E402
    analyze_site_profile_drift,
    render_json_report,
    render_text_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare current Smile AI runtime assumptions with one local site profile."
    )
    parser.add_argument("--site", required=True, help="Profile site_id.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of readable text.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero for production-critical hardcodes or unsafe migration findings.",
    )
    parser.add_argument("--output", help="Optional report path. No report file is written by default.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    report = analyze_site_profile_drift(
        args.site,
        root=root or ROOT,
        environ=environ,
    )
    rendered = render_json_report(report) if args.json else render_text_report(report)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 2 if args.strict and report.strict_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
