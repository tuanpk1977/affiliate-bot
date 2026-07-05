from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_video_assets import (  # noqa: E402
    DEFAULT_VIDEO_RENDER_CONFIG,
    VIDEO_RENDER_CONFIG,
    detect_ffmpeg,
    save_video_render_config,
)


def main() -> None:
    info = detect_ffmpeg()
    ffmpeg = str(info.get("ffmpeg", "") or "")
    ffprobe = str(info.get("ffprobe", "") or "")

    print("FFmpeg search report")
    print(f"ffmpeg: {ffmpeg or 'not found'}")
    print(f"ffprobe: {ffprobe or 'not found'}")

    config = dict(DEFAULT_VIDEO_RENDER_CONFIG)
    if VIDEO_RENDER_CONFIG.exists():
        try:
            loaded = json.loads(VIDEO_RENDER_CONFIG.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config.update(loaded)
        except Exception:
            pass

    if ffmpeg and ffprobe:
        config["ffmpeg_path"] = ffmpeg
        config["ffprobe_path"] = ffprobe
        save_video_render_config(config)
        print(f"Updated {VIDEO_RENDER_CONFIG}")
        print("FFmpeg detected: yes")
        print("FFprobe detected: yes")
        return

    save_video_render_config(config)
    print("FFmpeg detected: no")
    print("FFprobe detected: no")
    print("If winget just installed FFmpeg, close and reopen PowerShell/VS Code, then run again.")
    print("If it still fails, paste absolute ffmpeg.exe and ffprobe.exe paths into config/video_render.json.")


if __name__ == "__main__":
    main()
