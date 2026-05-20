from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image


FORBIDDEN_VISUAL_TEXT = ["科普", "新手", "小白", "评分", "暂无", "未提供", "数据缺失"]


def _collect_text(meta: dict[str, Any]) -> str:
    return "\n".join(str(item.get("text", "")) for item in meta.get("text_boxes", []))


def check_visual_asset(image_path: Path | str, metadata_path: Path | str | None = None) -> dict[str, Any]:
    image_path = Path(image_path)
    metadata_path = Path(metadata_path) if metadata_path else image_path.with_suffix(".json")
    errors: list[str] = []
    warnings: list[str] = []

    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        pixels = rgb.getdata()
        dark_pixels = 0
        for red, green, blue in pixels:
            luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
            if luminance < 90:
                dark_pixels += 1
        dark_ratio = dark_pixels / max(width * height, 1)
    if (width, height) != (1080, 1920):
        errors.append(f"分辨率不是 1080x1920: {width}x{height}")
    if dark_ratio > 0.08:
        errors.append(f"深色面积过大: {dark_ratio:.2%}")

    if not metadata_path.exists():
        errors.append("缺少视觉元数据")
        return {"passed": False, "image": str(image_path), "errors": errors, "warnings": warnings}

    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    canvas = meta.get("canvas", {})
    safe = int(canvas.get("safe_margin", meta.get("safe_margin", 72)))
    subtitle_top = int(canvas.get("subtitle_reserved_top", meta.get("subtitle_reserved_top", 1460)))
    text = _collect_text(meta)

    for word in FORBIDDEN_VISUAL_TEXT:
        if word in text:
            errors.append(f"出现禁用词: {word}")

    if int(meta.get("body_bottom", 0)) > subtitle_top:
        errors.append("正文区域进入字幕预留区")

    for item in meta.get("text_boxes", []):
        bbox = item.get("bbox", [0, 0, 0, 0])
        if len(bbox) != 4:
            errors.append("文字框格式不正确")
            continue
        x1, y1, x2, y2 = map(int, bbox)
        if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
            errors.append(f"文字越出画布: {item.get('text', '')}")
        if item.get("font_size", 99) < 28:
            errors.append(f"字体过小: {item.get('text', '')}")
        if x1 < safe - 12 and y1 > 220:
            warnings.append(f"文字接近左安全边距: {item.get('text', '')}")
        if x2 > width - safe + 12 and y1 > 220:
            warnings.append(f"文字接近右安全边距: {item.get('text', '')}")

    if meta.get("asset_type") == "cover":
        fields = meta.get("cover_fields", [])
        if fields != ["index_name", "positioning", "series_name"]:
            errors.append("封面字段不符合要求")
    if meta.get("asset_type") == "body_card":
        core_line_count = int(meta.get("core_line_count", 0))
        if core_line_count > 5:
            errors.append("正文卡核心文字超过 5 行")
    if meta.get("overflow"):
        warnings.append("存在文字压缩或截断，请人工复核")

    return {
        "passed": not errors,
        "image": str(image_path),
        "metadata": str(metadata_path),
        "errors": errors,
        "warnings": warnings,
        "dark_ratio": round(dark_ratio, 4),
    }


def write_visual_report(results: list[dict[str, Any]], output_path: Path | str) -> None:
    output_path = Path(output_path)
    rows = []
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        errors = "<br>".join(result["errors"]) if result["errors"] else "-"
        warnings = "<br>".join(result["warnings"]) if result["warnings"] else "-"
        img = Path(result["image"]).name
        rows.append(f"<tr><td>{status}</td><td>{img}</td><td>{errors}</td><td>{warnings}</td></tr>")
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Visual Theme Samples Report</title>
  <style>
    body {{ font-family: Arial, 'Microsoft YaHei', sans-serif; margin: 32px; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d8dee7; padding: 10px 12px; text-align: left; vertical-align: top; }}
    th {{ background: #f2f4f7; }}
    td:first-child {{ font-weight: 700; }}
  </style>
</head>
<body>
  <h1>Visual Theme Samples Report</h1>
  <p>用于人工确认的视觉主题样例，只包含确定性生成的封面和正文卡。</p>
  <table>
    <thead><tr><th>状态</th><th>文件</th><th>问题</th><th>提醒</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    target = Path(argv[0]) if argv else Path(".")
    images = sorted(target.glob("*.png")) if target.is_dir() else [target]
    results = [check_visual_asset(path) for path in images]
    if target.is_dir():
        write_visual_report(results, target / "visual_quality_report.html")
    print(json.dumps({"passed": all(item["passed"] for item in results), "count": len(results)}, ensure_ascii=False, indent=2))
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
