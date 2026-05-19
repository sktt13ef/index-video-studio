from __future__ import annotations

import asyncio
import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT_ROOT = ROOT / "runs" / f"zzhl_commercial_{datetime.now():%Y%m%d_%H%M%S}"
SIZE = (1080, 1920)
VOICE = "zh-CN-YunjianNeural"
RATE = "-6%"
VOLUME = "+0%"

INK = "#14201b"
MUTED = "#5e6a65"
BG = "#f5f7f3"
CARD = "#ffffff"
LINE = "#dce5df"
GREEN = "#1f7a4d"
DARK_GREEN = "#14563a"
BLUE = "#2f5d89"
AMBER = "#b06f16"
RED = "#a13f3f"

DISCLAIMER = "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。"


@dataclass
class VideoSpec:
    slug: str
    title: str
    subtitle: str
    script: str
    scenes: list[str]
    chart_type: str


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


F_TITLE = font(62, True)
F_H2 = font(46, True)
F_BODY = font(34)
F_SMALL = font(27)
F_BADGE = font(28, True)
F_NUM = font(50, True)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[。！？])", text)
    return [part.strip() for part in parts if part.strip()]


def wrap_text(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text.strip():
        current += char
        if len(current) >= max_chars or char in "。！？；":
            lines.append(current.strip())
            current = ""
    if current.strip():
        lines.append(current.strip())
    return lines


def wrap_text_by_width(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text.strip():
        trial = current + char
        width = draw.textbbox((0, 0), trial, font=text_font)[2]
        if current and (width > max_width or char in "。！？；"):
            lines.append(current.strip())
            current = char if char not in "。！？；" else ""
        else:
            current = trial
    if current.strip():
        lines.append(current.strip())
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_chars: int,
    fill: str,
    text_font: ImageFont.FreeTypeFont,
    line_gap: int,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    lines = wrap_text(text, max_chars)
    if max_lines:
        lines = lines[:max_lines]
    for line in lines:
        draw.text((x, y), line, fill=fill, font=text_font)
        y += text_font.size + line_gap
    return y


def draw_wrapped_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_width: int,
    fill: str,
    text_font: ImageFont.FreeTypeFont,
    line_gap: int,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    lines = wrap_text_by_width(draw, text, text_font, max_width)
    if max_lines:
        lines = lines[:max_lines]
    for line in lines:
        draw.text((x, y), line, fill=fill, font=text_font)
        y += text_font.size + line_gap
    return y


def draw_header(draw: ImageDraw.ImageDraw, title: str, subtitle: str, episode: str) -> None:
    draw.rounded_rectangle((52, 52, 1028, 1868), radius=34, fill=CARD, outline=LINE, width=3)
    draw.rectangle((52, 52, 1028, 238), fill=DARK_GREEN)
    draw.text((92, 92), "中证红利指数观察", fill="#dcefe5", font=F_BADGE)
    draw.rounded_rectangle((830, 86, 988, 148), radius=31, fill="#eaf3ed")
    draw.text((864, 101), episode, fill=DARK_GREEN, font=F_BADGE)
    draw_wrapped(draw, title, (92, 282), 14, INK, F_TITLE, 16, 3)
    draw_wrapped(draw, subtitle, (92, 515), 24, MUTED, F_BODY, 12, 2)
    draw.line((92, 655, 988, 655), fill=LINE, width=3)


def draw_footer(draw: ImageDraw.ImageDraw, data_note: str = "数据口径请以最新公开资料为准") -> None:
    draw.line((92, 1696, 988, 1696), fill=LINE, width=2)
    draw.text((92, 1732), DISCLAIMER, fill=MUTED, font=F_SMALL)
    draw.text((92, 1774), data_note, fill=MUTED, font=F_SMALL)


def draw_bullets(draw: ImageDraw.ImageDraw, items: list[str], y: int, color: str = GREEN) -> None:
    for index, item in enumerate(items, start=1):
        if y > 1540:
            break
        text_x = 205
        max_width = 988 - text_x - 54
        lines = wrap_text_by_width(draw, item, F_BODY, max_width)[:3]
        box_h = max(126, len(lines) * (F_BODY.size + 10) + 58)
        draw.rounded_rectangle((92, y, 988, y + box_h), radius=22, fill="#eef5f0")
        badge_y = y + max(34, (box_h - 52) // 2)
        draw.ellipse((126, badge_y, 178, badge_y + 52), fill=color)
        draw.text((143, badge_y + 7), str(index), fill="#ffffff", font=F_BADGE)
        line_y = y + 29
        for line in lines:
            draw.text((text_x, line_y), line, fill=INK, font=F_BODY)
            line_y += F_BODY.size + 10
        y += box_h + 28


def draw_bar_chart(draw: ImageDraw.ImageDraw, labels: list[str], values: list[int], box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    max_value = max(values)
    bar_gap = 32
    bar_h = (y2 - y1 - bar_gap * (len(values) - 1)) // len(values)
    for idx, (label, value) in enumerate(zip(labels, values)):
        y = y1 + idx * (bar_h + bar_gap)
        draw.text((x1, y - 2), label, fill=INK, font=F_SMALL)
        bar_x = x1 + 170
        width = int((x2 - bar_x - 90) * value / max_value)
        draw.rounded_rectangle((bar_x, y, x2 - 90, y + bar_h), radius=18, fill="#edf2ef")
        draw.rounded_rectangle((bar_x, y, bar_x + width, y + bar_h), radius=18, fill=[GREEN, BLUE, AMBER, "#6f8f64", RED][idx % 5])
        draw.text((x2 - 70, y + 6), f"{value}%", fill=MUTED, font=F_SMALL)


def draw_role_map(draw: ImageDraw.ImageDraw) -> None:
    boxes = [
        ("宽基核心", 126, 790, BLUE),
        ("红利现金流", 570, 790, GREEN),
        ("成长卫星", 126, 1060, AMBER),
        ("海外分散", 570, 1060, "#6f8f64"),
    ]
    for label, x, y, color in boxes:
        draw.rounded_rectangle((x, y, x + 380, y + 170), radius=28, fill="#eef5f0", outline=LINE, width=2)
        draw.ellipse((x + 30, y + 44, x + 108, y + 122), fill=color)
        draw.text((x + 135, y + 62), label, fill=INK, font=F_H2)
    draw.line((506, 875, 570, 875), fill=LINE, width=6)
    draw.line((316, 960, 316, 1060), fill=LINE, width=6)
    draw.line((760, 960, 760, 1060), fill=LINE, width=6)
    draw.text((318, 1340), "重点：它是组合中的一个角色，不是全部答案。", fill=DARK_GREEN, font=F_BODY)


def draw_risk_curve(draw: ImageDraw.ImageDraw) -> None:
    x0, y0 = 130, 1240
    points = [(x0, y0), (260, 1130), (390, 1300), (520, 1010), (650, 1200), (800, 925), (950, 1080)]
    draw.line(points, fill=RED, width=8, joint="curve")
    draw.line((130, 1370, 950, 1370), fill=LINE, width=4)
    draw.text((132, 1395), "历史波动示意", fill=MUTED, font=F_SMALL)
    draw.rounded_rectangle((120, 800, 960, 905), radius=24, fill="#fff4ed")
    draw.text((160, 830), "回撤不是异常，它是持有体验的一部分。", fill=RED, font=F_BODY)


def draw_gauge(draw: ImageDraw.ImageDraw) -> None:
    center = (540, 1110)
    radius = 330
    for idx, color in enumerate([GREEN, "#8aa35d", AMBER, RED]):
        start = 180 + idx * 45
        end = start + 43
        draw.arc((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), start, end, fill=color, width=36)
    draw.line((center[0], center[1], center[0] + 120, center[1] - 230), fill=INK, width=8)
    draw.ellipse((center[0] - 18, center[1] - 18, center[0] + 18, center[1] + 18), fill=INK)
    draw.text((250, 1315), "PE / PB / 股息率 / 估值分位", fill=INK, font=F_BODY)
    draw.text((285, 1370), "只辅助判断，不预测短期涨跌", fill=MUTED, font=F_SMALL)


def make_scene(path: Path, spec: VideoSpec, episode: int, scene_idx: int, total: int) -> None:
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)
    draw_header(draw, spec.title, spec.subtitle, f"{episode}/5")

    if scene_idx == 0:
        draw.rounded_rectangle((92, 740, 988, 958), radius=30, fill="#eaf3ed")
        draw.text((130, 784), "本条只解决一个问题", fill=DARK_GREEN, font=F_H2)
        draw_wrapped_width(draw, spec.scenes[0], (130, 858), 800, INK, F_BODY, 10, 3)
        draw_bullets(draw, spec.scenes[1:4], 1028, GREEN)
    elif spec.chart_type == "bars":
        draw.text((92, 720), "行业暴露示意", fill=INK, font=F_H2)
        draw_bar_chart(draw, ["银行", "煤炭", "交通运输", "公用事业", "钢铁"], [24, 18, 12, 10, 8], (120, 840, 960, 1330))
        draw_wrapped(draw, "真实占比请以最新指数公司披露为准。这里用于展示视频画面结构。", (120, 1425), 25, MUTED, F_SMALL, 8, 3)
    elif spec.chart_type == "role":
        draw.text((92, 720), "组合角色地图", fill=INK, font=F_H2)
        draw_role_map(draw)
    elif spec.chart_type == "risk":
        draw.text((92, 720), "风险和回撤体验", fill=INK, font=F_H2)
        draw_bullets(draw, spec.scenes[:3], 800, RED)
        draw_risk_curve(draw)
    elif spec.chart_type == "gauge":
        draw.text((92, 720), "估值观察框架", fill=INK, font=F_H2)
        draw_gauge(draw)
        draw_bullets(draw, spec.scenes[:2], 800, GREEN)
    else:
        draw_bullets(draw, spec.scenes[:4], 760, GREEN)

    progress_x = 92
    for i in range(total):
        color = GREEN if i <= scene_idx else "#dce5df"
        draw.rounded_rectangle((progress_x, 1628, progress_x + 205, 1648), radius=10, fill=color)
        progress_x += 224
    draw_footer(draw)
    img.save(path)


async def make_voice(text: str, output: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            communicate = edge_tts.Communicate(text=text, voice=VOICE, rate=RATE, volume=VOLUME)
            await communicate.save(str(output))
            return
        except Exception as exc:  # network TTS occasionally resets the websocket
            last_error = exc
            await asyncio.sleep(attempt * 2)
    raise RuntimeError(f"男声 TTS 生成失败：{last_error}") from last_error


def duration(path: Path) -> float:
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
    return max(1.0, float(result.stdout.strip()))


def ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def make_ass(path: Path, text: str, total_duration: float) -> None:
    sentences = split_sentences(text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current + sentence) > 32 and current:
            chunks.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        chunks.append(current)
    chunks = chunks[:12]
    slot = total_duration / max(1, len(chunks))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,46,&H00FFFFFF,&H000000FF,&H6A12201B,&HAA12201B,1,0,0,0,100,100,0,0,1,3,0,2,70,70,310,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for idx, chunk in enumerate(chunks):
        start = idx * slot
        end = min(total_duration, (idx + 1) * slot)
        subtitle = "\\N".join(wrap_text(chunk, 18)[:2])
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{subtitle}")
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def narration_text(text: str) -> str:
    sentences = split_sentences(text)
    return "\n".join(sentence for sentence in sentences)


def run(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def render_video(spec: VideoSpec, episode: int) -> Path:
    run_dir = OUT_ROOT / f"{episode:02d}_{spec.slug}"
    run_dir.mkdir(parents=True, exist_ok=True)
    slides: list[Path] = []
    total_scenes = 4
    for scene_idx in range(total_scenes):
        slide = run_dir / f"scene_{scene_idx + 1:02d}.png"
        make_scene(slide, spec, episode, scene_idx, total_scenes)
        slides.append(slide)

    voice = run_dir / "voice.mp3"
    asyncio.run(make_voice(narration_text(spec.script), voice))
    voice_duration = duration(voice)
    per_slide = max(4, voice_duration / total_scenes)

    concat = run_dir / "slides.txt"
    concat.write_text(
        "\n".join([line for slide in slides for line in [f"file '{slide.name}'", f"duration {per_slide:.3f}"]] + [f"file '{slides[-1].name}'"]),
        encoding="utf-8",
    )
    raw_video = run_dir / "slides.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "slides.txt",
            "-vf",
            "fps=30,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            raw_video.name,
        ],
        run_dir,
    )

    ass = run_dir / "subtitles.ass"
    make_ass(ass, spec.script, voice_duration)
    final = run_dir / "final.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            raw_video.name,
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

    manifest = {
        "title": spec.title,
        "voice": VOICE,
        "duration": voice_duration,
        "final": str(final),
        "disclaimer": DISCLAIMER,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return final


def build_specs() -> list[VideoSpec]:
    return [
        VideoSpec(
            slug="index_intro",
            title="中证红利到底跟踪什么？",
            subtitle="先看清它买的是什么，再谈适不适合你。",
            chart_type="intro",
            scenes=[
                "从沪深市场中，筛选现金股息率高、分红稳定、规模和流动性较好的上市公司。",
                "它不是追热门题材，而是偏向高股息、偏价值、偏现金流的股票集合。",
                "样本会按规则定期调整，所以它跟踪的是一种红利风格，而不是固定几家公司。",
                "这一条先解决：中证红利买的是什么。",
            ],
            script="今天我们用一分钟认识中证红利。它不是某一只股票，也不是单一行业基金，而是从沪深市场中，筛选现金股息率较高、分红比较稳定，同时具备一定规模和流动性的上市公司。简单说，它代表的是一种偏红利、偏价值、偏现金流的股票组合。它的样本会按规则定期调整，所以我们买到的不是固定几家公司，而是一套持续运转的红利选股规则。第一条先记住一句话：中证红利买的是高股息风格，不是短期热点。下一条，我们看它里面主要都是哪些行业。仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
        ),
        VideoSpec(
            slug="holdings_breakdown",
            title="中证红利里面，主要都是哪些行业？",
            subtitle="买指数之前，先看它真实装了什么。",
            chart_type="bars",
            scenes=[
                "红利指数往往偏向银行、煤炭、交通运输、公用事业、钢铁等成熟行业。",
                "这些行业共同特点是现金流相对明确，分红能力通常更容易被观察。",
                "但行业集中也意味着：少数板块的景气度，会明显影响指数体验。",
                "看成分和行业，比只看近期涨跌更重要。",
            ],
            script="看懂中证红利，第二步不是看它最近涨了多少，而是看它到底装了什么。红利指数通常会更多暴露在银行、煤炭、交通运输、公用事业、钢铁等成熟行业。这些行业的共同特点，是现金流相对明确，分红能力更容易被观察。但这也带来一个问题：如果行业集中度较高，少数板块的景气变化，就会明显影响指数表现。所以看中证红利，不能只看红利两个字，还要看行业分布、前十大权重和集中度。买指数，本质上是在买一篮子规则。仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
        ),
        VideoSpec(
            slug="portfolio_role",
            title="中证红利在组合里像什么角色？",
            subtitle="它更像一个稳定器，而不是全部答案。",
            chart_type="role",
            scenes=[
                "它偏防守、偏现金流、偏价值风格，适合承担卫星配置或风格补充。",
                "它可以和宽基指数、成长风格指数、海外指数搭配。",
                "它不适合作为唯一核心仓位，因为单一风格会有阶段性跑输。",
                "组合思维的关键，是让每个指数承担清楚的角色。",
            ],
            script="第三条，我们不问中证红利能不能涨，而是问它在组合里扮演什么角色。它更像偏防守、偏现金流、偏价值风格的卫星配置，适合给组合补充红利和低估值暴露。它可以和沪深三百、中证五百、创业板、海外指数搭配，减少单一风格带来的波动。但它不适合作为唯一核心仓位。因为红利风格也会有阶段性跑输，尤其在成长风格很强的时候。真正有用的配置，不是把所有钱押在一个指数上，而是让每个指数承担清楚的任务。仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
        ),
        VideoSpec(
            slug="risk_drawdown",
            title="买中证红利前，先看懂这几个风险",
            subtitle="红利不等于无波动，高股息也不等于稳赚。",
            chart_type="risk",
            scenes=[
                "第一，行业可能集中，少数行业表现会影响指数。",
                "第二，红利风格也会跑输成长风格，不是每个阶段都占优。",
                "第三，分红能力会变化，高股息有时也可能来自股价下跌。",
                "看风险，是为了知道自己能不能长期拿得住。",
            ],
            script="第四条，我们专门讲风险。中证红利的第一个风险，是行业可能集中。银行、煤炭、公用事业这些板块如果阶段性走弱，指数体验也会受影响。第二个风险，是红利风格并不是永远占优。当市场偏好成长和科技时，红利指数可能阶段性跑输。第三个风险，是高股息不等于稳赚。有些高股息来自稳定分红，也有些可能来自股价下跌后股息率被动抬高。所以看中证红利，既要看分红，也要看基本面和估值。风险讲清楚，才有可能长期拿得住。仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
        ),
        VideoSpec(
            slug="valuation_view",
            title="中证红利贵不贵？估值应该怎么看？",
            subtitle="估值是仪表盘，不是短期预测器。",
            chart_type="gauge",
            scenes=[
                "可以看 PE、PB、股息率、估值分位，最好结合历史区间一起看。",
                "红利指数尤其要关注股息率和分红可持续性。",
                "估值低不代表马上上涨，估值高也不代表立刻下跌。",
                "它的作用是帮助理解性价比和风险补偿。",
            ],
            script="最后一条，我们看中证红利的估值。判断它贵不贵，不能只看一个数字。可以同时看市盈率、市净率、股息率和估值分位，再和自己的历史区间做对比。对红利指数来说，股息率很重要，但也不能只看股息率，还要看分红是否可持续，行业基本面是否稳定。估值低，不代表马上会上涨；估值高，也不代表立刻会下跌。估值更像仪表盘，它帮助我们理解性价比和风险补偿，但不能预测短期行情。到这里，中证红利五条内容就完整了：认识、成分、角色、风险、估值。仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
        ),
    ]


def main() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("需要 ffmpeg 和 ffprobe。")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    outputs = []
    for episode, spec in enumerate(build_specs(), start=1):
        print(f"Rendering {episode}/5: {spec.title}")
        outputs.append(str(render_video(spec, episode)))
    (OUT_ROOT / "series_manifest.json").write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done: {OUT_ROOT}")


if __name__ == "__main__":
    main()
