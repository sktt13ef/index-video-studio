from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.visual_engine.card_layout import render_theme_pair
from src.visual_engine.visual_quality_check import check_visual_asset, write_visual_report


ROOT = Path(__file__).resolve().parent


SAMPLES = {
    "china_broad": {
        "index_name": "沪深300",
        "positioning": "A股大盘核心资产观察",
        "series_name": "A股指数观察",
        "title": "沪深300跟踪什么？",
        "subtitle": "先看覆盖范围，再看权重结构。",
        "section_title": "这条只看范围",
        "points": ["覆盖沪深两市头部公司", "偏大盘，不代表小盘股", "样本会按规则调整", "看指数，不看单只股票"],
        "episode": "1/5",
        "source_note": "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
    },
    "china_dividend": {
        "index_name": "中证红利",
        "positioning": "红利与现金流风格观察",
        "series_name": "红利指数观察",
        "title": "红利指数先看什么？",
        "subtitle": "核心不是高股息一个数字。",
        "section_title": "三件事要分开看",
        "points": ["看分红规则是否稳定", "看行业集中度", "看股息率来源", "看红利风格失效阶段"],
        "episode": "1/5",
        "source_note": "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
    },
    "hongkong": {
        "index_name": "恒生指数",
        "positioning": "港股核心资产观察",
        "series_name": "港股指数观察",
        "title": "恒生指数看什么？",
        "subtitle": "港股权重结构和A股不同。",
        "section_title": "先看市场特征",
        "points": ["覆盖香港市场代表公司", "注意币种和交易时段", "看权重行业变化", "不把它等同于A股"],
        "episode": "1/5",
        "source_note": "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
    },
    "us_broad": {
        "index_name": "标普500",
        "positioning": "美股大盘代表性观察",
        "series_name": "美股指数观察",
        "title": "标普500代表什么？",
        "subtitle": "看美国大盘，也要看权重。",
        "section_title": "三个观察入口",
        "points": ["覆盖美国主要大盘公司", "科技权重影响明显", "美元资产会受汇率影响", "估值要和盈利一起看"],
        "episode": "1/5",
        "source_note": "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
    },
    "us_technology": {
        "index_name": "纳斯达克100",
        "positioning": "科技成长资产观察",
        "series_name": "科技指数观察",
        "title": "纳指100怎么看？",
        "subtitle": "科技暴露强，波动也要单独看。",
        "section_title": "不要只看涨幅",
        "points": ["看龙头集中度", "看盈利兑现速度", "看估值波动", "看技术周期和回撤"],
        "episode": "1/5",
        "source_note": "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
    },
    "europe": {
        "index_name": "德国DAX",
        "positioning": "欧洲核心市场观察",
        "series_name": "欧洲指数观察",
        "title": "DAX指数看什么？",
        "subtitle": "它反映的是德国代表公司组合。",
        "section_title": "观察重点",
        "points": ["看出口和工业暴露", "看欧洲利率环境", "看成分股集中度", "看欧元汇率影响"],
        "episode": "1/5",
        "source_note": "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
    },
    "japan": {
        "index_name": "日经225",
        "positioning": "日本蓝筹市场观察",
        "series_name": "日本指数观察",
        "title": "日经225看什么？",
        "subtitle": "日本市场要把行业和汇率分开看。",
        "section_title": "三个拆解角度",
        "points": ["看制造业和出口暴露", "看日元汇率影响", "看权重编制方式", "看长期波动区间"],
        "episode": "1/5",
        "source_note": "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
    },
    "low_volatility": {
        "index_name": "低波动策略",
        "positioning": "波动筛选规则观察",
        "series_name": "策略指数观察",
        "title": "低波动指数看什么？",
        "subtitle": "波动筛选不等于没有回撤。",
        "section_title": "先看规则边界",
        "points": ["看筛选周期和样本池", "看行业偏向", "看失效阶段", "看回撤是否可承受"],
        "episode": "1/5",
        "source_note": "仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
    },
}


def write_index_html(output_dir: Path, results: list[dict]) -> None:
    cards = []
    for result in results:
        img = Path(result["image"]).name
        status = "通过" if result["passed"] else "失败"
        errors = "；".join(result["errors"]) if result["errors"] else "无"
        warnings = "；".join(result["warnings"]) if result["warnings"] else "无"
        cards.append(
            f"""
            <article>
              <img src="{img}" alt="{img}">
              <h2>{img}</h2>
              <p><strong>{status}</strong></p>
              <p>问题：{errors}</p>
              <p>提醒：{warnings}</p>
            </article>
            """
        )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Global Index Visual Theme Samples</title>
  <style>
    body {{ margin: 24px; font-family: Arial, 'Microsoft YaHei', sans-serif; background: #f4f6f8; color: #111827; }}
    main {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; }}
    article {{ background: white; border: 1px solid #d8dee7; border-radius: 8px; padding: 12px; }}
    img {{ width: 100%; border-radius: 6px; border: 1px solid #e5e7eb; }}
    h1 {{ margin: 0 0 8px; }}
    h2 {{ font-size: 15px; margin: 10px 0 6px; }}
    p {{ font-size: 13px; line-height: 1.45; margin: 4px 0; }}
  </style>
</head>
<body>
  <h1>Global Index Visual Theme Samples</h1>
  <p>8 张封面和 8 张正文卡，供人工确认。这里只生成静态视觉样例，不生成视频。</p>
  <main>{''.join(cards)}</main>
</body>
</html>"""
    (output_dir / "visual_samples_report.html").write_text(html, encoding="utf-8")


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ROOT / "runs" / f"visual_theme_samples_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=False)

    generated: list[Path] = []
    for theme_key, sample in SAMPLES.items():
        cover, card = render_theme_pair(output_dir, theme_key, sample)
        generated.extend([cover, card])

    results = [check_visual_asset(path) for path in generated]
    write_visual_report(results, output_dir / "visual_quality_report.html")
    write_index_html(output_dir, results)
    (output_dir / "sample_manifest.json").write_text(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "cover_count": 8,
                "body_card_count": 8,
                "passed": all(item["passed"] for item in results),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"output_dir": str(output_dir), "passed": all(item["passed"] for item in results)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
