from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import textwrap
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
VIDEO_SIZE = (1080, 1920)
DISCLAIMER = "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。"


app = FastAPI(title="ETF Video Planner")


class TestVideoRequest(BaseModel):
    series: str
    source: dict[str, Any]
    video: dict[str, Any]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc") if bold else Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for item in candidates:
        if item.exists():
            return ImageFont.truetype(str(item), size)
    return ImageFont.load_default()


def wrap_cjk(text: str, chars_per_line: int) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    for char in text:
        current += char
        if len(current) >= chars_per_line or char in "。！？；":
            chunks.append(current.strip())
            current = ""
    if current.strip():
        chunks.append(current.strip())
    return chunks


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fill: str,
    text_font: ImageFont.FreeTypeFont,
    chars_per_line: int,
    line_gap: int,
    max_lines: int,
) -> int:
    x, y = xy
    lines = wrap_cjk(text, chars_per_line)[:max_lines]
    for line in lines:
        draw.text((x, y), line, fill=fill, font=text_font)
        y += text_font.size + line_gap
    return y


def script_parts(script: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n{2,}", script) if part.strip()]
    return [part for part in parts if "数据来源" not in part and "不构成投资建议" not in part]


def make_slide(
    output: Path,
    title: str,
    kicker: str,
    body: list[str],
    footer: str,
    accent: str = "#1f7a4d",
) -> None:
    img = Image.new("RGB", VIDEO_SIZE, "#f4f6f5")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((70, 70, 1010, 1850), radius=28, fill="#ffffff", outline="#d8e0dc", width=3)
    draw.rectangle((70, 70, 1010, 250), fill=accent)
    draw.text((110, 115), kicker, fill="#dcefe5", font=font(34, bold=True))
    draw_wrapped(draw, (110, 285), title, "#17211d", font(58, bold=True), 15, 18, 4)

    y = 520
    body_font = font(38)
    for idx, paragraph in enumerate(body, start=1):
        if y > 1500:
            break
        draw.rounded_rectangle((110, y, 970, y + 96), radius=18, fill="#eef4f1")
        draw.ellipse((134, y + 28, 174, y + 68), fill=accent)
        draw.text((146, y + 31), str(idx), fill="#ffffff", font=font(24, bold=True))
        y = draw_wrapped(draw, (196, y + 24), paragraph, "#24302b", body_font, 18, 12, 3) + 30

    draw.line((110, 1680, 970, 1680), fill="#d8e0dc", width=2)
    draw_wrapped(draw, (110, 1710), footer, "#65716c", font(28), 27, 10, 3)
    img.save(output)


def make_slides(run_dir: Path, payload: TestVideoRequest) -> list[Path]:
    video = payload.video
    source = payload.source
    title = str(video.get("title") or "指数观察测试视频")
    template_name = str(video.get("templateName") or "测试视频")
    parts = script_parts(str(video.get("script") or ""))

    slides = [
        {
            "title": title,
            "kicker": f"{source.get('shortName', '指数')} | {template_name}",
            "body": parts[:2] or ["这是一条指数观察测试视频。"],
            "footer": DISCLAIMER,
        },
        {
            "title": "核心讲解",
            "kicker": "SCRIPT",
            "body": parts[2:5] or parts[:3],
            "footer": "建议成片时长：60-90 秒；超过 3 分钟建议拆成上下集。",
        },
        {
            "title": "画面安排",
            "kicker": "VISUALS",
            "body": [str(item) for item in video.get("visuals", [])][:4] or ["信息卡片", "字幕", "风险提示"],
            "footer": "图表和截图建议原样入画，AI 只做背景和转场辅助。",
        },
        {
            "title": "片尾提示",
            "kicker": "DISCLOSURE",
            "body": [DISCLAIMER, f"数据来源：{source.get('dataSource', '待确认')}", f"数据日期：{source.get('dataDate', '待确认')}"],
            "footer": "测试视频生成成功后，可继续接入 Qwen TTS 和批量合成。",
        },
    ]

    output_paths: list[Path] = []
    for index, slide in enumerate(slides, start=1):
        path = run_dir / f"slide_{index:02d}.png"
        make_slide(path, slide["title"], slide["kicker"], slide["body"], slide["footer"])
        output_paths.append(path)
    return output_paths


def run_command(args: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"Command failed: {' '.join(args)}")


def make_voice(run_dir: Path, script: str) -> Path:
    voice_path = run_dir / "voice.wav"
    ps_script = run_dir / "make_voice.ps1"
    text_path = run_dir / "voice_text.txt"
    clean_script = re.sub(r"\s+", " ", script).strip()
    text_path.write_text(clean_script, encoding="utf-8")
    estimated_duration = max(30, min(90, math.ceil(len(clean_script) / 4)))
    escaped_voice_path = str(voice_path).replace("'", "''")
    escaped_text_path = str(text_path).replace("'", "''")
    ps_script.write_text(
        "\n".join(
            [
                "Add-Type -AssemblyName System.Speech",
                f"$text = Get-Content -LiteralPath '{escaped_text_path}' -Raw -Encoding UTF8",
                "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer",
                "$synth.Rate = 0",
                "$synth.Volume = 100",
                f"$synth.SetOutputToWaveFile('{escaped_voice_path}')",
                "$synth.Speak($text)",
                "$synth.Dispose()",
            ]
        ),
        encoding="utf-8",
    )
    try:
        run_command(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_script)])
    except Exception:
        run_command(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t",
                str(estimated_duration),
                str(voice_path),
            ]
        )
    if probe_duration(voice_path) < 10:
        run_command(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t",
                str(estimated_duration),
                str(voice_path),
            ]
        )
    return voice_path


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        capture_output=True,
    )
    try:
        return max(1.0, float(result.stdout.strip()))
    except ValueError:
        return 45.0


def make_subtitles(run_dir: Path, script: str, duration: float) -> Path:
    path = run_dir / "subtitles.srt"
    parts = script_parts(script)[:6] or [script.strip()]
    slot = duration / max(1, len(parts))
    lines: list[str] = []
    for index, part in enumerate(parts, start=1):
        start = (index - 1) * slot
        end = min(duration, index * slot)
        lines.extend([str(index), f"{srt_time(start)} --> {srt_time(end)}", part[:80], ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def srt_time(seconds: float) -> str:
    total_ms = int(seconds * 1000)
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def make_video(run_dir: Path, slides: list[Path], voice: Path, script: str) -> Path:
    duration = probe_duration(voice)
    make_subtitles(run_dir, script, duration)
    per_slide = max(3.0, duration / len(slides))
    concat = run_dir / "slides.txt"
    concat_lines: list[str] = []
    for slide in slides:
        concat_lines.append(f"file '{slide.as_posix()}'")
        concat_lines.append(f"duration {per_slide:.3f}")
    concat_lines.append(f"file '{slides[-1].as_posix()}'")
    concat.write_text("\n".join(concat_lines), encoding="utf-8")

    slides_video = run_dir / "slides.mp4"
    final_video = run_dir / "final.mp4"
    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-vf",
            "fps=30,format=yuv420p",
            "-c:v",
            "libx264",
            str(slides_video),
        ]
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(slides_video),
            "-i",
            str(voice),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(final_video),
        ]
    )
    return final_video


@app.post("/api/render-test-video")
def render_test_video(payload: TestVideoRequest) -> dict[str, str]:
    run_id = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        (run_dir / "manifest.json").write_text(payload.model_dump_json(indent=2), encoding="utf-8")
        script = str(payload.video.get("script") or "")
        slides = make_slides(run_dir, payload)
        voice = make_voice(run_dir, script)
        final_video = make_video(run_dir, slides, voice, script)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "videoUrl": f"/runs/{run_id}/final.mp4",
        "outputPath": str(final_video),
        "runId": run_id,
    }


@app.get("/runs/{run_id}/{file_name}")
def get_run_file(run_id: str, file_name: str) -> FileResponse:
    safe_name = Path(file_name).name
    path = RUNS_DIR / run_id / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path)


if not shutil.which("ffmpeg"):
    raise RuntimeError("未找到 FFmpeg，请先安装或加入 PATH。")

app.mount("/", StaticFiles(directory=ROOT, html=True), name="static")
