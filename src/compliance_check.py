from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


FORBIDDEN_PATTERNS: dict[str, str] = {
    "science_popularization": r"科普",
    "beginner_labels": r"新手|小白",
    "score_language": r"评分",
    "investment_advice": r"推荐买入|可以上车|值得买|闭眼买|无脑买",
    "exaggerated_claims": r"稳赚|必涨|低风险|更安全|吊打|封神",
    "empty_data_placeholders": r"暂无|未提供|缺失|数据缺失",
    "market_prediction": r"未来一定|马上上涨|马上下跌|必然上涨|必然下跌",
}


@dataclass
class CheckResult:
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


def normalize_texts(*values: Any) -> list[str]:
    texts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            texts.extend(normalize_texts(*value.values()))
        elif isinstance(value, (list, tuple, set)):
            texts.extend(normalize_texts(*value))
        else:
            texts.append(str(value))
    return texts


def check_text_compliance(
    *,
    script: str,
    visual_text: list[str] | None = None,
    extra_text: list[str] | None = None,
) -> CheckResult:
    texts = [script]
    if visual_text:
        texts.extend(visual_text)
    if extra_text:
        texts.extend(extra_text)
    combined = "\n".join(normalize_texts(texts))

    errors: list[str] = []
    matches: dict[str, list[str]] = {}
    for rule, pattern in FORBIDDEN_PATTERNS.items():
        found = sorted(set(re.findall(pattern, combined)))
        if found:
            matches[rule] = found
            errors.append(f"命中禁用表达 {rule}: {', '.join(found)}")

    return CheckResult(
        passed=not errors,
        errors=errors,
        details={"forbidden_matches": matches, "checked_text_count": len(texts)},
    )


def assert_compliance(result: CheckResult) -> None:
    if not result.passed:
        raise ValueError("合规检查未通过：" + "; ".join(result.errors))
