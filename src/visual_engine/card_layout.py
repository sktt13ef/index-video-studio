from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .text_fit import fit_text_block, load_font, wrap_text
from .theme_loader import CanvasSpec, FontSpec, Theme, get_canvas, get_font_spec, get_theme, load_theme_config


def _rounded(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None, width: int = 3) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _line(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str) -> None:
    draw.line(xy, fill=fill, width=4)


def _write_lines(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    lines: list[str],
    *,
    font_size: int,
    fill: str,
    bold: bool = False,
    line_height: int | None = None,
) -> list[dict[str, Any]]:
    font = load_font(font_size, bold=bold)
    x, y = xy
    boxes: list[dict[str, Any]] = []
    line_height = line_height or int(font_size * 1.32)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        boxes.append({"text": line, "bbox": list(map(int, bbox)), "font_size": font_size})
        y += line_height
    return boxes


def _draw_header(draw: ImageDraw.ImageDraw, theme: Theme, canvas: CanvasSpec, label: str, episode: str | None = None) -> dict[str, Any]:
    header_h = 196
    draw.rectangle((0, 0, canvas.width, header_h), fill=theme.primary)
    boxes = _write_lines(draw, (canvas.safe_margin, 74), [label], font_size=30, fill=theme.surface, bold=True)
    if episode:
        pill_w = 258
        pill_h = 64
        x2 = canvas.width - canvas.safe_margin
        x1 = x2 - pill_w
        y1 = 66
        _rounded(draw, (x1, y1, x2, y1 + pill_h), 32, theme.surface, None)
        pill_font = load_font(34, bold=True)
        bbox = draw.textbbox((0, 0), episode, font=pill_font)
        draw.text((x1 + (pill_w - (bbox[2] - bbox[0])) / 2, y1 + 12), episode, font=pill_font, fill=theme.primary)
        boxes.append({"text": episode, "bbox": [x1, y1, x2, y1 + pill_h], "font_size": 34})
    return {"type": "header", "bbox": [0, 0, canvas.width, header_h], "text_boxes": boxes}


def render_cover(
    output_path: Path | str,
    *,
    theme: Theme,
    index_name: str,
    positioning: str,
    series_name: str,
    canvas: CanvasSpec | None = None,
    font_spec: FontSpec | None = None,
) -> dict[str, Any]:
    canvas = canvas or get_canvas()
    font_spec = font_spec or get_font_spec()
    output_path = Path(output_path)
    image = Image.new("RGB", (canvas.width, canvas.height), theme.background)
    draw = ImageDraw.Draw(image)
    boxes: list[dict[str, Any]] = []

    boxes.extend(_draw_header(draw, theme, canvas, series_name)["text_boxes"])
    x = canvas.safe_margin
    max_width = canvas.width - canvas.safe_margin * 2
    y = 346

    title_fit = fit_text_block(
        draw,
        index_name,
        max_width,
        2,
        start_size=font_spec.cover_title_size,
        min_size=50,
        bold=True,
        max_visual_chars=24,
    )
    boxes.extend(_write_lines(draw, (x, y), title_fit.lines, font_size=title_fit.font_size, fill=theme.text, bold=True, line_height=title_fit.line_height))
    y += title_fit.line_height * len(title_fit.lines) + 76

    pos_fit = fit_text_block(draw, positioning, max_width, 2, start_size=42, min_size=34, max_visual_chars=28)
    boxes.extend(_write_lines(draw, (x, y), pos_fit.lines, font_size=pos_fit.font_size, fill=theme.muted, line_height=pos_fit.line_height))

    y = 1010
    panel_h = 180
    _rounded(draw, (x, y, canvas.width - canvas.safe_margin, y + panel_h), 12 if theme.shape == "square_blocks" else 28, theme.panel, theme.border, 3)
    draw.rectangle((x + 44, y + 64, x + 220, y + 74), fill=theme.accent)
    draw.rectangle((x + 44, y + 96, x + 420, y + 106), fill=theme.primary)

    image.save(output_path)
    meta = {
        "asset_type": "cover",
        "path": str(output_path),
        "canvas": canvas.__dict__,
        "theme_key": theme.key,
        "safe_margin": canvas.safe_margin,
        "subtitle_reserved_top": canvas.subtitle_reserved_top,
        "body_bottom": y + panel_h,
        "text_boxes": boxes,
        "cover_fields": ["index_name", "positioning", "series_name"],
        "core_line_count": len(title_fit.lines) + len(pos_fit.lines),
        "overflow": title_fit.overflow or pos_fit.overflow,
    }
    output_path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def render_body_card(
    output_path: Path | str,
    *,
    theme: Theme,
    title: str,
    subtitle: str,
    section_title: str,
    points: list[str],
    episode: str,
    source_note: str,
    canvas: CanvasSpec | None = None,
    font_spec: FontSpec | None = None,
) -> dict[str, Any]:
    canvas = canvas or get_canvas()
    font_spec = font_spec or get_font_spec()
    output_path = Path(output_path)
    image = Image.new("RGB", (canvas.width, canvas.height), theme.background)
    draw = ImageDraw.Draw(image)
    boxes: list[dict[str, Any]] = []

    boxes.extend(_draw_header(draw, theme, canvas, theme.label, episode)["text_boxes"])
    x = canvas.safe_margin
    max_width = canvas.width - canvas.safe_margin * 2
    y = 310

    title_fit = fit_text_block(draw, title, max_width, 2, start_size=font_spec.body_title_size, min_size=42, bold=True, max_visual_chars=26)
    boxes.extend(_write_lines(draw, (x, y), title_fit.lines, font_size=title_fit.font_size, fill=theme.text, bold=True, line_height=title_fit.line_height))
    y += title_fit.line_height * len(title_fit.lines) + 58

    subtitle_fit = fit_text_block(draw, subtitle, max_width, 2, start_size=36, min_size=30, max_visual_chars=30)
    boxes.extend(_write_lines(draw, (x, y), subtitle_fit.lines, font_size=subtitle_fit.font_size, fill=theme.muted, line_height=subtitle_fit.line_height))
    y += subtitle_fit.line_height * len(subtitle_fit.lines) + 58
    _line(draw, (x, y, canvas.width - canvas.safe_margin, y), theme.border)
    y += 86

    panel_x1, panel_x2 = x, canvas.width - canvas.safe_margin
    panel_y1 = y
    inner_x = panel_x1 + 44
    inner_w = panel_x2 - panel_x1 - 88
    panel_h = 620
    _rounded(draw, (panel_x1, panel_y1, panel_x2, panel_y1 + panel_h), 24, theme.panel, theme.border, 3)
    boxes.extend(_write_lines(draw, (inner_x, panel_y1 + 44), [section_title], font_size=42, fill=theme.primary, bold=True))

    point_y = panel_y1 + 128
    shown_points = points[:5]
    point_font = load_font(font_spec.body_size)
    for idx, point in enumerate(shown_points, start=1):
        row_h = 82
        row_y = point_y + (idx - 1) * (row_h + 22)
        _rounded(draw, (inner_x, row_y, panel_x2 - 44, row_y + row_h), 12, theme.surface, None)
        badge_size = 48
        draw.ellipse((inner_x + 22, row_y + 17, inner_x + 22 + badge_size, row_y + 17 + badge_size), fill=theme.primary)
        badge_font = load_font(26, bold=True)
        draw.text((inner_x + 39, row_y + 22), str(idx), font=badge_font, fill=theme.surface)
        lines = wrap_text(draw, point, point_font, inner_w - 106, max_visual_chars=28)
        line = lines[0] if lines else point
        draw.text((inner_x + 96, row_y + 20), line, font=point_font, fill=theme.text)
        bbox = draw.textbbox((inner_x + 96, row_y + 20), line, font=point_font)
        boxes.append({"text": line, "bbox": list(map(int, bbox)), "font_size": font_spec.body_size})

    body_bottom = panel_y1 + panel_h
    _line(draw, (x, canvas.footer_top, canvas.width - canvas.safe_margin, canvas.footer_top), theme.border)
    footer_lines = wrap_text(draw, source_note, load_font(font_spec.small_size), max_width, max_visual_chars=34)
    boxes.extend(_write_lines(draw, (x, canvas.footer_top + 40), footer_lines[:3], font_size=font_spec.small_size, fill=theme.muted))

    image.save(output_path)
    meta = {
        "asset_type": "body_card",
        "path": str(output_path),
        "canvas": canvas.__dict__,
        "theme_key": theme.key,
        "safe_margin": canvas.safe_margin,
        "subtitle_reserved_top": canvas.subtitle_reserved_top,
        "body_bottom": body_bottom,
        "text_boxes": boxes,
        "core_line_count": len(shown_points),
        "overflow": title_fit.overflow or subtitle_fit.overflow or len(points) > 5,
    }
    output_path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def render_theme_pair(output_dir: Path | str, theme_key: str, sample: dict[str, Any]) -> tuple[Path, Path]:
    config = load_theme_config()
    theme = get_theme(theme_key, config)
    canvas = get_canvas(config)
    font_spec = get_font_spec(config)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cover = output_dir / f"cover_{theme_key}.png"
    card = output_dir / f"card_{theme_key}.png"
    render_cover(
        cover,
        theme=theme,
        index_name=sample["index_name"],
        positioning=sample["positioning"],
        series_name=sample["series_name"],
        canvas=canvas,
        font_spec=font_spec,
    )
    render_body_card(
        card,
        theme=theme,
        title=sample["title"],
        subtitle=sample["subtitle"],
        section_title=sample["section_title"],
        points=sample["points"],
        episode=sample["episode"],
        source_note=sample["source_note"],
        canvas=canvas,
        font_spec=font_spec,
    )
    return cover, card
