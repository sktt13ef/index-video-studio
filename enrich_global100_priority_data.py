from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parent
GLOBAL100_DIR = ROOT / "data" / "global100"
PROFILE_DIR = GLOBAL100_DIR / "profiles"
PLAN_PATH = GLOBAL100_DIR / "global100_plan.csv"
SOURCE_CACHE = GLOBAL100_DIR / "source_cache"


@dataclass(frozen=True)
class PriorityIndex:
    index_id: str
    history_source: str
    symbol: str
    official_url: str
    methodology_url: str
    source_label: str
    source_type: str = "public_price_series"


PRIORITY_INDEXES: list[PriorityIndex] = [
    PriorityIndex("spx", "yahoo", "^GSPC", "https://www.spglobal.com/spdji/en/indices/equity/sp-500/", "https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-us-indices.pdf", "Yahoo Finance chart API / S&P 500"),
    PriorityIndex("ndx", "yahoo", "^NDX", "https://indexes.nasdaqomx.com/Index/Overview/NDX", "https://indexes.nasdaqomx.com/docs/Methodology_NDX.pdf", "Yahoo Finance chart API / Nasdaq-100"),
    PriorityIndex("dji", "yahoo", "^DJI", "https://www.spglobal.com/spdji/en/indices/equity/dow-jones-industrial-average/", "https://www.spglobal.com/spdji/en/documents/methodologies/methodology-dj-averages.pdf", "Yahoo Finance chart API / Dow Jones Industrial Average"),
    PriorityIndex("rut", "yahoo", "^RUT", "https://www.lseg.com/en/ftse-russell/indices/russell-us", "https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/russell-us-indexes-construction-and-methodology.pdf", "Yahoo Finance chart API / Russell 2000"),
    PriorityIndex("hsi", "yahoo", "^HSI", "https://www.hsi.com.hk/eng/indexes/all-indexes/hsi", "https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/methodologies/IM_hsie.pdf", "Yahoo Finance chart API / Hang Seng Index"),
    PriorityIndex("hstech", "yahoo", "3033.HK", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech", "https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/methodologies/IM_hstech.pdf", "Yahoo Finance chart API / 3033.HK ETF proxy for Hang Seng TECH"),
    PriorityIndex("csi500", "akshare_cn", "000905", "https://www.csindex.com.cn/zh-CN/indices/index-detail/000905", "https://www.csindex.com.cn/zh-CN/indices/index-detail/000905", "AKShare / 中证指数公开数据"),
    PriorityIndex("csi1000", "akshare_cn", "000852", "https://www.csindex.com.cn/zh-CN/indices/index-detail/000852", "https://www.csindex.com.cn/zh-CN/indices/index-detail/000852", "AKShare / 中证指数公开数据"),
    PriorityIndex("csi_div", "akshare_cn", "000922", "https://www.csindex.com.cn/zh-CN/indices/index-detail/000922", "https://www.csindex.com.cn/zh-CN/indices/index-detail/000922", "AKShare / 中证指数公开数据"),
    PriorityIndex("n225", "yahoo", "^N225", "https://indexes.nikkei.co.jp/en/nkave", "https://indexes.nikkei.co.jp/en/nkave/index/profile?idx=nk225", "Yahoo Finance chart API / Nikkei 225"),
    PriorityIndex("topix", "yahoo", "1306.T", "https://www.jpx.co.jp/english/markets/indices/topix/", "https://www.jpx.co.jp/english/markets/indices/topix/", "Yahoo Finance chart API / 1306.T ETF proxy for TOPIX"),
    PriorityIndex("kospi", "yahoo", "^KS11", "https://global.krx.co.kr/contents/GLB/05/0501/0501010000/GLB0501010000.jsp", "https://global.krx.co.kr/", "Yahoo Finance chart API / KOSPI"),
    PriorityIndex("asx200", "yahoo", "^AXJO", "https://www.spglobal.com/spdji/en/indices/equity/sp-asx-200/", "https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-australian-indices.pdf", "Yahoo Finance chart API / S&P/ASX 200"),
    PriorityIndex("stoxx50e", "yahoo", "^STOXX50E", "https://www.stoxx.com/index/sx5e/", "https://www.stoxx.com/document/Indices/Common/Indexguide/stoxx_index_guide.pdf", "Yahoo Finance chart API / EURO STOXX 50"),
    PriorityIndex("dax", "yahoo", "^GDAXI", "https://www.stoxx.com/index/dax/", "https://www.stoxx.com/document/Indices/Common/Indexguide/dax_equity_indices_guide.pdf", "Yahoo Finance chart API / DAX"),
    PriorityIndex("ftse100", "yahoo", "^FTSE", "https://www.lseg.com/en/ftse-russell/indices/uk", "https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-uk-index-series-ground-rules.pdf", "Yahoo Finance chart API / FTSE 100"),
    PriorityIndex("cac40", "yahoo", "^FCHI", "https://live.euronext.com/en/product/indices/FR0003500008-XPAR", "https://live.euronext.com/en/resources/rules-regulations/indices", "Yahoo Finance chart API / CAC 40"),
    PriorityIndex("msci_world", "yahoo", "URTH", "https://www.msci.com/indexes/index/990100", "https://www.msci.com/index-methodology", "Yahoo Finance chart API / URTH ETF proxy for MSCI World"),
    PriorityIndex("msci_em", "yahoo", "EEM", "https://www.msci.com/indexes/index/891800", "https://www.msci.com/index-methodology", "Yahoo Finance chart API / EEM ETF proxy for MSCI Emerging Markets"),
    PriorityIndex("agg", "yahoo", "AGG", "https://www.bloomberg.com/professional/product/indices/bloomberg-fixed-income-indices/", "https://www.bloomberg.com/professional/product/indices/bloomberg-fixed-income-indices/", "Yahoo Finance chart API / AGG ETF proxy for Global Aggregate Bond"),
    PriorityIndex("gsci", "yahoo", "GSG", "https://www.spglobal.com/spdji/en/indices/commodities/sp-gsci/", "https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-gsci.pdf", "Yahoo Finance chart API / GSG ETF proxy for S&P GSCI"),
]


def read_plan() -> list[dict[str, str]]:
    with PLAN_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_plan(rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with PLAN_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_profile(index_id: str) -> dict[str, Any]:
    return json.loads((PROFILE_DIR / f"{index_id}.json").read_text(encoding="utf-8"))


def write_profile(index_id: str, profile: dict[str, Any]) -> None:
    (PROFILE_DIR / f"{index_id}.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_yahoo_history(symbol: str, cache_dir: Path) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = cache_dir / f"{symbol.replace('^', '').replace('.', '_')}_yahoo_history.csv"
    period2 = int(time.time())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    response = requests.get(
        url,
        params={"period1": 0, "period2": period2, "interval": "1d", "events": "history"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=40,
    )
    response.raise_for_status()
    payload = response.json()
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo history returned no data for {symbol}")
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    rows = []
    for ts, close in zip(timestamps, closes):
        if close is None or math.isnan(float(close)):
            continue
        rows.append({"date": pd.to_datetime(ts, unit="s").date().isoformat(), "close": float(close)})
    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    if df.empty:
        raise RuntimeError(f"Yahoo history parsed no closes for {symbol}")
    df.to_csv(output, index=False, encoding="utf-8-sig")
    df.attrs["source_file"] = str(output)
    df.attrs["source_url"] = url
    return df


def fetch_cn_history(symbol: str, cache_dir: Path) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = cache_dir / f"{symbol}_akshare_history.csv"
    df = ak.stock_zh_index_daily_tx(symbol=f"sh{symbol}")
    df = df[["date", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna().drop_duplicates("date").sort_values("date")
    df.to_csv(output, index=False, encoding="utf-8-sig")
    df.attrs["source_file"] = str(output)
    df.attrs["source_url"] = "akshare.stock_zh_index_daily"
    return df


def fetch_cn_holdings(symbol: str, cache_dir: Path) -> tuple[list[dict[str, Any]], str | None]:
    try:
        df = ak.index_stock_cons_weight_csindex(symbol=symbol)
    except Exception:
        return [], None
    output = cache_dir / f"{symbol}_csindex_constituent_weights.csv"
    df.to_csv(output, index=False, encoding="utf-8-sig")
    items = []
    for _, row in df.sort_values("权重", ascending=False).head(10).iterrows():
        items.append(
            {
                "code": str(row.get("成分券代码", "")),
                "name": str(row.get("成分券名称", "")),
                "weight": f"{float(row.get('权重')):.2f}%",
                "source_id": "constituent_weight_series",
            }
        )
    return items, str(output)


def fetch_cn_valuation(symbol: str, cache_dir: Path) -> tuple[list[dict[str, Any]], str | None]:
    try:
        df = ak.stock_zh_index_value_csindex(symbol=symbol)
    except Exception:
        return [], None
    output = cache_dir / f"{symbol}_csindex_valuation.csv"
    df.to_csv(output, index=False, encoding="utf-8-sig")
    latest = df.iloc[0]
    items = []
    if "市盈率1" in df.columns:
        pe = pd.to_numeric(df["市盈率1"], errors="coerce").dropna()
        current = float(latest["市盈率1"])
        percentile = (pe <= current).mean() * 100
        items.extend(
            [
                {
                    "label": "PE当前值",
                    "metric": "pe",
                    "category": "pe",
                    "value": f"{current:.2f}",
                    "source_id": "valuation_series",
                    "calculation_method": "中证指数公开估值序列最新值。",
                },
                {
                    "label": "PE区间",
                    "metric": "pe_range",
                    "category": "valuation_range",
                    "value": f"{pe.min():.2f}-{pe.max():.2f}",
                    "source_id": "valuation_series",
                    "calculation_method": "中证指数公开估值序列最小值到最大值。",
                },
                {
                    "label": "PE分位",
                    "metric": "pe_percentile",
                    "category": "valuation_percentile",
                    "value": f"{percentile:.1f}%",
                    "source_id": "valuation_series",
                    "calculation_method": "小于等于当前PE的历史样本占比。",
                },
            ]
        )
    if "股息率1" in df.columns:
        dy = float(latest["股息率1"])
        items.append(
            {
                "label": "股息率当前值",
                "metric": "dividend_yield",
                "category": "dividend_yield",
                "value": f"{dy:.2f}%",
                "source_id": "valuation_series",
                "calculation_method": "中证指数公开估值序列最新值。",
            }
        )
    return items, str(output)


def history_stats(df: pd.DataFrame) -> dict[str, Any]:
    points = df[["date", "close"]].to_dict("records")
    closes = df["close"].astype(float)
    running_max = closes.cummax()
    drawdowns = closes / running_max - 1
    max_drawdown = float(drawdowns.min())
    annual = df.assign(year=pd.to_datetime(df["date"]).dt.year).groupby("year").tail(1)
    annual_returns = annual.set_index("year")["close"].pct_change().dropna().tail(8)
    latest = df.iloc[-1]
    percentile = (closes <= float(latest["close"])).mean() * 100
    return {
        "points": points,
        "start_date": str(df.iloc[0]["date"]),
        "latest_date": str(latest["date"]),
        "latest_close": f"{float(latest['close']):.2f}",
        "level_range": f"{closes.min():.2f}-{closes.max():.2f}",
        "level_percentile": f"{percentile:.1f}%",
        "max_drawdown": f"{max_drawdown * 100:.2f}%",
        "annual_returns": {str(int(year)): f"{value * 100:.2f}%" for year, value in annual_returns.items()},
    }


def source_item(
    *,
    source_id: str,
    source_type: str,
    title: str,
    url: str | None = None,
    file: str | None = None,
    data_date: str,
    fields: list[str],
    calculation_method: str | None = None,
    allowed_for_final_numbers: bool = True,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_type": source_type,
        "title": title,
        "url": url,
        "file": file,
        "data_date": data_date,
        "fields": fields,
        "calculation_method": calculation_method,
        "human_confirmed": False,
        "allowed_for_final_numbers": allowed_for_final_numbers,
    }


def enrich_one(config: PriorityIndex) -> dict[str, Any]:
    profile = load_profile(config.index_id)
    cache_dir = SOURCE_CACHE / config.index_id
    cache_dir.mkdir(parents=True, exist_ok=True)

    if config.history_source == "akshare_cn":
        history = fetch_cn_history(config.symbol, cache_dir)
        top_holdings, holdings_file = fetch_cn_holdings(config.symbol, cache_dir)
        valuation_items, valuation_file = fetch_cn_valuation(config.symbol, cache_dir)
    else:
        history = fetch_yahoo_history(config.symbol, cache_dir)
        top_holdings, holdings_file = [], None
        valuation_items, valuation_file = [], None

    stats = history_stats(history)
    sample_range = f"{stats['start_date']} 至 {stats['latest_date']}"
    history_file = history.attrs.get("source_file")
    history_url = history.attrs.get("source_url")

    if not valuation_items:
        valuation_items = [
            {
                "label": "当前点位",
                "metric": "current_level",
                "category": "valuation_range",
                "value": stats["latest_close"],
                "source_id": "history_price_series",
                "calculation_method": "公开历史点位序列最新收盘值；用于点位区间观察，不等同于PE/PB估值。",
            },
            {
                "label": "点位历史区间",
                "metric": "level_range",
                "category": "valuation_range",
                "value": stats["level_range"],
                "source_id": "history_price_series",
                "calculation_method": "公开历史点位序列最小值到最大值；用于区间观察。",
            },
            {
                "label": "点位分位",
                "metric": "level_percentile",
                "category": "valuation_percentile",
                "value": stats["level_percentile"],
                "source_id": "history_price_series",
                "calculation_method": "公开历史点位序列中小于等于当前点位的样本占比。",
            },
        ]

    source_items = [
        source_item(
            source_id="official_index_page",
            source_type="official_index_page",
            title=f"{profile['basic_info']['index_name_cn']} 官方页面",
            url=config.official_url,
            data_date=stats["latest_date"],
            fields=["index_identity", "basic_info"],
            allowed_for_final_numbers=False,
        ),
        source_item(
            source_id="official_methodology",
            source_type="official_methodology",
            title=f"{profile['basic_info']['index_name_cn']} 编制规则入口",
            url=config.methodology_url,
            data_date=stats["latest_date"],
            fields=["methodology_reference"],
            allowed_for_final_numbers=False,
        ),
        source_item(
            source_id="history_price_series",
            source_type=config.source_type,
            title=config.source_label,
            url=history_url,
            file=history_file,
            data_date=stats["latest_date"],
            fields=["date", "close"],
            calculation_method="用于计算历史走势、年度收益、最大回撤、当前点位区间和点位分位。",
        ),
    ]
    if holdings_file:
        source_items.append(
            source_item(
                source_id="constituent_weight_series",
                source_type="public_constituent_weight_series",
                title=f"{profile['basic_info']['index_name_cn']} 成分权重",
                file=holdings_file,
                data_date=stats["latest_date"],
                fields=["constituent", "weight"],
            )
        )
    if valuation_file:
        source_items.append(
            source_item(
                source_id="valuation_series",
                source_type="public_valuation_series",
                title=f"{profile['basic_info']['index_name_cn']} 估值序列",
                file=valuation_file,
                data_date=stats["latest_date"],
                fields=["pe", "dividend_yield"],
                calculation_method="用于读取当前PE、股息率，并计算PE区间和分位。",
            )
        )

    annual_items = [
        {
            "label": f"{year}年度收益",
            "period": year,
            "return": value,
            "sample_range": sample_range,
            "calculation_method": "按年度最后一个交易日收盘点位计算年度收益。",
            "source_id": "history_price_series",
        }
        for year, value in stats["annual_returns"].items()
    ]

    profile["source_items"] = source_items
    profile["data_date"] = stats["latest_date"]
    profile["methodology_summary"] = {
        "status": "source_registered_needs_manual_parse",
        "summary": "已登记官方页面和编制规则入口；正式出片前仍需人工核验样本空间、选样规则、加权方式和调样频率。",
        "source_id": "official_methodology",
    }
    profile["historical_returns"] = {
        "status": "ready",
        "items": annual_items,
        "required_for_video": "04_return_drawdown_risk",
        "sample_range": sample_range,
    }
    profile["drawdown_stats"] = {
        "status": "ready",
        "items": [
            {
                "label": "最大回撤",
                "max_drawdown": stats["max_drawdown"],
                "calculation_range": sample_range,
                "calculation_method": "用公开收盘点位序列计算累计净值回撤。",
                "source_id": "history_price_series",
            }
        ],
        "required_for_video": "04_return_drawdown_risk",
    }
    profile["valuation_metrics"] = {
        "status": "ready",
        "items": valuation_items,
        "required_for_video": "05_valuation_view",
        "calculation_method": "优先使用公开估值序列；无法取得估值序列时，只登记点位区间和点位分位，不替代PE/PB估值。",
    }
    if top_holdings:
        profile["top_holdings"] = {
            "status": "ready",
            "items": top_holdings,
            "required_for_video": "02_holdings_breakdown",
        }

    missing = []
    for key in [
        "sector_weights",
        "top_holdings",
        "methodology_summary",
        "historical_returns",
        "drawdown_stats",
        "valuation_metrics",
    ]:
        section = profile.get(key)
        if not section or section.get("status") in {"missing", "needs_data", "needs_review", "needs_official_methodology"}:
            missing.append(key)
    if profile.get("methodology_summary", {}).get("status") == "source_registered_needs_manual_parse":
        missing.append("methodology_manual_parse")

    profile["missing_items"] = sorted(set(missing))
    profile["render_status"] = "ready_for_review" if not missing else "partially_enriched_needs_review"
    profile["data_status"] = "ready" if not missing else "needs_data"
    profile["review_status"] = "pending"
    write_profile(config.index_id, profile)

    return {
        "index_id": config.index_id,
        "data_status": profile["data_status"],
        "missing_items": profile["missing_items"],
        "history_rows": len(history),
        "history_latest": stats["latest_date"],
        "top_holdings": len(top_holdings),
        "valuation_items": len(valuation_items),
    }


def update_plan(results: list[dict[str, Any]]) -> None:
    by_id = {item["index_id"]: item for item in results}
    rows = read_plan()
    for row in rows:
        result = by_id.get(row.get("index_id"))
        if not result:
            continue
        if row.get("review_status") == "approved":
            continue
        row["data_status"] = result["data_status"]
        row["render_status"] = "ready_for_review" if result["data_status"] == "ready" else "partially_enriched_needs_review"
        row["notes"] = (
            f"已补历史走势、年度收益、最大回撤和区间数据；仍缺：{', '.join(result['missing_items'])}"
            if result["missing_items"]
            else "结构化数据已补齐；等待人工审核。"
        )
        row["review_status"] = "pending"
    write_plan(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich priority Global100 indexes with traceable structured data")
    parser.add_argument("--limit", type=int, default=21)
    parser.add_argument("--index", action="append", help="Only enrich selected index_id; can be repeated")
    args = parser.parse_args()

    wanted = set(args.index or [])
    configs = [item for item in PRIORITY_INDEXES if not wanted or item.index_id in wanted][: args.limit]
    results = []
    for item in configs:
        print(f"Enriching {item.index_id}...", flush=True)
        try:
            results.append(enrich_one(item))
        except Exception as exc:
            results.append({"index_id": item.index_id, "error": str(exc), "data_status": "needs_data", "missing_items": ["enrichment_failed"]})
    update_plan(results)
    output = GLOBAL100_DIR / "priority_enrichment_report.json"
    output.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
