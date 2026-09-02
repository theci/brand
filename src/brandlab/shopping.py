"""장바구니(구매 목록) 생성.

생산에 필요한 원료·포장 수량을 계산하고, 현재 재고를 빼서 '부족분'만,
그것도 공급사 판매 단위(원료=팩, 포장=MOQ)로 올림해 구매량과 비용을 낸다.

두 가지 모드:
  - units 모드: N개 생산. 원료(내용량×밀도 기반) + 포장(MOQ 반영) 모두 계산.
  - grams 모드: 원료 배치 G그램 제조. 원료만 계산(포장 무관, R&D 배치용).

재고(Inventory)는 선택 입력. 없으면 보유량 0으로 보고 전량 구매 목록이 된다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from .core.models import (
    Formula,
    Ingredient,
    IngredientMaster,
    Inventory,
    Packaging,
    PackagingMaster,
)

DEFAULT_DENSITY_G_PER_ML = 1.0


@dataclass
class ShoppingIngredient:
    id: str
    name: str
    need_g: float
    on_hand_g: float
    short_g: float
    buy_g: float
    packs: int | None
    pack_size_g: float | None
    cost: float
    note: str | None = None


@dataclass
class ShoppingPackaging:
    id: str
    name: str
    need_units: int
    on_hand: int
    short: int
    order_qty: int
    dead_qty: int
    moq: int | None
    cost: float
    note: str | None = None


@dataclass
class ShoppingList:
    slug: str
    version: int
    mode: str  # "units" | "grams"
    amount: float  # units 개수 또는 grams
    ingredients: list[ShoppingIngredient]
    packaging: list[ShoppingPackaging]
    material_cost: float
    packaging_cost: float
    total_cost: float
    warnings: list[str] = field(default_factory=list)


def _ing_index(ingredients: IngredientMaster | Mapping[str, Ingredient]) -> dict[str, Ingredient]:
    if isinstance(ingredients, IngredientMaster):
        return ingredients.index()
    return dict(ingredients)


def _pkg_index(packaging: PackagingMaster | Mapping[str, Packaging]) -> dict[str, Packaging]:
    if isinstance(packaging, PackagingMaster):
        return packaging.index()
    return dict(packaging)


def _aggregate(formula: Formula) -> dict[str, float]:
    agg: dict[str, float] = {}
    for fi in (i for p in formula.phases for i in p.ingredients):
        agg[fi.id] = agg.get(fi.id, 0.0) + fi.percent
    return agg


def _needed_grams(
    formula: Formula, agg: Mapping[str, float], idx: Mapping[str, Ingredient], *, units: int | None, grams: float | None
) -> tuple[dict[str, float], list[str]]:
    warnings: list[str] = []
    if grams is not None:
        return {i: pct / 100.0 * grams for i, pct in agg.items()}, warnings

    # units 모드: 개당 내용량 기준
    if formula.net_weight_g is not None:
        fill, volume_based = formula.net_weight_g, False
    elif formula.fill_volume_ml is not None:
        fill, volume_based = formula.fill_volume_ml, True
    else:
        raise ValueError(
            f"처방 '{formula.slug} v{formula.version}'에 내용량(fill_volume_ml/net_weight_g)이 "
            "없어 units 모드로 계산할 수 없습니다. --grams 를 쓰세요."
        )

    need: dict[str, float] = {}
    for ing_id, pct in agg.items():
        share = pct / 100.0
        if volume_based:
            ing = idx.get(ing_id)
            density = ing.density if ing and ing.density is not None else DEFAULT_DENSITY_G_PER_ML
            if ing is None or ing.density is None:
                warnings.append(f"원료 '{ing_id}' 밀도 미입력 — 1.0 g/ml로 가정")
            need[ing_id] = units * share * fill * density
        else:
            need[ing_id] = units * share * fill
    return need, warnings


def shopping_list(
    formula: Formula,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    packaging: PackagingMaster | Mapping[str, Packaging] | None = None,
    inventory: Inventory | None = None,
    units: int | None = None,
    grams: float | None = None,
) -> ShoppingList:
    """구매 목록을 생성한다. units 또는 grams 중 하나를 준다."""
    if (units is None) == (grams is None):
        raise ValueError("units 또는 grams 중 정확히 하나를 지정하세요.")
    if units is not None and units <= 0:
        raise ValueError(f"units는 0보다 커야 합니다: {units}")
    if grams is not None and grams <= 0:
        raise ValueError(f"grams는 0보다 커야 합니다: {grams}")

    idx = _ing_index(ingredients)
    pidx = _pkg_index(packaging) if packaging is not None else {}
    inv_ing = inventory.ingredient_index() if inventory else {}
    inv_pkg = inventory.packaging_index() if inventory else {}

    agg = _aggregate(formula)
    need_g, warnings = _needed_grams(formula, agg, idx, units=units, grams=grams)

    # 원료
    ing_lines: list[ShoppingIngredient] = []
    for ing_id, need in need_g.items():
        ing = idx.get(ing_id)
        name = ing.name if ing else ing_id
        stock = inv_ing.get(ing_id)
        on_hand = stock.on_hand_g if stock else 0.0
        short = max(0.0, need - on_hand)

        packs: int | None = None
        pack_size = stock.pack_size_g if stock else None
        cost = 0.0
        note: str | None = None

        if short <= 0:
            buy_g = 0.0
        elif pack_size:
            packs = math.ceil(short / pack_size)
            buy_g = packs * pack_size
            if stock and stock.pack_price is not None:
                cost = packs * stock.pack_price
            elif ing and ing.price_per_kg is not None:
                cost = buy_g / 1000.0 * ing.price_per_kg
            else:
                note = "단가 미입력 — 비용 0"
        else:
            buy_g = short
            if ing and ing.price_per_kg is not None:
                cost = buy_g / 1000.0 * ing.price_per_kg
            else:
                note = "단가 미입력 — 비용 0"

        ing_lines.append(
            ShoppingIngredient(
                id=ing_id,
                name=name,
                need_g=round(need, 2),
                on_hand_g=round(on_hand, 2),
                short_g=round(short, 2),
                buy_g=round(buy_g, 2),
                packs=packs,
                pack_size_g=pack_size,
                cost=round(cost, 2),
                note=note,
            )
        )

    # 포장 (units 모드에서만)
    pkg_lines: list[ShoppingPackaging] = []
    if units is not None:
        for ref in formula.packaging:
            pkg = pidx.get(ref.id)
            name = pkg.name if pkg else ref.id
            need_units = units * ref.qty_per_unit
            on_hand = inv_pkg[ref.id].on_hand if ref.id in inv_pkg else 0
            short = max(0, need_units - on_hand)
            moq = pkg.moq if pkg else None
            cost = 0.0
            note = None
            if short <= 0:
                order = 0
                dead = 0
            else:
                order = max(short, moq) if moq else short
                dead = order - short
                if pkg and pkg.unit_price is not None:
                    cost = order * pkg.unit_price
                else:
                    note = "단가 미입력 — 비용 0"
            pkg_lines.append(
                ShoppingPackaging(
                    id=ref.id,
                    name=name,
                    need_units=need_units,
                    on_hand=on_hand,
                    short=short,
                    order_qty=order,
                    dead_qty=dead,
                    moq=moq,
                    cost=round(cost, 2),
                    note=note,
                )
            )

    material_cost = round(sum(l.cost for l in ing_lines), 2)
    packaging_cost = round(sum(l.cost for l in pkg_lines), 2)

    return ShoppingList(
        slug=formula.slug,
        version=formula.version,
        mode="units" if units is not None else "grams",
        amount=float(units) if units is not None else float(grams),
        ingredients=ing_lines,
        packaging=pkg_lines,
        material_cost=material_cost,
        packaging_cost=packaging_cost,
        total_cost=round(material_cost + packaging_cost, 2),
        warnings=warnings,
    )


__all__ = [
    "ShoppingIngredient",
    "ShoppingPackaging",
    "ShoppingList",
    "shopping_list",
]
