"""원가·손익 계산 엔진.

용어
  - unit_cost : 개당 제조원가(원료비 + 부자재비). MOQ로 인한 사장 재고는 별도 표시.
  - contribution : 개당 공헌이익(매출에서 변동비를 뺀 값)
  - breakeven : 손익분기 수량

가정값(수수료율·배송비·반품률·부가세)은 코드가 아니라 config.yaml(Economics)에서 읽으며,
결과의 assumptions 필드에 출처를 남긴다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from .models import (
    Economics,
    Formula,
    Ingredient,
    IngredientMaster,
    Packaging,
    PackagingMaster,
)

# 부피 기준 내용량을 질량으로 환산할 때, 밀도가 없으면 사용하는 가정값.
DEFAULT_DENSITY_G_PER_ML = 1.0


# ---------------------------------------------------------------------------
# 자료구조
# ---------------------------------------------------------------------------
@dataclass
class CostLine:
    ref_id: str
    name: str
    detail: str  # 계산 근거 요약
    cost: float  # 개당 원(KRW)


@dataclass
class DeadStock:
    packaging_id: str
    name: str
    need_qty: int  # 이번 생산에 필요한 수량
    moq: int
    order_qty: int  # 실제 발주 수량(= max(need, moq))
    dead_qty: int  # 사장 재고 수량
    unit_price: float
    dead_capital: float  # 사장 재고에 묶이는 자본(원)


@dataclass
class UnitCost:
    slug: str
    version: int
    batch_units: int
    material_lines: list[CostLine]
    packaging_lines: list[CostLine]
    material_cost: float  # 개당 원료비
    packaging_cost: float  # 개당 부자재비(실사용 기준)
    unit_cost: float  # 개당 원가(원료비 + 부자재비)
    dead_stock: list[DeadStock]
    dead_stock_capital: float
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PriceSimulation:
    price: float  # 소비자 판매가(부가세 포함)
    unit_cost: float
    net_revenue: float  # 부가세 제외 실매출
    channel_fee: float
    shipping: float
    return_cost: float
    contribution: float  # 개당 공헌이익
    margin_on_net: float  # 공헌이익 / 실매출
    margin_on_price: float  # 공헌이익 / 판매가
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class MoqItem:
    packaging_id: str
    name: str
    qty_per_unit: int
    need_qty: int
    moq: int | None
    order_qty: int
    dead_qty: int
    unit_price: float
    capital: float
    max_units_without_waste: int | None  # 이 부자재가 허용하는 무낭비 최대 생산량


@dataclass
class MoqBottleneck:
    slug: str
    version: int
    target_units: int
    items: list[MoqItem]
    bottleneck: MoqItem | None  # 초도 물량을 결정하는 부자재
    min_units_no_waste: int | None  # 사장 재고 없이 만들려면 필요한 최소 생산량
    material_capital: float  # 원료 선투입(target_units 생산분)
    packaging_capital: float  # 부자재 선투입(MOQ 기준 발주)
    total_upfront_capital: float
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
def _ingredient_index(
    ingredients: IngredientMaster | Mapping[str, Ingredient],
) -> dict[str, Ingredient]:
    if isinstance(ingredients, IngredientMaster):
        return ingredients.index()
    return dict(ingredients)


def _packaging_index(
    packaging: PackagingMaster | Mapping[str, Packaging],
) -> dict[str, Packaging]:
    if isinstance(packaging, PackagingMaster):
        return packaging.index()
    return dict(packaging)


def _fill_basis(formula: Formula) -> tuple[float, str, bool]:
    """개당 내용량과 단위를 반환. (양, 단위, 부피기준여부)."""
    if formula.net_weight_g is not None:
        return formula.net_weight_g, "g", False
    if formula.fill_volume_ml is not None:
        return formula.fill_volume_ml, "ml", True
    raise ValueError(
        f"처방 '{formula.slug} v{formula.version}'에 내용량(fill_volume_ml/net_weight_g)이 "
        "없어 원료비를 계산할 수 없습니다."
    )


# ---------------------------------------------------------------------------
# 1. unit_cost
# ---------------------------------------------------------------------------
def unit_cost(
    formula: Formula,
    batch_units: int,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    packaging: PackagingMaster | Mapping[str, Packaging],
) -> UnitCost:
    """개당 원가를 계산한다.

    원료비 = Σ (처방 함량% × 개당 내용량 × 밀도(부피기준일 때) × 원료 단가)
    부자재비 = Σ (개당 수량 × 개당 단가)
    MOQ 미달 시 발주는 MOQ 기준으로 잡고, 남는 수량은 사장 재고로 별도 표시한다.
    """
    if batch_units <= 0:
        raise ValueError(f"batch_units는 0보다 커야 합니다: {batch_units}")

    idx = _ingredient_index(ingredients)
    pidx = _packaging_index(packaging)
    fill, unit, volume_based = _fill_basis(formula)

    assumptions: list[str] = []
    warnings: list[str] = []

    # 같은 원료가 여러 상에 있으면 합산
    agg: dict[str, float] = {}
    for fi in (i for p in formula.phases for i in p.ingredients):
        agg[fi.id] = agg.get(fi.id, 0.0) + fi.percent

    material_lines: list[CostLine] = []
    density_assumed = False
    for ing_id, percent in agg.items():
        ing = idx.get(ing_id)
        if ing is None or ing.price_per_kg is None:
            warnings.append(
                f"원료 '{ing_id}' 단가(price_per_kg) 미입력 — 원료비 0으로 처리(과소 추정)."
            )
            material_lines.append(
                CostLine(ing_id, ing.name if ing else ing_id, "단가 미입력", 0.0)
            )
            continue

        share = percent / 100.0
        if volume_based:
            density = ing.density if ing.density is not None else DEFAULT_DENSITY_G_PER_ML
            if ing.density is None:
                density_assumed = True
            amount_g = share * fill * density
            detail = (
                f"{percent:g}% × {fill:g}ml × {density:g}g/ml × {ing.price_per_kg:g}원/kg"
            )
        else:
            amount_g = share * fill
            detail = f"{percent:g}% × {fill:g}g × {ing.price_per_kg:g}원/kg"

        cost = amount_g * (ing.price_per_kg / 1000.0)  # 원/kg → 원/g
        material_lines.append(
            CostLine(ing_id, ing.name, detail, round(cost, 4))
        )

    material_cost = round(sum(l.cost for l in material_lines), 2)

    # 부자재비 (실사용 기준) + MOQ 사장 재고
    packaging_lines: list[CostLine] = []
    dead_stock: list[DeadStock] = []
    for ref in formula.packaging:
        pkg = pidx.get(ref.id)
        if pkg is None or pkg.unit_price is None:
            warnings.append(
                f"부자재 '{ref.id}' 단가(unit_price) 미입력 — 부자재비 0으로 처리(과소 추정)."
            )
            packaging_lines.append(
                CostLine(ref.id, pkg.name if pkg else ref.id, "단가 미입력", 0.0)
            )
            continue

        line_cost = ref.qty_per_unit * pkg.unit_price
        packaging_lines.append(
            CostLine(
                ref.id,
                pkg.name,
                f"{ref.qty_per_unit}개 × {pkg.unit_price:g}원",
                round(line_cost, 2),
            )
        )

        need_qty = batch_units * ref.qty_per_unit
        if pkg.moq is not None and pkg.moq > need_qty:
            order_qty = pkg.moq
            dead_qty = order_qty - need_qty
            dead_stock.append(
                DeadStock(
                    packaging_id=ref.id,
                    name=pkg.name,
                    need_qty=need_qty,
                    moq=pkg.moq,
                    order_qty=order_qty,
                    dead_qty=dead_qty,
                    unit_price=pkg.unit_price,
                    dead_capital=round(dead_qty * pkg.unit_price, 2),
                )
            )

    packaging_cost = round(sum(l.cost for l in packaging_lines), 2)
    total_unit_cost = round(material_cost + packaging_cost, 2)
    dead_capital = round(sum(d.dead_capital for d in dead_stock), 2)

    assumptions.append("원료 단가·밀도, 부자재 단가·MOQ = data/ingredients.yaml, packaging.yaml")
    assumptions.append(
        f"개당 내용량 {fill:g}{unit} 기준 "
        + ("(부피 → 밀도로 질량 환산)" if volume_based else "(질량 기준)")
    )
    if density_assumed:
        assumptions.append(
            f"밀도 미입력 원료는 {DEFAULT_DENSITY_G_PER_ML:g}g/ml로 가정"
        )
    if dead_stock:
        assumptions.append(
            "MOQ 미달 부자재는 MOQ 기준 발주로 비용을 잡고, 남는 수량은 사장 재고로 별도 표시"
        )

    return UnitCost(
        slug=formula.slug,
        version=formula.version,
        batch_units=batch_units,
        material_lines=material_lines,
        packaging_lines=packaging_lines,
        material_cost=material_cost,
        packaging_cost=packaging_cost,
        unit_cost=total_unit_cost,
        dead_stock=dead_stock,
        dead_stock_capital=dead_capital,
        assumptions=assumptions,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 2. price_simulator
# ---------------------------------------------------------------------------
def _coerce_unit_cost(value: float | UnitCost) -> float:
    return value.unit_cost if isinstance(value, UnitCost) else float(value)


def price_simulator(
    unit_cost: float | UnitCost,
    price: float,
    *,
    economics: Economics,
) -> PriceSimulation:
    """판매가에 대한 개당 손익을 계산한다.

    net_revenue  = price / (1 + vat)                (부가세 제외 실매출)
    channel_fee  = price × channel_fee_rate         (판매가 기준 수수료)
    shipping     = shipping_cost                     (개당 출고 배송비)
    return_cost  = return_rate × (shipping + 원가)   (반품분 역배송 + 제품 손실 가정)
    contribution = net_revenue − channel_fee − shipping − 원가 − return_cost
    """
    cost = _coerce_unit_cost(unit_cost)
    if price <= 0:
        raise ValueError(f"price는 0보다 커야 합니다: {price}")

    net_revenue = price / (1 + economics.vat_rate)
    channel_fee = price * economics.channel_fee_rate
    shipping = economics.shipping_cost
    return_cost = economics.return_rate * (shipping + cost)
    contribution = net_revenue - channel_fee - shipping - cost - return_cost

    margin_on_net = contribution / net_revenue if net_revenue else 0.0
    margin_on_price = contribution / price if price else 0.0

    warnings: list[str] = []
    if contribution <= 0:
        warnings.append("공헌이익이 0 이하입니다. 이 판매가로는 팔수록 손해입니다.")

    assumptions = [
        f"채널 수수료율 {economics.channel_fee_rate:.0%}, 배송비 {economics.shipping_cost:g}원, "
        f"반품률 {economics.return_rate:.0%}, 부가세 {economics.vat_rate:.0%} = config.yaml",
        "마진율(net) = 공헌이익 / (부가세 제외 실매출)",
        "반품분은 역배송비와 제품 원가를 손실로 가정(리셀 불가 보수적 가정)",
    ]

    return PriceSimulation(
        price=round(price, 2),
        unit_cost=round(cost, 2),
        net_revenue=round(net_revenue, 2),
        channel_fee=round(channel_fee, 2),
        shipping=round(shipping, 2),
        return_cost=round(return_cost, 2),
        contribution=round(contribution, 2),
        margin_on_net=margin_on_net,
        margin_on_price=margin_on_price,
        assumptions=assumptions,
        warnings=warnings,
    )


def min_price_for_margin(
    unit_cost: float | UnitCost,
    target_margin: float,
    *,
    economics: Economics,
) -> float | None:
    """목표 마진율(net 기준)을 만족하는 최소 판매가를 닫힌형으로 역산한다.

    순환 참조 없이 1차식으로 푼다.
      margin = contribution / net_revenue,  net_revenue = price/(1+vat)
      contribution = price·[1/(1+vat) − fee] − K,   K = shipping·(1+r) + cost·(1+r)
      → price = K / ( (1−margin)/(1+vat) − fee )
    분모가 0 이하이면 어떤 가격으로도 목표 마진 달성 불가 → None.
    """
    cost = _coerce_unit_cost(unit_cost)
    vat = economics.vat_rate
    fee = economics.channel_fee_rate
    r = economics.return_rate

    # price에 무관한 상수항 K (shipping·(1+r) + cost·(1+r))
    k_const = economics.shipping_cost * (1 + r) + cost * (1 + r)
    denom = (1 - target_margin) / (1 + vat) - fee
    if denom <= 0:
        return None
    return round(k_const / denom, 2)


# ---------------------------------------------------------------------------
# 3. breakeven
# ---------------------------------------------------------------------------
def breakeven(fixed_cost: float, unit_contribution: float) -> int | None:
    """손익분기 수량 = ceil(고정비 / 개당 공헌이익). 공헌이익 0 이하면 None."""
    if unit_contribution <= 0:
        return None
    return math.ceil(fixed_cost / unit_contribution)


# ---------------------------------------------------------------------------
# 4. moq_bottleneck
# ---------------------------------------------------------------------------
def moq_bottleneck(
    formula: Formula,
    target_units: int,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    packaging: PackagingMaster | Mapping[str, Packaging],
) -> MoqBottleneck:
    """부자재 MOQ 대비 필요 수량을 비교해 초도 물량 병목과 총 선투입 자본을 계산한다."""
    if target_units <= 0:
        raise ValueError(f"target_units는 0보다 커야 합니다: {target_units}")

    pidx = _packaging_index(packaging)
    warnings: list[str] = []

    items: list[MoqItem] = []
    for ref in formula.packaging:
        pkg = pidx.get(ref.id)
        need = target_units * ref.qty_per_unit
        unit_price = pkg.unit_price if (pkg and pkg.unit_price is not None) else 0.0
        if pkg is None or pkg.unit_price is None:
            warnings.append(f"부자재 '{ref.id}' 단가 미입력 — 자본 계산에서 0으로 처리.")
        moq = pkg.moq if pkg else None
        order = max(need, moq) if moq is not None else need
        dead = order - need
        # 이 부자재로 사장 재고 없이 만들 수 있는 최대 생산량(= floor(order/qty))
        max_units = order // ref.qty_per_unit if ref.qty_per_unit else None
        items.append(
            MoqItem(
                packaging_id=ref.id,
                name=pkg.name if pkg else ref.id,
                qty_per_unit=ref.qty_per_unit,
                need_qty=need,
                moq=moq,
                order_qty=order,
                dead_qty=dead,
                unit_price=unit_price,
                capital=round(order * unit_price, 2),
                max_units_without_waste=max_units,
            )
        )

    # 초도 물량을 결정하는 병목: MOQ가 요구 수량을 초과(사장 재고 발생)하는 항목 중
    # ceil(moq/qty)가 가장 큰 항목. 즉 낭비 없이 만들려면 이 수량 이상 생산해야 한다.
    floors: list[tuple[int, MoqItem]] = []
    for it in items:
        if it.moq is not None and it.moq > it.need_qty:
            floors.append((math.ceil(it.moq / it.qty_per_unit), it))
    if floors:
        floors.sort(key=lambda t: t[0], reverse=True)
        min_units_no_waste, bottleneck = floors[0]
    else:
        min_units_no_waste, bottleneck = None, None

    # 원료 선투입: target_units 생산분 원료비 (사장 재고 없음 가정)
    uc = unit_cost(
        formula, target_units, ingredients=ingredients, packaging=packaging
    )
    material_capital = round(uc.material_cost * target_units, 2)
    packaging_capital = round(sum(it.capital for it in items), 2)
    total = round(material_capital + packaging_capital, 2)

    assumptions = [
        "부자재 MOQ·단가 = packaging.yaml, 원료 단가 = ingredients.yaml",
        "총 선투입 자본 = 원료비(생산량분) + 부자재 발주비(MOQ 기준)",
        "원료 MOQ는 미반영(부자재 MOQ만 병목으로 계산)",
    ]
    if bottleneck is not None:
        assumptions.append(
            f"초도 물량 병목 = '{bottleneck.name}' (MOQ {bottleneck.moq} → "
            f"낭비 없이 만들려면 최소 {min_units_no_waste}개 생산 필요)"
        )

    return MoqBottleneck(
        slug=formula.slug,
        version=formula.version,
        target_units=target_units,
        items=items,
        bottleneck=bottleneck,
        min_units_no_waste=min_units_no_waste,
        material_capital=material_capital,
        packaging_capital=packaging_capital,
        total_upfront_capital=total,
        assumptions=assumptions,
        warnings=warnings,
    )


__all__ = [
    "DEFAULT_DENSITY_G_PER_ML",
    "CostLine",
    "DeadStock",
    "UnitCost",
    "PriceSimulation",
    "MoqItem",
    "MoqBottleneck",
    "unit_cost",
    "price_simulator",
    "min_price_for_margin",
    "breakeven",
    "moq_bottleneck",
]
