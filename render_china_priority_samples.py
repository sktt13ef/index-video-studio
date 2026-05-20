from __future__ import annotations

import asyncio
import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

import render_csi300_series as speech
from src.ai_script_writer import AIScriptError, AIScriptWriter


ROOT = Path(__file__).resolve().parent
PROFILE_DIR = ROOT / "data" / "global100" / "profiles"
RUNS_DIR = ROOT / "runs"
INDEX_IDS = ["csi300", "csi500", "csi1000", "csi_div"]
SIZE = (1080, 1920)
VOICE = "zh-CN-YunjianNeural"
RATE = "+3%"
DISCLAIMER = "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。"
CTA = "感谢观看，可以点点关注，继续了解更多指数观察。"
DATA_NOTE = "数据来源：中证指数官方单张、公开历史点位和估值序列；发布前以最新公开资料为准。"


THEMES = {
    "broad_based": {
        "series": "A股指数观察",
        "bg": "#f7f8fc",
        "ink": "#121820",
        "muted": "#667085",
        "line": "#d8e2ec",
        "soft": "#eef3fb",
        "accent": "#bd5b5d",
        "blue": "#315d8c",
    },
    "dividend": {
        "series": "红利指数观察",
        "bg": "#fbf7f5",
        "ink": "#151719",
        "muted": "#6b6360",
        "line": "#eadad5",
        "soft": "#f5ece8",
        "accent": "#b65b55",
        "blue": "#7d5139",
    },
}


@dataclass
class Scene:
    kind: str
    heading: str
    summary: str
    items: list[Any]
    narration: str


@dataclass
class Episode:
    number: int
    slug: str
    title: str
    subtitle: str
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


F_TITLE = font(60, True)
F_H1 = font(48, True)
F_H2 = font(40, True)
F_BODY = font(32)
F_SMALL = font(25)
F_FOOTER = font(23)
F_BADGE = font(28, True)
F_NUM = font(44, True)


def load_profile(index_id: str) -> dict[str, Any]:
    return json.loads((PROFILE_DIR / f"{index_id}.json").read_text(encoding="utf-8"))


def pct_float(value: str) -> float:
    return float(str(value).replace("%", "").replace(",", "").strip())


def valuation_map(profile: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in profile.get("valuation_metrics", {}).get("items", []):
        metric = item.get("metric") or item.get("category") or item.get("label")
        result[str(metric)] = str(item.get("value"))
    return result


def history_summary(profile: dict[str, Any]) -> dict[str, Any]:
    returns = profile.get("historical_returns", {}).get("items", [])
    drawdown = (profile.get("drawdown_stats", {}).get("items") or [{}])[0]
    recent = returns[-5:] if len(returns) >= 5 else returns
    return {
        "returns": recent,
        "drawdown": drawdown.get("max_drawdown", ""),
        "range": drawdown.get("calculation_range") or profile.get("historical_returns", {}).get("sample_range", ""),
    }


def sum_top_weight(profile: dict[str, Any]) -> str:
    values = [pct_float(item["weight"]) for item in profile.get("top_holdings", {}).get("items", [])[:10]]
    return f"{sum(values):.1f}%"


def sum_sector_weight(profile: dict[str, Any], count: int) -> str:
    values = [pct_float(item["weight"]) for item in profile.get("sector_weights", {}).get("items", [])[:count]]
    return f"{sum(values):.1f}%"


def sample_count_label(method: str, holdings: list[dict[str, Any]]) -> str:
    for token in ("1000只", "500只", "300只", "100只"):
        if token in method:
            return token
    return f"{len(holdings)}项权重已追溯"


def script_tail(text: str) -> str:
    product_closing = "最后做个小结：看指数时，不要只看名字或者单个数字，要把样本范围、权重结构、估值区间和历史回撤放在一起看。这样更容易判断它在组合里承担什么角色，也更容易理解它可能带来的波动。真正有用的指数观察，不是给出一个简单结论，而是把边界、结构和风险讲清楚。"
    if product_closing not in text:
        text += product_closing
    if DISCLAIMER not in text:
        text += DISCLAIMER
    if CTA not in text:
        text += CTA
    return text


def build_episodes(profile: dict[str, Any]) -> list[Episode]:
    basic = profile["basic_info"]
    name = basic["index_name_cn"]
    index_type = basic["index_type"]
    sample = profile["methodology_summary"].get("sample_scope", "")
    focus = "、".join(profile["methodology_summary"].get("selection_focus", [])[:3])
    rebalance = profile["methodology_summary"].get("rebalance_frequency", "")
    method = profile["methodology_summary"]["summary"]
    sectors = profile["sector_weights"]["items"]
    holdings = profile["top_holdings"]["items"]
    valuation = valuation_map(profile)
    history = history_summary(profile)
    risks = profile["risk_points"]["items"]
    role = profile["role_in_portfolio"]["summary"]
    top_sector = sectors[0]
    top_holding = holdings[0]
    top10_sum = sum_top_weight(profile)
    sample_count = sample_count_label(method, holdings)
    pe = valuation.get("pe", "")
    pe_range = valuation.get("pe_range", valuation.get("valuation_range", ""))
    pe_pct = valuation.get("pe_percentile", "")
    dy = valuation.get("dividend_yield", "")
    max_dd = history["drawdown"]
    recent_returns = "；".join(f"{item['period']}：{item['return']}" for item in history["returns"][-4:])

    if index_type == "dividend":
        role_angle = "它不是普通宽基，而是红利和价值风格的观察工具。"
        valuation_angle = f"这类指数要重点看股息率、PE区间和分红稳定性。目前股息率为{dy}，PE为{pe}，PE样本区间为{pe_range}。"
        intro_angle = "先看分红规则，再看行业集中度。"
    elif "1000" in name:
        role_angle = "它更像A股小盘风格的补充，不适合拿来替代大盘宽基。"
        valuation_angle = f"小盘宽基估值波动更敏感。目前PE为{pe}，PE样本区间为{pe_range}，分位为{pe_pct}。"
        intro_angle = "先看它和沪深300、中证500的边界。"
    else:
        role_angle = "它更像A股中盘风格的补充，适合和大盘宽基一起观察。"
        valuation_angle = f"中盘宽基可以先看PE、股息率和历史区间。目前PE为{pe}，PE样本区间为{pe_range}，分位为{pe_pct}。"
        intro_angle = "先看它为什么不是大盘，也不是小盘。"

    return [
        Episode(
            1,
            "01_index_intro",
            f"{name}，到底跟踪什么？",
            intro_angle,
            [
                Scene("cover", "本条只解决一个问题", intro_angle, [name, sample], f"第一条看{name}到底跟踪什么。{intro_angle}"),
                Scene("bullets", "指数边界", method, [sample, focus, f"调样频率：{rebalance}"], f"从指数规则看，{method}这句话的重点不是名字，而是样本范围、筛选条件和调样频率。"),
                Scene("metrics", "三个基础信息", "先把边界看清楚，再谈权重和估值。", [("样本范围", sample), ("筛选重点", focus), ("调样频率", rebalance), ("样本数量", sample_count)], f"理解{name}，先记住三点：样本范围是{sample}，筛选重点是{focus}，调样频率是{rebalance}。"),
                Scene("bullets", "这一条的结论", "它回答的是一类资产表现，不回答所有问题。", [f"{name}有清楚的样本边界", "下一步看行业和前十大", "不要只凭指数名称判断"], script_tail(f"这一条的结论是：{name}有明确边界。先确认它代表哪类公司，再看行业权重、前十大和估值位置。")),
            ],
        ),
        Episode(
            2,
            "02_holdings_breakdown",
            f"{name}里面，主要买到了什么？",
            "看行业和前十大，别只看指数名字。",
            [
                Scene("cover", "本条只解决一个问题", "这条看成分结构。", [name, "行业权重、前十大权重"], f"第二条看{name}里面装了什么。"),
                Scene("bars", "行业权重TOP5", "权重靠前的行业，更容易影响阶段表现。", sectors[:5], f"从官方单张看，{name}行业权重靠前的是{sectors[0]['name']}、{sectors[1]['name']}和{sectors[2]['name']}。其中{top_sector['name']}约占{top_sector['weight']}。"),
                Scene("table", "前十大权重", f"前十大合计约{top10_sum}。", holdings[:8], f"再看前十大权重。权重最高的是{top_holding['name']}，约占{top_holding['weight']}。前十大合计约{top10_sum}，说明它不是平均分配。"),
                Scene("bullets", "这一条的结论", "看成分，就是看风险来源。", [f"第一行业：{top_sector['name']} {top_sector['weight']}", f"第一权重股：{top_holding['name']} {top_holding['weight']}", "行业变化会改变指数气质"], script_tail(f"这一条的结论是：看{name}，不能只看名字。行业权重和前十大权重，才决定它更容易被哪些公司和行业影响。")),
            ],
        ),
        Episode(
            3,
            "03_portfolio_role",
            f"{name}在组合里是什么角色？",
            "先定分工，再谈比例。",
            [
                Scene("cover", "本条只解决一个问题", "这条只看组合角色。", [name, role], f"第三条看{name}在组合里的角色。"),
                Scene("role", "组合里的位置", role, [("承担", role), ("搭配", "大盘、海外、债券或现金"), ("不承担", "单独控制回撤")], f"{role_angle}{role}"),
                Scene("bullets", "适合和不适合", "一个指数只承担一个清楚任务。", ["适合作为风格暴露", "可和其他宽基分工", "不替代债券和现金"], f"{name}可以承担风格暴露，但不应该承担所有任务。它不能替代债券和现金，也不能保证组合回撤变小。"),
                Scene("bullets", "这一条的结论", "角色清楚，后面的仓位讨论才有意义。", [role, "回撤控制靠资产搭配", "不要让单个指数做全部工作"], script_tail(f"这一条的结论是：{name}的作用是提供一类权益风格观察，不是万能组合。先定角色，再讨论比例。")),
            ],
        ),
        Episode(
            4,
            "04_return_drawdown_risk",
            f"{name}历史走势，要重点看什么？",
            "历史不是预测器，是持有体验说明书。",
            [
                Scene("cover", "本条只解决一个问题", "这条看历史收益、走势和回撤。", [name, "历史走势与风险"], f"第四条看{name}的历史走势和回撤。"),
                Scene("history", "多年历史走势", "看长期曲线，也看中间跌了多少。", history["returns"], f"历史走势不是用来预测涨跌，而是用来看持有体验。把多年收益放在一起，能看到不同年份差异很大。"),
                Scene("metrics", "回撤和年度收益", "回撤是权益资产必须面对的部分。", [("最大回撤", max_dd), ("近期年度收益", recent_returns), ("主要风险", risks[0])], f"用公开历史点位计算，{name}历史样本中的最大回撤为{max_dd}。近几年年度收益也有明显差异：{recent_returns}。"),
                Scene("bullets", "这一条的结论", "风险要落到回撤、波动和恢复时间。", [risks[0], risks[1], "只看收益会低估持有难度"], script_tail(f"这一条的结论是：{name}不能只看收益，也要看最大回撤和年度差异。能接受波动，再谈长期持有。")),
            ],
        ),
        Episode(
            5,
            "05_valuation_view",
            f"{name}贵不贵，应该怎么看？",
            "不同指数，估值重点不一样。",
            [
                Scene("cover", "本条只解决一个问题", "这条看估值框架。", [name, "估值与区间"], f"第五条看{name}的估值。"),
                Scene("metrics", "当前估值指标", "当前值必须配合区间看。", [("PE", pe), ("PE区间", pe_range), ("PE分位", pe_pct), ("股息率", dy)], valuation_angle),
                Scene("bullets", "估值怎么看", "估值是仪表盘，不是交易按钮。", ["宽基看PE、股息率和区间", "红利看股息率和分红稳定性", "行业集中会影响估值解释"], f"估值不能只看一个数字。宽基更重视PE、股息率和历史区间；红利指数还要看分红稳定性和行业集中。"),
                Scene("bullets", "这一条的结论", "估值只帮助判断位置，不预测短期涨跌。", ["当前值要配区间", "分位可以自己复算", "数据来源必须能追溯"], script_tail(f"这一条的结论是：{name}估值要看当前值、区间和分位，不能把估值说成短期预测。")),
            ],
        ),
    ]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in str(text):
        trial = current + char
        width = draw.textbbox((0, 0), trial, font=text_font)[2]
        if current and width > max_width:
            lines.append(current)
            current = char
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], width: int, text_font: ImageFont.FreeTypeFont, fill: str, gap: int = 10, max_lines: int | None = None) -> int:
    x, y = xy
    lines = wrap_text(draw, text, text_font, width)
    if max_lines:
        lines = lines[:max_lines]
    for line in lines:
        draw.text((x, y), line, fill=fill, font=text_font)
        y += text_font.size + gap
    return y


def base_slide(theme: dict[str, str], episode: Episode) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", SIZE, theme["bg"])
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1080, 14), fill=theme["accent"])
    draw.rounded_rectangle((74, 52, 1006, 150), radius=18, fill="#ffffff", outline=theme["line"], width=3)
    draw.rectangle((104, 88, 182, 98), fill=theme["accent"])
    draw.text((210, 74), theme.get("series", "指数观察"), fill=theme["blue"], font=F_BADGE)
    draw.rounded_rectangle((800, 70, 966, 132), radius=30, fill=theme["soft"], outline=theme["line"], width=2)
    draw.text((852, 84), f"{episode.number}/5", fill=theme["blue"], font=F_BADGE)
    draw_wrapped(draw, episode.title, (74, 276), 900, F_TITLE, theme["ink"], 16, 3)
    draw_wrapped(draw, episode.subtitle, (74, 508), 890, F_BODY, theme["muted"], 12, 2)
    draw.line((74, 650, 1006, 650), fill=theme["line"], width=3)
    draw.line((74, 1562, 1006, 1562), fill=theme["line"], width=2)
    draw_wrapped(draw, DISCLAIMER, (74, 1588), 920, F_FOOTER, theme["muted"], 8, 2)
    draw_wrapped(draw, CTA, (74, 1644), 920, F_FOOTER, theme["blue"], 8, 1)
    draw_wrapped(draw, DATA_NOTE, (74, 1690), 920, F_FOOTER, theme["muted"], 8, 2)
    return img, draw


def draw_scene(path: Path, profile: dict[str, Any], episode: Episode, scene: Scene, scene_index: int) -> None:
    index_type = profile["basic_info"]["index_type"]
    theme = THEMES["dividend" if index_type == "dividend" else "broad_based"].copy()
    theme["series"] = THEMES["dividend" if index_type == "dividend" else "broad_based"]["series"]
    img, draw = base_slide(theme, episode)
    top = 728
    draw.rounded_rectangle((74, top, 1006, top + 176), radius=22, fill=theme["soft"], outline=theme["line"], width=2)
    draw.text((114, top + 36), scene.heading, fill=theme["blue"], font=F_H2)
    draw_wrapped(draw, scene.summary, (114, top + 96), 820, F_BODY, theme["ink"], 10, 2)
    y = top + 236

    if scene.kind in {"cover", "bullets"}:
        for i, item in enumerate(scene.items[:4], 1):
            draw.rounded_rectangle((74, y, 1006, y + 114), radius=18, fill="#ffffff", outline=theme["line"], width=2)
            draw.ellipse((108, y + 30, 162, y + 84), fill=theme["blue"])
            draw.text((126, y + 38), str(i), fill="#ffffff", font=F_BADGE)
            draw_wrapped(draw, str(item), (190, y + 28), 760, F_BODY, theme["ink"], 8, 2)
            y += 136
    elif scene.kind == "bars":
        max_value = max(pct_float(item["weight"]) for item in scene.items[:5])
        for item in scene.items[:5]:
            value = pct_float(item["weight"])
            draw.text((100, y), item["name"], fill=theme["ink"], font=F_BODY)
            draw.text((860, y), item["weight"], fill=theme["blue"], font=F_BODY)
            bar_w = int(650 * value / max_value)
            draw.rounded_rectangle((100, y + 50, 100 + bar_w, y + 82), radius=16, fill=theme["blue"])
            draw.rounded_rectangle((100 + bar_w, y + 50, 760, y + 82), radius=16, fill=theme["soft"])
            y += 116
    elif scene.kind == "table":
        draw.rounded_rectangle((74, y, 1006, y + 610), radius=18, fill="#ffffff", outline=theme["line"], width=2)
        draw.text((110, y + 30), "名称", fill=theme["blue"], font=F_SMALL)
        draw.text((620, y + 30), "权重", fill=theme["blue"], font=F_SMALL)
        row_y = y + 84
        for item in scene.items[:8]:
            draw.text((110, row_y), str(item["name"])[:12], fill=theme["ink"], font=F_SMALL)
            draw.text((620, row_y), str(item["weight"]), fill=theme["ink"], font=F_SMALL)
            row_y += 62
    elif scene.kind == "metrics":
        for i, (label, value) in enumerate(scene.items[:4]):
            x = 74 if i % 2 == 0 else 548
            yy = y + (i // 2) * 188
            draw.rounded_rectangle((x, yy, x + 430, yy + 150), radius=18, fill="#ffffff", outline=theme["line"], width=2)
            draw.text((x + 34, yy + 28), str(label), fill=theme["blue"], font=F_SMALL)
            draw_wrapped(draw, str(value), (x + 34, yy + 76), 355, F_BODY, theme["ink"], 6, 2)
    elif scene.kind == "role":
        for i, (label, value) in enumerate(scene.items[:3], 1):
            x = 96 + (i - 1) * 315
            draw.ellipse((x, y, x + 128, y + 128), fill=theme["blue"] if i == 1 else theme["soft"], outline=theme["blue"], width=3)
            draw.text((x + 52, y + 36), str(i), fill="#ffffff" if i == 1 else theme["blue"], font=F_NUM)
            draw.text((x - 8, y + 164), label, fill=theme["ink"], font=F_SMALL)
            draw_wrapped(draw, value, (x - 40, y + 208), 230, F_SMALL, theme["muted"], 8, 3)
    elif scene.kind == "history":
        returns = [(str(item["period"]), pct_float(item["return"])) for item in scene.items]
        zero = y + 310
        draw.line((116, zero, 980, zero), fill=theme["line"], width=3)
        step = 820 // max(1, len(returns) - 1)
        points = []
        for i, (year, value) in enumerate(returns):
            x = 126 + i * step
            yy = zero - int(value * 6)
            yy = max(y + 40, min(y + 560, yy))
            points.append((x, yy))
            draw.ellipse((x - 7, yy - 7, x + 7, yy + 7), fill=theme["accent"])
            draw.text((x - 24, zero + 18), year[-2:], fill=theme["muted"], font=F_SMALL)
        if len(points) >= 2:
            draw.line(points, fill=theme["blue"], width=5)
    img.save(path)


def ffprobe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def video_quality(path: Path) -> dict[str, Any]:
    info = ffprobe(path)
    streams = info.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    duration = float(info.get("format", {}).get("duration") or 0)
    return {
        "passed": path.exists() and path.stat().st_size > 0 and video.get("width") == 1080 and video.get("height") == 1920 and audio is not None and 60 <= duration <= 100,
        "duration_seconds": round(duration, 2),
        "resolution": f"{video.get('width')}x{video.get('height')}",
        "has_audio": audio is not None,
        "size_mb": round(path.stat().st_size / 1024 / 1024, 2),
    }


def raise_subtitle_safe_area(path: Path) -> None:
    content = path.read_text(encoding="utf-8-sig")
    content = content.replace("Default,Microsoft YaHei,38,", "Default,Microsoft YaHei,36,")
    content = content.replace(",76,76,260,1", ",76,76,405,1")
    path.write_text(content, encoding="utf-8-sig")


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_episode_ending(episode: Episode) -> None:
    tail = DISCLAIMER + CTA
    if episode.scenes and DISCLAIMER not in episode.scenes[-1].narration:
        episode.scenes[-1].narration += tail
    elif episode.scenes and CTA not in episode.scenes[-1].narration:
        episode.scenes[-1].narration += CTA


def render_episode(profile: dict[str, Any], episode: Episode, index_dir: Path, script_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    episode_dir = index_dir / f"episode_{episode.number:02d}_{episode.slug}"
    episode_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    ensure_episode_ending(episode)
    script = "".join(scene.narration for scene in episode.scenes)
    if script_meta:
        write_json(episode_dir / "ai_script.json", script_meta)
    for i, scene in enumerate(episode.scenes, 1):
        slide = episode_dir / f"scene_{i:02d}.png"
        draw_scene(slide, profile, episode, scene, i)
        voice = episode_dir / f"voice_{i:02d}.mp3"
        cues = asyncio.run(speech.make_voice_and_cues(scene.narration, voice))
        voice_duration = speech.duration(voice)
        if not cues:
            cues = speech.fallback_cues(scene.narration, voice_duration)
        ass = episode_dir / f"subtitles_{i:02d}.ass"
        speech.make_ass(ass, cues, voice_duration)
        raise_subtitle_safe_area(ass)
        segment = episode_dir / f"segment_{i:02d}.mp4"
        speech.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", slide.name, "-i", voice.name,
                "-t", f"{voice_duration + 0.35:.3f}", "-vf", f"ass={ass.name},format=yuv420p",
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
                "-c:a", "aac", "-b:a", "160k", "-shortest", segment.name,
            ],
            episode_dir,
        )
        segments.append(segment)
    (episode_dir / "segments.txt").write_text("\n".join(f"file '{item.name}'" for item in segments), encoding="utf-8")
    final = episode_dir / "final.mp4"
    speech.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "segments.txt", "-c:v", "libx264", "-preset", "medium", "-c:a", "aac", "-b:a", "160k", final.name], episode_dir)
    shutil.copy2(episode_dir / "scene_01.png", episode_dir / "cover.png")
    quality = video_quality(final)
    data_used = {
        "index_id": profile["index_id"],
        "episode": episode.number,
        "source_items": profile.get("source_items", []),
        "numbers": [],
        "data_date": profile.get("data_date"),
    }
    if episode.number == 2:
        data_used["numbers"] = [
            {"label": item["name"], "value": item["weight"], "category": "sector_weight", "source_id": "csi_factsheet"} for item in profile["sector_weights"]["items"][:5]
        ] + [
            {"label": item["name"], "value": item["weight"], "category": "holding_weight", "source_id": "constituent_weight_series"} for item in profile["top_holdings"]["items"][:8]
        ] + [
            {"label": "前两大行业合计", "value": sum_sector_weight(profile, 2), "category": "derived_sector_weight_sum", "source_id": "csi_factsheet", "calculation_method": "行业权重TOP1+TOP2。"},
            {"label": "前三大行业合计", "value": sum_sector_weight(profile, 3), "category": "derived_sector_weight_sum", "source_id": "csi_factsheet", "calculation_method": "行业权重TOP1+TOP2+TOP3。"},
        ]
    if episode.number == 4:
        data_used["numbers"] = [
            {"label": "最大回撤", "value": profile["drawdown_stats"]["items"][0]["max_drawdown"], "category": "max_drawdown", "source_id": "history_price_series", "calculation_range": profile["drawdown_stats"]["items"][0].get("calculation_range")},
            *[
                {"label": item["period"], "value": item["return"], "category": "historical_return", "source_id": "history_price_series", "sample_range": item.get("sample_range")}
                for item in profile["historical_returns"]["items"][-5:]
            ],
        ]
    if episode.number == 5:
        data_used["numbers"] = profile["valuation_metrics"]["items"]
    write_json(episode_dir / "data_used.json", data_used)
    write_json(
        episode_dir / "manifest.json",
        {
            "index_id": profile["index_id"],
            "index_name": profile["basic_info"]["index_name_cn"],
            "index_code": profile["basic_info"]["index_code"],
            "episode": episode.number,
            "episode_slug": episode.slug,
            "title": episode.title,
            "script": script,
            "voice": VOICE,
            "rate": RATE,
            "script_generation": script_meta or {"mode": "template", "provider": "local_template"},
            "data_date": profile.get("data_date"),
            "source_items": profile.get("source_items", []),
            "quality_check_result": quality,
            "final": str(final),
        },
    )
    (episode_dir / "script.md").write_text(f"# {episode.title}\n\n{script}\n", encoding="utf-8")
    return {"episode": episode.number, "title": episode.title, "final": str(final), "quality": quality}


def write_report(run_dir: Path, results: list[dict[str, Any]]) -> None:
    rows = []
    for item in results:
        quality = item["quality"]
        rows.append(
            f"<tr><td>{item['index_name']}</td><td>{item['episode']}</td><td>{item['title']}</td>"
            f"<td>{'PASS' if quality['passed'] else 'FAIL'}</td><td>{quality['duration_seconds']}</td>"
            f"<td>{quality['resolution']}</td><td>{quality['has_audio']}</td><td><a href='{item['relative_final']}'>final.mp4</a></td></tr>"
        )
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>中证重点指数15条成品</title>
<style>body{{margin:32px;font-family:Arial,'Microsoft YaHei',sans-serif;background:#f7f8fc;color:#121820}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{border:1px solid #d8e2ec;padding:10px;text-align:left}}th{{background:#eef3fb}}a{{color:#315d8c}}</style></head>
<body><h1>中证重点指数15条成品</h1><p>本批视频读取已批准的 profile 数据生成；已调整字幕安全区和片尾关注语，供最终复核。</p>
<table><thead><tr><th>指数</th><th>集数</th><th>标题</th><th>质量</th><th>时长</th><th>分辨率</th><th>音频</th><th>视频</th></tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""
    (run_dir / "sample_report.html").write_text(html, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render approved China priority index videos.")
    parser.add_argument("--ai-scripts", action="store_true", help="Use local AI to write each episode narration independently.")
    parser.add_argument("--llm-model", default=None, help="Ollama model name, for example qwen3:14b.")
    parser.add_argument("--template-fallback", action="store_true", help="Use template narration if AI writing fails.")
    parser.add_argument("--index", dest="index_ids", action="append", choices=INDEX_IDS, help="Render only one index; can be used more than once.")
    parser.add_argument("--episode", type=int, choices=[1, 2, 3, 4, 5], help="Render only one episode number.")
    parser.add_argument("--output-prefix", default="china_priority_products", help="Run output directory prefix.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("需要 ffmpeg 和 ffprobe")
    writer = AIScriptWriter(model=args.llm_model) if args.ai_scripts else None
    run_dir = RUNS_DIR / f"{args.output_prefix}_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    target_ids = args.index_ids or INDEX_IDS
    for index_id in target_ids:
        profile = load_profile(index_id)
        if profile.get("data_status") != "ready" or profile.get("review_status") != "approved":
            raise RuntimeError(f"{index_id} is not ready/approved")
        index_dir = run_dir / index_id
        index_dir.mkdir(parents=True, exist_ok=True)
        write_json(index_dir / "profile.json", profile)
        for episode in build_episodes(profile):
            if args.episode and episode.number != args.episode:
                continue
            script_meta: dict[str, Any] | None = None
            if writer:
                print(f"Writing AI script {index_id} {episode.number}/5 {episode.title}", flush=True)
                try:
                    episode, ai_result = writer.rewrite_episode(profile, episode)
                    script_meta = {
                        "mode": "ai_per_episode",
                        "provider": ai_result.provider,
                        "model": ai_result.model,
                        "attempts": ai_result.attempts,
                        "checks": ai_result.checks,
                        "scene_narrations": ai_result.scene_narrations,
                        "prompt": ai_result.prompt,
                        "raw_response": ai_result.raw_response,
                    }
                except AIScriptError as exc:
                    if not args.template_fallback:
                        raise
                    script_meta = {
                        "mode": "template_fallback_after_ai_error",
                        "provider": "local_template",
                        "error": str(exc),
                    }
            print(f"Rendering {index_id} {episode.number}/5 {episode.title}", flush=True)
            item = render_episode(profile, episode, index_dir, script_meta)
            item["index_id"] = index_id
            item["index_name"] = profile["basic_info"]["index_name_cn"]
            item["relative_final"] = str(Path(item["final"]).relative_to(run_dir)).replace("\\", "/")
            results.append(item)
    write_json(
        run_dir / "sample_manifest.json",
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "run_dir": str(run_dir),
            "index_count": len(set(item["index_id"] for item in results)),
            "episode_count": len(results),
            "all_passed": all(item["quality"]["passed"] for item in results),
            "episodes": results,
        },
    )
    write_report(run_dir, results)
    print(json.dumps({"output_dir": str(run_dir), "sample_report": str(run_dir / "sample_report.html"), "all_passed": all(item["quality"]["passed"] for item in results)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
