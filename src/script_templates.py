from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .compliance_check import check_text_compliance


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "templates" / "scripts"
REQUIRED_TEMPLATE_TYPES = [
    "broad_based",
    "dividend",
    "sector",
    "overseas",
    "strategy",
    "technology",
    "low_volatility",
]
EPISODE_SLUGS = [
    "01_index_intro",
    "02_holdings_breakdown",
    "03_portfolio_role",
    "04_return_drawdown_risk",
    "05_valuation_view",
]
CTA = "感谢观看，可以点点关注，继续了解更多指数观察。"


class SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def load_template_group(template_type: str, root: Path = TEMPLATE_ROOT) -> dict[str, Any]:
    path = root / template_type / "episodes.json"
    if not path.exists():
        raise FileNotFoundError(f"脚本模板不存在：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_script_templates(root: Path = TEMPLATE_ROOT) -> dict[str, dict[str, Any]]:
    return {template_type: load_template_group(template_type, root) for template_type in REQUIRED_TEMPLATE_TYPES}


def resolve_script_template_key(index_type: str, template_type: str | None = None) -> str:
    value = (template_type or index_type or "").strip()
    if value in {"overseas", "overseas_broad_based"}:
        return "overseas"
    if value in {"technology", "technology_growth"}:
        return "technology"
    if value in {"dividend", "dividend_strategy"}:
        return "dividend"
    if value in REQUIRED_TEMPLATE_TYPES:
        return value
    if index_type in REQUIRED_TEMPLATE_TYPES:
        return index_type
    raise ValueError(f"暂不支持的脚本模板类型：index_type={index_type}, template_type={template_type}")


def validate_template_group(group: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    template_type = group.get("template_type")
    episodes = group.get("episodes") or []
    if template_type not in REQUIRED_TEMPLATE_TYPES:
        errors.append(f"未知模板类型：{template_type}")
    if len(episodes) != 5:
        errors.append(f"{template_type} 必须包含 5 条 episode 模板，当前 {len(episodes)} 条")
    slugs = [episode.get("slug") for episode in episodes]
    if slugs != EPISODE_SLUGS:
        errors.append(f"{template_type} episode 顺序不正确：{slugs}")
    for episode in episodes:
        prefix = f"{template_type}/{episode.get('slug')}"
        for field in ["title_template", "single_theme", "required_data", "visual_cards", "risk_point", "angle_rules", "script_template"]:
            if not episode.get(field):
                errors.append(f"{prefix} 缺少字段：{field}")
        compliance = check_text_compliance(
            script=episode.get("script_template", ""),
            visual_text=[episode.get("title_template", ""), episode.get("risk_point", ""), episode.get("single_theme", "")],
        )
        if not compliance.passed:
            errors.extend([f"{prefix} {error}" for error in compliance.errors])
    return errors


def validate_all_script_templates(root: Path = TEMPLATE_ROOT) -> dict[str, Any]:
    errors: list[str] = []
    groups: dict[str, dict[str, Any]] = {}
    for template_type in REQUIRED_TEMPLATE_TYPES:
        try:
            group = load_template_group(template_type, root)
            groups[template_type] = group
            errors.extend(validate_template_group(group))
        except Exception as exc:
            errors.append(str(exc))
    return {
        "passed": not errors,
        "errors": errors,
        "template_count": len(groups),
        "episode_count": sum(len(group.get("episodes", [])) for group in groups.values()),
    }


def context_from_profile(profile: dict[str, Any]) -> dict[str, str]:
    basic = profile.get("basic_info") or {}
    role = profile.get("role_in_portfolio") or {}
    return {
        "index_id": str(profile.get("index_id", "")),
        "index_name": str(basic.get("index_name_cn") or basic.get("index_name_en") or ""),
        "index_name_en": str(basic.get("index_name_en") or ""),
        "index_code": str(basic.get("index_code") or ""),
        "provider": str(basic.get("provider") or ""),
        "region": str(basic.get("region") or ""),
        "market": str(basic.get("market") or basic.get("region") or ""),
        "currency": str(basic.get("currency") or ""),
        "index_type": str(basic.get("index_type") or ""),
        "template_type": str(basic.get("template_type") or ""),
        "role_summary": str(role.get("summary") or basic.get("catalog_focus") or "这类资产暴露"),
    }


def render_episode_draft(template: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
    values = SafeFormatDict(context)
    script = template["script_template"].format_map(values)
    if CTA not in script:
        script += CTA
    return {
        "episode": template["episode"],
        "slug": template["slug"],
        "title": template["title_template"].format_map(values),
        "single_theme": template["single_theme"],
        "script": script,
        "required_data": template["required_data"],
        "visual_cards": template["visual_cards"],
        "risk_point": template["risk_point"].format_map(values),
        "angle_rules": template["angle_rules"],
    }


def render_five_episode_drafts(profile: dict[str, Any], root: Path = TEMPLATE_ROOT) -> list[dict[str, Any]]:
    basic = profile.get("basic_info") or {}
    key = resolve_script_template_key(str(basic.get("index_type", "")), str(basic.get("template_type", "")))
    group = load_template_group(key, root)
    errors = validate_template_group(group)
    if errors:
        raise ValueError("脚本模板校验失败：" + "; ".join(errors))
    context = context_from_profile(profile)
    return [render_episode_draft(episode, context) for episode in group["episodes"]]


def main() -> None:
    result = validate_all_script_templates()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
