"""규제 레짐(regulatory regime) 추상화.

각 레짐(화장품법, 화학제품안전법, …)이 구현하는 공통 인터페이스와,
그 결과를 담는 레짐 무관 자료구조를 정의한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..core.models import Formula


class UnsupportedRegimeError(Exception):
    """지원하지 않는 레짐에 대해 비용/라벨 등을 요청할 때 발생."""


@dataclass
class Finding:
    """검증 결과 1건."""

    level: str  # "error" | "warning" | "info"
    code: str
    message: str
    reference: str | None = None


@dataclass
class LabelItem:
    key: str
    label: str
    required: bool = True
    note: str | None = None


@dataclass
class LabelSpec:
    """라벨 필수 기재 항목 명세."""

    regime_code: str
    items: list[LabelItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class CostBreakdown:
    """진입/규제 비용 내역."""

    regime_code: str
    entry_cost: int
    currency: str = "KRW"
    lead_time_days: int = 0
    detail: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@runtime_checkable
class Regime(Protocol):
    """규제 레짐 인터페이스. 새 레짐은 이 프로토콜을 구현하고 registry에 등록한다."""

    code: str
    law_name: str
    display_name: str

    def validate(self, product: Formula) -> list[Finding]: ...

    def label_spec(self, product: Formula) -> LabelSpec: ...

    def entry_cost(self, product: Formula) -> CostBreakdown: ...

    def lead_time_days(self, product: Formula) -> int: ...

    def sku_expansion_cost(self, product: Formula) -> int: ...

    def renewal_period_years(self, product: Formula) -> int | None: ...


__all__ = [
    "Finding",
    "LabelItem",
    "LabelSpec",
    "CostBreakdown",
    "Regime",
    "UnsupportedRegimeError",
]
