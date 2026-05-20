from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import ImageDraw

import render_csi300_series as csi300


ROOT = Path(__file__).resolve().parent
SOURCE_CACHE = ROOT / "data" / "global50" / "source_cache" / "csi300"


def patch_light_theme() -> None:
    csi300.BG = "#f6f8fb"
    csi300.CARD = "#ffffff"
    csi300.LINE = "#d8e2ec"
    csi300.GREEN = "#315d8c"
    csi300.ACCENT = "#c45d5d"
    csi300.SOFT = "#eaf1f8"
    csi300.INK = "#111820"
    csi300.MUTED = "#5f6d78"
    csi300.AMBER = "#a15d30"
    csi300.RED = "#a84d4d"
    csi300.BLUE = "#315d8c"
    csi300.RENDER_VERSION = "index_video_studio_light_sample_v1"

    def draw_base(draw: ImageDraw.ImageDraw, spec: csi300.VideoSpec) -> None:
        draw.rectangle((0, 0, 1080, 1920), fill=csi300.BG)
        draw.rectangle((0, 0, 1080, 14), fill=csi300.ACCENT)
        draw.rounded_rectangle((72, 50, 1008, 150), radius=18, fill=csi300.CARD, outline=csi300.LINE, width=3)
        draw.rectangle((104, 86, 180, 96), fill=csi300.ACCENT)
        draw.text((208, 72), "A股指数观察", fill=csi300.GREEN, font=csi300.F_BADGE)
        draw.rounded_rectangle((760, 68, 970, 132), radius=32, fill="#f8fafc", outline=csi300.LINE, width=2)
        draw.text((832, 82), f"{spec.episode}/5", fill=csi300.GREEN, font=csi300.F_BADGE)
        csi300.draw_text(draw, spec.title, (72, 300), 936, csi300.F_TITLE, csi300.INK, 16, 3)
        csi300.draw_text(draw, spec.subtitle, (72, 520), 920, csi300.F_BODY, csi300.MUTED, 12, 2)
        draw.line((72, 650, 1008, 650), fill=csi300.LINE, width=3)

    def draw_footer(draw: ImageDraw.ImageDraw) -> None:
        draw.line((72, 1696, 1008, 1696), fill=csi300.LINE, width=2)
        csi300.draw_text(draw, csi300.DISCLAIMER, (72, 1732), 936, csi300.F_SMALL, csi300.MUTED, 6, 2)
        csi300.draw_text(draw, csi300.DATA_NOTE, (72, 1788), 936, csi300.F_SMALL, csi300.MUTED, 6, 2)

    def draw_scene_header(draw: ImageDraw.ImageDraw, scene: csi300.Scene) -> None:
        draw.rounded_rectangle((72, 730, 1008, 926), radius=22, fill=csi300.SOFT, outline=csi300.LINE, width=2)
        draw.text((112, 774), scene.heading, fill=csi300.GREEN, font=csi300.F_H2)
        csi300.draw_text(draw, scene.summary, (112, 842), 840, csi300.F_BODY, csi300.INK, 10, 2)

    csi300.draw_base = draw_base
    csi300.draw_footer = draw_footer
    csi300.draw_scene_header = draw_scene_header


def load_data() -> csi300.Csi300Data:
    SOURCE_CACHE.mkdir(parents=True, exist_ok=True)
    factsheet_text_path = SOURCE_CACHE / "000300factsheet.txt"
    if factsheet_text_path.exists():
        factsheet_text = factsheet_text_path.read_text(encoding="utf-8")
    else:
        factsheet_pdf, factsheet_text = csi300.download_pdf_text(csi300.FACTSHEET_URL)
        (SOURCE_CACHE / "000300factsheet.pdf").write_bytes(factsheet_pdf)
        factsheet_text_path.write_text(factsheet_text, encoding="utf-8")

    methodology_path = SOURCE_CACHE / "000300_Index_Methodology_cn.pdf"
    if not methodology_path.exists():
        methodology_pdf, _ = csi300.download_pdf_text(csi300.METHODOLOGY_URL)
        methodology_path.write_bytes(methodology_pdf)

    data = csi300.parse_factsheet(factsheet_text)
    data.history = csi300.load_history_data(SOURCE_CACHE)
    data.valuation = csi300.load_valuation_data(SOURCE_CACHE, data)
    data.max_drawdown = csi300.source(
        data.history["max_drawdown"],
        data.history["latest_date"],
        "公开日线点位计算/最大回撤",
        data.history["source"],
    )
    return data


def ffprobe_json(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def check_video(path: Path) -> dict[str, Any]:
    info = ffprobe_json(path)
    streams = info.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    duration = float((info.get("format") or {}).get("duration") or 0)
    passed = (
        path.exists()
        and path.stat().st_size > 0
        and int(video.get("width") or 0) == 1080
        and int(video.get("height") or 0) == 1920
        and audio is not None
        and 45 <= duration <= 100
    )
    return {
        "passed": passed,
        "file": str(path),
        "duration_seconds": round(duration, 2),
        "resolution": f"{video.get('width')}x{video.get('height')}",
        "has_audio": audio is not None,
        "size_mb": round(path.stat().st_size / 1024 / 1024, 2),
    }


def write_sample_report(output_root: Path, results: list[dict[str, Any]]) -> None:
    rows = []
    for item in results:
        status = "PASS" if item["quality"]["passed"] else "FAIL"
        rows.append(
            f"<tr><td>{item['episode']}</td><td>{item['title']}</td><td>{status}</td>"
            f"<td>{item['quality']['duration_seconds']}</td><td>{item['quality']['resolution']}</td>"
            f"<td>{item['quality']['has_audio']}</td><td><a href='{item['relative_final']}'>final.mp4</a></td></tr>"
        )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>沪深300五条样片报告</title>
  <style>
    body {{ margin: 32px; font-family: Arial, 'Microsoft YaHei', sans-serif; color: #111827; background: #f6f8fb; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; }}
    th, td {{ border: 1px solid #d8e2ec; padding: 10px 12px; text-align: left; }}
    th {{ background: #edf2f7; }}
    a {{ color: #315d8c; }}
  </style>
</head>
<body>
  <h1>沪深300五条样片报告</h1>
  <p>人工批准后生成。用途：检查声音、字幕、浅色画面和数据追溯。</p>
  <table>
    <thead><tr><th>集数</th><th>标题</th><th>质量</th><th>时长秒</th><th>分辨率</th><th>音频</th><th>视频</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>"""
    (output_root / "sample_report.html").write_text(html, encoding="utf-8")


def main() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("需要先安装 ffmpeg 和 ffprobe")

    patch_light_theme()
    data = load_data()
    output_root = ROOT / "runs" / f"csi300_light_sample_{datetime.now():%Y%m%d_%H%M%S}"
    output_root.mkdir(parents=True, exist_ok=False)

    results: list[dict[str, Any]] = []
    for spec in csi300.build_specs(data):
        print(f"Rendering {spec.episode}/5 {spec.title}", flush=True)
        final = csi300.render_video(spec, data, output_root)
        episode_dir = final.parent
        first_slide = episode_dir / "scene_01.png"
        if first_slide.exists():
            shutil.copy2(first_slide, episode_dir / "cover.png")
        quality = check_video(final)
        manifest_path = episode_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["sample_approval_status"] = "approved"
        manifest["quality_check_result"] = {**manifest.get("quality_check_result", {}), **quality}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(
            {
                "episode": spec.episode,
                "slug": spec.slug,
                "title": spec.title,
                "final": str(final),
                "relative_final": str(final.relative_to(output_root)).replace("\\", "/"),
                "quality": quality,
            }
        )

    series_manifest = {
        "index_id": "csi300",
        "index_name": "沪深300",
        "review_status": "approved",
        "render_status": "sample_rendered",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output_root": str(output_root),
        "episode_count": len(results),
        "all_passed": all(item["quality"]["passed"] for item in results),
        "episodes": results,
    }
    (output_root / "sample_manifest.json").write_text(json.dumps(series_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_sample_report(output_root, results)
    print(json.dumps(series_manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
