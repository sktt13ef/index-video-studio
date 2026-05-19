from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataNumber:
    label: str
    value: str
    category: str
    source_field: str
    source_id: str
    source_url: str | None
    source_file: str | None
    data_date: str
    calculation_method: str
    human_confirmed: bool = False
    display_context: str | None = None
    sample_range: str | None = None
    calculation_range: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "category": self.category,
            "source_field": self.source_field,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "source_file": self.source_file,
            "data_date": self.data_date,
            "calculation_method": self.calculation_method,
            "human_confirmed": self.human_confirmed,
            "display_context": self.display_context,
            "sample_range": self.sample_range,
            "calculation_range": self.calculation_range,
        }


@dataclass
class DataUsedBuilder:
    index_id: str
    episode: int
    episode_slug: str
    source_items: list[dict[str, Any]]
    data_date: str
    numbers: list[DataNumber] = field(default_factory=list)

    def add_number(
        self,
        *,
        label: str,
        value: str | int | float,
        category: str,
        source_field: str,
        source_id: str,
        calculation_method: str,
        human_confirmed: bool = False,
        display_context: str | None = None,
        sample_range: str | None = None,
        calculation_range: str | None = None,
    ) -> None:
        source = self._source(source_id)
        self.numbers.append(
            DataNumber(
                label=label,
                value=str(value),
                category=category,
                source_field=source_field,
                source_id=source_id,
                source_url=source.get("url"),
                source_file=source.get("file"),
                data_date=str(source.get("data_date") or self.data_date),
                calculation_method=calculation_method,
                human_confirmed=human_confirmed,
                display_context=display_context,
                sample_range=sample_range,
                calculation_range=calculation_range,
            )
        )

    def build(self) -> dict[str, Any]:
        return {
            "index_id": self.index_id,
            "episode": self.episode,
            "episode_slug": self.episode_slug,
            "data_date": self.data_date,
            "source_items": self.source_items,
            "numbers": [number.to_dict() for number in self.numbers],
        }

    def _source(self, source_id: str) -> dict[str, Any]:
        for source in self.source_items:
            if source.get("source_id") == source_id:
                return source
        raise KeyError(f"未找到数据源：{source_id}")


def parse_numeric(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    text = re.sub(r"[^\d.\-]", "", text)
    if text in {"", "-", ".", "-."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def percent_sum(values: list[Any]) -> float:
    nums = [parse_numeric(value) for value in values]
    return sum(num for num in nums if num is not None)
