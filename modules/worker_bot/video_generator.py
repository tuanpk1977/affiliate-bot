from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from .config import WorkerBotConfig
from .data_loader import TopicCandidate
from .utils import write_json, write_text

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional runtime dependency
    Image = None
    ImageDraw = None
    ImageFont = None


def _load_ffmpeg(config: WorkerBotConfig) -> Path | None:
    if not config.ffmpeg_config.exists():
        return None
    payload = json.loads(config.ffmpeg_config.read_text(encoding="utf-8"))
    path = Path(payload.get("ffmpeg_path") or payload.get("ffmpeg") or "")
    return path if path.exists() else None


def _load_ffprobe(config: WorkerBotConfig) -> Path | None:
    if not config.ffmpeg_config.exists():
        return None
    payload = json.loads(config.ffmpeg_config.read_text(encoding="utf-8"))
    path = Path(payload.get("ffprobe_path") or payload.get("ffprobe") or "")
    return path if path.exists() else None


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _read_outline(folder: Path, candidate: TopicCandidate) -> dict[str, Any]:
    path = folder / "video-outline.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    return {
        "topic": candidate.topic,
        "duration_seconds": 54,
        "scenes": [
            {"title": "Intro", "voiceover": f"Researching {candidate.topic}? Start with workflow fit."},
            {"title": "Feature checklist", "voiceover": "Check features, integrations, pricing limits, and support."},
            {"title": "Pricing", "voiceover": "Verify current pricing on the official website."},
            {"title": "Pros and cons", "voiceover": "Compare upside, limits, and switching risk."},
            {"title": "Verdict", "voiceover": "Read the full review on Smile AI Review Hub."},
        ],
    }


def _translate_caption(text: str, topic: str) -> str:
    clean = _safe_text(text)
    known = {
        "A practical buyer-focused review draft.": "Bản nháp đánh giá tập trung vào nhu cầu người mua.",
        f"Researching {topic}? Start with workflow fit.": f"Nếu bạn đang tìm hiểu {topic}, hãy bắt đầu từ mức độ phù hợp với quy trình làm việc.",
        "Check features, integrations, pricing limits, and support.": "Kiểm tra tính năng, tích hợp, giới hạn gói và hỗ trợ trước khi chọn.",
        "Verify current pricing on the official website.": "Luôn xác minh giá hiện tại trên trang chính thức.",
        "Compare upside, limits, and switching risk.": "So sánh lợi ích, giới hạn và rủi ro khi chuyển đổi.",
        "Read the full review on Smile AI Review Hub.": "Xem bài đánh giá đầy đủ trên Smile AI Review Hub.",
        "Visit smileaireviewhub.com for the full article and comparison notes.": "Xem bài đầy đủ và ghi chú so sánh tại smileaireviewhub.com.",
    }
    if clean in known:
        return known[clean]
    lowered = clean.lower()
    if "pricing" in lowered:
        return "Kiểm tra giá, giới hạn gói và điều khoản hiện tại trước khi mua."
    if "alternative" in lowered or "compare" in lowered:
        return "So sánh với các lựa chọn thay thế trước khi quyết định."
    if "workflow" in lowered:
        return "Tập trung vào việc công cụ có cải thiện quy trình thực tế hay không."
    return "Kiểm tra mức độ phù hợp, chi phí, lợi ích và rủi ro trước khi chọn công cụ này."


def _build_scenes(candidate: TopicCandidate, outline: dict[str, Any]) -> list[dict[str, str]]:
    source_scenes = [item for item in outline.get("scenes", []) if isinstance(item, dict)]
    display_topic = candidate.topic.title()
    labels = {
        "Intro": ("Overview", "Tổng quan", "overview"),
        "Feature checklist": ("Key Features", "Tính năng chính", "key-features"),
        "Pricing": ("Pricing", "Giá bán", "pricing"),
        "Pros and cons": ("Pros and Cons", "Ưu và nhược điểm", "pros-cons"),
        "Verdict": ("Final Verdict", "Kết luận", "final-verdict"),
    }
    scenes: list[dict[str, str]] = [
        {
            "title": "Introduction",
            "label_vi": "Giới thiệu",
            "body": display_topic,
            "caption": "A practical buyer-focused review draft.",
            "section": "intro",
        }
    ]
    for item in source_scenes[:5]:
        raw_title = _safe_text(item.get("title")) or "Review Point"
        title, label_vi, section = labels.get(raw_title, (raw_title, "Tổng quan", raw_title.lower().replace(" ", "-")))
        scenes.append(
            {
                "title": title,
                "label_vi": label_vi,
                "body": _safe_text(item.get("visual")) or "Buyer checklist",
                "caption": _safe_text(item.get("voiceover")) or "Review the workflow, pricing, pros, cons, and alternatives.",
                "section": section,
            }
        )
    scenes.append(
        {
            "title": "Final CTA",
            "label_vi": "Xem bài đầy đủ",
            "body": "Read the full review",
            "caption": "Visit smileaireviewhub.com for the full article and comparison notes.",
            "section": "end-screen",
        }
    )
    for scene in scenes:
        scene["caption_vi"] = _translate_caption(scene["caption"], display_topic)
    return scenes[:8]


def _font(size: int, bold: bool = False) -> Any:
    if ImageFont is None:
        return None
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(_safe_text(text), width=width)) or ""


def _draw_slide(path: Path, index: int, total: int, scene: dict[str, str], topic: str) -> None:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is not available")
    width, height = 1280, 720
    palette = [
        ("#071923", "#0f766e"),
        ("#0b1720", "#2563eb"),
        ("#111827", "#7c3aed"),
        ("#082f49", "#0d9488"),
        ("#172554", "#059669"),
        ("#111827", "#dc2626"),
    ]
    bg, accent = palette[index % len(palette)]
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    title_font = _font(58, bold=True)
    body_font = _font(31, bold=True)
    caption_font = _font(30, bold=True)
    small_font = _font(24, bold=True)

    draw.rectangle((0, 0, width, 86), fill=accent)
    draw.text((56, 26), "MS Smile AI Review Hub", fill="white", font=small_font)
    draw.text((1042, 26), "ARTICLE SECTION", fill="white", font=small_font)

    draw.text((72, 155), _wrap(scene["title"], 18), fill="white", font=title_font)
    draw.text((72, 255), scene.get("label_vi", ""), fill="#5eead4", font=_font(30, bold=True))
    bullets = ["Check official pricing.", "Compare workflow fit.", "Review risks before buying."]
    y = 360
    for bullet_index, bullet in enumerate(bullets):
        outline = "#155e75" if bullet_index != 1 else "#2563eb"
        draw.rounded_rectangle((72, y, 500, y + 56), radius=12, fill="#0b2940", outline=outline, width=2)
        draw.ellipse((95, y + 20, 110, y + 35), fill="#2dd4bf")
        draw.text((126, y + 15), bullet, fill="#e2e8f0", font=_font(23))
        y += 68

    draw.rounded_rectangle((540, 116, 1205, 568), radius=20, fill="#f8fafc", outline="#5eead4", width=3)
    draw.rectangle((560, 138, 1185, 190), fill=accent)
    draw.text((586, 154), "MS Smile AI Review Hub", fill="white", font=_font(22, bold=True))
    draw.text((1030, 154), "REVIEW", fill="white", font=_font(18, bold=True))
    draw.text((586, 220), _wrap(topic.title(), 34), fill="#334155", font=_font(21, bold=True))
    draw.text((586, 260), _wrap(scene["title"], 24), fill="#0f172a", font=_font(40, bold=True))
    box_fill, box_outline = "#dbeafe", "#38bdf8"
    section = scene.get("section", "")
    if "pros" in section:
        box_fill, box_outline = "#dcfce7", "#22c55e"
    elif "cons" in section:
        box_fill, box_outline = "#fee2e2", "#ef4444"
    elif "pricing" in section:
        box_fill, box_outline = "#fef3c7", "#f59e0b"
    draw.rounded_rectangle((586, 344, 1156, 502), radius=14, fill=box_fill, outline=box_outline, width=2)
    bullet_text = "• " + _wrap(scene["caption"], 58).replace("\n", "\n• ")
    draw.text((622, 374), bullet_text, fill="#1f2937", font=body_font)
    draw.text((586, 526), "Source: draft article package", fill="#64748b", font=_font(18))

    # Subtitle layout follows the corrected production rule: English higher, Vietnamese lower.
    draw.text((140, 593), _wrap(scene["caption"], 92), fill="white", font=_font(22, bold=True))
    draw.text((140, 645), _wrap(scene.get("caption_vi", ""), 70), fill="#fde047", font=caption_font)
    draw.text((972, 682), "smileaireviewhub.com", fill="#93c5fd", font=small_font)
    image.save(path)


def _draw_thumbnail(path: Path, candidate: TopicCandidate) -> None:
    if Image is None or ImageDraw is None:
        return
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), "#071923")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 120), fill="#0f766e")
    draw.text((70, 38), "MS Smile AI Review Hub", fill="white", font=_font(34, bold=True))
    draw.rounded_rectangle((690, 170, 1180, 570), radius=28, fill="#f8fafc", outline="#5eead4", width=4)
    draw.text((735, 230), "REVIEW", fill="#0f766e", font=_font(32, bold=True))
    draw.text((735, 292), _wrap(candidate.topic.title(), 16), fill="#0f172a", font=_font(58, bold=True))
    draw.rounded_rectangle((70, 235, 570, 405), radius=24, fill="#0f766e")
    draw.text((110, 270), "Review 2026", fill="white", font=_font(64, bold=True))
    draw.text((96, 500), "Features - Pricing - Pros & Cons", fill="#fde047", font=_font(34, bold=True))
    image.save(path)


def _format_timestamp(seconds: float) -> str:
    whole = int(seconds)
    millis = int(round((seconds - whole) * 1000))
    h = whole // 3600
    m = (whole % 3600) // 60
    s = whole % 60
    return f"{h:02}:{m:02}:{s:02},{millis:03}"


def _write_subtitles(path: Path, scenes: list[dict[str, str]], scene_duration: float, key: str = "caption") -> None:
    lines: list[str] = []
    start = 0.0
    for index, scene in enumerate(scenes, start=1):
        end = start + scene_duration
        lines.extend([str(index), f"{_format_timestamp(start)} --> {_format_timestamp(end)}", scene[key], ""])
        start = end
    write_text(path, "\n".join(lines))


def _write_text_sig(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8-sig")


def _run(command: list[str], timeout: int = 180) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, str(exc)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "command failed")[-1500:]
    return True, result.stdout


def _synthesize_voice(narration_path: Path, audio_path: Path) -> tuple[bool, str]:
    command = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{str(audio_path)}'); "
        f"$s.Speak((Get-Content -Raw '{str(narration_path)}')); "
        "$s.Dispose()"
    )
    ok, message = _run(["powershell", "-NoProfile", "-Command", command], timeout=180)
    if ok and audio_path.exists() and audio_path.stat().st_size > 1000:
        return True, "voiceover generated with local Windows SAPI"
    return False, message or "local Windows SAPI TTS unavailable"


def _probe_duration(config: WorkerBotConfig, path: Path) -> float:
    ffprobe = _load_ffprobe(config)
    if not ffprobe or not path.exists():
        return 0.0
    ok, output = _run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=30,
    )
    if not ok:
        return 0.0
    try:
        return float(output.strip())
    except ValueError:
        return 0.0


def _probe_audio_stream(config: WorkerBotConfig, path: Path) -> bool:
    ffprobe = _load_ffprobe(config)
    if not ffprobe or not path.exists():
        return False
    ok, output = _run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ],
        timeout=30,
    )
    return ok and "audio" in output


def _scene_visuals_for_metadata(scenes: list[dict[str, str]], article_dir: Path, scene_duration: float) -> list[dict[str, Any]]:
    visuals: list[dict[str, Any]] = []
    start = 0.0
    for index, scene in enumerate(scenes, start=1):
        section = scene.get("section", "scene").replace(" ", "-")
        visuals.append(
            {
                "index": index,
                "section": section,
                "title": scene.get("title", ""),
                "path": str(article_dir / f"{index:02}-{section}.png").replace("\\", "/"),
                "start": round(start, 2),
                "duration": round(scene_duration, 2),
            }
        )
        start += scene_duration
    return visuals


def create_draft_video(candidate: TopicCandidate, output_path: Path, config: WorkerBotConfig) -> tuple[bool, str, dict[str, Any]]:
    ffmpeg = _load_ffmpeg(config)
    if not ffmpeg:
        return False, "ffmpeg not found; draft video was not rendered", {"voice_status": "voiceover_missing"}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    outline = _read_outline(output_path.parent, candidate)
    scenes = _build_scenes(candidate, outline)
    total_duration = min(60, max(45, int(config.video_duration_seconds)))
    scene_duration = total_duration / len(scenes)
    render_dir = output_path.parent / "render_assets"
    article_section_dir = output_path.parent / "editor_assets" / "article_sections"
    audio_dir = output_path.parent / "audio"
    exports_dir = output_path.parent / "exports"
    shorts_dir = output_path.parent / "shorts"
    render_dir.mkdir(parents=True, exist_ok=True)
    article_section_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)
    for index in range(1, 4):
        (shorts_dir / f"short-{index}").mkdir(parents=True, exist_ok=True)

    narration = "\n".join(scene["caption"] for scene in scenes)
    narration_vi = "\n".join(scene["caption_vi"] for scene in scenes)
    narration_path = output_path.parent / "narration.txt"
    voiceover_path = output_path.parent / "voiceover.txt"
    subtitles_path = output_path.parent / "subtitles.srt"
    subtitles_vi_path = output_path.parent / "subtitles_vi.srt"
    subtitles_vi_txt_path = output_path.parent / "subtitles_vi.txt"
    audio_path = render_dir / "voiceover.wav"
    public_voiceover_wav = audio_dir / "voiceover_aligned.wav"
    write_text(narration_path, narration + "\n")
    write_text(voiceover_path, narration + "\n")
    _write_text_sig(subtitles_vi_txt_path, narration_vi + "\n")
    _write_subtitles(subtitles_path, scenes, scene_duration)
    _write_subtitles(subtitles_vi_path, scenes, scene_duration, key="caption_vi")
    subtitles_vi_path.write_text(subtitles_vi_path.read_text(encoding="utf-8"), encoding="utf-8-sig")

    slide_paths: list[Path] = []
    for index, scene in enumerate(scenes):
        section_name = scene.get("section", "scene").replace(" ", "-")
        slide_path = article_section_dir / f"{index + 1:02}-{section_name}.png"
        _draw_slide(slide_path, index, len(scenes), scene, candidate.topic)
        render_copy = render_dir / f"scene_{index + 1:02}.png"
        try:
            render_copy.write_bytes(slide_path.read_bytes())
        except OSError:
            pass
        slide_paths.append(slide_path)
    _draw_thumbnail(output_path.parent / "thumbnail.png", candidate)

    voice_ok, voice_message = _synthesize_voice(narration_path, audio_path)
    if voice_ok:
        try:
            public_voiceover_wav.write_bytes(audio_path.read_bytes())
        except OSError:
            pass
        for mp3_name in ("voiceover.mp3", "voiceover_with_music.mp3"):
            _run([str(ffmpeg), "-y", "-i", str(audio_path), "-codec:a", "libmp3lame", str(audio_dir / mp3_name)], timeout=60)

    segment_paths: list[Path] = []
    for index, slide_path in enumerate(slide_paths):
        segment_path = render_dir / f"segment_{index + 1:02}.mp4"
        ok, message = _run(
            [
                str(ffmpeg),
                "-y",
                "-loop",
                "1",
                "-t",
                f"{scene_duration:.3f}",
                "-i",
                str(slide_path),
                "-vf",
                "scale=1280:720,format=yuv420p",
                "-c:v",
                "libx264",
                "-r",
                "30",
                "-pix_fmt",
                "yuv420p",
                str(segment_path),
            ]
        )
        if not ok:
            return False, f"scene render failed: {message}", {"voice_status": "ok" if voice_ok else "voiceover_missing"}
        segment_paths.append(segment_path)

    concat_path = render_dir / "concat.txt"
    write_text(concat_path, "".join(f"file '{str(path).replace(chr(92), '/')}'\n" for path in segment_paths))
    silent_video = render_dir / "video_silent.mp4"
    ok, message = _run([str(ffmpeg), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path), "-c", "copy", str(silent_video)])
    if not ok:
        return False, f"concat failed: {message}", {"voice_status": "ok" if voice_ok else "voiceover_missing"}

    if voice_ok:
        command = [
            str(ffmpeg),
            "-y",
            "-i",
            str(silent_video),
            "-i",
            str(audio_path),
            "-filter_complex",
            f"[1:a]apad=pad_dur={total_duration}[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-t",
            str(total_duration),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            str(output_path),
        ]
    else:
        command = [
            str(ffmpeg),
            "-y",
            "-i",
            str(silent_video),
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=mono:sample_rate=44100:d={total_duration}",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-t",
            str(total_duration),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            str(output_path),
        ]
    ok, message = _run(command)
    if not ok:
        return False, f"audio merge failed: {message}", {"voice_status": "ok" if voice_ok else "voiceover_missing"}

    duration = _probe_duration(config, output_path)
    has_audio = _probe_audio_stream(config, output_path)
    scene_visuals = _scene_visuals_for_metadata(scenes, article_section_dir, scene_duration)
    write_json(
        output_path.parent / "subtitle_translation_cache.json",
        [{"english": scene["caption"], "vietnamese": scene["caption_vi"]} for scene in scenes],
    )
    write_json(
        output_path.parent / "scenes.json",
        [
            {
                "time": f"{int(index * scene_duration)}-{int((index + 1) * scene_duration)}",
                "type": scene.get("section", "scene"),
                "title": scene.get("title", ""),
            }
            for index, scene in enumerate(scenes)
        ],
    )
    details = {
        "scene_count": len(scenes),
        "scene_visuals": scene_visuals,
        "duration_seconds": round(duration, 2),
        "audio_stream": has_audio,
        "voice_status": "real_placeholder_voice" if voice_ok else "voiceover_missing",
        "voice_message": voice_message,
        "subtitles": str(subtitles_path),
        "subtitles_vi": str(subtitles_vi_path),
        "narration": str(narration_path),
        "voiceover": str(voiceover_path),
    }
    if not voice_ok:
        return output_path.exists() and output_path.stat().st_size > 0, "multi-scene draft video rendered; voiceover_missing; silent audio fallback used", details
    return output_path.exists() and output_path.stat().st_size > 0, "multi-scene draft video rendered with local placeholder voiceover", details
