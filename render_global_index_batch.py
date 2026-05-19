from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import edge_tts
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
SIZE = (1080, 1920)
VOICE = "zh-CN-YunjianNeural"
RATE = "+12%"
VOLUME = "+0%"
DISCLAIMER = "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。"


@dataclass
class Theme:
    key: str
    label: str
    bg: str
    header: str
    accent: str
    accent2: str
    soft: str


@dataclass
class IndexDemo:
    code: str
    name: str
    market: str
    provider: str
    category: str
    title: str
    subtitle: str
    scenes: list[dict[str, Any]]
    script: str
    theme: str


THEMES: dict[str, Theme] = {
    "china": Theme("china", "A股指数观察", "#f5f7f3", "#14563a", "#1f7a4d", "#b06f16", "#eaf3ed"),
    "red": Theme("red", "红利指数观察", "#f7f5f1", "#5a3f22", "#9a6a24", "#1f7a4d", "#f0eadf"),
    "us": Theme("us", "美股指数观察", "#f6f5f1", "#233b59", "#315d8c", "#a66b10", "#edf2f7"),
    "europe": Theme("europe", "欧洲指数观察", "#f5f5f0", "#4a4f2b", "#6f8f64", "#b06f16", "#eef2e8"),
}


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
F_SUBTITLE = font(38, True)
F_SMALL = font(27)
F_BADGE = font(28, True)


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
    if max_lines:
        lines = lines[:max_lines]
    for line in lines:
        draw.text((x, y), line, fill=fill, font=text_font)
        y += text_font.size + line_gap
    return y


def draw_base(draw: ImageDraw.ImageDraw, demo: IndexDemo, theme: Theme) -> None:
    draw.rounded_rectangle((52, 52, 1028, 1868), radius=34, fill="#ffffff", outline="#dce5df", width=3)
    draw.rectangle((52, 52, 1028, 238), fill=theme.header)
    draw.text((92, 92), theme.label, fill="#eef6f2", font=F_BADGE)
    draw.rounded_rectangle((760, 86, 988, 148), radius=31, fill="#f2f7f4")
    draw.text((800, 101), demo.market[:7], fill=theme.header, font=F_BADGE)
    draw_text(draw, demo.title, (92, 282), 860, F_TITLE, "#14201b", 16, 3)
    draw_text(draw, demo.subtitle, (92, 515), 850, F_BODY, "#5e6a65", 12, 2)
    draw.line((92, 655, 988, 655), fill="#dce5df", width=3)


def draw_footer(draw: ImageDraw.ImageDraw) -> None:
    draw.line((92, 1696, 988, 1696), fill="#dce5df", width=2)
    draw.text((92, 1732), DISCLAIMER, fill="#5e6a65", font=F_SMALL)
    draw.text((92, 1774), "数据口径请以指数公司最新公开资料为准", fill="#5e6a65", font=F_SMALL)


def draw_bullets(draw: ImageDraw.ImageDraw, items: list[str], y: int, theme: Theme) -> None:
    for idx, item in enumerate(items, start=1):
        if y > 1508:
            break
        text_x = 205
        max_width = 988 - text_x - 54
        lines = wrap_by_width(draw, item, F_BODY, max_width)[:3]
        box_h = max(126, len(lines) * (F_BODY.size + 10) + 58)
        draw.rounded_rectangle((92, y, 988, y + box_h), radius=22, fill=theme.soft)
        badge_y = y + max(34, (box_h - 52) // 2)
        draw.ellipse((126, badge_y, 178, badge_y + 52), fill=theme.accent)
        draw.text((143, badge_y + 7), str(idx), fill="#ffffff", font=F_BADGE)
        line_y = y + 29
        for line in lines:
            draw.text((text_x, line_y), line, fill="#14201b", font=F_BODY)
            line_y += F_BODY.size + 10
        y += box_h + 28


def draw_info_grid(draw: ImageDraw.ImageDraw, items: list[tuple[str, str]], y: int, theme: Theme) -> None:
    x_positions = [92, 550]
    for idx, (label, value) in enumerate(items[:6]):
        x = x_positions[idx % 2]
        row = idx // 2
        top = y + row * 178
        draw.rounded_rectangle((x, top, x + 438, top + 138), radius=22, fill=theme.soft)
        draw.text((x + 30, top + 24), label, fill=theme.accent, font=F_SMALL)
        draw_text(draw, value, (x + 30, top + 68), 370, F_BODY, "#14201b", 8, 2)


def draw_market_map(draw: ImageDraw.ImageDraw, demo: IndexDemo, theme: Theme) -> None:
    draw.rounded_rectangle((110, 820, 970, 1360), radius=30, fill=theme.soft)
    draw.text((150, 860), "看这个指数，重点看三件事", fill=theme.header, font=F_H2)
    draw.line((160, 980, 920, 980), fill="#dce5df", width=3)
    labels = ["覆盖范围", "权重结构", "组合角色"]
    for idx, label in enumerate(labels):
        cx = 235 + idx * 280
        draw.ellipse((cx - 55, 1060, cx + 55, 1170), fill=theme.accent)
        draw.text((cx - 15, 1080), str(idx + 1), fill="#ffffff", font=F_H2)
        draw.text((cx - 70, 1225), label, fill="#14201b", font=F_SMALL)
    draw_text(draw, "这些维度都可以用公开资料核验，不需要凭感觉给分。", (150, 1440), 760, F_BODY, "#5e6a65", 10, 3)


def make_slide(path: Path, demo: IndexDemo, scene_idx: int) -> None:
    theme = THEMES[demo.theme]
    img = Image.new("RGB", SIZE, theme.bg)
    draw = ImageDraw.Draw(img)
    draw_base(draw, demo, theme)
    scene = demo.scenes[scene_idx]

    draw.rounded_rectangle((92, 740, 988, 934), radius=30, fill=theme.soft)
    draw.text((130, 784), scene["heading"], fill=theme.header, font=F_H2)
    draw_text(draw, scene["summary"], (130, 852), 800, F_BODY, "#14201b", 10, 2)

    if scene["type"] == "bullets":
        draw_bullets(draw, scene["items"], 1010, theme)
    elif scene["type"] == "grid":
        draw_info_grid(draw, scene["items"], 1010, theme)
    else:
        draw_market_map(draw, demo, theme)

    draw_footer(draw)
    img.save(path)


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[。！？])", re.sub(r"\s+", " ", text)) if part.strip()]


async def make_voice_and_cues(text: str, output: Path) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=VOICE,
                rate=RATE,
                volume=VOLUME,
                boundary="SentenceBoundary",
            )
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
    if not cues:
        cues = []
    normalized: list[dict[str, Any]] = []
    sorted_cues = sorted(cues, key=lambda item: float(item["start"]))
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
Style: Default,Microsoft YaHei,38,&H00FFFFFF,&H000000FF,&H6A12201B,&HAA12201B,1,0,0,0,100,100,0,0,1,3,0,2,76,76,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = [header]
    for cue in normalized:
        start = max(0.0, float(cue["start"]))
        end = min(total_duration, max(start + 0.35, float(cue["end"])))
        wrapped = wrap_by_width(draw, str(cue["text"]), F_SUBTITLE, 840)
        pages = ["\\N".join(wrapped[i : i + 2]) for i in range(0, len(wrapped), 2)]
        pages = [page for page in pages if page.strip()]
        if not pages:
            continue
        span = max(0.45, end - start)
        weights = [max(1, len(page.replace("\\N", ""))) for page in pages]
        total_weight = sum(weights)
        cursor = start
        for idx, page in enumerate(pages):
            if idx == len(pages) - 1:
                page_end = end
            else:
                page_end = min(end, cursor + span * weights[idx] / total_weight)
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


def render_one(demo: IndexDemo, output_root: Path) -> Path:
    run_dir = output_root / safe_name(f"{demo.code}_{demo.name}")
    run_dir.mkdir(parents=True, exist_ok=True)
    slides = []
    for idx in range(len(demo.scenes)):
        slide = run_dir / f"scene_{idx + 1:02d}.png"
        make_slide(slide, demo, idx)
        slides.append(slide)

    voice = run_dir / "voice.mp3"
    cues = asyncio.run(make_voice_and_cues(demo.script, voice))
    voice_duration = duration(voice)
    if not cues:
        cues = fallback_cues(demo.script, voice_duration)

    per_slide = max(4.0, voice_duration / len(slides))
    (run_dir / "slides.txt").write_text(
        "\n".join([line for slide in slides for line in [f"file '{slide.name}'", f"duration {per_slide:.3f}"]] + [f"file '{slides[-1].name}'"]),
        encoding="utf-8",
    )
    raw = run_dir / "slides.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "slides.txt", "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", raw.name], run_dir)

    ass = run_dir / "subtitles.ass"
    make_ass(ass, cues, voice_duration)
    final = run_dir / "final.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            raw.name,
            "-i",
            voice.name,
            "-vf",
            "ass=subtitles.ass",
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
            final.name,
        ],
        run_dir,
    )
    (run_dir / "manifest.json").write_text(
        json.dumps({"demo": asdict(demo), "duration": voice_duration, "voice": VOICE, "subtitle_cues": len(cues)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return final


def demos() -> dict[str, IndexDemo]:
    return {
        "CSI300": IndexDemo(
            code="CSI300",
            name="沪深300",
            market="中国内地",
            provider="中证指数",
            category="A股大盘宽基",
            title="沪深300，代表A股核心资产吗？",
            subtitle="中证指数 | A股大盘宽基 | 沪深两市代表性公司",
            theme="china",
            scenes=[
                {
                    "type": "bullets",
                    "heading": "先看它覆盖什么",
                    "summary": "它选取沪深市场规模大、流动性好的代表性证券。",
                    "items": ["不是全市场指数，而是偏大盘、偏核心公司的样本。", "常被用作观察A股大盘表现的基准。", "成分会定期调整，跟踪的是一套规则。"],
                },
                {
                    "type": "grid",
                    "heading": "发布前要核验的数据",
                    "summary": "这条视频不编造权重，关键数字应从最新公开资料替换。",
                    "items": [("指数公司", "中证指数"), ("市场范围", "沪深两市"), ("风格定位", "大盘宽基"), ("重点核验", "行业权重、前十大、估值")],
                },
                {
                    "type": "map",
                    "heading": "组合里的角色",
                    "summary": "它更适合作为A股核心宽基暴露，而不是短期择时工具。",
                    "items": [],
                },
                {
                    "type": "bullets",
                    "heading": "主要风险",
                    "summary": "宽基也不是无风险，行业权重和市场估值都会影响体验。",
                    "items": ["金融、消费、工业等权重变化会影响阶段表现。", "市场整体估值抬升时，回撤体验也会变差。", "它代表大盘，不代表所有A股风格。"],
                },
            ],
            script=("今天看沪深300。它由中证指数编制，样本来自上海和深圳市场，重点选取规模较大、流动性较好的上市公司。"
                    "所以它不是全市场指数，更不是小盘指数，而是偏大盘、偏核心资产的一组样本。"
                    "理解沪深300，第一步要看它代表什么：它通常覆盖金融、消费、工业、信息技术、医药等主要板块，能反映A股头部公司的整体状态。"
                    "第二步要看权重结构。沪深300不是三百家公司平均分配，前十大成分和高权重行业会明显影响指数走势。"
                    "第三步看组合角色。它更适合做A股核心宽基的观察对象，用来承担基础权益暴露；但它不能替代中证500、中证1000，也不能代表红利、小盘、成长等所有风格。"
                    "最后看风险。沪深300也会经历估值回落和阶段性回撤，尤其当权重行业同时承压时，指数波动并不低。"
                    "看它，不是猜明天涨跌，而是核验范围、权重、估值和长期持有体验。仅作指数观察，不构成投资建议；本视频由AI辅助生成。"),
        ),
        "CSI_DIV": IndexDemo(
            code="CSI_DIV",
            name="中证红利",
            market="中国内地",
            provider="中证指数",
            category="红利策略指数",
            title="中证红利，买的是高股息风格",
            subtitle="中证指数 | 红利策略 | 分红与价值风格",
            theme="red",
            scenes=[
                {
                    "type": "bullets",
                    "heading": "它跟踪的是一种风格",
                    "summary": "中证红利不是单一行业，而是一套偏高股息的选股规则。",
                    "items": ["重点关注现金股息率、分红稳定性、规模和流动性。", "它更偏价值和现金流，不是追逐短期热门题材。", "样本定期调整，所以持仓会随规则变化。"],
                },
                {
                    "type": "grid",
                    "heading": "发布前要核验的数据",
                    "summary": "红利指数尤其需要核验行业暴露和前十大权重。",
                    "items": [("指数公司", "中证指数"), ("风格定位", "高股息/价值"), ("重点指标", "股息率、PB、行业集中度"), ("重点核验", "前十大、分红稳定性")],
                },
                {
                    "type": "map",
                    "heading": "组合里的角色",
                    "summary": "它更像现金流和价值风格补充，不适合作为唯一仓位。",
                    "items": [],
                },
                {
                    "type": "bullets",
                    "heading": "主要风险",
                    "summary": "高股息不等于低风险，红利风格也会阶段性跑输。",
                    "items": ["高股息有时来自股价下跌后的被动抬升。", "行业可能集中，少数板块会影响整体表现。", "成长行情很强时，红利风格可能阶段性落后。"],
                },
            ],
            script=("今天看中证红利。它的核心不是追热门行业，而是按照红利规则筛选公司，重点看现金股息率、分红连续性、规模和流动性。"
                    "这意味着它更偏价值、偏现金流，也更容易和银行、煤炭、交通运输、公用事业等高分红行业产生联系。"
                    "看中证红利，不能只看到股息率三个字。第一，要核验行业分布，如果少数周期行业权重过高，指数就会受到行业景气度影响。"
                    "第二，要看分红是否可持续。高股息有时来自股价下跌，也可能来自阶段性高利润，不能简单理解成稳定收益。"
                    "第三，要看它在组合里的位置。中证红利更像防守、现金流和价值风格的补充，可以和宽基、成长风格、海外资产搭配，但不适合作为唯一核心仓位。"
                    "它最大的风险，是红利风格阶段性跑输成长风格，以及行业集中带来的波动。"
                    "所以这条指数要看的不是会不会涨，而是分红质量、行业结构和长期回撤体验。仅作指数观察，不构成投资建议；本视频由AI辅助生成。"),
        ),
        "NDX": IndexDemo(
            code="NDX",
            name="纳斯达克100",
            market="美国",
            provider="Nasdaq",
            category="美股成长宽基",
            title="纳斯达克100，不只是科技股",
            subtitle="Nasdaq | 美股大型成长公司 | 非金融为主",
            theme="us",
            scenes=[
                {
                    "type": "bullets",
                    "heading": "它代表什么",
                    "summary": "纳斯达克100覆盖纳斯达克市场里规模较大的非金融公司。",
                    "items": ["它常被视为美股成长和科技风格的重要代表。", "大型科技公司权重通常较高，但并不等于纯科技行业指数。", "成分和权重会随市值变化而改变。"],
                },
                {
                    "type": "grid",
                    "heading": "发布前要核验的数据",
                    "summary": "这类指数最怕只看涨幅，忽略权重集中和估值。",
                    "items": [("指数公司", "Nasdaq"), ("市场范围", "美国"), ("风格定位", "大型成长/科技"), ("重点核验", "前十大权重、估值、汇率")],
                },
                {
                    "type": "map",
                    "heading": "组合里的角色",
                    "summary": "它更适合作为成长风格和美元资产暴露。",
                    "items": [],
                },
                {
                    "type": "bullets",
                    "heading": "主要风险",
                    "summary": "高成长也伴随高估值波动和集中度风险。",
                    "items": ["大型科技股权重高时，少数公司会影响指数表现。", "利率变化会影响成长股估值。", "人民币投资者还要考虑美元汇率波动。"],
                },
            ],
            script=("今天看纳斯达克100。它覆盖纳斯达克市场里规模较大的非金融公司，很多人会把它理解成美股科技成长的代表。"
                    "但它不是一个纯科技行业指数，因为成分里也可能包括消费、通信服务、医疗保健等大型公司。"
                    "看纳斯达克100，最重要的是不要只看过去长期涨幅。第一，要看前十大权重。大型科技公司占比高时，少数龙头的业绩和估值变化，就会明显影响指数表现。"
                    "第二，要看估值和利率。成长股的远期现金流占比高，利率上行时，估值压力往往更明显。"
                    "第三，要看汇率。国内投资者通过相关产品配置时，美元和人民币汇率也会影响最终体验。"
                    "在组合里，纳斯达克100更像成长风格和美元资产暴露，适合补充全球配置，但不能替代标普500，也不能代表全部海外市场。"
                    "它的优势是创新公司集中，风险也是集中。看这条指数，核心是权重、估值、利率和汇率四件事。仅作指数观察，不构成投资建议；本视频由AI辅助生成。"),
        ),
        "DAX": IndexDemo(
            code="DAX",
            name="德国DAX",
            market="德国",
            provider="STOXX/Qontigo",
            category="欧洲蓝筹宽基",
            title="德国DAX，看的是欧洲工业底色",
            subtitle="德国市场 | 大型上市公司 | 工业与出口周期",
            theme="europe",
            scenes=[
                {
                    "type": "bullets",
                    "heading": "它代表什么",
                    "summary": "德国DAX主要反映德国大型上市公司的整体表现。",
                    "items": ["它是观察德国股票市场的重要宽基指标。", "德国经济有明显工业和出口特征。", "指数表现会受欧洲经济和欧元汇率影响。"],
                },
                {
                    "type": "grid",
                    "heading": "发布前要核验的数据",
                    "summary": "DAX适合结合行业权重、出口周期和欧洲利率环境来看。",
                    "items": [("市场范围", "德国"), ("风格定位", "大型蓝筹"), ("重点变量", "工业、出口、欧元汇率"), ("重点核验", "行业权重、前十大、估值")],
                },
                {
                    "type": "map",
                    "heading": "组合里的角色",
                    "summary": "它更像欧洲权益资产的一块区域暴露。",
                    "items": [],
                },
                {
                    "type": "bullets",
                    "heading": "主要风险",
                    "summary": "区域指数最需要注意经济周期和汇率。",
                    "items": ["德国工业周期会影响相关公司盈利预期。", "欧洲利率和欧元汇率会影响估值和收益体验。", "单一国家指数不等于整个欧洲市场。"],
                },
            ],
            script=("今天看德国DAX。它主要反映德国大型上市公司的整体表现，是观察德国股票市场的重要宽基指标。"
                    "德国市场的底色很鲜明：工业、制造、出口和欧洲经济周期，会比很多人想象得更重要。"
                    "所以看DAX，不能只看指数点位。第一，要看行业权重。汽车、工业、化工、金融、软件等板块的变化，会决定它更偏周期还是更偏成长。"
                    "第二，要看出口需求。德国大型企业和全球贸易联系紧密，如果欧洲需求、全球制造业周期或能源成本变化，指数表现也会受到影响。"
                    "第三，要看欧元和欧洲利率。对国内投资者来说，区域市场收益和汇率变化会一起影响持有体验。"
                    "在组合里，DAX更像欧洲权益资产的区域暴露，可以补充全球配置视角，但它不等于整个欧洲，也不是低波动资产。"
                    "它的主要风险，是工业周期、出口需求、欧洲利率和汇率同时变化。看这条指数，重点是理解德国经济结构，而不是只追一条价格曲线。仅作指数观察，不构成投资建议；本视频由AI辅助生成。"),
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", default="CSI300,CSI_DIV,NDX,DAX")
    parser.add_argument("--output", default=str(ROOT / "runs" / "demo_four_indices"))
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("需要 ffmpeg 和 ffprobe。")

    all_demos = demos()
    wanted = [code.strip().upper() for code in args.codes.split(",") if code.strip()]
    missing = [code for code in wanted if code not in all_demos]
    if missing:
        raise RuntimeError(f"Unknown codes: {', '.join(missing)}")

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = []
    for code in wanted:
        demo = all_demos[code]
        print(f"Rendering {demo.name}")
        outputs.append(str(render_one(demo, output_root)))
    (output_root / "batch_manifest.json").write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done: {output_root}")


if __name__ == "__main__":
    main()
