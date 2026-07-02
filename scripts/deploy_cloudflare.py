from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
SITE_OUTPUT = ROOT / "site_output"


def enabled(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def cloudflare_command(project_name: str) -> list[str]:
    configured = os.getenv("CLOUDFLARE_DEPLOY_COMMAND", "").strip()
    if configured:
        return shlex.split(configured, posix=os.name != "nt")
    npx = "npx.cmd" if os.name == "nt" else "npx"
    return [npx, "wrangler", "pages", "deploy", str(SITE_OUTPUT), "--project-name", project_name]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy site_output to Cloudflare Pages, then validate the live batch and notify search engines."
    )
    parser.add_argument("--project-name", default=os.getenv("CLOUDFLARE_PAGES_PROJECT", "").strip())
    parser.add_argument("--max-urls", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not SITE_OUTPUT.exists():
        print(f"[Cloudflare] Missing publish directory: {SITE_OUTPUT}")
        return 1
    if not args.project_name and not os.getenv("CLOUDFLARE_DEPLOY_COMMAND", "").strip():
        print("[Cloudflare] Set CLOUDFLARE_PAGES_PROJECT or CLOUDFLARE_DEPLOY_COMMAND before deployment.")
        return 1

    command = cloudflare_command(args.project_name)
    print("[Cloudflare] Deploy command:", subprocess.list2cmdline(command))
    if args.dry_run:
        print("[Cloudflare] Dry run: deployment and IndexNow submission skipped.")
        return 0

    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        print(f"[Cloudflare] Deployment failed with exit code {result.returncode}. IndexNow was NOT submitted.")
        return result.returncode

    if not enabled("AUTO_INDEXNOW_AFTER_DEPLOY", True):
        print("[Cloudflare] Deployment succeeded. AUTO_INDEXNOW_AFTER_DEPLOY is disabled; indexing automation skipped.")
        return 0
    print("[Cloudflare] Deployment command completed successfully. Running post-deploy validation and indexing.")
    post_deploy = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "post_deploy_indexing.py"),
            "--from-git",
            "--wait-seconds",
            "600",
        ],
        cwd=ROOT,
        check=False,
    )
    if post_deploy.returncode != 0:
        print("[Cloudflare] WARNING: post-deploy validation/indexing failed. Review logs/indexing before continuing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
