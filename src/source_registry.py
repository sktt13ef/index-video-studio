from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = ROOT / "data" / "global50" / "sources" / "source_registry.json"


def load_source_registry(path: str | Path | None = None) -> dict[str, Any]:
    registry_path = Path(path) if path else DEFAULT_REGISTRY_PATH
    if not registry_path.exists():
        return {
            "version": 0,
            "source_policy": {
                "principle": "AI 只负责表达，不负责事实。",
                "ready_rule": "只有 data_status = ready 的指数才能进入视频生成。",
            },
            "source_types": {},
        }
    return json.loads(registry_path.read_text(encoding="utf-8"))


def normalize_source_item(
    *,
    source_id: str,
    source_type: str,
    title: str,
    url: str | None = None,
    file: str | None = None,
    data_date: str,
    fields: list[str] | None = None,
    calculation_method: str | None = None,
    human_confirmed: bool = False,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_type": source_type,
        "title": title,
        "url": url,
        "file": file,
        "data_date": data_date,
        "fields": fields or [],
        "calculation_method": calculation_method,
        "human_confirmed": human_confirmed,
    }


def validate_source_items(source_items: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not source_items:
        return ["数据来源不能为空"]
    for index, item in enumerate(source_items, start=1):
        prefix = f"source_items[{index}]"
        if not str(item.get("source_id", "")).strip():
            errors.append(f"{prefix}.source_id 不能为空")
        if not str(item.get("source_type", "")).strip():
            errors.append(f"{prefix}.source_type 不能为空")
        if not str(item.get("data_date", "")).strip():
            errors.append(f"{prefix}.data_date 不能为空")
        if not str(item.get("url") or item.get("file") or "").strip():
            errors.append(f"{prefix} 必须包含 url 或 file")
    return errors


def source_ref(source_items: list[dict[str, Any]], source_id: str) -> dict[str, Any]:
    for item in source_items:
        if item.get("source_id") == source_id:
            return item
    raise KeyError(f"未找到数据源：{source_id}")
