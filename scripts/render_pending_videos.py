from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO_OUTPUT = ROOT / "video_output"
STATUS_CSV = VIDEO_OUTPUT / "render_status.csv"
LOG_DIR = VIDEO_OUTPUT / "logs" / "render_pending"


def pending_folders() -> list[str]:
    with STATUS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return sorted(
            str(row.get("FolderName") or "").strip()
            for row in rows
            if str(row.get("RenderStatus") or "").strip() == "PENDING"
            and str(row.get("FolderName") or "").strip()
        )


def render_folder(folder: str) -> tuple[str, bool, str]:
    command = [
        sys.executable,
        "scripts/generate_video_assets.py",
        "--render",
        "--slug",
        folder,
        "--skip-shorts",
        "--force",
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / f"{folder}.log").write_text(output + "\n", encoding="utf-8")
    return folder, result.returncode == 0 and "Rendered long videos: 1" in output, output


def main() -> int:
    parser = argparse.ArgumentParser(description="Render video packages currently marked PENDING.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    folders = pending_folders()[max(0, args.offset):]
    if args.limit > 0:
        folders = folders[: args.limit]
    print(f"Folders queued: {len(folders)}", flush=True)

    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(render_folder, folder): folder for folder in folders}
        for future in as_completed(futures):
            folder, ok, output = future.result()
            print(f"{'OK' if ok else 'FAILED'} {folder}", flush=True)
            if not ok:
                failed.append(folder)
                print(output[-1200:], flush=True)

    subprocess.run([sys.executable, "scripts/update_render_status.py"], cwd=ROOT, check=False)
    print(f"Completed: {len(folders) - len(failed)}", flush=True)
    print(f"Failed: {len(failed)}", flush=True)
    if failed:
        print("Failed folders: " + ", ".join(failed), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
