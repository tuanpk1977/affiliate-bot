from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.runtime_usage import aggregate_usage, observe_usage_best_effort  # noqa: E402


def _bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Local, privacy-bounded runtime usage evidence")
    sub = result.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record")
    record.add_argument("--profile", required=True)
    record.add_argument("--entry-point", required=True)
    record.add_argument("--feature", required=True)
    record.add_argument("--workflow", required=True)
    record.add_argument("--operation", required=True)
    record.add_argument("--success", required=True, type=_bool)
    record.add_argument("--output-generated", required=True, type=_bool)
    record.add_argument("--duration-ms", type=int)
    record.add_argument("--error-class")
    record.add_argument("--root", type=Path, default=ROOT)
    report = sub.add_parser("report")
    report.add_argument("--window-days", type=int)
    report.add_argument("--registry", type=Path, default=ROOT / "architecture" / "LEAN_RUNTIME_CLASSIFICATION_V1.json")
    report.add_argument("--root", type=Path, default=ROOT)
    report.add_argument("--output", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "record":
        result = observe_usage_best_effort(
            args.root,
            runtime_profile=args.profile,
            entry_point=args.entry_point,
            feature=args.feature,
            workflow=args.workflow,
            operation=args.operation,
            success=args.success,
            output_generated=args.output_generated,
            duration_ms=args.duration_ms,
            error_class=args.error_class,
        )
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    config = json.loads((args.root / "config" / "usage_evidence.json").read_text(encoding="utf-8"))
    window = args.window_days or int(config.get("default_window_days", 30))
    report = aggregate_usage(root=args.root, registry=registry, window_days=window)
    rendered = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
