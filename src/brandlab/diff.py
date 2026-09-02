"""처방 버전 비교(diff).

두 버전(old → new)의 원료 구성·함량 변화와 개당 원가 변화를 계산한다.
개선 이력을 추적해 "무엇을 바꿔서 원가가 어떻게 달라졌는지"를 한 표로 본다.

물성(보습력 등)은 계산하지 않는다. 여기서 다루는 것은 처방서에 적힌 값
(원료·함량·원가)의 변화뿐이다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .core.costing import unit_cost
from .core.models import (
    Formula,
    Ingredient,
    IngredientMaster,
    Packaging,
    PackagingMaster,
)

# 함량 변화로 보지 않을 오차(부동소수점 잡음 제거).
_EPS = 1e-9


@dataclass
class IngredientDelta:
    """원료 1종의 버전 간 함량 변화."""

    id: str
    name: str
    old_percent: float | None  # None = 이번 버전에서 신규
    new_percent: float | None  # None = 이번 버전에서 삭제
    change: str  # "신규" | "삭제" | "증량" | "감량" | "유지"

    @property
    def delta(self) -> float | None:
        if self.old_percent is None or self.new_percent is None:
            return None
        return round(self.new_percent - self.old_percent, 4)


@dataclass
class CostDelta:
    """개당 원가 변화. 계산 불가(내용량 미기재 등)면 값은 None, note에 사유."""

    old_material: float | None = None
    new_material: float | None = None
    old_unit: float | None = None
    new_unit: float | None = None
    note: str | None = None

    @property
    def material_delta(self) -> float | None:
        if self.old_material is None or self.new_material is None:
            return None
        return round(self.new_material - self.old_material, 2)

    @property
    def unit_delta(self) -> float | None:
        if self.old_unit is None or self.new_unit is None:
            return None
        return round(self.new_unit - self.old_unit, 2)


@dataclass
class FormulaDiff:
    slug: str
    old_version: int
    new_version: int
    old_product: str
    new_product: str
    lines: list[IngredientDelta]
    cost: CostDelta
    warnings: list[str] = field(default_factory=list)

    @property
    def changed_lines(self) -> list[IngredientDelta]:
        return [l for l in self.lines if l.change != "유지"]


def _ingredient_index(
    ingredients: IngredientMaster | Mapping[str, Ingredient],
) -> dict[str, Ingredient]:
    if isinstance(ingredients, IngredientMaster):
        return ingredients.index()
    return dict(ingredients)


def _aggregate(formula: Formula) -> tuple[dict[str, float], list[str]]:
    """같은 원료가 여러 상에 있으면 합산. (함량맵, 등장순서 id리스트)."""
    agg: dict[str, float] = {}
    order: list[str] = []
    for fi in (i for p in formula.phases for i in p.ingredients):
        if fi.id not in agg:
            order.append(fi.id)
        agg[fi.id] = agg.get(fi.id, 0.0) + fi.percent
    return agg, order


def _classify(old: float | None, new: float | None) -> str:
    if old is None:
        return "신규"
    if new is None:
        return "삭제"
    if abs(new - old) < _EPS:
        return "유지"
    return "증량" if new > old else "감량"


def _cost_delta(
    old: Formula,
    new: Formula,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    packaging: PackagingMaster | Mapping[str, Packaging] | None,
    units: int,
) -> CostDelta:
    pkg: PackagingMaster | Mapping[str, Packaging] = packaging if packaging is not None else {}
    try:
        oc = unit_cost(old, units, ingredients=ingredients, packaging=pkg)
        nc = unit_cost(new, units, ingredients=ingredients, packaging=pkg)
    except ValueError as exc:
        return CostDelta(note=f"원가 비교 불가: {exc}")
    return CostDelta(
        old_material=oc.material_cost,
        new_material=nc.material_cost,
        old_unit=oc.unit_cost,
        new_unit=nc.unit_cost,
    )


def formula_diff(
    old: Formula,
    new: Formula,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    packaging: PackagingMaster | Mapping[str, Packaging] | None = None,
    cost_units: int = 1000,
) -> FormulaDiff:
    """두 처방 버전을 비교한다.

    - 원료별 함량 변화(신규/삭제/증량/감량/유지)
    - 개당 원료비·원가 변화(cost_units 수량 기준, 내용량이 있어야 계산)
    """
    idx = _ingredient_index(ingredients)
    warnings: list[str] = []
    if old.slug != new.slug:
        warnings.append(
            f"슬러그가 다릅니다({old.slug} ≠ {new.slug}). 서로 다른 제품을 비교하고 있습니다."
        )

    old_agg, old_order = _aggregate(old)
    new_agg, new_order = _aggregate(new)
    # 신규 버전 등장 순서를 우선, 그 뒤에 삭제된 원료를 붙인다.
    ordered_ids = list(dict.fromkeys(new_order + old_order))

    lines: list[IngredientDelta] = []
    for ing_id in ordered_ids:
        o = old_agg.get(ing_id)
        n = new_agg.get(ing_id)
        name = idx[ing_id].name if ing_id in idx else ing_id
        lines.append(IngredientDelta(ing_id, name, o, n, _classify(o, n)))

    cost = _cost_delta(old, new, ingredients, packaging, cost_units)

    return FormulaDiff(
        slug=new.slug,
        old_version=old.version,
        new_version=new.version,
        old_product=old.product,
        new_product=new.product,
        lines=lines,
        cost=cost,
        warnings=warnings,
    )


__all__ = [
    "IngredientDelta",
    "CostDelta",
    "FormulaDiff",
    "formula_diff",
]
