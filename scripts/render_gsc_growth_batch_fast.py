from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import generate_video_assets as video


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "video_output"
SLUGS = [
    "review-surfer-seo-review-2026",
    "surfer-seo-free-trial",
    "review-surfer-seo-alternatives",
    "compare-surfer-seo-vs-frase",
    "surfer-seo-vs-clearscope",
    "best-ai-seo-tools-2026",
    "best-website-builder-2026",
    "best-ai-website-builders-compared",
    "best-affiliate-marketing-software-saas",
    "review-trackdesk-review-2026",
]
SECTION_NAMES = ["Overview", "Key Features", "Pricing", "Pros", "Cons", "Best Use Cases", "Alternatives", "Final Verdict"]


def require_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    if not text:
        raise RuntimeError(f"Required text file is missing or empty: {path}")
    return text


def make_audio(folder: Path, ffmpeg: str, config: dict) -> Path:
    voiceover = require_text(folder / "voiceover.txt")
    audio_dir = folder / "audio"
    audio_dir.mkdir(exist_ok=True)
    wav = audio_dir / "voiceover_fast.wav"
    mp3 = audio_dir / "voiceover_fast.mp3"
    ok, error = video.generate_windows_tts_wav(voiceover, wav, config)
    if not ok:
        raise RuntimeError(f"TTS failed: {error[-500:]}")
    ok, error = video.convert_audio_to_mp3(ffmpeg, wav, mp3)
    if not ok:
        raise RuntimeError(f"Audio conversion failed: {error[-500:]}")
    return mp3


def build_google_paired_srts(voiceover: str, duration: float, cache_path: Path) -> tuple[str, str, str]:
    english_sentences = [
        video.clean_text(item)
        for item in re.split(r"(?<=[.!?])\s+|\n\s*\n", voiceover)
        if video.clean_text(item)
    ]
    pairs = [(sentence, "") for sentence in english_sentences]
    pairs = video.translate_paired_cues_with_google(pairs, cache_path)
    weights = [max(1, len(english.split())) for english, _ in pairs]
    total_weight = max(1, sum(weights))
    current = 0.0
    english_blocks = []
    vietnamese_blocks = []
    vietnamese_text = []
    for index, ((english, vietnamese), weight) in enumerate(zip(pairs, weights), start=1):
        end = duration if index == len(pairs) else current + duration * weight / total_weight
        english_blocks.append(f"{index}\n{video.srt_time(current)} --> {video.srt_time(end)}\n{english}\n")
        vietnamese_blocks.append(f"{index}\n{video.srt_time(current)} --> {video.srt_time(end)}\n{vietnamese}\n")
        vietnamese_text.append(vietnamese)
        current = end
    return (
        "\n".join(english_blocks).strip() + "\n",
        "\n".join(vietnamese_blocks).strip() + "\n",
        "\n\n".join(vietnamese_text).strip() + "\n",
    )


def make_slides(folder: Path, title: str) -> list[Path]:
    slides_dir = folder / "fast_render_assets"
    slides_dir.mkdir(exist_ok=True)
    slides = []
    for index, section in enumerate(SECTION_NAMES, start=1):
        slide = slides_dir / f"slide-{index:02d}.png"
        bullets = [
            f"{section} for {title}",
            "Practical buyer-focused research",
            "Verify current pricing and terms",
        ]
        video.create_video_slide(slide, title, bullets, (1920, 1080), "review", index / len(SECTION_NAMES), section.lower())
        slides.append(slide)
    return slides


def make_concat(folder: Path, slides: list[Path], duration: float) -> Path:
    concat = folder / "fast_render_assets" / "concat.txt"
    blocks = []
    repeats = max(1, math.ceil(duration / (len(slides) * 5.0)))
    for _ in range(repeats):
        for slide in slides:
            blocks.append(f"file '{slide.as_posix()}'")
            blocks.append("duration 5")
    blocks.append(f"file '{slides[-1].as_posix()}'")
    concat.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return concat


def render_slug(slug: str, ffmpeg: str, ffprobe: str, config: dict) -> dict[str, object]:
    folder = VIDEO / slug
    metadata_path = folder / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    title = str(metadata.get("title") or slug.replace("-", " ").title())
    voiceover = require_text(folder / "voiceover.txt")
    if not (folder / "thumbnail.png").exists():
        raise RuntimeError(f"Thumbnail missing: {folder / 'thumbnail.png'}")

    audio = make_audio(folder, ffmpeg, config)
    duration = float(video.ffprobe_duration(ffprobe, audio) or "0")
    if not 270 <= duration <= 480:
        raise RuntimeError(f"Audio duration must be 4.5-8 minutes before export; found {duration:.1f}s")

    english_srt = folder / "subtitles.srt"
    vietnamese_srt = folder / "subtitles_vi.srt"
    english_text, vietnamese_text, vi_text = build_google_paired_srts(
        voiceover, duration, folder / "subtitle_translation_cache.json"
    )
    english_srt.write_text(english_text, encoding="utf-8")
    (folder / "subtitles_vi.txt").write_text(vi_text, encoding="utf-8")
    vietnamese_srt.write_text(vietnamese_text, encoding="utf-8")
    require_text(english_srt)
    require_text(vietnamese_srt)

    slides = make_slides(folder, title)
    concat = make_concat(folder, slides, duration)
    output = folder / "review_video.mp4"
    exports = folder / "exports"
    exports.mkdir(exist_ok=True)
    export = exports / "long_video_1920x1080.mp4"
    vf = (
        f"subtitles='{video.ffmpeg_escape_filter_path(english_srt)}':"
        "force_style='FontName=Arial,Fontsize=9,PrimaryColour=&H00FFFFFF,OutlineColour=&HDD000000,"
        "Bold=1,BorderStyle=1,Outline=1,Shadow=0,Alignment=2,MarginV=70,MarginL=12,MarginR=12',"
        f"subtitles='{video.ffmpeg_escape_filter_path(vietnamese_srt)}':"
        "force_style='FontName=Arial,Fontsize=11,PrimaryColour=&H0000FFFF,OutlineColour=&HDD000000,"
        "Bold=1,BorderStyle=1,Outline=1,Shadow=0,Alignment=2,MarginV=10,MarginL=12,MarginR=12'"
    )
    command = [
        ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(audio),
        "-vf", vf, "-r", "15", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(export),
    ]
    result = subprocess.run(command, cwd=ROOT, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not export.exists() or export.stat().st_size < 100_000:
        raise RuntimeError(f"FFmpeg failed: {(result.stderr or result.stdout)[-1200:]}")
    shutil.copy2(export, output)
    shutil.copy2(english_srt, exports / "subtitles.srt")
    shutil.copy2(vietnamese_srt, exports / "subtitles_vi.srt")
    metadata.update({
        "render_status": "success",
        "video_render_status": "long_form_fast_render",
        "video_style": "section_slides_with_bilingual_subtitles",
        "motion_style": "slide_change_every_5_seconds",
        "voiceover_language": "en",
        "subtitle_language": "en+vi",
        "subtitle_status": "bilingual_burned",
        "subtitle_pairing": "english_vietnamese_same_cue_timestamps",
        "review_video_duration_seconds": video.ffprobe_duration(ffprobe, output),
        "review_video_size_bytes": output.stat().st_size,
        "render_date": datetime.now(timezone.utc).isoformat(),
    })
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"slug": slug, "duration": metadata["review_video_duration_seconds"], "bytes": output.stat().st_size, "status": "READY"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default="")
    args = parser.parse_args()
    ffmpeg_info = video.detect_ffmpeg()
    if not ffmpeg_info.get("available"):
        raise RuntimeError("FFmpeg and FFprobe are required")
    selected = [args.slug] if args.slug else SLUGS
    config = video.load_video_render_config()
    results = []
    for slug in selected:
        print(f"RENDER {slug}", flush=True)
        results.append(render_slug(slug, str(ffmpeg_info["ffmpeg"]), str(ffmpeg_info["ffprobe"]), config))
        print(json.dumps(results[-1]), flush=True)
    (VIDEO / "gsc_growth_video_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    video.update_render_status_tracker()


if __name__ == "__main__":
    main()
