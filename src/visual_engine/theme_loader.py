from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_THEME_PATH = ROOT / "config" / "style_themes.yaml"


@dataclass(frozen=True)
class CanvasSpec:
    width: int
    height: int
    safe_margin: int
    subtitle_reserved_top: int
    footer_top: int


@dataclass(frozen=True)
class FontSpec:
    family: str
    min_body_size: int
    cover_title_size: int
    body_title_size: int
    body_size: int
    small_size: int


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    region: str
    index_type: str
    background: str
    surface: str
    panel: str
    primary: str
    secondary: str
    accent: str
    text: str
    muted: str
    border: str
    shape: str
    mood: str

    @property
    def palette(self) -> list[str]:
        return [self.primary, self.secondary, self.accent]


def load_theme_config(path: Path | str = DEFAULT_THEME_PATH) -> dict[str, Any]:
    theme_path = Path(path)
    with theme_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_canvas(config: dict[str, Any] | None = None) -> CanvasSpec:
    config = config or load_theme_config()
    canvas = config["canvas"]
    return CanvasSpec(
        width=int(canvas["width"]),
        height=int(canvas["height"]),
        safe_margin=int(canvas["safe_margin"]),
        subtitle_reserved_top=int(canvas["subtitle_reserved_top"]),
        footer_top=int(canvas["footer_top"]),
    )


def get_font_spec(config: dict[str, Any] | None = None) -> FontSpec:
    config = config or load_theme_config()
    font = config["font"]
    return FontSpec(
        family=str(font["family"]),
        min_body_size=int(font["min_body_size"]),
        cover_title_size=int(font["cover_title_size"]),
        body_title_size=int(font["body_title_size"]),
        body_size=int(font["body_size"]),
        small_size=int(font["small_size"]),
    )


def get_theme(theme_key: str, config: dict[str, Any] | None = None) -> Theme:
    config = config or load_theme_config()
    themes = config["themes"]
    if theme_key not in themes:
        theme_key = "global"
    raw = themes[theme_key]
    return Theme(key=theme_key, **raw)


def resolve_theme_key(
    *,
    region: str = "",
    index_type: str = "",
    template_type: str = "",
    style_theme: str = "",
) -> str:
    region_text = (region or "").lower()
    index_type_text = (index_type or template_type or "").lower()
    style_text = (style_theme or "").lower()
    combined = " ".join([region_text, index_type_text, style_text])

    if "low_volatility" in combined or "低波" in combined:
        return "low_volatility"
    if "dividend" in combined or "红利" in combined:
        if any(token in combined for token in ["hongkong", "香港", "港股"]):
            return "hongkong"
        return "china_dividend"
    if "technology" in combined or "科技" in combined or "nasdaq" in combined:
        return "us_technology" if any(token in combined for token in ["美国", "us", "美股", "nasdaq"]) else "global"
    if any(token in combined for token in ["香港", "港股", "hongkong", "hong kong"]):
        return "hongkong"
    if any(token in combined for token in ["美国", "us", "美股", "spx", "s&p"]):
        return "us_broad"
    if any(token in combined for token in ["欧洲", "德国", "法国", "英国", "欧元区", "europe", "dax", "ftse", "cac"]):
        return "europe"
    if any(token in combined for token in ["日本", "japan", "nikkei"]):
        return "japan"
    if any(token in combined for token in ["印度", "india", "nifty", "sensex"]):
        return "india"
    if any(token in combined for token in ["中国内地", "a股", "china", "csi", "沪深", "中证"]):
        return "china_broad"
    return "global"


def load_resolved_theme(**kwargs: str) -> tuple[Theme, CanvasSpec, FontSpec]:
    config = load_theme_config()
    key = resolve_theme_key(**kwargs)
    return get_theme(key, config), get_canvas(config), get_font_spec(config)

