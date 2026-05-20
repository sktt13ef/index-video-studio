from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.compliance_check import check_text_compliance
from src.data_validation import validate_episode_payload
from src.script_templates import load_template_group, render_episode_draft, render_five_episode_drafts, resolve_script_template_key
from src.visual_engine.card_layout import render_body_card, render_cover
from src.visual_engine.theme_loader import get_canvas, get_font_spec, get_theme, load_theme_config, resolve_theme_key
from src.visual_engine.visual_quality_check import check_visual_asset, write_visual_report


ROOT = Path(__file__).resolve().parent
GLOBAL50_DIR = ROOT / "data" / "global50"
PLAN_PATH = GLOBAL50_DIR / "global50_plan.csv"
PROFILE_DIR = GLOBAL50_DIR / "profiles"
RUNS_DIR = ROOT / "runs"
SCRIPT_VERSION = "global50_dry_run_v1"
RENDER_VERSION = "visual_theme_v2_light"
EPISODE_SLUGS = [
    "01_index_intro",
    "02_holdings_breakdown",
    "03_portfolio_role",
    "04_return_drawdown_risk",
    "05_valuation_view",
]


@dataclass
class EpisodeBuild:
    index_id: str
    episode_number: int
    slug: str
    title: str
    output_dir: Path
    data_status: str
    review_status: str
    missing_items: list[str]
    compliance: dict[str, Any]
    data_validation: dict[str, Any]
    visual_checks: list[dict[str, Any]]
    ready: bool


def read_plan(path: Path = PLAN_PATH) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_plan(rows: list[dict[str, Any]], path: Path) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_profile(index_id: str) -> dict[str, Any]:
    path = PROFILE_DIR / f"{index_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"profile not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def data_date_text(profile: dict[str, Any]) -> str:
    value = profile.get("data_date")
    if isinstance(value, dict):
        return str(value.get("production_data") or value.get("catalog_data") or "not_collected")
    return str(value or "not_collected")


def source_items(profile: dict[str, Any]) -> list[dict[str, Any]]:
    date_text = data_date_text(profile)
    normalized: list[dict[str, Any]] = []
    for item in profile.get("source_items") or []:
        normalized.append(
            {
                "source_id": item.get("source_id") or item.get("id") or "unknown_source",
                "source_type": item.get("source_type") or item.get("type") or "unknown",
                "title": item.get("title") or item.get("source_id") or "source",
                "url": item.get("url"),
                "file": item.get("file") or item.get("path"),
                "data_date": item.get("data_date") or date_text,
                "fields": item.get("fields") or item.get("fields_used") or [],
                "calculation_method": item.get("calculation_method"),
                "human_confirmed": bool(item.get("human_confirmed", False)),
                "allowed_for_final_numbers": bool(item.get("allowed_for_final_numbers", True)),
            }
        )
    return normalized


def basic_info(profile: dict[str, Any], plan_row: dict[str, str]) -> dict[str, str]:
    basic = profile.get("basic_info") or {}
    return {
        "index_id": str(profile.get("index_id") or plan_row.get("index_id") or ""),
        "index_name": str(basic.get("index_name_cn") or plan_row.get("index_name_cn") or basic.get("index_name_en") or ""),
        "index_name_en": str(basic.get("index_name_en") or plan_row.get("index_name_en") or ""),
        "index_code": str(basic.get("index_code") or plan_row.get("index_code") or ""),
        "provider": str(basic.get("provider") or plan_row.get("provider") or ""),
        "region": str(basic.get("region") or plan_row.get("region") or ""),
        "market": str(basic.get("market") or plan_row.get("market") or ""),
        "currency": str(basic.get("currency") or plan_row.get("currency") or ""),
        "index_type": str(basic.get("index_type") or plan_row.get("index_type") or ""),
        "template_type": str(basic.get("template_type") or plan_row.get("template_type") or ""),
        "style_theme": str(basic.get("style_theme") or plan_row.get("style_theme") or ""),
    }


def profile_section_ready(profile: dict[str, Any], section: str) -> bool:
    if section == "basic_info":
        basic = profile.get("basic_info") or {}
        return bool(basic.get("index_name_cn") or basic.get("index_name_en")) and bool(basic.get("index_code")) and bool(basic.get("index_type"))
    value = profile.get(section)
    if not value:
        return False
    if isinstance(value, dict):
        status = str(value.get("status", "")).lower()
        if status in {"missing", "needs_data", "needs_review", "needs_official_methodology", "catalog_draft_needs_review"}:
            return False
        if "items" in value and not value.get("items"):
            return False
    return True


def missing_for_episode(profile: dict[str, Any], required_data: list[str], plan_row: dict[str, str]) -> list[str]:
    missing = list(profile.get("missing_items") or [])
    for key in required_data:
        if not profile_section_ready(profile, key) and key not in missing:
            missing.append(key)
    if plan_row.get("data_status") != "ready" and "plan_data_status_not_ready" not in missing:
        missing.append("plan_data_status_not_ready")
    return missing


def number_source_id(sources: list[dict[str, Any]]) -> str:
    return str((sources[0] or {}).get("source_id")) if sources else "unknown_source"


def data_number(
    *,
    label: str,
    value: Any,
    category: str,
    source: dict[str, Any] | None,
    source_field: str,
    calculation_method: str,
    sample_range: str | None = None,
    calculation_range: str | None = None,
    display_context: str | None = None,
) -> dict[str, Any]:
    source = source or {}
    return {
        "label": str(label),
        "value": str(value),
        "category": category,
        "source_field": source_field,
        "source_id": str(source.get("source_id") or "unknown_source"),
        "source_url": source.get("url"),
        "source_file": source.get("file"),
        "data_date": str(source.get("data_date") or "not_collected"),
        "calculation_method": calculation_method,
        "human_confirmed": bool(source.get("human_confirmed", False)),
        "display_context": display_context,
        "sample_range": sample_range,
        "calculation_range": calculation_range,
    }


def extract_numbers(profile: dict[str, Any], episode_slug: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = sources[0] if sources else None
    numbers: list[dict[str, Any]] = []
    if episode_slug == "02_holdings_breakdown":
        for item in (profile.get("sector_weights") or {}).get("items") or []:
            label = item.get("name") or item.get("sector") or item.get("label")
            value = item.get("weight") or item.get("value")
            if label and value is not None:
                numbers.append(
                    data_number(
                        label=label,
                        value=value,
                        category="sector_weight",
                        source=source,
                        source_field="sector_weights.items.weight",
                        calculation_method="official_or_structured_profile_field",
                        display_context="industry weight preview",
                    )
                )
        for item in (profile.get("top_holdings") or {}).get("items") or []:
            label = item.get("name") or item.get("holding") or item.get("label")
            value = item.get("weight") or item.get("value")
            if label and value is not None:
                numbers.append(
                    data_number(
                        label=label,
                        value=value,
                        category="holding_weight",
                        source=source,
                        source_field="top_holdings.items.weight",
                        calculation_method="official_or_structured_profile_field",
                        display_context="top holding weight preview",
                    )
                )
    if episode_slug == "04_return_drawdown_risk":
        for item in (profile.get("historical_returns") or {}).get("items") or []:
            label = item.get("label") or item.get("period") or "historical return"
            value = item.get("return") or item.get("value")
            if value is not None:
                numbers.append(
                    data_number(
                        label=label,
                        value=value,
                        category="historical_return",
                        source=source,
                        source_field="historical_returns.items.return",
                        calculation_method=item.get("calculation_method") or "calculated_from_historical_price_series",
                        sample_range=item.get("sample_range") or item.get("range"),
                    )
                )
        for item in (profile.get("drawdown_stats") or {}).get("items") or []:
            label = item.get("label") or "max drawdown"
            value = item.get("max_drawdown") or item.get("value")
            if value is not None:
                numbers.append(
                    data_number(
                        label=label,
                        value=value,
                        category="max_drawdown",
                        source=source,
                        source_field="drawdown_stats.items.max_drawdown",
                        calculation_method=item.get("calculation_method") or "calculated_from_historical_price_series",
                        calculation_range=item.get("calculation_range") or item.get("range"),
                    )
                )
    if episode_slug == "05_valuation_view":
        metrics = profile.get("valuation_metrics") or {}
        metric_items = metrics.get("items") if isinstance(metrics, dict) else None
        if isinstance(metric_items, list):
            for item in metric_items:
                label = item.get("label") or item.get("name") or item.get("metric")
                value = item.get("value")
                category = str(item.get("category") or item.get("metric") or "valuation_range")
                if label and value is not None:
                    numbers.append(
                        data_number(
                            label=label,
                            value=value,
                            category=category,
                            source=source,
                            source_field=f"valuation_metrics.items.{label}",
                            calculation_method=item.get("calculation_method") or "official_or_structured_profile_field",
                        )
                    )
        elif isinstance(metrics, dict):
            for key, category in [("pe", "pe"), ("pb", "pb"), ("dividend_yield", "dividend_yield"), ("valuation_percentile", "valuation_percentile"), ("valuation_range", "valuation_range")]:
                value = metrics.get(key)
                if value not in (None, "", [], {}):
                    numbers.append(
                        data_number(
                            label=key,
                            value=value,
                            category=category,
                            source=source,
                            source_field=f"valuation_metrics.{key}",
                            calculation_method=str(metrics.get("calculation_method") or "official_or_structured_profile_field"),
                        )
                    )
    return numbers


def features_for_episode(required_data: list[str], slug: str) -> dict[str, bool]:
    return {
        "sector_weights": "sector_weights" in required_data,
        "top_holdings": "top_holdings" in required_data,
        "valuation_metrics": "valuation_metrics" in required_data,
        "max_drawdown": "drawdown_stats" in required_data or slug == "04_return_drawdown_risk",
        "historical_returns": "historical_returns" in required_data or slug == "04_return_drawdown_risk",
    }


def build_data_used(profile: dict[str, Any], draft: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "index_id": str(profile.get("index_id", "")),
        "episode": int(draft["episode"]),
        "episode_slug": draft["slug"],
        "data_date": data_date_text(profile),
        "source_items": sources,
        "numbers": extract_numbers(profile, draft["slug"], sources),
    }


def storyboard_points(profile: dict[str, Any], draft: dict[str, Any], missing: list[str]) -> list[str]:
    cards = [str(item) for item in draft.get("visual_cards") or []]
    if missing:
        cards = cards[:2] + ["数据来源与口径卡"]
    return cards[:5] or ["标题卡", "信息卡", "风险提示卡"]


def positioning_text(profile: dict[str, Any], info: dict[str, str]) -> str:
    basic = profile.get("basic_info") or {}
    focus = str(basic.get("catalog_focus") or "").strip()
    if focus:
        if focus.endswith("观察"):
            return focus
        return f"{focus}观察"
    role = profile.get("role_in_portfolio") or {}
    summary = str(role.get("summary") or "").strip()
    if summary:
        summary = summary.replace("暴露", "观察").replace("资产观察观察", "资产观察")
        return summary
    return str(f"{info['region']}指数观察")


def cover_series_name(theme_key: str, theme_label: str) -> str:
    mapping = {
        "china_broad": "A股指数观察",
        "china_dividend": "红利指数观察",
        "hongkong": "港股指数观察",
        "us_broad": "美股指数观察",
        "us_technology": "科技指数观察",
        "europe": "欧洲指数观察",
        "japan": "日本指数观察",
        "india": "印度指数观察",
        "global": "全球指数观察",
        "low_volatility": "策略指数观察",
    }
    return mapping.get(theme_key, theme_label)


def write_script(path: Path, draft: dict[str, Any], missing: list[str]) -> None:
    missing_text = "\n".join(f"- {item}" for item in missing) if missing else "- 无"
    text = f"""# {draft['title']}

## 主题
{draft.get('single_theme', '')}

## 解说词草稿
{draft['script']}

## 风险点
{draft.get('risk_point', '')}

## 需要的数据
{chr(10).join(f"- {item}" for item in draft.get('required_data') or [])}

## 待审核项
{missing_text}
"""
    path.write_text(text, encoding="utf-8")


def write_episode_quality_report(path: Path, episode: EpisodeBuild) -> None:
    visual_rows = []
    for item in episode.visual_checks:
        visual_rows.append(
            f"<tr><td>{'PASS' if item['passed'] else 'FAIL'}</td><td>{Path(item['image']).name}</td><td>{'<br>'.join(item['errors']) or '-'}</td><td>{'<br>'.join(item['warnings']) or '-'}</td></tr>"
        )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{episode.title} Quality Report</title>
  <style>
    body {{ font-family: Arial, 'Microsoft YaHei', sans-serif; margin: 28px; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 14px; }}
    th, td {{ border: 1px solid #d8dee7; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f2f4f7; }}
    .fail {{ color: #a33; font-weight: 700; }}
    .pass {{ color: #28734f; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>{episode.title}</h1>
  <p class="{'pass' if episode.ready else 'fail'}">Ready: {episode.ready}</p>
  <h2>缺失项</h2>
  <p>{'<br>'.join(episode.missing_items) if episode.missing_items else '-'}</p>
  <h2>合规检查</h2>
  <p>{'通过' if episode.compliance.get('passed') else '未通过'}：{'; '.join(episode.compliance.get('errors') or []) or '-'}</p>
  <h2>数据检查</h2>
  <p>{'通过' if episode.data_validation.get('passed') else '未通过'}：{'; '.join(episode.data_validation.get('errors') or []) or '-'}</p>
  <h2>视觉检查</h2>
  <table><thead><tr><th>状态</th><th>图片</th><th>问题</th><th>提醒</th></tr></thead><tbody>{''.join(visual_rows)}</tbody></table>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")


def render_episode_preview(
    *,
    run_dir: Path,
    index_dir: Path,
    profile: dict[str, Any],
    plan_row: dict[str, str],
    draft: dict[str, Any],
    force: bool,
) -> EpisodeBuild:
    info = basic_info(profile, plan_row)
    episode_number = int(draft["episode"])
    episode_dir = index_dir / f"episode_{episode_number:02d}"
    if episode_dir.exists() and force:
        shutil.rmtree(episode_dir)
    episode_dir.mkdir(parents=True, exist_ok=True)

    missing = missing_for_episode(profile, list(draft.get("required_data") or []), plan_row)
    sources = source_items(profile)
    data_used = build_data_used(profile, draft, sources)
    write_json(episode_dir / "data_used.json", data_used)
    write_script(episode_dir / "script.md", draft, missing)

    storyboard = {
        "index_id": info["index_id"],
        "episode": episode_number,
        "slug": draft["slug"],
        "title": draft["title"],
        "single_theme": draft.get("single_theme"),
        "cards": [
            {
                "card_id": "cover",
                "type": "cover",
                "text": [info["index_name"], positioning_text(profile, info)],
            },
            {
                "card_id": "body_01",
                "type": "body_card",
                "title": draft["title"],
                "points": storyboard_points(profile, draft, missing),
            },
        ],
        "subtitle_policy": {
            "reserved_top": 1460,
            "no_overlap_required": True,
        },
    }
    write_json(episode_dir / "storyboard.json", storyboard)

    config = load_theme_config()
    theme_key = resolve_theme_key(
        region=info["region"],
        index_type=info["index_type"],
        template_type=info["template_type"],
        style_theme=info["style_theme"],
    )
    theme = get_theme(theme_key, config)
    canvas = get_canvas(config)
    font_spec = get_font_spec(config)
    render_cover(
        episode_dir / "cover.png",
        theme=theme,
        index_name=info["index_name"],
        positioning=positioning_text(profile, info),
        series_name=cover_series_name(theme.key, theme.label),
        canvas=canvas,
        font_spec=font_spec,
    )
    render_body_card(
        episode_dir / "card_preview_01.png",
        theme=theme,
        title=draft["title"],
        subtitle=str(draft.get("single_theme") or "只讲一个主题。"),
        section_title="本条画面重点",
        points=storyboard_points(profile, draft, missing),
        episode=f"{episode_number}/5",
        source_note="仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。",
        canvas=canvas,
        font_spec=font_spec,
    )

    visual_checks = [
        check_visual_asset(episode_dir / "cover.png"),
        check_visual_asset(episode_dir / "card_preview_01.png"),
    ]
    write_visual_report(visual_checks, episode_dir / "visual_quality_report.html")

    visual_text = [draft["title"], draft.get("single_theme"), draft.get("risk_point"), *storyboard_points(profile, draft, missing)]
    compliance = check_text_compliance(script=draft["script"], visual_text=[str(item) for item in visual_text]).to_dict()
    validation_payload = {
        "metadata": {
            "index_name": info["index_name"],
            "index_code": info["index_code"],
            "index_type": info["index_type"],
            "data_date": data_date_text(profile),
            "source_items": sources,
        },
        "data_used": data_used,
        "features": features_for_episode(list(draft.get("required_data") or []), draft["slug"]),
        "visual_text": visual_text,
    }
    data_validation_result = validate_episode_payload(validation_payload).to_dict()
    if missing:
        data_validation_result["passed"] = False
        data_validation_result.setdefault("errors", []).extend([f"待补齐数据: {item}" for item in missing])

    ready = (
        plan_row.get("data_status") == "ready"
        and plan_row.get("review_status") == "approved"
        and not missing
        and compliance.get("passed")
        and data_validation_result.get("passed")
        and all(item["passed"] for item in visual_checks)
    )

    try:
        resolved_template_type = resolve_script_template_key(info["index_type"], info["template_type"])
    except ValueError:
        resolved_template_type = "broad_based"

    manifest = {
        "index_id": info["index_id"],
        "index_name": info["index_name"],
        "index_code": info["index_code"],
        "region": info["region"],
        "index_type": info["index_type"],
        "template_type": resolved_template_type,
        "style_theme": theme.key,
        "data_date": data_date_text(profile),
        "source_items": sources,
        "episode": episode_number,
        "episode_slug": draft["slug"],
        "title": draft["title"],
        "script_version": SCRIPT_VERSION,
        "render_version": RENDER_VERSION,
        "dry_run": True,
        "review_status": plan_row.get("review_status") or "pending",
        "compliance_check_result": compliance,
        "data_validation_result": data_validation_result,
        "quality_check_result": {
            "passed": all(item["passed"] for item in visual_checks),
            "visual_checks": visual_checks,
            "audio_checked": False,
            "video_checked": False,
        },
        "ready": ready,
        "missing_items": missing,
    }
    write_json(episode_dir / "manifest.json", manifest)

    episode = EpisodeBuild(
        index_id=info["index_id"],
        episode_number=episode_number,
        slug=draft["slug"],
        title=draft["title"],
        output_dir=episode_dir,
        data_status=plan_row.get("data_status") or "needs_data",
        review_status=plan_row.get("review_status") or "pending",
        missing_items=missing,
        compliance=compliance,
        data_validation=data_validation_result,
        visual_checks=visual_checks,
        ready=ready,
    )
    write_episode_quality_report(episode_dir / "quality_report.html", episode)
    return episode


def render_index_dry_run(
    *,
    run_dir: Path,
    plan_row: dict[str, str],
    episode_filter: int | None,
    force: bool,
) -> dict[str, Any]:
    profile = load_profile(plan_row["index_id"])
    info = basic_info(profile, plan_row)
    index_dir = run_dir / info["index_id"]
    if index_dir.exists() and force:
        shutil.rmtree(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    write_json(index_dir / "profile.json", profile)

    template_fallback: str | None = None
    try:
        drafts = render_five_episode_drafts(profile)
    except ValueError as exc:
        template_fallback = str(exc)
        fallback_profile = json.loads(json.dumps(profile, ensure_ascii=False))
        fallback_profile.setdefault("basic_info", {})
        fallback_profile["basic_info"]["template_type"] = "broad_based"
        fallback_profile["basic_info"]["index_type"] = "broad_based"
        context = {
            "index_id": info["index_id"],
            "index_name": info["index_name"],
            "index_name_en": info["index_name_en"],
            "index_code": info["index_code"],
            "provider": info["provider"],
            "region": info["region"],
            "market": info["market"] or info["region"],
            "currency": info["currency"],
            "index_type": info["index_type"],
            "template_type": info["template_type"],
            "role_summary": positioning_text(profile, info),
        }
        drafts = [render_episode_draft(episode, context) for episode in load_template_group("broad_based")["episodes"]]
    if episode_filter:
        drafts = [draft for draft in drafts if int(draft["episode"]) == episode_filter]

    episodes = [
        render_episode_preview(
            run_dir=run_dir,
            index_dir=index_dir,
            profile=profile,
            plan_row=plan_row,
            draft=draft,
            force=force,
        )
        for draft in drafts
    ]
    ready = all(ep.ready for ep in episodes) if episodes else False
    index_manifest = {
        "index_id": info["index_id"],
        "index_name": info["index_name"],
        "index_code": info["index_code"],
        "region": info["region"],
        "index_type": info["index_type"],
        "data_status": plan_row.get("data_status"),
        "review_status": plan_row.get("review_status") or "pending",
        "ready": ready,
        "template_fallback": template_fallback,
        "episode_count": len(episodes),
        "missing_items": sorted({item for episode in episodes for item in episode.missing_items} | ({f"template_fallback: {template_fallback}"} if template_fallback else set())),
        "episodes": [
            {
                "episode": episode.episode_number,
                "slug": episode.slug,
                "title": episode.title,
                "ready": episode.ready,
                "path": str(episode.output_dir.relative_to(run_dir)),
            }
            for episode in episodes
        ],
    }
    write_json(index_dir / "index_manifest.json", index_manifest)
    return index_manifest


def make_review_html(run_dir: Path, index_manifests: list[dict[str, Any]]) -> None:
    cards: list[str] = []
    for item in index_manifests:
        index_id = item["index_id"]
        missing = "<br>".join(item.get("missing_items") or []) or "-"
        episode_rows = []
        preview_blocks = []
        for ep in item.get("episodes") or []:
            ep_dir = Path(ep["path"])
            script_path = run_dir / ep_dir / "script.md"
            script = script_path.read_text(encoding="utf-8") if script_path.exists() else ""
            script_preview = script.split("## 解说词草稿", 1)[-1].strip().split("## 风险点", 1)[0].strip()[:260]
            episode_rows.append(f"<li>{ep['episode']}. {ep['title']} - {'ready' if ep['ready'] else 'needs_review'}</li>")
            preview_blocks.append(
                f"""
                <details>
                  <summary>{ep['episode']} - {ep['title']}</summary>
                  <p>{script_preview}</p>
                  <div class="images">
                    <img src="{ep_dir.as_posix()}/cover.png" alt="cover">
                    <img src="{ep_dir.as_posix()}/card_preview_01.png" alt="card preview">
                  </div>
                  <p><a href="{ep_dir.as_posix()}/manifest.json">manifest.json</a> · <a href="{ep_dir.as_posix()}/data_used.json">data_used.json</a> · <a href="{ep_dir.as_posix()}/quality_report.html">quality_report.html</a></p>
                </details>
                """
            )
        cards.append(
            f"""
            <section class="index-card">
              <header>
                <h2>{item['index_name']} <span>{item['index_code']}</span></h2>
                <p>{item['region']} / {item['index_type']} / data: {item.get('data_status')} / review: {item.get('review_status')}</p>
                <strong class="{'ready' if item.get('ready') else 'blocked'}">{'READY' if item.get('ready') else 'NEEDS REVIEW'}</strong>
              </header>
              <h3>5条视频标题</h3>
              <ol>{''.join(episode_rows)}</ol>
              <h3>缺失项</h3>
              <p>{missing}</p>
              <h3>预览</h3>
              {''.join(preview_blocks)}
            </section>
            """
        )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Global50 Batch Review</title>
  <style>
    body {{ margin: 28px; font-family: Arial, 'Microsoft YaHei', sans-serif; background: #f6f8fb; color: #111827; }}
    h1 {{ margin: 0 0 8px; }}
    .summary {{ margin-bottom: 24px; color: #5f6d78; }}
    .index-card {{ background: #fff; border: 1px solid #d8e2ec; border-radius: 8px; padding: 18px; margin-bottom: 18px; }}
    header {{ display: flex; align-items: start; justify-content: space-between; gap: 16px; border-bottom: 1px solid #e5ebf2; padding-bottom: 12px; }}
    h2 {{ margin: 0; font-size: 24px; }}
    h2 span {{ color: #667085; font-size: 16px; }}
    h3 {{ margin: 16px 0 8px; font-size: 16px; }}
    p, li {{ line-height: 1.55; }}
    .ready {{ color: #28734f; }}
    .blocked {{ color: #a15d30; }}
    details {{ border-top: 1px solid #edf1f5; padding: 10px 0; }}
    summary {{ cursor: pointer; font-weight: 700; }}
    .images {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    img {{ width: 180px; border: 1px solid #d8e2ec; border-radius: 6px; background: white; }}
    a {{ color: #315d8c; }}
  </style>
</head>
<body>
  <h1>Global50 Batch Review</h1>
  <p class="summary">dry_run 只生成审核材料，不生成配音、字幕或 final.mp4。READY 需要 data_status=ready 且 review_status=approved。</p>
  {''.join(cards)}
</body>
</html>"""
    (run_dir / "batch_review.html").write_text(html, encoding="utf-8")


def make_batch_manifest(run_dir: Path, index_manifests: list[dict[str, Any]], mode: str) -> None:
    payload = {
        "mode": mode,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "index_count": len(index_manifests),
        "episode_count": sum(len(item.get("episodes") or []) for item in index_manifests),
        "ready_index_count": sum(1 for item in index_manifests if item.get("ready")),
        "script_version": SCRIPT_VERSION,
        "render_version": RENDER_VERSION,
        "indexes": index_manifests,
    }
    write_json(run_dir / "batch_manifest.json", payload)


def select_rows(rows: list[dict[str, str]], index_id: str | None) -> list[dict[str, str]]:
    if not index_id:
        return rows
    wanted = index_id.strip().lower()
    return [row for row in rows if row.get("index_id", "").lower() == wanted]


def create_run_dir(prefix: str = "global50_dry_run") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = RUNS_DIR / f"{prefix}_{timestamp}"
    for index in range(100):
        candidate = base if index == 0 else RUNS_DIR / f"{prefix}_{timestamp}_{index:02d}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError("无法创建唯一输出目录")


def render_dry_run(args: argparse.Namespace, mode: str = "dry_run") -> Path:
    run_dir = create_run_dir()

    rows = read_plan()
    rows = select_rows(rows, args.index)
    if args.render_sample:
        grouped: dict[tuple[str, str], dict[str, str]] = {}
        for row in rows:
            key = (row.get("region", ""), row.get("index_type", ""))
            grouped.setdefault(key, row)
        rows = list(grouped.values())[: int(args.render_sample)]
    if not rows:
        raise SystemExit("没有匹配的指数")

    output_rows: list[dict[str, Any]] = []
    index_manifests: list[dict[str, Any]] = []
    for row in rows:
        review_status = row.get("review_status") or "pending"
        out_row = dict(row)
        out_row["review_status"] = review_status
        out_row["dry_run_status"] = "pending"
        try:
            manifest = render_index_dry_run(run_dir=run_dir, plan_row=out_row, episode_filter=args.episode, force=args.force)
            out_row["dry_run_status"] = "ready" if manifest["ready"] else "needs_review"
            out_row["review_missing_items"] = "; ".join(manifest.get("missing_items") or [])
            index_manifests.append(manifest)
        except Exception as exc:
            out_row["dry_run_status"] = "failed"
            out_row["review_missing_items"] = str(exc)
        output_rows.append(out_row)

    write_plan(output_rows, run_dir / "global50_plan.csv")
    make_review_html(run_dir, index_manifests)
    make_batch_manifest(run_dir, index_manifests, mode)
    return run_dir


def guarded_render_message(args: argparse.Namespace, mode: str) -> Path:
    run_dir = render_dry_run(args, mode=mode)
    notice = {
        "mode": mode,
        "status": "guarded",
        "message": "本阶段先生成审核材料。完整视频生成需要 data_status=ready 且 review_status=approved 后再执行。",
        "run_dir": str(run_dir),
    }
    write_json(run_dir / "render_guard.json", notice)
    return run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Global50 index video dry-run and review workflow")
    parser.add_argument("--dry-run", action="store_true", help="Generate review materials only")
    parser.add_argument("--render-sample", type=int, help="Prepare sample review set from different regions/types")
    parser.add_argument("--render-ready", action="store_true", help="Guarded command for approved ready batch rendering")
    parser.add_argument("--index", help="Only process one index_id")
    parser.add_argument("--episode", type=int, choices=[1, 2, 3, 4, 5], help="Only process one episode")
    parser.add_argument("--resume", action="store_true", help="Reserved for later full rendering; dry-run creates a fresh review run")
    parser.add_argument("--force", action="store_true", help="Overwrite per-index files inside the current generated run")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not (args.dry_run or args.render_sample or args.render_ready):
        args.dry_run = True

    if args.render_ready:
        run_dir = guarded_render_message(args, mode="render_ready_guard")
    elif args.render_sample:
        run_dir = guarded_render_message(args, mode=f"render_sample_{args.render_sample}_guard")
    else:
        run_dir = render_dry_run(args)
    print(json.dumps({"output_dir": str(run_dir), "batch_review": str(run_dir / "batch_review.html")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
