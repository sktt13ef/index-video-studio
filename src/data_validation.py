from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .data_used_builder import parse_numeric, percent_sum
from .source_registry import validate_source_items


PLACEHOLDER_WORDS = ("暂无", "未提供", "缺失", "数据缺失")


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details,
        }


def validate_episode_payload(payload: dict[str, Any]) -> ValidationResult:
    metadata = payload.get("metadata") or {}
    data_used = payload.get("data_used") or {}
    features = payload.get("features") or {}
    visual_text = payload.get("visual_text") or []
    source_items = metadata.get("source_items") or data_used.get("source_items") or []
    numbers = data_used.get("numbers") or []

    errors: list[str] = []
    warnings: list[str] = []

    required_fields = {
        "index_name": "指数名称不能为空",
        "index_code": "指数代码不能为空",
        "index_type": "指数类型不能为空",
        "data_date": "数据日期必须写入 manifest.json",
    }
    for field_name, message in required_fields.items():
        if not str(metadata.get(field_name, "")).strip():
            errors.append(message)

    errors.extend(validate_source_items(source_items))

    joined_visual_text = "\n".join(str(item) for item in visual_text)
    for word in PLACEHOLDER_WORDS:
        if word in joined_visual_text:
            errors.append(f"成品画面不得出现占位表达：{word}")

    if features.get("sector_weights"):
        sector_numbers = [item for item in numbers if item.get("category") == "sector_weight"]
        if not sector_numbers:
            errors.append("展示行业权重时，data_used.json 必须记录 sector_weight 数字")
        for item in sector_numbers:
            if parse_numeric(item.get("value")) is None:
                errors.append(f"行业权重不是数值：{item.get('label')}")
        total = percent_sum([item.get("value") for item in sector_numbers])
        if sector_numbers and not (0 < total <= 100.5):
            errors.append(f"行业权重合计不在合理范围：{total:.2f}%")

    if features.get("top_holdings"):
        holding_numbers = [item for item in numbers if item.get("category") == "holding_weight"]
        if not holding_numbers:
            errors.append("展示前十大权重时，data_used.json 必须记录 holding_weight 数字")
        for item in holding_numbers:
            if parse_numeric(item.get("value")) is None:
                errors.append(f"前十大权重不是数值：{item.get('label')}")

    if features.get("valuation_metrics"):
        valuation_numbers = [item for item in numbers if item.get("category") in {"pe", "pb", "dividend_yield", "valuation_percentile", "valuation_range"}]
        if not valuation_numbers:
            errors.append("展示 PE/PB/股息率时，data_used.json 必须记录估值数字")
        for item in valuation_numbers:
            if not str(item.get("source_id", "")).strip():
                errors.append(f"估值数字缺少数据来源：{item.get('label')}")
            if not str(item.get("calculation_method", "")).strip():
                errors.append(f"估值数字缺少计算口径：{item.get('label')}")

    if features.get("max_drawdown"):
        drawdown_numbers = [item for item in numbers if item.get("category") == "max_drawdown"]
        if not drawdown_numbers:
            errors.append("展示最大回撤时，data_used.json 必须记录 max_drawdown")
        for item in drawdown_numbers:
            if not str(item.get("calculation_range", "")).strip():
                errors.append("最大回撤必须有计算区间")
            if not (item.get("source_url") or item.get("source_file")):
                errors.append("最大回撤必须有历史点位来源")

    if features.get("historical_returns"):
        return_numbers = [item for item in numbers if item.get("category") == "historical_return"]
        if not return_numbers:
            errors.append("展示历史收益时，data_used.json 必须记录 historical_return")
        for item in return_numbers:
            if not str(item.get("sample_range", "")).strip():
                errors.append(f"历史收益必须有样本区间说明：{item.get('label')}")

    if not numbers:
        warnings.append("本集未记录展示数字；只适用于无数字的信息类视频")

    return ValidationResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        details={
            "number_count": len(numbers),
            "source_count": len(source_items),
            "features": features,
        },
    )


def assert_valid(result: ValidationResult) -> None:
    if not result.passed:
        raise ValueError("数据校验未通过：" + "; ".join(result.errors))


def blocked_profile_update(profile: dict[str, Any], result: ValidationResult) -> dict[str, Any]:
    updated = dict(profile)
    if not result.passed:
        updated["data_status"] = "needs_review"
        updated["render_status"] = "blocked_until_ready"
        updated["validation_errors"] = result.errors
    return updated
