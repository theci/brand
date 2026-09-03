"""자금 6:4 대시보드 (Phase 10) — 제품 60 : 마케팅 40, 런웨이·편차.

제품별 원가가 아니라 **사업 전체 자금 배분 시야**를 준다. 커머스 회계는 하지 않는다.
지출을 제품/마케팅/기타로 분류해 6:4 목표 대비 편차와 런웨이(잔여 개월)를 계산한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .core.models import Budget
from .loader import DATA_DIR

PRODUCT = "제품"
MARKETING = "마케팅"
OTHER = "기타"
CATEGORIES = (PRODUCT, MARKETING, OTHER)

# 6:4 목표 대비 이 이상 벗어나면 경고(±).
DEVIATION_WARN = 0.10
# 런웨이가 이 개월 미만이면 경고.
RUNWAY_WARN_MONTHS = 3.0


@dataclass
class BudgetSummary:
    total_capital: float
    total_spent: float
    remaining: float
    product_spent: float
    marketing_spent: float
    other_spent: float
    target_product_ratio: float
    product_ratio: float | None  # 제품/(제품+마케팅). 둘 다 0이면 None
    marketing_ratio: float | None
    deviation: float | None  # product_ratio - target (양수=제품 편중)
    runway_months: float | None
    warnings: list[str] = field(default_factory=list)


def summarize(budget: Budget) -> BudgetSummary:
    spent = {c: 0.0 for c in CATEGORIES}
    for e in budget.expenses:
        cat = e.category if e.category in spent else OTHER
        spent[cat] += e.amount

    product = round(spent[PRODUCT], 2)
    marketing = round(spent[MARKETING], 2)
    other = round(spent[OTHER], 2)
    total_spent = round(product + marketing + other, 2)
    remaining = round(budget.total_capital - total_spent, 2)

    base = product + marketing
    product_ratio = round(product / base, 4) if base > 0 else None
    marketing_ratio = round(marketing / base, 4) if base > 0 else None
    deviation = (
        round(product_ratio - budget.target_product_ratio, 4)
        if product_ratio is not None
        else None
    )

    runway = None
    if budget.monthly_burn and budget.monthly_burn > 0:
        runway = round(remaining / budget.monthly_burn, 1)

    warnings: list[str] = []
    if remaining < 0:
        warnings.append(f"자본 초과 지출: {-remaining:,.0f}원 적자.")
    if deviation is not None and deviation > DEVIATION_WARN:
        warnings.append(
            f"제품 편중 — 제품 {product_ratio:.0%} vs 목표 {budget.target_product_ratio:.0%}. 마케팅 투자 부족."
        )
    elif deviation is not None and deviation < -DEVIATION_WARN:
        warnings.append(
            f"마케팅 과다 — 제품 {product_ratio:.0%} vs 목표 {budget.target_product_ratio:.0%}. 제품력 투자 부족(철학: 마케팅은 제품력으로 수렴)."
        )
    if runway is not None and runway < RUNWAY_WARN_MONTHS:
        warnings.append(f"런웨이 {runway:g}개월 — 3개월 미만. 자금 계획 재검토.")

    return BudgetSummary(
        total_capital=round(budget.total_capital, 2),
        total_spent=total_spent,
        remaining=remaining,
        product_spent=product,
        marketing_spent=marketing,
        other_spent=other,
        target_product_ratio=budget.target_product_ratio,
        product_ratio=product_ratio,
        marketing_ratio=marketing_ratio,
        deviation=deviation,
        runway_months=runway,
        warnings=warnings,
    )


def save_budget(budget: Budget, path: Path | str = DATA_DIR / "brand" / "budget.yaml") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(budget.model_dump(exclude_none=True), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


__all__ = [
    "PRODUCT",
    "MARKETING",
    "OTHER",
    "CATEGORIES",
    "BudgetSummary",
    "summarize",
    "save_budget",
]
