from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "data" / "global_index_catalog_500.csv"
GLOBAL50_DIR = ROOT / "data" / "global50"
GLOBAL100_DIR = ROOT / "data" / "global100"
PROFILES_DIR = GLOBAL100_DIR / "profiles"
SOURCES_DIR = GLOBAL100_DIR / "sources"
RUNS_DIR = ROOT / "runs"

PLAN_COLUMNS = [
    "index_id",
    "index_name_cn",
    "index_name_en",
    "index_code",
    "provider",
    "region",
    "market",
    "index_type",
    "currency",
    "template_type",
    "style_theme",
    "priority",
    "data_status",
    "render_status",
    "notes",
    "review_status",
]

KNOWN_EN_NAMES = {
    "SPX": "S&P 500",
    "NDX": "Nasdaq-100",
    "DJI": "Dow Jones Industrial Average",
    "RUT": "Russell 2000",
    "HSI": "Hang Seng Index",
    "HSTECH": "Hang Seng TECH Index",
    "CSI300": "CSI 300",
    "CSI500": "CSI 500",
    "CSI1000": "CSI 1000",
    "CSI_DIV": "CSI Dividend Index",
    "N225": "Nikkei 225",
    "TOPIX": "TOPIX",
    "KOSPI": "KOSPI Composite Index",
    "ASX200": "S&P/ASX 200",
    "STOXX50E": "EURO STOXX 50",
    "DAX": "DAX",
    "FTSE100": "FTSE 100",
    "CAC40": "CAC 40",
    "MSCI_WORLD": "MSCI World Index",
    "MSCI_EM": "MSCI Emerging Markets Index",
    "AGG": "Bloomberg Global Aggregate Bond Index",
    "GSCI": "S&P GSCI",
}

REGION_MARKET = {
    "美国": "US",
    "中国内地": "China A-share",
    "中国香港": "Hong Kong",
    "日本": "Japan",
    "韩国": "Korea",
    "澳大利亚": "Australia",
    "德国": "Germany",
    "法国": "France",
    "英国": "United Kingdom",
    "欧元区": "Eurozone",
    "印度": "India",
    "加拿大": "Canada",
    "巴西": "Brazil",
    "全球": "Global",
    "全球发达市场": "Global developed",
    "全球新兴市场": "Global emerging",
}

REGION_CURRENCY = {
    "美国": "USD",
    "中国内地": "CNY",
    "中国香港": "HKD",
    "日本": "JPY",
    "韩国": "KRW",
    "澳大利亚": "AUD",
    "德国": "EUR",
    "法国": "EUR",
    "英国": "GBP",
    "欧元区": "EUR",
    "印度": "INR",
    "加拿大": "CAD",
    "巴西": "BRL",
    "全球": "multi_currency",
    "全球发达市场": "multi_currency",
    "全球新兴市场": "multi_currency",
}

CONTENT_RULES = [
    "成品视频里不出现“科普”。",
    "不出现“新手”“小白”。",
    "不出现“评分”。",
    "不出现投资建议表达，不预测未来涨跌。",
    "所有数字必须来自结构化数据或代码计算结果。",
    "缺关键数据时进入 needs_review，不生成成品。",
    "成品画面不得出现空数据、缺数据、未提供、暂无。",
]


def is_synthetic_code(code: str) -> bool:
    return bool(re.fullmatch(r"G\d{4}", str(code).strip()))


def slugify(code: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", str(code).strip().lower()).strip("_")
    return value or "index"


def map_index_type(asset_class: str, focus: str) -> str:
    text = f"{asset_class} {focus}"
    if "债券" in text:
        return "bond"
    if "商品" in text:
        return "commodity"
    if "低波动" in text:
        return "low_volatility"
    if "高股息" in text or "红利" in text:
        return "dividend"
    if "科技" in text or "成长" in text:
        return "technology"
    if "股票主题" in asset_class or "行业" in focus:
        return "sector"
    if "股票策略" in asset_class:
        return "strategy"
    return "broad_based"


def map_template_type(index_type: str, region: str) -> str:
    if index_type == "technology":
        return "technology_growth"
    if index_type == "dividend":
        return "dividend_strategy"
    if index_type == "broad_based" and region not in {"中国内地", "中国香港"}:
        return "overseas_broad_based"
    return index_type


def expected_valuation_metrics(index_type: str) -> list[str]:
    if index_type == "bond":
        return ["到期收益率", "久期", "信用质量", "利率敏感性"]
    if index_type == "commodity":
        return ["商品篮子权重", "展期规则", "历史波动", "供需敏感项"]
    if index_type == "dividend":
        return ["股息率", "分红稳定性", "PB", "行业集中度"]
    if index_type == "sector":
        return ["PE", "PB", "盈利周期", "需求和政策因素"]
    if index_type == "technology":
        return ["PE", "PB", "盈利增速", "技术周期", "估值区间"]
    return ["PE", "PB", "股息率", "历史区间", "估值分位"]


def missing_items_for(row: dict[str, Any], index_type: str) -> list[str]:
    missing = [
        "official_index_page",
        "official_methodology",
        "sector_weights",
        "top_holdings",
        "historical_price_series",
        "historical_returns",
        "max_drawdown",
        "source_date",
    ]
    if index_type in {"broad_based", "overseas", "sector", "strategy", "technology", "low_volatility"}:
        missing.append("valuation_metrics")
    if index_type == "dividend":
        missing.extend(["dividend_yield", "dividend_stability"])
    if index_type == "bond":
        missing.extend(["yield_to_maturity", "duration", "credit_quality"])
    if index_type == "commodity":
        missing.extend(["contract_or_index_method", "roll_or_weighting_rules"])
    if is_synthetic_code(str(row["code"])):
        missing.insert(0, "index_identity_review")
    return missing


def select_global100(catalog: pd.DataFrame) -> list[dict[str, Any]]:
    canonical = catalog[~catalog["code"].astype(str).map(is_synthetic_code)].copy()
    selected = [row.to_dict() for _, row in canonical.iterrows()]
    selected_codes = {str(row["code"]) for row in selected}

    synthetic = catalog[catalog["code"].astype(str).map(is_synthetic_code)].copy()
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for _, row in synthetic.iterrows():
        item = row.to_dict()
        item_type = map_index_type(str(item["asset_class"]), str(item["focus"]))
        buckets[(str(item["region"]), item_type)].append(item)

    region_order = [
        "美国",
        "中国内地",
        "中国香港",
        "日本",
        "韩国",
        "澳大利亚",
        "德国",
        "英国",
        "法国",
        "印度",
        "加拿大",
        "巴西",
        "全球发达市场",
        "全球新兴市场",
    ]
    type_order = ["broad_based", "dividend", "low_volatility", "strategy", "technology", "sector"]

    while len(selected) < 100:
        progressed = False
        for index_type in type_order:
            for region in region_order:
                if len(selected) >= 100:
                    break
                bucket = buckets.get((region, index_type), [])
                while bucket:
                    candidate = bucket.pop(0)
                    code = str(candidate["code"])
                    if code not in selected_codes:
                        selected.append(candidate)
                        selected_codes.add(code)
                        progressed = True
                        break
            if len(selected) >= 100:
                break
        if not progressed:
            break
    return selected[:100]


def plan_row(row: dict[str, Any], priority: int) -> dict[str, Any]:
    code = str(row["code"])
    index_type = map_index_type(str(row["asset_class"]), str(row["focus"]))
    missing = missing_items_for(row, index_type)
    if code == "CSI300":
        data_status = "ready"
        render_status = "approved_for_sample"
        notes = "已继承沪深300结构化数据；已人工批准样片。"
        review_status = "approved"
    elif "index_identity_review" in missing:
        data_status = "needs_review"
        render_status = "blocked_until_ready"
        notes = "候选指数身份需人工核验；不可直接生成成品。"
        review_status = "pending"
    else:
        data_status = "needs_data"
        render_status = "blocked_until_ready"
        notes = "目录级资料已建立；等待结构化生产数据。"
        review_status = "pending"
    return {
        "index_id": slugify(code),
        "index_name_cn": str(row["name"]),
        "index_name_en": KNOWN_EN_NAMES.get(code, code),
        "index_code": code,
        "provider": str(row["provider"]),
        "region": str(row["region"]),
        "market": REGION_MARKET.get(str(row["region"]), str(row["region"])),
        "index_type": index_type,
        "currency": REGION_CURRENCY.get(str(row["region"]), "unknown"),
        "template_type": map_template_type(index_type, str(row["region"])),
        "style_theme": str(row["theme"]),
        "priority": priority,
        "data_status": data_status,
        "render_status": render_status,
        "notes": notes,
        "review_status": review_status,
    }


def profile_for(plan: dict[str, Any], catalog_row: dict[str, Any]) -> dict[str, Any]:
    if plan["index_id"] == "csi300":
        source_profile = GLOBAL50_DIR / "profiles" / "csi300.json"
        if source_profile.exists():
            profile = json.loads(source_profile.read_text(encoding="utf-8"))
            profile["review_status"] = "approved"
            profile["render_status"] = "approved_for_sample"
            return profile

    missing = missing_items_for(catalog_row, plan["index_type"])
    risks = [item.strip() for item in re.split(r"[、,，;；]", str(catalog_row.get("risks", ""))) if item.strip()]
    return {
        "index_id": plan["index_id"],
        "data_status": plan["data_status"],
        "render_status": plan["render_status"],
        "review_status": plan["review_status"],
        "missing_items": missing,
        "basic_info": {
            "index_name_cn": plan["index_name_cn"],
            "index_name_en": plan["index_name_en"],
            "index_code": plan["index_code"],
            "provider": plan["provider"],
            "region": plan["region"],
            "market": plan["market"],
            "currency": plan["currency"],
            "index_type": plan["index_type"],
            "template_type": plan["template_type"],
            "style_theme": plan["style_theme"],
            "catalog_focus": str(catalog_row.get("focus", "")),
            "catalog_asset_class": str(catalog_row.get("asset_class", "")),
            "identity_status": "needs_human_review" if is_synthetic_code(str(catalog_row["code"])) else "catalog_candidate",
        },
        "methodology_summary": {
            "status": "needs_official_methodology",
            "draft_from_catalog": f"目录描述显示，该指数关注：{catalog_row.get('focus', '')}。",
            "must_confirm": ["样本空间", "选样规则", "加权方式", "调样频率", "成分限制"],
        },
        "sector_weights": {"status": "missing", "items": [], "required_for_video": "02_holdings_breakdown"},
        "top_holdings": {"status": "missing", "items": [], "required_for_video": "02_holdings_breakdown"},
        "valuation_metrics": {
            "status": "missing",
            "expected_by_type": expected_valuation_metrics(plan["index_type"]),
            "required_for_video": "05_valuation_view",
        },
        "historical_returns": {"status": "missing", "items": [], "required_for_video": "04_return_drawdown_risk"},
        "drawdown_stats": {
            "status": "missing",
            "items": [],
            "required_for_video": "04_return_drawdown_risk",
            "calculation_required": "使用公开历史点位计算最大回撤、回撤区间和恢复情况。",
        },
        "dividend_metrics": {
            "status": "missing" if plan["index_type"] == "dividend" else "not_required",
            "items": [],
            "required_for_video": "05_valuation_view",
        },
        "risk_points": {"status": "catalog_draft_needs_review", "items": risks},
        "role_in_portfolio": {
            "status": "catalog_draft_needs_review",
            "summary": str(catalog_row.get("role", "")),
            "must_confirm": ["核心/卫星定位", "适合搭配对象", "不适合承担的角色", "主要回撤来源"],
        },
        "source_items": [
            {
                "source_id": "global_index_catalog_500",
                "source_type": "catalog",
                "path": "data/global_index_catalog_500.csv",
                "fields_used": ["code", "name", "region", "provider", "asset_class", "focus", "role", "risks", "theme"],
                "allowed_for_final_numbers": False,
            }
        ],
        "data_date": {"catalog_data": "not_dated", "production_data": "not_collected"},
        "calculation_notes": [
            "当前 profile 是生产计划资料，不是成片数据文件。",
            "缺口补齐前不得生成成品视频。",
            "未来 data_used.json 必须记录每个数字的来源、字段、区间和计算方法。",
        ],
    }


def write_plan(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_source_registry(path: Path) -> None:
    payload = {
        "version": 1,
        "project": "global100",
        "source_policy": {
            "principle": "AI 只负责表达，不负责事实。所有成片数字必须来自结构化数据或代码计算。",
            "ready_rule": "只有 data_status=ready 且 review_status=approved 的指数才能进入正式渲染。",
            "no_empty_video_data": "成品画面不得出现未提供、暂无、数据缺失等占位表达。",
        },
        "content_rules": CONTENT_RULES,
        "required_profile_fields": [
            "basic_info",
            "methodology_summary",
            "sector_weights",
            "top_holdings",
            "valuation_metrics",
            "historical_returns",
            "drawdown_stats",
            "dividend_metrics",
            "risk_points",
            "role_in_portfolio",
            "source_items",
            "data_date",
            "calculation_notes",
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_report(path: Path, plan_rows: list[dict[str, Any]], profiles: list[dict[str, Any]]) -> None:
    status_counts = Counter(row["data_status"] for row in plan_rows)
    type_counts = Counter(row["index_type"] for row in plan_rows)
    profile_by_id = {profile["index_id"]: profile for profile in profiles}
    rows = []
    for row in plan_rows:
        profile = profile_by_id[row["index_id"]]
        missing = profile.get("missing_items") or []
        rows.append(
            "<tr>"
            f"<td>{row['priority']}</td>"
            f"<td>{html.escape(row['index_name_cn'])}<br><span>{html.escape(row['index_code'])}</span></td>"
            f"<td>{html.escape(row['region'])}</td>"
            f"<td>{html.escape(row['index_type'])}</td>"
            f"<td class='status {row['data_status']}'>{html.escape(row['data_status'])}</td>"
            f"<td>{html.escape(row['review_status'])}</td>"
            f"<td>{len(missing)}</td>"
            f"<td>{html.escape(', '.join(missing))}</td>"
            f"<td>{html.escape(row['notes'])}</td>"
            "</tr>"
        )
    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Global100 Readiness Report</title>
  <style>
    body {{ font-family: Arial, 'Microsoft YaHei', sans-serif; margin: 32px; background: #f6f8fb; color: #111827; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0 24px; }}
    .card {{ background: white; border: 1px solid #d8e2ec; border-radius: 8px; padding: 14px 18px; min-width: 160px; }}
    .card strong {{ display: block; font-size: 28px; color: #315d8c; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ border: 1px solid #d8e2ec; padding: 9px 10px; text-align: left; vertical-align: top; font-size: 14px; }}
    th {{ background: #edf2f7; }}
    td span {{ color: #667085; font-size: 12px; }}
    .status {{ font-weight: 700; }}
    .ready {{ color: #28734f; }}
    .needs_data {{ color: #9a6a24; }}
    .needs_review {{ color: #a13f3f; }}
  </style>
</head>
<body>
  <h1>Global100 Readiness Report</h1>
  <p>本报告用于“全球100组代表指数视频”的生产准备。每个指数计划生成5条视频，但只有数据和人工审核都通过后才允许生成成品。</p>
  <div class="summary">
    <div class="card"><span>候选指数</span><strong>{len(plan_rows)}</strong></div>
    <div class="card"><span>Ready</span><strong>{status_counts.get('ready', 0)}</strong></div>
    <div class="card"><span>Needs Data</span><strong>{status_counts.get('needs_data', 0)}</strong></div>
    <div class="card"><span>Needs Review</span><strong>{status_counts.get('needs_review', 0)}</strong></div>
  </div>
  <p>类型分布：{html.escape(', '.join(f'{key}: {value}' for key, value in sorted(type_counts.items())))}</p>
  <table>
    <thead><tr><th>优先级</th><th>指数</th><th>地区</th><th>类型</th><th>数据状态</th><th>审核</th><th>缺口数</th><th>缺口</th><th>备注</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>"""
    path.write_text(html_doc, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Global100 index video production plan")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if GLOBAL100_DIR.exists() and args.force:
        shutil.rmtree(GLOBAL100_DIR)
    GLOBAL100_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    for old in PROFILES_DIR.glob("*.json"):
        old.unlink()

    catalog = pd.read_csv(CATALOG_PATH)
    selected = select_global100(catalog)[: args.count]
    plan_rows: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    for priority, row in enumerate(selected, start=1):
        plan = plan_row(row, priority)
        profile = profile_for(plan, row)
        plan_rows.append(plan)
        profiles.append(profile)
        (PROFILES_DIR / f"{plan['index_id']}.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    write_plan(GLOBAL100_DIR / "global100_plan.csv", plan_rows)
    write_source_registry(SOURCES_DIR / "source_registry.json")
    render_report(GLOBAL100_DIR / "global100_readiness_report.html", plan_rows, profiles)

    run_dir = RUNS_DIR / f"global100_plan_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=False)
    write_plan(run_dir / "global100_plan.csv", plan_rows)
    render_report(run_dir / "global100_readiness_report.html", plan_rows, profiles)
    (run_dir / "profiles_summary.json").write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "plan": str(GLOBAL100_DIR / "global100_plan.csv"),
        "profiles": str(PROFILES_DIR),
        "report": str(GLOBAL100_DIR / "global100_readiness_report.html"),
        "run_dir": str(run_dir),
        "count": len(plan_rows),
        "ready": sum(1 for row in plan_rows if row["data_status"] == "ready"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
