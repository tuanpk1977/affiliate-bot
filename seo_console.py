from __future__ import annotations

import argparse
import json
import webbrowser
from pathlib import Path

from modules.seo_engine import SeoPipeline


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Offline SEO opportunity engine.")
    commands = cli.add_subparsers(dest="command", required=True)
    imported = commands.add_parser("import-keywords")
    imported.add_argument("--seed", action="append", default=[])
    imported.add_argument("--file", action="append", type=Path, default=[])
    for name in ("build-clusters", "analyze-gaps", "plan-internal-links", "rank-opportunities", "run-pipeline"):
        command = commands.add_parser(name)
        command.add_argument("--seed", action="append", default=[])
        command.add_argument("--file", action="append", type=Path, default=[])
    report = commands.add_parser("show-report")
    report.add_argument("--open", action="store_true")
    queue = commands.add_parser("queue-opportunity")
    queue.add_argument("--slug", required=True)
    queue.add_argument("--date")
    queue.add_argument("--apply", action="store_true", help="Write selected opportunity to editorial queue. Default is dry-run.")
    top = commands.add_parser("queue-top")
    top.add_argument("--count", type=int, default=1)
    top.add_argument("--date")
    top.add_argument("--apply", action="store_true")
    return cli


def main() -> int:
    args = parser().parse_args()
    pipeline = SeoPipeline()
    if args.command == "import-keywords":
        result = pipeline.import_keywords(args.seed, args.file)
    elif args.command in {"build-clusters", "analyze-gaps", "plan-internal-links", "rank-opportunities", "run-pipeline"}:
        report = pipeline.run(seeds=args.seed or None, imports=args.file)
        result = report
    elif args.command == "show-report":
        report_path = pipeline.data_dir / "pipeline_report.json"
        dashboard = pipeline.render_dashboard()
        if args.open:
            webbrowser.open(dashboard.resolve().as_uri())
        result = pipeline._read(report_path, {"status": "not_generated", "dashboard": str(dashboard)})
    else:
        opportunities = pipeline._read(pipeline.data_dir / "opportunities.json", [])
        slugs = [args.slug] if args.command == "queue-opportunity" else [row["slug"] for row in opportunities[: max(0, args.count)]]
        result = pipeline.queue_opportunities(slugs, batch_date=args.date, dry_run=not args.apply)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
