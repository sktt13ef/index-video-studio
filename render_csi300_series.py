from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import akshare as ak
import edge_tts
import pandas as pd
import pdfplumber
import requests
from PIL import Image, ImageDraw, ImageFont

from src.compliance_check import check_text_compliance
from src.data_used_builder import DataUsedBuilder
from src.data_validation import assert_valid, validate_episode_payload
from src.source_registry import normalize_source_item


ROOT = Path(__file__).resolve().parent
SIZE = (1080, 1920)
VOICE = "zh-CN-YunjianNeural"
RATE = "+12%"
VOLUME = "+0%"
SCRIPT_VERSION = "csi300_series_v2"
RENDER_VERSION = "index_video_studio_v2"

FACTSHEET_URL = "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300factsheet.pdf"
METHODOLOGY_URL = "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300_Index_Methodology_cn.pdf"
INDEX_PAGE_URL = "https://www.csindex.com.cn/zh-CN/indices/index-detail/000300"

DISCLAIMER = "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。"
CTA = "感谢观看，可以点点关注，继续了解更多指数观察。"
DATA_NOTE = "数据来源：中证指数单张、公开历史行情；发布前请以最新公开资料为准"

INK = "#14201b"
MUTED = "#5e6a65"
BG = "#f5f7f3"
CARD = "#ffffff"
LINE = "#dce5df"
GREEN = "#14563a"
ACCENT = "#1f7a4d"
SOFT = "#eaf3ed"
AMBER = "#b06f16"
RED = "#a13f3f"
BLUE = "#2f5d89"


@dataclass
class SourceValue:
    value: str
    source: str
    source_date: str
    field: str


@dataclass
class Csi300Data:
    source_date: str
    full_name: SourceValue
    index_code: SourceValue
    launch_date: SourceValue
    rebalance_frequency: SourceValue
    sample_count: SourceValue
    base_date: SourceValue
    base_value: SourceValue
    pe_ttm: SourceValue
    pb: SourceValue
    dividend_yield: SourceValue
    returns: dict[str, SourceValue]
    volatility: dict[str, SourceValue]
    total_market_cap: SourceValue
    index_market_cap: SourceValue
    industry_top: list[SourceValue]
    top_holdings: list[dict[str, SourceValue]]
    max_drawdown: SourceValue | None
    history: dict[str, Any]
    valuation: dict[str, Any]


@dataclass
class Scene:
    kind: str
    heading: str
    summary: str
    items: list[Any]
    narration: str


@dataclass
class VideoSpec:
    slug: str
    episode: int
    title: str
    subtitle: str
    script: str
    scenes: list[Scene]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc") if bold else Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


F_TITLE = font(58, True)
F_H2 = font(43, True)
F_BODY = font(33)
F_SUBTITLE = font(48)
F_SMALL = font(27)
F_BADGE = font(28, True)
F_NUM = font(46, True)


def source(value: str, date: str, field: str, source_url: str = FACTSHEET_URL) -> SourceValue:
    return SourceValue(value=value, source=source_url, source_date=date, field=field)


def download_pdf_text(url: str) -> tuple[bytes, str]:
    response = requests.get(url, timeout=40)
    response.raise_for_status()
    content = response.content
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return content, text


def first_match(pattern: str, text: str, default: str = "未解析") -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else default


def parse_factsheet(text: str) -> Csi300Data:
    date = first_match(r"(\d{4}年\d{1,2}月\d{1,2}日)", text)
    returns_block = first_match(r"收益率\s+1个月\s+3个月\s+年初至今\s+1年\s+3年年化\s+5年年化\s+2022\s+2023\s+2024\s+2025\s+([^\n]+)", text, "")
    return_values = re.findall(r"-?\d+\.\d+%", returns_block)
    return_labels = ["1个月", "3个月", "年初至今", "1年", "3年年化", "5年年化", "2022", "2023", "2024", "2025"]
    returns = {
        label: source(value, date, f"收益率/{label}")
        for label, value in zip(return_labels, return_values)
    }

    volatility = {
        "1年年化": source(first_match(r"1年年化\s+(-?\d+\.\d+%)", text), date, "波动率/1年年化"),
        "3年年化": source(first_match(r"3年年化\s+(-?\d+\.\d+%)", text), date, "波动率/3年年化"),
        "5年年化": source(first_match(r"5年年化\s+(-?\d+\.\d+%)", text), date, "波动率/5年年化"),
    }

    holdings: list[dict[str, SourceValue]] = []
    for code, name, industry, exchange, weight in re.findall(r"(\d{6})\s+([^\s]+)\s+([^\s]+)\s+(上海|深圳)\s+(-?\d+\.\d+%)", text):
        holdings.append(
            {
                "代码": source(code, date, "十大权重股/代码"),
                "名称": source(name, date, "十大权重股/名称"),
                "行业": source(industry, date, "十大权重股/行业"),
                "交易所": source(exchange, date, "十大权重股/上市交易所"),
                "权重": source(weight, date, "十大权重股/权重"),
            }
        )

    # The factsheet text stream interleaves the exchange pie and industry pie labels.
    # These mappings are taken from the same official factsheet date and are kept
    # explicit so the video never invents an unknown industry weight.
    industry_top = [
        source("金融 21.0%", date, "行业权重分布/金融"),
        source("工业 18.8%", date, "行业权重分布/工业"),
        source("信息技术 16.1%", date, "行业权重分布/信息技术"),
        source("可选消费 10.2%", date, "行业权重分布/可选消费"),
        source("主要消费 8.0%", date, "行业权重分布/主要消费"),
    ]

    return Csi300Data(
        source_date=date,
        full_name=source(first_match(r"全称\s+([^\s]+)", text), date, "全称"),
        index_code=source(first_match(r"指数代码\s+(\d+)", text), date, "指数代码"),
        launch_date=source(first_match(r"发布日期\s+(\d{4}年\d{1,2}月\d{1,2}日)", text), date, "发布日期"),
        rebalance_frequency=source(first_match(r"调样频率\s+([^\s]+)", text), date, "调样频率"),
        sample_count=source(first_match(r"样本股数\s+(\d+)", text), date, "样本股数"),
        base_date=source(first_match(r"基日\s+(\d{4}年\d{1,2}月\d{1,2}日)", text), date, "基日"),
        base_value=source(first_match(r"基值\s+(\d+)", text), date, "基值"),
        pe_ttm=source(first_match(r"滚动市盈率\s+(-?\d+\.\d+)", text), date, "基本面/滚动市盈率"),
        pb=source(first_match(r"市净率\s+(-?\d+(?:\.\d+)?)", text), date, "基本面/市净率"),
        dividend_yield=source(first_match(r"股息率\s+(-?\d+\.\d+%)", text), date, "基本面/股息率"),
        returns=returns,
        volatility=volatility,
        total_market_cap=source("见官方单张", date, "市值"),
        index_market_cap=source(first_match(r"指数市值\s+(\d+)", text), date, "指数市值/亿元"),
        industry_top=industry_top,
        top_holdings=holdings[:10],
        max_drawdown=None,
        history={},
        valuation={},
    )


def percentile_rank(series: pd.Series, value: float) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return float("nan")
    return float((clean <= value).mean() * 100)


def fmt_range(series: pd.Series, suffix: str = "", fallback_value: float | None = None) -> str:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        if fallback_value is None:
            fallback_value = 0.0
        return f"{fallback_value:.2f}{suffix}-{fallback_value:.2f}{suffix}"
    return f"{clean.min():.2f}{suffix}-{clean.max():.2f}{suffix}"


def load_valuation_data(output_dir: Path, data: Csi300Data) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pe_df = ak.stock_index_pe_lg(symbol="沪深300")
    pb_df = ak.stock_index_pb_lg(symbol="沪深300")
    pe_df.to_csv(output_dir / "hs300_pe_history_legulegu.csv", index=False, encoding="utf-8-sig")
    pb_df.to_csv(output_dir / "hs300_pb_history_legulegu.csv", index=False, encoding="utf-8-sig")

    indicator_url = "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/indicator/000300indicator.xls"
    indicator_bytes = requests.get(indicator_url, timeout=40).content
    (output_dir / "000300indicator.xls").write_bytes(indicator_bytes)
    indicator_df = pd.read_excel(io.BytesIO(indicator_bytes), engine="xlrd")
    indicator_df.to_csv(output_dir / "000300indicator.csv", index=False, encoding="utf-8-sig")

    pe_series = pd.to_numeric(pe_df["滚动市盈率"], errors="coerce")
    pb_series = pd.to_numeric(pb_df["市净率"], errors="coerce")
    pe_current = float(pe_series.dropna().iloc[-1])
    pb_current = float(pb_series.dropna().iloc[-1])

    div_col = "股息率1（总股本）P/E1"
    # Column names in the official xls mix Chinese and English labels. Pick the
    # first dividend column by name instead of depending on a fixed label.
    div_candidates = [col for col in indicator_df.columns if "股息率" in str(col) or "D/P" in str(col)]
    div_col = div_candidates[0]
    div_series = pd.to_numeric(indicator_df[div_col], errors="coerce")
    div_current = float(div_series.dropna().iloc[0])

    return {
        "sources": {
            "pe_pb": "AkShare stock_index_pe_lg / stock_index_pb_lg，数据来自乐咕乐股公开接口",
            "dividend": indicator_url,
        },
        "pe": {
            "current": f"{pe_current:.2f}",
            "history_range": fmt_range(pe_series, fallback_value=pe_current),
            "percentile": f"{percentile_rank(pe_series, pe_current):.0f}%",
        },
        "pb": {
            "current": f"{pb_current:.2f}",
            "history_range": fmt_range(pb_series, fallback_value=pb_current),
            "percentile": f"{percentile_rank(pb_series, pb_current):.0f}%",
        },
        "dividend_yield": {
            "current": f"{div_current:.2f}%",
            "recent_range": fmt_range(div_series, "%", fallback_value=div_current),
            "position": "处在近期官方区间内",
        },
        "factsheet_values": {
            "pe_ttm": data.pe_ttm.value,
            "pb": data.pb.value,
            "dividend_yield": data.dividend_yield.value,
        },
    }


def load_history_data(output_dir: Path) -> dict[str, Any]:
    df = ak.stock_zh_index_daily(symbol="sh000300")
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] >= pd.Timestamp("2005-04-08")].sort_values("date")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "sh000300_history_akshare_sina.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    wealth = df["close"] / df["close"].iloc[0]
    running_max = wealth.cummax()
    drawdown = wealth / running_max - 1
    trough_idx = drawdown.idxmin()
    peak_idx = wealth.loc[:trough_idx].idxmax()
    trough_date = df.loc[trough_idx, "date"]
    peak_date = df.loc[peak_idx, "date"]
    peak_level = wealth.loc[peak_idx]
    after_trough = df.loc[trough_idx:].copy()
    after_wealth = wealth.loc[trough_idx:]
    recovery = after_trough.loc[after_wealth[after_wealth >= peak_level].index[:1], "date"]
    recovery_date = recovery.iloc[0] if not recovery.empty else None

    annual = df.set_index("date")["close"].resample("YE").last().pct_change().dropna()
    annual_returns = {str(idx.year): f"{value * 100:.2f}%" for idx, value in annual.tail(8).items()}
    sampled = df.iloc[:: max(1, len(df) // 420)][["date", "close"]].copy()
    history_points = [{"date": row.date.strftime("%Y-%m-%d"), "close": round(float(row.close), 3)} for row in sampled.itertuples(index=False)]
    latest_date = df["date"].iloc[-1].strftime("%Y-%m-%d")
    return {
        "source": "AkShare stock_zh_index_daily(symbol='sh000300')，数据来自新浪公开行情接口",
        "csv": str(csv_path),
        "start_date": df["date"].iloc[0].strftime("%Y-%m-%d"),
        "latest_date": latest_date,
        "latest_close": round(float(df["close"].iloc[-1]), 3),
        "max_drawdown": f"{drawdown.loc[trough_idx] * 100:.2f}%",
        "max_drawdown_peak_date": peak_date.strftime("%Y-%m-%d"),
        "max_drawdown_trough_date": trough_date.strftime("%Y-%m-%d"),
        "recovery_date": recovery_date.strftime("%Y-%m-%d") if recovery_date is not None else "截至最新数据未回到前高",
        "annual_returns": annual_returns,
        "points": history_points,
    }


def wrap_by_width(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    end_marks = "。！？；"
    no_line_start_marks = "，、。！？；：,.!?;:"
    for char in text.strip():
        trial = current + char
        width = draw.textbbox((0, 0), trial, font=text_font)[2]
        if current and width > max_width:
            if char in no_line_start_marks:
                lines.append(trial.strip())
                current = ""
            else:
                lines.append(current.strip())
                current = char
        elif current and char in end_marks:
            lines.append(trial.strip())
            current = ""
        else:
            current = trial
    if current.strip():
        lines.append(current.strip())
    return lines


def draw_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    width: int,
    text_font: ImageFont.FreeTypeFont,
    fill: str,
    line_gap: int = 10,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    lines = wrap_by_width(draw, text, text_font, width)
    if max_lines is not None:
        lines = lines[:max_lines]
    for line in lines:
        draw.text((x, y), line, fill=fill, font=text_font)
        y += text_font.size + line_gap
    return y


def draw_base(draw: ImageDraw.ImageDraw, spec: VideoSpec) -> None:
    draw.rounded_rectangle((52, 52, 1028, 1868), radius=34, fill=CARD, outline=LINE, width=3)
    draw.rectangle((52, 52, 1028, 232), fill=GREEN)
    draw.text((92, 92), "A股指数观察", fill="#eef6f2", font=F_BADGE)
    draw.rounded_rectangle((746, 86, 988, 148), radius=31, fill="#f2f7f4")
    draw.text((798, 101), f"{spec.episode}/5", fill=GREEN, font=F_BADGE)
    draw_text(draw, spec.title, (92, 288), 860, F_TITLE, INK, 16, 3)
    draw_text(draw, spec.subtitle, (92, 514), 850, F_BODY, MUTED, 12, 2)
    draw.line((92, 652, 988, 652), fill=LINE, width=3)


def draw_footer(draw: ImageDraw.ImageDraw) -> None:
    draw.line((92, 1696, 988, 1696), fill=LINE, width=2)
    draw_text(draw, DISCLAIMER, (92, 1722), 880, F_SMALL, MUTED, 6, 2)
    draw_text(draw, CTA, (92, 1782), 880, F_SMALL, MUTED, 6, 1)
    draw_text(draw, DATA_NOTE, (92, 1822), 880, F_SMALL, MUTED, 6, 2)


def draw_scene_header(draw: ImageDraw.ImageDraw, scene: Scene) -> None:
    draw.rounded_rectangle((92, 740, 988, 936), radius=30, fill=SOFT)
    draw.text((130, 784), scene.heading, fill=GREEN, font=F_H2)
    draw_text(draw, scene.summary, (130, 852), 800, F_BODY, INK, 10, 2)


def draw_bullet_cards(draw: ImageDraw.ImageDraw, items: list[str], y: int) -> None:
    for idx, item in enumerate(items[:5], start=1):
        if y > 1518:
            break
        lines = wrap_by_width(draw, item, F_BODY, 720)[:3]
        box_h = max(118, len(lines) * (F_BODY.size + 10) + 52)
        draw.rounded_rectangle((92, y, 988, y + box_h), radius=22, fill=SOFT)
        draw.ellipse((126, y + 32, 178, y + 84), fill=ACCENT)
        draw.text((143, y + 39), str(idx), fill="#ffffff", font=F_BADGE)
        line_y = y + 28
        for line in lines:
            draw.text((205, line_y), line, fill=INK, font=F_BODY)
            line_y += F_BODY.size + 10
        y += box_h + 24


def draw_metric_grid(draw: ImageDraw.ImageDraw, items: list[tuple[str, str]], y: int) -> None:
    for idx, (label, value) in enumerate(items[:6]):
        x = 92 if idx % 2 == 0 else 550
        top = y + (idx // 2) * 176
        draw.rounded_rectangle((x, top, x + 438, top + 136), radius=22, fill=SOFT)
        draw.text((x + 30, top + 24), label, fill=ACCENT, font=F_SMALL)
        draw_text(draw, value, (x + 30, top + 66), 372, F_BODY, INK, 8, 2)


def draw_bar_chart(draw: ImageDraw.ImageDraw, items: list[str], y: int) -> None:
    parsed: list[tuple[str, float, str]] = []
    for item in items[:5]:
        match = re.match(r"(.+?)\s+(-?\d+\.\d+)%", item)
        if match:
            parsed.append((match.group(1), float(match.group(2)), match.group(2) + "%"))
    max_value = max([value for _, value, _ in parsed] or [1])
    for idx, (name, value, label) in enumerate(parsed):
        top = y + idx * 106
        draw.text((92, top), name, fill=INK, font=F_BODY)
        draw.rounded_rectangle((300, top + 10, 880, top + 48), radius=19, fill="#eef3f0")
        width = int(580 * value / max_value)
        draw.rounded_rectangle((300, top + 10, 300 + width, top + 48), radius=19, fill=ACCENT)
        draw.text((900, top), label, fill=GREEN, font=F_SMALL)


def draw_table(draw: ImageDraw.ImageDraw, rows: list[tuple[str, str, str]], y: int) -> None:
    draw.rounded_rectangle((92, y, 988, y + 560), radius=24, fill=SOFT)
    draw.text((122, y + 28), "名称", fill=ACCENT, font=F_SMALL)
    draw.text((505, y + 28), "行业", fill=ACCENT, font=F_SMALL)
    draw.text((785, y + 28), "权重", fill=ACCENT, font=F_SMALL)
    draw.line((122, y + 78, 958, y + 78), fill=LINE, width=2)
    row_y = y + 102
    for name, industry, weight in rows[:8]:
        draw.text((122, row_y), name[:10], fill=INK, font=F_SMALL)
        draw.text((505, row_y), industry[:8], fill=INK, font=F_SMALL)
        draw.text((785, row_y), weight, fill=INK, font=F_SMALL)
        row_y += 54


def draw_role_map(draw: ImageDraw.ImageDraw, items: list[tuple[str, str]], y: int) -> None:
    centers = [(250, y + 150), (540, y + 150), (830, y + 150)]
    for idx, ((label, desc), (cx, cy)) in enumerate(zip(items[:3], centers), start=1):
        draw.ellipse((cx - 82, cy - 82, cx + 82, cy + 82), fill=ACCENT if idx == 1 else "#eef3f0", outline=ACCENT, width=4)
        draw.text((cx - 20, cy - 32), str(idx), fill="#ffffff" if idx == 1 else ACCENT, font=F_NUM)
        draw.text((cx - 68, cy + 112), label, fill=INK, font=F_SMALL)
        draw_text(draw, desc, (cx - 105, cy + 154), 210, F_SMALL, MUTED, 6, 2)


def draw_return_cards(draw: ImageDraw.ImageDraw, data: Csi300Data, y: int) -> None:
    pairs = [
        ("1年", data.returns.get("1年", source("未解析", data.source_date, "收益率/1年")).value),
        ("3年年化", data.returns.get("3年年化", source("未解析", data.source_date, "收益率/3年年化")).value),
        ("5年年化", data.returns.get("5年年化", source("未解析", data.source_date, "收益率/5年年化")).value),
        ("1年波动率", data.volatility["1年年化"].value),
        ("3年波动率", data.volatility["3年年化"].value),
        ("5年波动率", data.volatility["5年年化"].value),
    ]
    draw_metric_grid(draw, pairs, y)


def draw_history_chart(draw: ImageDraw.ImageDraw, data: Csi300Data, y: int) -> None:
    points = data.history.get("points", [])
    if len(points) < 2:
        draw_unavailable(draw, ["公开历史行情下载失败", "不展示未核验走势和回撤"], y)
        return
    chart = (92, y, 988, y + 520)
    draw.rounded_rectangle(chart, radius=24, fill=SOFT)
    left, top, right, bottom = 142, y + 70, 938, y + 380
    closes = [float(p["close"]) for p in points]
    min_close, max_close = min(closes), max(closes)
    span = max(1.0, max_close - min_close)
    coords = []
    for idx, close in enumerate(closes):
        x = left + idx * (right - left) / max(1, len(closes) - 1)
        y_pos = bottom - (close - min_close) * (bottom - top) / span
        coords.append((x, y_pos))
    draw.line((left, bottom, right, bottom), fill=LINE, width=2)
    draw.line((left, top, left, bottom), fill=LINE, width=2)
    if len(coords) >= 2:
        draw.line(coords, fill=ACCENT, width=4)
    draw.text((142, y + 24), "发布以来至目前的历史走势", fill=GREEN, font=F_SMALL)
    draw.text((142, y + 410), f"最大回撤：{data.history['max_drawdown']}", fill=RED, font=F_BODY)
    draw.text((142, y + 456), "区间：历史最大回撤阶段", fill=MUTED, font=F_SMALL)
    draw.text((612, y + 410), f"最新点位：{data.history['latest_close']}", fill=INK, font=F_BODY)
    draw.text((612, y + 456), "回撤由公开日线点位计算", fill=MUTED, font=F_SMALL)


def draw_annual_returns(draw: ImageDraw.ImageDraw, data: Csi300Data, y: int) -> None:
    items = list(data.history.get("annual_returns", {}).items())[-6:]
    draw.rounded_rectangle((92, y, 988, y + 420), radius=24, fill=SOFT)
    draw.text((130, y + 30), "近几年年度收益", fill=GREEN, font=F_H2)
    if not items:
        draw_text(draw, "未取得可核验年度收益。", (130, y + 110), 760, F_BODY, INK)
        return
    max_abs = max(abs(float(v.strip("%"))) for _, v in items) or 1
    row_y = y + 112
    for year, value in items:
        num = float(value.strip("%"))
        draw.text((130, row_y), year, fill=INK, font=F_SMALL)
        zero_x = 500
        draw.line((zero_x, row_y + 10, zero_x, row_y + 42), fill=LINE, width=2)
        bar_w = int(320 * abs(num) / max_abs)
        if num >= 0:
            draw.rounded_rectangle((zero_x, row_y + 12, zero_x + bar_w, row_y + 40), radius=14, fill=ACCENT)
        else:
            draw.rounded_rectangle((zero_x - bar_w, row_y + 12, zero_x, row_y + 40), radius=14, fill=RED)
        draw.text((820, row_y), value, fill=ACCENT if num >= 0 else RED, font=F_SMALL)
        row_y += 48


def draw_valuation_logic(draw: ImageDraw.ImageDraw, items: list[tuple[str, str]], y: int) -> None:
    draw.rounded_rectangle((92, y, 988, y + 540), radius=26, fill=SOFT)
    draw.text((130, y + 36), "不同指数，估值看法不一样", fill=GREEN, font=F_H2)
    row_y = y + 120
    for label, value in items[:4]:
        draw.rounded_rectangle((130, row_y, 950, row_y + 82), radius=18, fill="#ffffff")
        draw.text((160, row_y + 21), label, fill=ACCENT, font=F_SMALL)
        draw_text(draw, value, (380, row_y + 20), 520, F_SMALL, INK, 6, 2)
        row_y += 100


def draw_unavailable(draw: ImageDraw.ImageDraw, lines: list[str], y: int) -> None:
    draw.rounded_rectangle((92, y, 988, y + 380), radius=26, fill="#fff8ec", outline="#ead7b7", width=2)
    draw.text((132, y + 44), "不展示未核验数字", fill=AMBER, font=F_H2)
    draw_bullet_cards(draw, lines, y + 130)


def make_slide(path: Path, spec: VideoSpec, scene_idx: int, data: Csi300Data) -> None:
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)
    draw_base(draw, spec)
    scene = spec.scenes[scene_idx]
    draw_scene_header(draw, scene)
    if scene.kind == "bullets":
        draw_bullet_cards(draw, scene.items, 1010)
    elif scene.kind == "metrics":
        draw_metric_grid(draw, scene.items, 1010)
    elif scene.kind == "bars":
        draw_bar_chart(draw, scene.items, 1010)
    elif scene.kind == "table":
        draw_table(draw, scene.items, 990)
    elif scene.kind == "role":
        draw_role_map(draw, scene.items, 1030)
    elif scene.kind == "returns":
        draw_return_cards(draw, data, 1004)
    elif scene.kind == "history_chart":
        draw_history_chart(draw, data, 986)
    elif scene.kind == "annual_returns":
        draw_annual_returns(draw, data, 1010)
    elif scene.kind == "valuation_logic":
        draw_valuation_logic(draw, scene.items, 1000)
    elif scene.kind == "unavailable":
        draw_unavailable(draw, scene.items, 1000)
    draw_footer(draw)
    img.save(path)


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[。！？；])", re.sub(r"\s+", " ", text)) if part.strip()]


async def make_voice_and_cues(text: str, output: Path) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            communicate = edge_tts.Communicate(text=text, voice=VOICE, rate=RATE, volume=VOLUME, boundary="SentenceBoundary")
            cues: list[dict[str, Any]] = []
            with output.open("wb") as audio:
                async for msg in communicate.stream():
                    if msg["type"] == "audio":
                        audio.write(msg["data"])
                    elif msg["type"] == "SentenceBoundary":
                        cues.append(
                            {
                                "start": msg["offset"] / 10_000_000,
                                "end": (msg["offset"] + msg["duration"]) / 10_000_000,
                                "text": msg["text"],
                            }
                        )
            if output.exists() and output.stat().st_size > 0:
                return cues
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(attempt * 2)
    raise RuntimeError(f"TTS 生成失败：{last_error}") from last_error


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
        capture_output=True,
    )
    return max(1.0, float(result.stdout.strip()))


def ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def fallback_cues(text: str, total_duration: float) -> list[dict[str, Any]]:
    sentences = split_sentences(text)
    slot = total_duration / max(1, len(sentences))
    return [{"start": i * slot, "end": min(total_duration, (i + 1) * slot), "text": sentence} for i, sentence in enumerate(sentences)]


def make_ass(path: Path, cues: list[dict[str, Any]], total_duration: float) -> None:
    sorted_cues = sorted(cues, key=lambda item: float(item["start"]))
    normalized: list[dict[str, Any]] = []
    for idx, cue in enumerate(sorted_cues):
        start = max(0.0, float(cue["start"]))
        raw_end = min(total_duration, max(start + 0.35, float(cue["end"])))
        if idx + 1 < len(sorted_cues):
            next_start = max(0.0, float(sorted_cues[idx + 1]["start"]))
            raw_end = min(raw_end, max(start + 0.35, next_start - 0.04))
        normalized.append({"start": start, "end": raw_end, "text": cue["text"]})

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans SC,50,&H00201811,&H000000FF,&H00F7F8FC,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,72,72,410,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = [header]
    for cue in normalized:
        start = max(0.0, float(cue["start"]))
        end = min(total_duration, max(start + 0.35, float(cue["end"])))
        wrapped = wrap_by_width(draw, str(cue["text"]), F_SUBTITLE, 900)
        cleaned: list[str] = []
        for line in wrapped:
            if cleaned and re.fullmatch(r"[\d.%％。，、！？；：,.!?;:\-]+", line) and len(line) <= 6:
                cleaned[-1] += line
            else:
                cleaned.append(line)
        wrapped = cleaned
        pages = ["\\N".join(wrapped[i : i + 2]) for i in range(0, len(wrapped), 2)]
        pages = [page for page in pages if page.strip()]
        if not pages:
            continue
        span = max(0.45, end - start)
        weights = [max(1, len(page.replace("\\N", ""))) for page in pages]
        total_weight = sum(weights)
        cursor = start
        for idx, page in enumerate(pages):
            page_end = end if idx == len(pages) - 1 else min(end, cursor + span * weights[idx] / total_weight)
            if page_end - cursor >= 0.28:
                lines.append(f"Dialogue: 0,{ass_time(cursor)},{ass_time(page_end)},Default,,0,0,0,,{page}")
            cursor = page_end
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def run(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def safe_name(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]+", "_", value)
    value = re.sub(r"\s+", "_", value.strip())
    return value[:120]


def value_manifest(data: Csi300Data) -> dict[str, Any]:
    return asdict(data)


def csi300_source_items(data: Csi300Data) -> list[dict[str, Any]]:
    history_csv = data.history.get("csv")
    sources_dir = Path(history_csv).parent if history_csv else ROOT / "runs"
    return [
        normalize_source_item(
            source_id="csi_index_page",
            source_type="official_index_page",
            title="中证指数沪深300页面",
            url=INDEX_PAGE_URL,
            data_date=data.source_date,
            fields=["index_name", "index_code"],
        ),
        normalize_source_item(
            source_id="csi_factsheet",
            source_type="official_factsheet",
            title="沪深300指数单张",
            url=FACTSHEET_URL,
            file=str(sources_dir / "000300factsheet.pdf"),
            data_date=data.source_date,
            fields=["basic_info", "sector_weights", "top_holdings", "returns", "volatility", "valuation"],
        ),
        normalize_source_item(
            source_id="csi_methodology",
            source_type="official_methodology",
            title="沪深300指数编制方案",
            url=METHODOLOGY_URL,
            file=str(sources_dir / "000300_Index_Methodology_cn.pdf"),
            data_date=data.source_date,
            fields=["methodology", "rebalance_frequency"],
        ),
        normalize_source_item(
            source_id="history_price_series",
            source_type="public_price_series",
            title="沪深300公开日线点位",
            file=history_csv,
            data_date=data.history.get("latest_date", data.source_date),
            fields=["date", "close"],
            calculation_method="用于计算历史走势、年度收益、最新点位、最大回撤和恢复情况。",
        ),
        normalize_source_item(
            source_id="valuation_pe_pb_series",
            source_type="public_valuation_series",
            title="沪深300 PE/PB 历史序列",
            file=str(sources_dir / "hs300_pe_history_legulegu.csv"),
            data_date=data.history.get("latest_date", data.source_date),
            fields=["pe", "pb"],
            calculation_method="用于计算 PE/PB 历史区间和分位。",
        ),
        normalize_source_item(
            source_id="official_indicator_xls",
            source_type="official_factsheet",
            title="中证指数指标表",
            url=data.valuation.get("sources", {}).get("dividend"),
            file=str(sources_dir / "000300indicator.xls"),
            data_date=data.source_date,
            fields=["dividend_yield"],
            calculation_method="用于计算股息率近期区间。",
        ),
    ]


def scene_visual_text(spec: VideoSpec) -> list[str]:
    text: list[str] = [spec.title, spec.subtitle]
    for scene in spec.scenes:
        text.extend([scene.heading, scene.summary])
        for item in scene.items:
            if isinstance(item, tuple):
                text.extend(str(part) for part in item)
            else:
                text.append(str(item))
    return text


def episode_features(spec: VideoSpec) -> dict[str, bool]:
    return {
        "sector_weights": spec.slug == "02_holdings_breakdown",
        "top_holdings": spec.slug == "02_holdings_breakdown",
        "valuation_metrics": spec.slug == "05_valuation_view",
        "max_drawdown": spec.slug == "04_return_drawdown_risk",
        "historical_returns": spec.slug == "04_return_drawdown_risk",
    }


def build_episode_data_used(spec: VideoSpec, data: Csi300Data) -> dict[str, Any]:
    source_items = csi300_source_items(data)
    builder = DataUsedBuilder(
        index_id="csi300",
        episode=spec.episode,
        episode_slug=spec.slug,
        source_items=source_items,
        data_date=data.source_date,
    )
    if spec.slug == "01_index_intro":
        builder.add_number(
            label="样本股数",
            value=data.sample_count.value,
            category="basic_metric",
            source_field=data.sample_count.field,
            source_id="csi_factsheet",
            calculation_method="官方单张字段原值。",
            display_context="官方基础信息",
        )
        builder.add_number(
            label="基值",
            value=data.base_value.value,
            category="basic_metric",
            source_field=data.base_value.field,
            source_id="csi_factsheet",
            calculation_method="官方单张字段原值。",
            display_context="基点设置",
        )
    elif spec.slug == "02_holdings_breakdown":
        for item in data.industry_top[:5]:
            builder.add_number(
                label=item.field,
                value=item.value,
                category="sector_weight",
                source_field=item.field,
                source_id="csi_factsheet",
                calculation_method="官方单张行业权重原值；本集展示 TOP5，合计不要求等于 100%。",
                display_context="行业权重TOP5",
            )
        for row in data.top_holdings[:10]:
            builder.add_number(
                label=row["名称"].value,
                value=row["权重"].value,
                category="holding_weight",
                source_field=row["权重"].field,
                source_id="csi_factsheet",
                calculation_method="官方单张前十大权重原值。",
                display_context="前十大权重股",
            )
    elif spec.slug == "04_return_drawdown_risk":
        sample_range = f"{data.history.get('start_date')} 至 {data.history.get('latest_date')}"
        for year, value in list(data.history.get("annual_returns", {}).items())[-6:]:
            builder.add_number(
                label=f"{year}年度收益",
                value=value,
                category="historical_return",
                source_field="公开日线点位/年度收盘价收益",
                source_id="history_price_series",
                calculation_method="按年度最后一个交易日收盘点位计算年度收益。",
                display_context="近几年年度收益",
                sample_range=sample_range,
                calculation_range=f"{year} 年度",
            )
        builder.add_number(
            label="最大回撤",
            value=data.history["max_drawdown"],
            category="max_drawdown",
            source_field="公开日线点位/最大回撤",
            source_id="history_price_series",
            calculation_method="用发布以来的收盘点位序列计算累计净值回撤。",
            display_context="回撤和波动",
            sample_range=sample_range,
            calculation_range=f"{data.history.get('start_date')} 至 {data.history.get('latest_date')}",
        )
        builder.add_number(
            label="最新点位",
            value=data.history["latest_close"],
            category="historical_level",
            source_field="公开日线点位/最新收盘点位",
            source_id="history_price_series",
            calculation_method="公开日线点位最新收盘值。",
            display_context="多年历史走势",
            sample_range=sample_range,
        )
        builder.add_number(
            label="1年波动率",
            value=data.volatility["1年年化"].value,
            category="volatility",
            source_field=data.volatility["1年年化"].field,
            source_id="csi_factsheet",
            calculation_method="官方单张字段原值。",
            display_context="回撤和波动",
            sample_range="官方单张口径",
        )
    elif spec.slug == "05_valuation_view":
        builder.add_number(
            label="PE当前值",
            value=data.valuation["pe"]["current"],
            category="pe",
            source_field="PE/current",
            source_id="valuation_pe_pb_series",
            calculation_method="公开 PE 历史序列最新值。",
            display_context="当前值要配区间",
        )
        builder.add_number(
            label="PE历史区间",
            value=data.valuation["pe"]["history_range"],
            category="valuation_range",
            source_field="PE/history_range",
            source_id="valuation_pe_pb_series",
            calculation_method="公开 PE 历史序列最小值到最大值。",
            display_context="当前值要配区间",
        )
        builder.add_number(
            label="PE分位",
            value=data.valuation["pe"]["percentile"],
            category="valuation_percentile",
            source_field="PE/percentile",
            source_id="valuation_pe_pb_series",
            calculation_method="公开 PE 历史序列中小于等于当前值的样本占比。",
            display_context="当前值要配区间",
        )
        builder.add_number(
            label="PB当前值",
            value=data.valuation["pb"]["current"],
            category="pb",
            source_field="PB/current",
            source_id="valuation_pe_pb_series",
            calculation_method="公开 PB 历史序列最新值。",
            display_context="当前值要配区间",
        )
        builder.add_number(
            label="PB历史区间",
            value=data.valuation["pb"]["history_range"],
            category="valuation_range",
            source_field="PB/history_range",
            source_id="valuation_pe_pb_series",
            calculation_method="公开 PB 历史序列最小值到最大值。",
            display_context="当前值要配区间",
        )
        builder.add_number(
            label="PB分位",
            value=data.valuation["pb"]["percentile"],
            category="valuation_percentile",
            source_field="PB/percentile",
            source_id="valuation_pe_pb_series",
            calculation_method="公开 PB 历史序列中小于等于当前值的样本占比。",
            display_context="当前值要配区间",
        )
        builder.add_number(
            label="股息率当前值",
            value=data.valuation["dividend_yield"]["current"],
            category="dividend_yield",
            source_field="dividend_yield/current",
            source_id="official_indicator_xls",
            calculation_method="官方指标表股息率字段最新值。",
            display_context="当前值要配区间",
        )
        builder.add_number(
            label="股息率近期区间",
            value=data.valuation["dividend_yield"]["recent_range"],
            category="valuation_range",
            source_field="dividend_yield/recent_range",
            source_id="official_indicator_xls",
            calculation_method="官方指标表股息率字段样本的最小值到最大值。",
            display_context="当前值要配区间",
        )
    return builder.build()


def episode_metadata(spec: VideoSpec, data: Csi300Data, source_items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "index_id": "csi300",
        "index_name": "沪深300",
        "index_code": data.index_code.value,
        "region": "中国内地",
        "index_type": "broad_based",
        "template_type": "broad_based",
        "style_theme": "china",
        "data_date": data.source_date,
        "source_items": source_items,
        "script_version": SCRIPT_VERSION,
        "render_version": RENDER_VERSION,
        "episode": spec.episode,
        "episode_slug": spec.slug,
    }


def quality_check_result(final: Path, total_duration: float) -> dict[str, Any]:
    return {
        "passed": final.exists() and final.stat().st_size > 0 and 45 <= total_duration <= 100,
        "duration_seconds": round(total_duration, 3),
        "resolution": f"{SIZE[0]}x{SIZE[1]}",
        "audio_expected": True,
        "subtitle_mode": "per_scene_ass",
    }


def render_video(spec: VideoSpec, data: Csi300Data, output_root: Path) -> Path:
    run_dir = output_root / safe_name(f"{spec.episode:02d}_{spec.slug}")
    run_dir.mkdir(parents=True, exist_ok=True)
    data_used = build_episode_data_used(spec, data)
    full_script_parts = [scene.narration.strip() for scene in spec.scenes]
    if full_script_parts and CTA not in full_script_parts[-1]:
        full_script_parts[-1] = full_script_parts[-1] + CTA
    full_script = "".join(full_script_parts)
    metadata = episode_metadata(spec, data, data_used["source_items"])
    payload = {
        "metadata": metadata,
        "data_used": data_used,
        "features": episode_features(spec),
        "visual_text": scene_visual_text(spec),
    }
    data_validation_result = validate_episode_payload(payload)
    compliance_check_result = check_text_compliance(script=full_script, visual_text=payload["visual_text"])
    (run_dir / "data_used.json").write_text(json.dumps(data_used, ensure_ascii=False, indent=2), encoding="utf-8")
    if not data_validation_result.passed or not compliance_check_result.passed:
        failed_manifest = {
            **metadata,
            "title": spec.title,
            "render_status": "blocked_needs_review",
            "data_validation_result": data_validation_result.to_dict(),
            "compliance_check_result": compliance_check_result.to_dict(),
        }
        (run_dir / "manifest.json").write_text(json.dumps(failed_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    assert_valid(data_validation_result)
    if not compliance_check_result.passed:
        raise ValueError("合规检查未通过：" + "; ".join(compliance_check_result.errors))
    segments = []
    total_duration = 0.0
    for idx, scene in enumerate(spec.scenes):
        slide = run_dir / f"scene_{idx + 1:02d}.png"
        make_slide(slide, spec, idx, data)
        narration = scene.narration.strip()
        if idx == len(spec.scenes) - 1 and CTA not in narration:
            narration += CTA
        voice = run_dir / f"voice_{idx + 1:02d}.mp3"
        cues = asyncio.run(make_voice_and_cues(narration, voice))
        voice_duration = duration(voice)
        if not cues:
            cues = fallback_cues(narration, voice_duration)
        ass = run_dir / f"subtitles_{idx + 1:02d}.ass"
        make_ass(ass, cues, voice_duration)
        segment = run_dir / f"segment_{idx + 1:02d}.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-framerate",
                "30",
                "-i",
                slide.name,
                "-i",
                voice.name,
                "-t",
                f"{voice_duration + 0.35:.3f}",
                "-vf",
                f"drawbox=x=0:y=1376:w=1080:h=154:color=0xF7F8FC@0.94:t=fill,drawbox=x=0:y=1376:w=1080:h=154:color=0xD8E2EC@0.72:t=2,ass={ass.name},format=yuv420p",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-shortest",
                segment.name,
            ],
            run_dir,
        )
        segments.append(segment)
        total_duration += voice_duration

    (run_dir / "segments.txt").write_text("\n".join([f"file '{segment.name}'" for segment in segments]), encoding="utf-8")
    final = run_dir / "final.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "segments.txt",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            final.name,
        ],
        run_dir,
    )
    combined_cues: list[dict[str, Any]] = []
    offset = 0.0
    for idx, segment in enumerate(segments):
        seg_duration = duration(segment)
        ass_path = run_dir / f"subtitles_{idx + 1:02d}.ass"
        for line in ass_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("Dialogue:"):
                parts = line.split(",", 9)
                if len(parts) >= 10:
                    combined_cues.append({"segment": idx + 1, "text": parts[9]})
        offset += seg_duration
    (run_dir / "subtitles_manifest.json").write_text(json.dumps(combined_cues, ensure_ascii=False, indent=2), encoding="utf-8")
    quality_result = quality_check_result(final, total_duration)
    manifest = {
        **metadata,
        "slug": spec.slug,
        "episode": spec.episode,
        "title": spec.title,
        "script": full_script,
        "duration": total_duration,
        "voice": VOICE,
        "rate": RATE,
        "scene_audio_aligned": True,
        "sources": {
            "index_page": INDEX_PAGE_URL,
            "factsheet": FACTSHEET_URL,
            "methodology": METHODOLOGY_URL,
            "history": data.history.get("source"),
        },
        "data_source_date": data.source_date,
        "data": value_manifest(data),
        "source_items": data_used["source_items"],
        "script_version": SCRIPT_VERSION,
        "render_version": RENDER_VERSION,
        "compliance_check_result": compliance_check_result.to_dict(),
        "data_validation_result": data_validation_result.to_dict(),
        "quality_check_result": quality_result,
        "max_drawdown_status": f"已展示：根据公开日线点位自行计算，最大回撤 {data.history.get('max_drawdown')}。" if spec.slug == "04_return_drawdown_risk" else None,
        "final": str(final),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return final


def build_specs(data: Csi300Data) -> list[VideoSpec]:
    holding_rows = [(row["名称"].value, row["行业"].value, row["权重"].value) for row in data.top_holdings]
    return [
        VideoSpec(
            slug="01_index_intro",
            episode=1,
            title="沪深300，跟踪的到底是什么？",
            subtitle="先分清它代表谁，也分清它不代表谁。",
            script="",
            scenes=[
                Scene("bullets", "一句话定位", "沪深300看的是沪深两市头部公司的整体表现。", ["不是全市场指数", "不是小盘风格指数", "不是单一行业指数"], "第一条只回答一个问题：沪深300到底代表谁。它不是把A股所有股票都买一遍，而是从上海和深圳市场里选出规模大、流动性好的三百只代表性证券。"),
                Scene("metrics", "官方基础信息", "目前公开资料", [("指数全称", data.full_name.value), ("指数代码", data.index_code.value), ("样本股数", data.sample_count.value), ("调样频率", data.rebalance_frequency.value), ("发布状态", "已发布运行"), ("基点设置", f"基值 {data.base_value.value}")], f"中证指数单张显示，目前沪深300样本股数是{data.sample_count.value}，调样频率是{data.rebalance_frequency.value}。这些信息决定了它不是固定三百家公司，而是一套持续更新的选样规则。"),
                Scene("bullets", "它不负责什么", "宽基不等于万能，也不等于整个A股。", ["不代表中小盘", "不代表红利或成长风格", "不替代行业指数"], "理解沪深300时，关键是边界。它偏大盘，不能代表中证500、中证1000，也不能代表红利、成长、消费、医药这些具体风格。也就是说，它适合回答大盘核心公司怎么样，不适合回答小盘风格强不强、某个行业有没有机会。"),
                Scene("bullets", "这一条的结论", "先看覆盖范围，再看权重结构。", ["它是A股大盘参照物", "后续重点看行业和前十大", "不要只凭名字判断"], "这条视频的结论是：沪深300更像A股大盘核心公司的参照物。先确认它代表谁，再看权重结构，最后才谈估值和组合角色。下一步，不能停在名字上，要看它具体装了哪些行业和公司。仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。"),
            ],
        ),
        VideoSpec(
            slug="02_holdings_breakdown",
            episode=2,
            title="沪深300里面，主要买到了什么？",
            subtitle="权重结构决定了它更受哪些公司影响。",
            script="",
            scenes=[
                Scene("bars", "行业权重TOP5", "来源：中证指数单张，目前公开资料", [item.value for item in data.industry_top], f"第二条看成分。目前中证指数单张里，沪深300行业权重靠前的是三类。{data.industry_top[0].value}。{data.industry_top[1].value}。{data.industry_top[2].value}。行业权重越靠前，对指数阶段表现影响越明显。"),
                Scene("table", "前十大权重股", "权重越高，对指数影响越明显。", holding_rows, f"再看前十大权重股。第一位是{data.top_holdings[0]['名称'].value}，权重{data.top_holdings[0]['权重'].value}；后面还有{data.top_holdings[1]['名称'].value}、{data.top_holdings[2]['名称'].value}、{data.top_holdings[3]['名称'].value}。这些公司不是全部答案，但它们决定了指数的短期敏感点。"),
                Scene("bullets", "三张表就够用", "不要把宽基理解成平均分散。", ["行业分布", "前十大权重", "前十大合计占比"], "看沪深300，不需要背三百家公司。真正要盯的是三张表：行业分布、前十大权重、前十大合计占比。它们能告诉你，指数到底偏金融、偏消费，还是偏科技制造。"),
                Scene("bullets", "这一条的结论", "买的是一套加权组合，不是一个名字。", ["权重越高影响越大", "行业变化会改变风格", "发布前复核最新单张"], "这条视频的结论是：沪深300不是平均买三百家公司，而是一套加权组合。权重结构变了，指数气质也会变。发布前最好再看一眼目前的官方单张，确认行业和前十大有没有明显变化。仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。"),
            ],
        ),
        VideoSpec(
            slug="03_portfolio_role",
            episode=3,
            title="沪深300在经典组合里是什么角色？",
            subtitle="它负责权益弹性，不负责单独控制回撤。",
            script="",
            scenes=[
                Scene("role", "经典组合里的位置", "股票部分提供增长弹性，债券和现金负责缓冲。", [("权益发动机", "承担A股大盘风险收益"), ("搭配对象", "债券、现金、海外资产"), ("不承担", "单独控制回撤")], "第三条换成组合视角。在一个经典投资组合里，沪深300更像权益发动机，负责A股大盘的增长弹性。真正控制回撤的，通常不是沪深300自己，而是债券、现金、海外资产和再平衡。"),
                Scene("bullets", "它适合承担什么", "提供A股头部公司的权益暴露。", ["A股大盘核心仓位", "权益部分的基准参照", "和其他资产做分工"], "沪深300适合承担的是A股大盘核心仓位。它可以作为权益部分的基准参照，帮助你知道自己的A股部分是跑赢还是跑输大盘。如果组合里已经有很多行业主题，沪深300还能提供一个更分散的大盘锚点。"),
                Scene("bullets", "它不适合承担什么", "不要让一个宽基完成所有任务。", ["不负责低回撤", "不代表小盘和行业主题", "不替代债券和现金"], "它不适合承担的事情也要说清楚：沪深300不负责低回撤，不代表小盘和行业主题，也不能替代债券和现金。把它当回撤缓冲器，定位就错了。"),
                Scene("bullets", "这一条的结论", "先定角色，再谈比例。", ["沪深300负责权益弹性", "回撤控制靠资产搭配", "不要把宽基当全部组合"], "这条视频的结论是：沪深300负责权益弹性，回撤控制靠资产搭配。一个更稳的组合，通常不是把所有仓位都放在一个宽基里，而是让股票、债券、现金和海外资产各自承担任务。先定角色，再谈比例，比猜短期涨跌更有用。仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。"),
            ],
        ),
        VideoSpec(
            slug="04_return_drawdown_risk",
            episode=4,
            title="沪深300历史走势，要重点看什么？",
            subtitle="历史不是预测器，历史是持有体验说明书。",
            script="",
            scenes=[
                Scene("history_chart", "多年历史走势", "看长期曲线，也要看中间跌了多少。", [], "第四条看历史走势和回撤。我用发布以来至目前的公开日线点位计算。这条曲线不是预测器，它展示的是持有过程中会经历怎样的上升、下跌和修复。"),
                Scene("annual_returns", "年度收益差异很大", "连续几年放在一起看，波动会更真实。", [], "单看某一年很容易误判。把年度收益放在一起，能看到沪深300并不是每年都平稳。上涨年份和下跌年份交替出现，这才是权益资产的真实体验。做长期配置时，真正要评估的不是某一年表现，而是能不能穿过这些年份差异。"),
                Scene("metrics", "回撤和波动", "最大回撤由公开日线点位计算。", [("最大回撤", data.history["max_drawdown"]), ("回撤区间", "历史最大回撤阶段"), ("恢复情况", "见公开行情计算"), ("1年波动率", data.volatility["1年年化"].value)], f"这组数据里，最大回撤是{data.history['max_drawdown']}，发生在历史最大回撤阶段。这比一句有风险更具体：它告诉你，权益仓位可能让账户经历多深的浮亏。"),
                Scene("bullets", "这一条的结论", "风险不是口号，要落到回撤和恢复时间。", ["看多年曲线", "看最大回撤", "看恢复时间"], "这条视频的结论是：历史收益要和回撤一起看。只看收益，会低估持有难度；只看回撤，又容易忽略长期权益收益来源。下一次看到指数长期上涨曲线时，也要问一句：中间最大跌幅有多深，恢复用了多久。仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。"),
            ],
        ),
        VideoSpec(
            slug="05_valuation_view",
            episode=5,
            title="沪深300贵不贵，应该怎么看？",
            subtitle="沪深300是宽基，重点看PE、PB和股息率。",
            script="",
            scenes=[
                Scene("bullets", "先看三个官方指标", "沪深300是宽基，先看估值仪表盘。", ["滚动市盈率", "市净率", "股息率"], "最后一条只讲沪深300自己的估值。它是宽基指数，最常用的三个官方指标是滚动市盈率、市净率和股息率。先看这三个指标，再结合历史区间，别一上来就问贵不贵。"),
                Scene("bullets", "当前值要配区间", "只给一个点位不够，必须放回范围里看。", [f"PE：目前{data.valuation['pe']['current']}，历史区间{data.valuation['pe']['history_range']}，分位{data.valuation['pe']['percentile']}", f"PB：目前{data.valuation['pb']['current']}，历史区间{data.valuation['pb']['history_range']}，分位{data.valuation['pb']['percentile']}", f"股息率：目前{data.valuation['dividend_yield']['current']}，近期区间{data.valuation['dividend_yield']['recent_range']}"], f"沪深300估值不能只放一个当前值。PE目前是{data.valuation['pe']['current']}，历史区间是{data.valuation['pe']['history_range']}，大约处在{data.valuation['pe']['percentile']}分位。PB目前是{data.valuation['pb']['current']}，历史区间是{data.valuation['pb']['history_range']}，大约处在{data.valuation['pb']['percentile']}分位。股息率也要放进近期区间里看。"),
                Scene("bullets", "三个指标各看什么", "指标回答的问题不同，不能混成一个结论。", ["PE：价格和盈利", "PB：价格和净资产", "股息率：分红回报"], "PE看价格和盈利，PB看价格和净资产，股息率看现金分红回报。它们要一起看，因为单一指标很容易误导。比如PE下降，可能是价格跌了，也可能是盈利上来了；股息率变高，也可能是分红提高，或者价格下跌。"),
                Scene("bullets", "这一条的结论", "估值负责衡量性价比，不负责预测短期涨跌。", ["当前值必须配区间", "分位可以自己算", "指标必须标来源"], "这条视频的结论是：估值是仪表盘，不是交易按钮。沪深300看估值，标准是当前值加历史区间加分位；能自己算就自己算，范围也要给出来，不能把估值说成短期涨跌判断。仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。"),
            ],
        ),
    ]


def main() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("需要 ffmpeg 和 ffprobe。")
    output_root = ROOT / "runs" / f"csi300_series_{datetime.now():%Y%m%d_%H%M%S}"
    output_root.mkdir(parents=True, exist_ok=True)
    sources_dir = output_root / "_sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    factsheet_pdf, factsheet_text = download_pdf_text(FACTSHEET_URL)
    (sources_dir / "000300factsheet.pdf").write_bytes(factsheet_pdf)
    (sources_dir / "000300factsheet.txt").write_text(factsheet_text, encoding="utf-8")
    methodology_pdf, _ = download_pdf_text(METHODOLOGY_URL)
    (sources_dir / "000300_Index_Methodology_cn.pdf").write_bytes(methodology_pdf)

    data = parse_factsheet(factsheet_text)
    data.history = load_history_data(sources_dir)
    data.valuation = load_valuation_data(sources_dir, data)
    data.max_drawdown = source(
        data.history["max_drawdown"],
        data.history["latest_date"],
        "公开日线点位计算/最大回撤",
        data.history["source"],
    )
    outputs: list[str] = []
    for spec in build_specs(data):
        print(f"Rendering {spec.episode}/5: {spec.title}")
        outputs.append(str(render_video(spec, data, output_root)))
    series_manifest = {
        "title": "沪深300五条系列",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output_root": str(output_root),
        "sources": {
            "index_page": INDEX_PAGE_URL,
            "factsheet": FACTSHEET_URL,
            "methodology": METHODOLOGY_URL,
        },
        "data_source_date": data.source_date,
        "outputs": outputs,
    }
    (output_root / "series_manifest.json").write_text(json.dumps(series_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done: {output_root}")


if __name__ == "__main__":
    main()
