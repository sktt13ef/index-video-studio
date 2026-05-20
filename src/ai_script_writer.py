from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests


FORBIDDEN_TERMS = [
    "科普",
    "新手",
    "小白",
    "评分",
    "推荐买入",
    "可以买",
    "可以上车",
    "值得买",
    "闭眼买",
    "无脑买",
    "稳赚",
    "必涨",
    "低风险",
    "更安全",
    "吊打",
    "封神",
]

HOLLOW_PHRASES = [
    "不要只看名字",
    "别只看名字",
    "不要只看收益",
    "不是万能",
    "交易按钮",
    "仪表盘",
    "真正有用",
    "先定角色",
    "再讨论比例",
    "能接受波动",
    "长期持有",
    "看清楚风险",
    "不能只看一个数字",
    "不构成投资建议",
    "本视频由 AI 辅助生成",
    "感谢观看",
]

TIME_WORDS = [
    "今年以来",
    "上个月",
    "最近",
    "近几天",
    "近期",
    "明年",
    "下半年",
]

UNSUPPORTED_FACT_WORDS = [
    "ST",
    "季度",
    "月度",
    "年以来",
    "调样调整",
    "银行股占",
    "前八大",
    "超过四成",
    "未超过",
    "三分之一",
    "两成",
    "三足鼎立",
    "相对可控",
]


@dataclass
class AIScriptResult:
    scene_narrations: list[str]
    provider: str
    model: str
    prompt: str
    raw_response: str
    attempts: int
    checks: dict[str, Any]


class AIScriptError(RuntimeError):
    pass


class AIScriptWriter:
    def __init__(self, model: str | None = None, endpoint: str | None = None, timeout: int = 180) -> None:
        self.endpoint = endpoint or os.getenv("INDEX_VIDEO_OLLAMA_URL", "http://127.0.0.1:11434")
        self.model = model or os.getenv("INDEX_VIDEO_LLM_MODEL") or self._pick_ollama_model()
        self.timeout = timeout

    def _pick_ollama_model(self) -> str:
        tags_url = f"{self.endpoint.rstrip('/')}/api/tags"
        try:
            response = requests.get(tags_url, timeout=8)
            response.raise_for_status()
            models = [item.get("name", "") for item in response.json().get("models", [])]
        except Exception as exc:  # noqa: BLE001
            raise AIScriptError(f"本地 AI 服务不可用：{exc}") from exc
        preferred = ["qwen3.6:35b", "qwen3:14b", "glm-4.7-flash:q8_0", "gemma3:12b"]
        for name in preferred:
            if name in models:
                return name
        if models:
            return models[0]
        raise AIScriptError("本地 AI 服务没有可用模型。")

    def rewrite_episode(self, profile: dict[str, Any], episode: Any) -> tuple[Any, AIScriptResult]:
        prompt = build_prompt(profile, episode)
        feedback = ""
        last_raw = ""
        last_checks: dict[str, Any] = {}
        for attempt in range(1, 6):
            raw = self._generate(prompt, feedback)
            last_raw = raw
            payload = extract_json(raw)
            narrations = payload.get("scene_narrations")
            if not isinstance(narrations, list):
                feedback = "上次输出不合格：scene_narrations 必须是数组。"
                continue
            if len(narrations) < len(episode.scenes):
                feedback = "上次输出不合格：scene_narrations 数量少于画面数量。"
                continue
            if len(narrations) > len(episode.scenes):
                narrations = narrations[: len(episode.scenes)]
            narrations = [clean_text(str(item)) for item in narrations]
            checks = validate_narrations(narrations, prompt)
            last_checks = checks
            if checks["passed"]:
                for scene, narration in zip(episode.scenes, narrations, strict=True):
                    scene.narration = narration
                return episode, AIScriptResult(
                    scene_narrations=narrations,
                    provider="ollama",
                    model=self.model,
                    prompt=prompt,
                    raw_response=raw,
                    attempts=attempt,
                    checks=checks,
                )
            feedback = (
                "上次输出不合格，请在上一版基础上扩写，不要改变事实。"
                "每个场景补到两句话即可，总字数必须控制在 240 到 340 个中文字符，"
                "可以解释这些事实为什么影响指数边界、权重或风险，但不能跨集数。问题："
                + "；".join(checks["issues"])
                + "\n上一版输出："
                + json.dumps({"scene_narrations": narrations}, ensure_ascii=False)
            )
        raise AIScriptError(f"AI 解说词五次生成仍未通过：{last_checks.get('issues', [])}\n最后输出：{last_raw[:500]}")

    def _generate(self, prompt: str, feedback: str = "") -> str:
        body = {
            "model": self.model,
            "prompt": prompt + ("\n\n" + feedback if feedback else ""),
            "stream": False,
            "options": {
                "temperature": 0.55,
                "top_p": 0.9,
                "num_ctx": 8192,
            },
        }
        response = requests.post(f"{self.endpoint.rstrip('/')}/api/generate", json=body, timeout=self.timeout)
        response.raise_for_status()
        return str(response.json().get("response", "")).strip()


def build_prompt(profile: dict[str, Any], episode: Any) -> str:
    pack = data_pack(profile, episode)
    return f"""你是指数观察短视频的中文解说词作者。请为一个竖屏视频单独写口播稿。

硬性规则：
1. 只使用我给你的结构化数据，不要补充任何外部事实，不要编数字。
2. 不要出现这些词：{", ".join(FORBIDDEN_TERMS)}。
3. 不要出现这些模板腔：{", ".join(HOLLOW_PHRASES)}。
4. 不要写“今年以来、最近、上个月、近期”等强时效表达；不要在口播中写具体年月日。
5. 不预测未来涨跌，不评价绝对好坏，不给投资动作。
6. 每个场景口播必须紧贴该场景画面；只能使用 topic_data 和 visual_scenes 里的信息，不能跨到其他集数的话题。
7. 语言要像认真讲给普通投资者听，短句、具体、少形容词，不要研报腔。
8. 整条视频的四个场景合计 240 到 340 个中文字符；每个场景尽量写成两句话，太短或太长都会被系统拒绝。
9. 每个场景至少讲两个具体事实，并解释这些事实为什么重要，例如样本范围、筛选逻辑、调样频率、行业权重、前十大、回撤、PE区间、股息率或组合角色。
10. 不要自行计算“前八大合计、两年累计、超过几成”等派生数字；只有 topic_data 明确给出的数字才能写。
11. 只输出 JSON。

输出 JSON 格式：
{{
  "scene_narrations": ["场景1口播", "场景2口播", "场景3口播", "场景4口播"]
}}

结构化数据：
{json.dumps(pack, ensure_ascii=False, indent=2)}
"""


def data_pack(profile: dict[str, Any], episode: Any) -> dict[str, Any]:
    basic = profile["basic_info"]
    shared = {
        "index": {
            "id": profile.get("index_id"),
            "name": basic.get("index_name_cn"),
            "code": basic.get("index_code"),
            "type": basic.get("index_type"),
            "provider": basic.get("provider"),
            "region": basic.get("region"),
        },
        "episode": {
            "number": episode.number,
            "slug": episode.slug,
            "title": episode.title,
            "subtitle": episode.subtitle,
        },
        "visual_scenes": sanitize_for_prompt([scene_digest(scene, i) for i, scene in enumerate(episode.scenes, 1)]),
    }
    if episode.number == 1:
        shared["topic_data"] = {
            "methodology": sanitize_for_prompt(profile.get("methodology_summary", {})),
            "allowed_focus": "只解释样本范围、筛选逻辑、调样频率和指数边界，不讲行业、估值、收益、回撤。",
        }
    elif episode.number == 2:
        shared["topic_data"] = {
            "sector_weights_top3": sanitize_for_prompt(profile.get("sector_weights", {}).get("items", [])[:3]),
            "top_holding": sanitize_for_prompt((profile.get("top_holdings", {}).get("items") or [{}])[0]),
            "top10_weight_sum": _top10_sum(profile),
            "top2_sector_weight_sum": _sector_sum(profile, 2),
            "top3_sector_weight_sum": _sector_sum(profile, 3),
            "risk_points": profile.get("risk_points", {}).get("items", [])[:2],
            "allowed_focus": "只解释行业分布、前十大权重和集中度，不讲估值、历史收益、回撤。",
        }
    elif episode.number == 3:
        shared["topic_data"] = {
            "role_in_portfolio": sanitize_for_prompt(profile.get("role_in_portfolio", {})),
            "methodology": sanitize_for_prompt(profile.get("methodology_summary", {})),
            "risk_points": profile.get("risk_points", {}).get("items", [])[:3],
            "allowed_focus": "只解释组合中的分工、适合观察的资产暴露、不承担的任务，不讲估值和历史收益。",
        }
    elif episode.number == 4:
        shared["topic_data"] = {
            "historical_returns_recent": sanitize_for_prompt(profile.get("historical_returns", {}).get("items", [])[-5:]),
            "drawdown": sanitize_for_prompt((profile.get("drawdown_stats", {}).get("items") or [{}])[0]),
            "risk_points": profile.get("risk_points", {}).get("items", [])[:4],
            "allowed_focus": "只解释历史收益、历史走势、最大回撤和风险，不讲估值。",
        }
    elif episode.number == 5:
        shared["topic_data"] = {
            "valuation_metrics": sanitize_for_prompt(profile.get("valuation_metrics", {}).get("items", [])),
            "risk_points": profile.get("risk_points", {}).get("items", [])[:3],
            "allowed_focus": "只解释估值指标、估值区间、分位和股息率，不讲历史收益和最大回撤。",
        }
    return shared


def _top10_sum(profile: dict[str, Any]) -> str:
    total = 0.0
    for item in profile.get("top_holdings", {}).get("items", [])[:10]:
        total += float(str(item.get("weight", "0")).replace("%", "").replace(",", ""))
    return f"{total:.1f}%"


def _sector_sum(profile: dict[str, Any], count: int) -> str:
    total = 0.0
    for item in profile.get("sector_weights", {}).get("items", [])[:count]:
        total += float(str(item.get("weight", "0")).replace("%", "").replace(",", ""))
    return f"{total:.1f}%"


def scene_digest(scene: Any, scene_number: int) -> dict[str, Any]:
    digest: dict[str, Any] = {
        "scene": scene_number,
        "kind": scene.kind,
        "heading": scene.heading,
        "summary": scene.summary,
    }
    if scene.kind == "bars":
        digest["items"] = scene.items[:3]
    elif scene.kind == "table":
        digest["items"] = scene.items[:1]
        digest["table_summary"] = scene.summary
    elif scene.kind in {"metrics", "role"}:
        digest["items"] = scene.items
    elif scene.kind == "bullets":
        digest["items"] = scene.items[:3]
    else:
        digest["items"] = scene.items[:2] if isinstance(scene.items, list) else scene.items
    return digest


def sanitize_for_prompt(value: Any) -> Any:
    if isinstance(value, list):
        return [sanitize_for_prompt(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"sample_range", "calculation_range", "data_date"}:
                continue
            if key == "period" and re.fullmatch(r"\d{4}", str(item)):
                result[key] = "某年度样本"
                continue
            result[key] = sanitize_for_prompt(item)
        return result
    if isinstance(value, str):
        value = re.sub(r"\d{4}-\d{1,2}-\d{1,2}\s*至\s*\d{4}-\d{1,2}-\d{1,2}", "公开历史样本区间", value)
        value = re.sub(r"\d{4}年度", "某年度", value)
        value = re.sub(r"\d{4}年", "某年", value)
        value = re.sub(r"\d{4}年\d{1,2}月|\d{1,2}月\d{1,2}日", "目前", value)
    return value


def extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise AIScriptError("AI 输出不是 JSON。")
        return json.loads(match.group(0))


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = text.replace("；；", "；").replace("。。", "。")
    return text


def validate_narrations(narrations: list[str], allowed_text: str = "") -> dict[str, Any]:
    issues: list[str] = []
    joined = "".join(narrations)
    for term in FORBIDDEN_TERMS + HOLLOW_PHRASES + TIME_WORDS + UNSUPPORTED_FACT_WORDS:
        if term == "低风险":
            if re.search(r"(?<!降)低风险", joined):
                issues.append(f"出现禁用或空泛表达：{term}")
            continue
        if term in joined:
            issues.append(f"出现禁用或空泛表达：{term}")
    if re.search(r"\d{4}年|\d{4}年\d{1,2}月|\d{1,2}月\d{1,2}日", joined):
        issues.append("出现具体年份或年月日。")
    allowed_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", allowed_text))
    allowed_normalized = {_normalize_number(item) for item in allowed_numbers}
    allowed_variants = _number_variants(allowed_numbers)
    for number in re.findall(r"\d+(?:\.\d+)?%?", joined):
        if number not in allowed_numbers and _normalize_number(number) not in allowed_normalized and number not in allowed_variants:
            issues.append(f"出现未在数据包中的数字：{number}")
    for i, text in enumerate(narrations, 1):
        length = len(text)
        if length < 42 or length > 110:
            issues.append(f"场景{i}长度不合适：{length}字")
    if sum(len(item) for item in narrations) < 240:
        issues.append("四个场景合计少于240字。")
    if sum(len(item) for item in narrations) > 340:
        issues.append("四个场景合计超过340字。")
    return {
        "passed": not issues,
        "issues": issues,
        "char_counts": [len(item) for item in narrations],
    }


def _normalize_number(value: str) -> str:
    suffix = "%" if value.endswith("%") else ""
    raw = value[:-1] if suffix else value
    try:
        return f"{float(raw):.4f}{suffix}"
    except ValueError:
        return value


def _number_variants(values: set[str]) -> set[str]:
    variants: set[str] = set()
    for value in values:
        if not value.endswith("%"):
            continue
        raw = value[:-1]
        try:
            numeric = float(raw)
        except ValueError:
            continue
        variants.add(f"{int(numeric)}%")
        variants.add(f"{round(numeric)}%")
    return variants
