from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "data" / "global_index_catalog_500.csv"
GLOBAL50_DIR = ROOT / "data" / "global50"
PROFILES_DIR = GLOBAL50_DIR / "profiles"
SOURCES_DIR = GLOBAL50_DIR / "sources"
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
]

CONTENT_RULES = [
    "成品视频里不出现“科普”。",
    "不出现“新手”“小白”。",
    "不出现“评分”。",
    "不出现“推荐买入”“可以上车”“值得买”“闭眼买”“无脑买”等投资建议表达。",
    "不出现“稳赚”“必涨”“低风险”“更安全”“吊打”“封神”等夸张表达。",
    "不预测未来涨跌，不评价指数绝对好坏。",
    "所有数字必须来自结构化数据文件或代码计算结果。",
    "缺关键数据时进入 needs_review，不生成成品视频。",
]

INDEX_NAME_EN: dict[str, str] = {
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

CURRENCY_BY_REGION: dict[str, str] = {
    "美国": "USD",
    "中国内地": "CNY",
    "中国香港": "HKD",
    "日本": "JPY",
    "韩国": "KRW",
    "澳大利亚": "AUD",
    "德国": "EUR",
    "法国": "EUR",
    "欧元区": "EUR",
    "英国": "GBP",
    "印度": "INR",
    "加拿大": "CAD",
    "巴西": "BRL",
    "全球": "multi_currency",
    "全球发达市场": "multi_currency",
    "全球新兴市场": "multi_currency",
}

MARKET_BY_REGION: dict[str, str] = {
    "美国": "US",
    "中国内地": "China A-share",
    "中国香港": "Hong Kong",
    "日本": "Japan",
    "韩国": "Korea",
    "澳大利亚": "Australia",
    "德国": "Germany",
    "法国": "France",
    "欧元区": "Eurozone",
    "英国": "United Kingdom",
    "印度": "India",
    "加拿大": "Canada",
    "巴西": "Brazil",
    "全球": "Global",
    "全球发达市场": "Global developed",
    "全球新兴市场": "Global emerging",
}


@dataclass(frozen=True)
class PlannedIndex:
    row: dict[str, Any]
    priority: int


def slugify(code: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(code).strip().lower()).strip("_")
    return slug or "index"


def is_synthetic_code(code: str) -> bool:
    return bool(re.fullmatch(r"G\d{4}", str(code).strip()))


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
    if "股票行业" in asset_class:
        return "sector"
    if "股票策略" in asset_class:
        return "strategy"
    if "股票宽基" in asset_class:
        return "broad_based"
    return "strategy"


def map_template_type(index_type: str, region: str) -> str:
    if index_type == "broad_based" and region not in {"中国内地", "中国香港"}:
        return "overseas_broad_based"
    if index_type == "technology":
        return "technology_growth"
    if index_type == "dividend":
        return "dividend_strategy"
    return index_type


def select_global50(catalog: pd.DataFrame) -> list[PlannedIndex]:
    canonical = catalog[~catalog["code"].astype(str).map(is_synthetic_code)].copy()
    selected_rows = [row.to_dict() for _, row in canonical.iterrows()]
    selected_codes = {str(row["code"]) for row in selected_rows}

    synthetic = catalog[catalog["code"].astype(str).map(is_synthetic_code)].copy()
    by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for _, row in synthetic.iterrows():
        by_region[str(row["region"])].append(row.to_dict())

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
        "全球发达市场",
        "全球新兴市场",
        "巴西",
    ]
    addition_targets = [
        ("dividend", 5),
        ("low_volatility", 5),
        ("strategy", 6),
        ("technology", 4),
        ("sector", 8),
    ]
    for desired_type, target_count in addition_targets:
        added = 0
        while len(selected_rows) < 50 and added < target_count:
            progressed = False
            for region in region_order:
                if len(selected_rows) >= 50 or added >= target_count:
                    break
                bucket = by_region.get(region, [])
                match_index = None
                for idx, candidate in enumerate(bucket):
                    candidate_type = map_index_type(str(candidate["asset_class"]), str(candidate["focus"]))
                    code = str(candidate["code"])
                    if candidate_type == desired_type and code not in selected_codes:
                        match_index = idx
                        break
                if match_index is None:
                    continue
                candidate = bucket.pop(match_index)
                selected_rows.append(candidate)
                selected_codes.add(str(candidate["code"]))
                added += 1
                progressed = True
            if not progressed:
                break

    while len(selected_rows) < 50:
        progressed = False
        for region in region_order:
            if len(selected_rows) >= 50:
                break
            bucket = by_region.get(region, [])
            while bucket:
                candidate = bucket.pop(0)
                code = str(candidate["code"])
                if code not in selected_codes:
                    selected_rows.append(candidate)
                    selected_codes.add(code)
                    progressed = True
                    break
        if not progressed:
            break

    return [PlannedIndex(row=row, priority=idx) for idx, row in enumerate(selected_rows[:50], start=1)]


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


def data_status_for(row: dict[str, Any], missing: list[str]) -> str:
    if "index_identity_review" in missing:
        return "needs_review"
    if missing:
        return "needs_data"
    return "ready"


def plan_row(planned: PlannedIndex) -> dict[str, Any]:
    row = planned.row
    code = str(row["code"])
    index_type = map_index_type(str(row["asset_class"]), str(row["focus"]))
    missing = missing_items_for(row, index_type)
    data_status = data_status_for(row, missing)
    notes = "候选指数身份需人工核验；不可直接生成成品" if data_status == "needs_review" else "目录级资料已建立；等待结构化生产数据"
    if code == "CSI300":
        notes = "已有沪深300单指数生成器，可作为该指数的数据接入样板"
    return {
        "index_id": slugify(code),
        "index_name_cn": str(row["name"]),
        "index_name_en": INDEX_NAME_EN.get(code, code),
        "index_code": code,
        "provider": str(row["provider"]),
        "region": str(row["region"]),
        "market": MARKET_BY_REGION.get(str(row["region"]), str(row["region"])),
        "index_type": index_type,
        "currency": CURRENCY_BY_REGION.get(str(row["region"]), "unknown"),
        "template_type": map_template_type(index_type, str(row["region"])),
        "style_theme": str(row["theme"]),
        "priority": planned.priority,
        "data_status": data_status,
        "render_status": "blocked_until_ready" if data_status != "ready" else "not_started",
        "notes": notes,
    }


def source_registry() -> dict[str, Any]:
    return {
        "version": 1,
        "created_by": "build_global50_plan.py",
        "source_policy": {
            "principle": "AI 只负责表达，不负责事实。所有成片数字必须来自结构化数据或代码计算。",
            "ready_rule": "只有 data_status = ready 的指数才能进入视频生成。",
            "no_empty_video_data": "成品画面不得出现未提供、暂无、数据缺失等占位表达。",
        },
        "source_types": {
            "catalog": {
                "description": "本项目自带指数目录，只能用于候选清单和初步定位。",
                "file": "data/global_index_catalog_500.csv",
                "allowed_for_ready": False,
            },
            "official_index_page": {
                "description": "指数公司官方页面，确认指数名称、代码、范围和基础资料。",
                "allowed_for_ready": True,
            },
            "official_factsheet": {
                "description": "指数公司官方单张，优先用于行业权重、前十大、估值、收益和波动率。",
                "allowed_for_ready": True,
            },
            "official_methodology": {
                "description": "指数编制方案，确认选样、加权、调样和限制规则。",
                "allowed_for_ready": True,
            },
            "public_price_series": {
                "description": "公开历史点位序列，用于计算收益、走势图、最大回撤和恢复时间。",
                "allowed_for_ready": True,
            },
            "public_valuation_series": {
                "description": "公开估值历史序列，用于计算区间和分位。",
                "allowed_for_ready": True,
            },
        },
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
        "content_rules": CONTENT_RULES,
    }


def profile_for(plan: dict[str, Any], catalog_row: dict[str, Any]) -> dict[str, Any]:
    missing = missing_items_for(catalog_row, str(plan["index_type"]))
    risk_points = [item.strip() for item in re.split(r"[、,，;；]", str(catalog_row["risks"])) if item.strip()]
    return {
        "index_id": plan["index_id"],
        "data_status": plan["data_status"],
        "render_status": plan["render_status"],
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
            "catalog_focus": str(catalog_row["focus"]),
            "catalog_asset_class": str(catalog_row["asset_class"]),
            "identity_status": "needs_human_review" if is_synthetic_code(str(catalog_row["code"])) else "catalog_candidate",
        },
        "methodology_summary": {
            "status": "needs_official_methodology",
            "draft_from_catalog": f"从目录描述看，该指数关注：{catalog_row['focus']}。",
            "must_confirm": ["样本空间", "选样规则", "加权方式", "调样频率", "成分限制"],
        },
        "sector_weights": {
            "status": "missing",
            "items": [],
            "required_for_video": "02_holdings_breakdown",
        },
        "top_holdings": {
            "status": "missing",
            "items": [],
            "required_for_video": "02_holdings_breakdown",
        },
        "valuation_metrics": {
            "status": "missing",
            "required_for_video": "05_valuation_view",
            "expected_by_type": expected_valuation_metrics(str(plan["index_type"])),
        },
        "historical_returns": {
            "status": "missing",
            "items": [],
            "required_for_video": "04_return_drawdown_risk",
        },
        "drawdown_stats": {
            "status": "missing",
            "items": [],
            "required_for_video": "04_return_drawdown_risk",
            "calculation_required": "使用公开历史点位计算最大回撤、回撤区间和恢复情况。",
        },
        "dividend_metrics": {
            "status": "required_for_dividend_only" if plan["index_type"] != "dividend" else "missing",
            "items": [],
            "required_for_video": "05_valuation_view",
        },
        "risk_points": {
            "status": "catalog_draft_needs_review",
            "items": risk_points,
        },
        "role_in_portfolio": {
            "status": "catalog_draft_needs_review",
            "summary": str(catalog_row["role"]),
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
        "data_date": {
            "catalog_data": "not_dated",
            "production_data": "not_collected",
        },
        "calculation_notes": [
            "当前 profile 是生产计划资料，不是成片数据文件。",
            "缺口补齐前不得生成成品视频。",
            "未来 data_used.json 必须记录每个数字的来源、字段、区间和计算方法。",
        ],
    }


def expected_valuation_metrics(index_type: str) -> list[str]:
    if index_type == "bond":
        return ["yield_to_maturity", "duration", "credit_quality", "interest_rate_sensitivity"]
    if index_type == "commodity":
        return ["spot_or_futures_reference", "weighting_rules", "roll_or_rebalance_rules"]
    if index_type == "dividend":
        return ["dividend_yield", "dividend_stability", "pb", "sector_concentration"]
    if index_type == "sector":
        return ["pe", "pb", "profit_cycle", "policy_or_demand_drivers"]
    if index_type == "technology":
        return ["pe", "pb", "profit_growth", "rate_sensitivity", "valuation_range"]
    return ["pe", "pb", "dividend_yield", "valuation_range", "valuation_percentile"]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def render_report(plan_rows: list[dict[str, Any]], profiles: list[dict[str, Any]], output: Path) -> None:
    profile_by_id = {profile["index_id"]: profile for profile in profiles}
    status_counts = Counter(row["data_status"] for row in plan_rows)
    type_counts = Counter(row["index_type"] for row in plan_rows)
    rows_html = []
    for row in plan_rows:
        profile = profile_by_id[row["index_id"]]
        missing = profile["missing_items"]
        rows_html.append(
            "<tr>"
            f"<td>{row['priority']}</td>"
            f"<td>{html.escape(row['index_name_cn'])}<br><span>{html.escape(row['index_code'])}</span></td>"
            f"<td>{html.escape(row['region'])}</td>"
            f"<td>{html.escape(row['index_type'])}</td>"
            f"<td class='status {row['data_status']}'>{html.escape(row['data_status'])}</td>"
            f"<td>{len(missing)}</td>"
            f"<td>{html.escape(', '.join(missing))}</td>"
            f"<td>{html.escape(row['notes'])}</td>"
            "</tr>"
        )

    report = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Global50 Readiness Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; margin: 32px; color: #17211d; background: #f6f7f5; }}
    h1 {{ margin-bottom: 8px; }}
    .summary {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 20px 0; }}
    .card {{ background: white; border: 1px solid #dce5df; border-radius: 8px; padding: 14px 18px; min-width: 160px; }}
    .card strong {{ display: block; font-size: 28px; color: #14563a; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce5df; }}
    th, td {{ border-bottom: 1px solid #e4ebe7; padding: 10px 12px; text-align: left; vertical-align: top; font-size: 14px; }}
    th {{ background: #eaf3ed; }}
    td span {{ color: #66736d; font-size: 12px; }}
    .status {{ font-weight: 700; white-space: nowrap; }}
    .needs_data {{ color: #9a6a24; }}
    .needs_review {{ color: #a13f3f; }}
    .ready {{ color: #1f7a4d; }}
    .rules li {{ margin: 6px 0; }}
  </style>
</head>
<body>
  <h1>Global50 Readiness Report</h1>
  <p>本报告只检查全球50指数观察视频的生产准备度，不生成视频。只有 <code>data_status = ready</code> 的指数才允许进入后续渲染。</p>
  <div class="summary">
    <div class="card"><span>候选指数</span><strong>{len(plan_rows)}</strong></div>
    <div class="card"><span>Ready</span><strong>{status_counts.get('ready', 0)}</strong></div>
    <div class="card"><span>Needs Data</span><strong>{status_counts.get('needs_data', 0)}</strong></div>
    <div class="card"><span>Needs Review</span><strong>{status_counts.get('needs_review', 0)}</strong></div>
  </div>
  <h2>类型分布</h2>
  <p>{html.escape(', '.join(f'{key}: {value}' for key, value in sorted(type_counts.items())))}</p>
  <h2>内容标准</h2>
  <ul class="rules">{''.join(f'<li>{html.escape(rule)}</li>' for rule in CONTENT_RULES)}</ul>
  <h2>数据缺口</h2>
  <table>
    <thead>
      <tr>
        <th>优先级</th>
        <th>指数</th>
        <th>地区</th>
        <th>类型</th>
        <th>数据状态</th>
        <th>缺口数</th>
        <th>缺口项目</th>
        <th>备注</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</body>
</html>
"""
    output.write_text(report, encoding="utf-8")


def main() -> None:
    catalog = pd.read_csv(CATALOG_PATH)
    GLOBAL50_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    for old_profile in PROFILES_DIR.glob("*.json"):
        old_profile.unlink()

    selected = select_global50(catalog)
    plan_rows: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    row_by_code = {str(row["code"]): row.to_dict() for _, row in catalog.iterrows()}
    for planned in selected:
        row = plan_row(planned)
        plan_rows.append(row)
        profile = profile_for(row, row_by_code[row["index_code"]])
        profiles.append(profile)
        (PROFILES_DIR / f"{row['index_id']}.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    write_csv(GLOBAL50_DIR / "global50_plan.csv", plan_rows)
    (SOURCES_DIR / "source_registry.json").write_text(
        json.dumps(source_registry(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    run_dir = RUNS_DIR / f"global50_dry_run_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=True)
    write_csv(run_dir / "global50_plan.csv", plan_rows)
    (run_dir / "profiles_summary.json").write_text(
        json.dumps(profiles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "source_registry.json").write_text(
        json.dumps(source_registry(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    render_report(plan_rows, profiles, run_dir / "global50_readiness_report.html")
    render_report(plan_rows, profiles, GLOBAL50_DIR / "global50_readiness_report.html")

    print(f"Global50 plan written: {GLOBAL50_DIR / 'global50_plan.csv'}")
    print(f"Profiles written: {PROFILES_DIR}")
    print(f"Dry run written: {run_dir}")


if __name__ == "__main__":
    main()
