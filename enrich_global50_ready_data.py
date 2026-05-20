from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from render_csi300_series import (
    FACTSHEET_URL,
    INDEX_PAGE_URL,
    METHODOLOGY_URL,
    csi300_source_items,
    download_pdf_text,
    load_history_data,
    load_valuation_data,
    parse_factsheet,
)


ROOT = Path(__file__).resolve().parent
GLOBAL50_DIR = ROOT / "data" / "global50"
PROFILE_DIR = GLOBAL50_DIR / "profiles"
PLAN_PATH = GLOBAL50_DIR / "global50_plan.csv"
SOURCE_CACHE = GLOBAL50_DIR / "source_cache"


def read_plan(path: Path = PLAN_PATH) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_plan(rows: list[dict[str, Any]], path: Path = PLAN_PATH) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def split_name_weight(text: str) -> tuple[str, str]:
    match = re.match(r"(.+?)\s+(-?\d+(?:\.\d+)?%)$", text.strip())
    if not match:
        return text.strip(), ""
    return match.group(1).strip(), match.group(2).strip()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def enrich_csi300() -> dict[str, Any]:
    cache_dir = SOURCE_CACHE / "csi300"
    cache_dir.mkdir(parents=True, exist_ok=True)

    factsheet_pdf, factsheet_text = download_pdf_text(FACTSHEET_URL)
    (cache_dir / "000300factsheet.pdf").write_bytes(factsheet_pdf)
    (cache_dir / "000300factsheet.txt").write_text(factsheet_text, encoding="utf-8")
    methodology_pdf, _ = download_pdf_text(METHODOLOGY_URL)
    (cache_dir / "000300_Index_Methodology_cn.pdf").write_bytes(methodology_pdf)

    data = parse_factsheet(factsheet_text)
    data.history = load_history_data(cache_dir)
    data.valuation = load_valuation_data(cache_dir, data)

    source_items = csi300_source_items(data)
    profile_path = PROFILE_DIR / "csi300.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    sector_items = []
    for item in data.industry_top:
        name, weight = split_name_weight(item.value)
        sector_items.append(
            {
                "name": name,
                "weight": weight,
                "source_field": item.field,
                "source_id": "csi_factsheet",
            }
        )

    holding_items = []
    for row in data.top_holdings[:10]:
        holding_items.append(
            {
                "code": row["代码"].value,
                "name": row["名称"].value,
                "industry": row["行业"].value,
                "exchange": row["交易所"].value,
                "weight": row["权重"].value,
                "source_id": "csi_factsheet",
            }
        )

    sample_range = f"{data.history.get('start_date')} 至 {data.history.get('latest_date')}"
    annual_items = []
    for year, value in list(data.history.get("annual_returns", {}).items())[-8:]:
        annual_items.append(
            {
                "label": f"{year}年度收益",
                "period": year,
                "return": value,
                "sample_range": sample_range,
                "calculation_method": "按年度最后一个交易日收盘点位计算年度收益。",
                "source_id": "history_price_series",
            }
        )

    valuation_items = [
        {
            "label": "PE当前值",
            "metric": "pe",
            "category": "pe",
            "value": data.valuation["pe"]["current"],
            "calculation_method": "公开 PE 历史序列最新值。",
            "source_id": "valuation_pe_pb_series",
        },
        {
            "label": "PE历史区间",
            "metric": "pe_range",
            "category": "valuation_range",
            "value": data.valuation["pe"]["history_range"],
            "calculation_method": "公开 PE 历史序列最小值到最大值。",
            "source_id": "valuation_pe_pb_series",
        },
        {
            "label": "PE分位",
            "metric": "pe_percentile",
            "category": "valuation_percentile",
            "value": data.valuation["pe"]["percentile"],
            "calculation_method": "公开 PE 历史序列中小于等于当前值的样本占比。",
            "source_id": "valuation_pe_pb_series",
        },
        {
            "label": "PB当前值",
            "metric": "pb",
            "category": "pb",
            "value": data.valuation["pb"]["current"],
            "calculation_method": "公开 PB 历史序列最新值。",
            "source_id": "valuation_pe_pb_series",
        },
        {
            "label": "PB历史区间",
            "metric": "pb_range",
            "category": "valuation_range",
            "value": data.valuation["pb"]["history_range"],
            "calculation_method": "公开 PB 历史序列最小值到最大值。",
            "source_id": "valuation_pe_pb_series",
        },
        {
            "label": "PB分位",
            "metric": "pb_percentile",
            "category": "valuation_percentile",
            "value": data.valuation["pb"]["percentile"],
            "calculation_method": "公开 PB 历史序列中小于等于当前值的样本占比。",
            "source_id": "valuation_pe_pb_series",
        },
        {
            "label": "股息率当前值",
            "metric": "dividend_yield",
            "category": "dividend_yield",
            "value": data.valuation["dividend_yield"]["current"],
            "calculation_method": "官方指标表股息率字段最新值。",
            "source_id": "official_indicator_xls",
        },
        {
            "label": "股息率近期区间",
            "metric": "dividend_yield_range",
            "category": "valuation_range",
            "value": data.valuation["dividend_yield"]["recent_range"],
            "calculation_method": "官方指标表股息率字段样本的最小值到最大值。",
            "source_id": "official_indicator_xls",
        },
    ]

    profile.update(
        {
            "data_status": "ready",
            "render_status": "ready_for_review",
            "review_status": profile.get("review_status") or "pending",
            "missing_items": [],
            "basic_info": {
                **(profile.get("basic_info") or {}),
                "index_name_cn": "沪深300",
                "index_name_en": "CSI 300",
                "index_code": data.index_code.value,
                "provider": "中证指数",
                "region": "中国内地",
                "market": "China A-share",
                "currency": "CNY",
                "index_type": "broad_based",
                "template_type": "broad_based",
                "style_theme": "china",
                "catalog_focus": "A股大盘核心公司",
                "identity_status": "official_verified",
            },
            "methodology_summary": {
                "status": "ready",
                "summary": "从沪深市场中选取规模大、流动性好的代表性证券，样本按规则定期调整。",
                "sample_scope": "沪深市场",
                "selection_focus": ["规模", "流动性", "代表性"],
                "rebalance_frequency": data.rebalance_frequency.value,
                "source_id": "csi_methodology",
            },
            "sector_weights": {
                "status": "ready",
                "items": sector_items,
                "required_for_video": "02_holdings_breakdown",
            },
            "top_holdings": {
                "status": "ready",
                "items": holding_items,
                "required_for_video": "02_holdings_breakdown",
            },
            "valuation_metrics": {
                "status": "ready",
                "items": valuation_items,
                "required_for_video": "05_valuation_view",
                "calculation_method": "PE/PB 使用公开历史序列计算当前值、历史区间和分位；股息率使用官方指标表。",
            },
            "historical_returns": {
                "status": "ready",
                "items": annual_items,
                "required_for_video": "04_return_drawdown_risk",
                "sample_range": sample_range,
            },
            "drawdown_stats": {
                "status": "ready",
                "items": [
                    {
                        "label": "最大回撤",
                        "max_drawdown": data.history["max_drawdown"],
                        "calculation_range": sample_range,
                        "calculation_method": "用发布以来的收盘点位序列计算累计净值回撤。",
                        "source_id": "history_price_series",
                    }
                ],
                "required_for_video": "04_return_drawdown_risk",
            },
            "dividend_metrics": {
                "status": "ready",
                "items": [
                    {
                        "label": "股息率当前值",
                        "value": data.valuation["dividend_yield"]["current"],
                        "source_id": "official_indicator_xls",
                    }
                ],
                "required_for_video": "05_valuation_view",
            },
            "risk_points": {
                "status": "ready",
                "items": [
                    "偏大盘核心公司，不代表中小盘。",
                    "行业权重和前十大公司变化会影响阶段表现。",
                    "历史样本中出现过明显回撤，组合需要考虑承受能力。",
                ],
            },
            "role_in_portfolio": {
                "status": "ready",
                "summary": "A股大盘核心公司观察",
                "role": "权益资产中的A股大盘核心仓位参照。",
                "not_for": ["不代表中小盘", "不代表单一行业", "不单独承担回撤控制"],
            },
            "source_items": source_items,
            "data_date": data.source_date,
            "calculation_notes": [
                "沪深300数据由官方单张、官方编制方案、官方指标表和公开行情序列组成。",
                "历史收益和最大回撤由公开日线点位计算。",
                "PE/PB 区间和分位由公开估值历史序列计算。",
            ],
        }
    )
    write_json(profile_path, profile)

    rows = read_plan()
    for row in rows:
        if row.get("index_id") == "csi300":
            row["index_code"] = data.index_code.value
            row["data_status"] = "ready"
            row["render_status"] = "ready_for_review"
            row["review_status"] = row.get("review_status") or "pending"
            row["notes"] = f"已补齐结构化数据；数据日期 {data.source_date}；等待人工审核批准"
        elif "review_status" not in row:
            row["review_status"] = "pending"
    write_plan(rows)

    return {
        "index_id": "csi300",
        "data_status": "ready",
        "review_status": profile["review_status"],
        "data_date": data.source_date,
        "source_cache": str(cache_dir),
        "sector_count": len(sector_items),
        "holding_count": len(holding_items),
        "historical_return_count": len(annual_items),
        "valuation_metric_count": len(valuation_items),
        "sources": {
            "index_page": INDEX_PAGE_URL,
            "factsheet": FACTSHEET_URL,
            "methodology": METHODOLOGY_URL,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich Global50 profiles with verified structured data")
    parser.add_argument("--index", default="csi300", choices=["csi300"], help="Index id to enrich")
    args = parser.parse_args()
    if args.index == "csi300":
        result = enrich_csi300()
    else:
        raise SystemExit(f"Unsupported index: {args.index}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
