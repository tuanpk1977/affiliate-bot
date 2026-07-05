from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO_OUTPUT = ROOT / "video_output"
LOG_DIR = VIDEO_OUTPUT / "logs" / "rerender_remaining"
MIN_VIDEO_BYTES = 1024 * 1024
DEFAULT_EXCLUDE = {
    "category-automation-tools",
    "category-ai-coding-tools",
    "review-chatgpt",
    "review-surfer-seo",
}


def discover_folders(exclude: set[str]) -> list[str]:
    folders = []
    for folder in VIDEO_OUTPUT.iterdir():
        video = folder / "review_video.mp4"
        if folder.is_dir() and folder.name not in exclude and video.exists() and video.stat().st_size > MIN_VIDEO_BYTES:
            folders.append(folder.name)
    return sorted(folders)


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
    ok = result.returncode == 0 and "Rendered long videos: 1" in output
    return folder, ok, output


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-render existing video packages with synchronized bilingual subtitles.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--include-all", action="store_true", help="Also re-render the four recently completed packages.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many folders from the sorted queue.")
    parser.add_argument("--limit", type=int, default=0, help="Render only this many folders after offset.")
    args = parser.parse_args()

    exclude = set() if args.include_all else DEFAULT_EXCLUDE
    folders = discover_folders(exclude)
    folders = folders[max(0, args.offset):]
    if args.limit > 0:
        folders = folders[:args.limit]
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

    subprocess.run([sys.executable, "-c", "from scripts.generate_video_assets import write_video_quality_reports; write_video_quality_reports()"], cwd=ROOT)
    subprocess.run([sys.executable, "scripts/update_render_status.py"], cwd=ROOT)
    print(f"Completed: {len(folders) - len(failed)}", flush=True)
    print(f"Failed: {len(failed)}", flush=True)
    if failed:
        print("Failed folders: " + ", ".join(failed), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
