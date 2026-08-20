"""원가·손익 계산 엔진 테스트."""

from __future__ import annotations

import pytest

from brandlab.cost import (
    breakeven,
    min_price_for_margin,
    moq_bottleneck,
    price_simulator,
    unit_cost,
)
from brandlab.models import (
    Economics,
    Formula,
    Ingredient,
    IngredientMaster,
    Packaging,
    PackagingMaster,
)


# ---------------------------------------------------------------------------
# 통제된 픽스처 (손 계산 검증용 라운드 넘버)
# ---------------------------------------------------------------------------
@pytest.fixture
def ing_master() -> IngredientMaster:
    return IngredientMaster(
        ingredients=[
            # 밀도 1.0, 단가 10,000원/kg = 10원/g
            Ingredient(
                id="oilA",
                name="오일A",
                inci="Oil A",
                category="에몰리언트",
                price_per_kg=10000,
                density=1.0,
            ),
            # 밀도 0.5, 단가 20,000원/kg = 20원/g
            Ingredient(
                id="oilB",
                name="오일B",
                inci="Oil B",
                category="에몰리언트",
                price_per_kg=20000,
                density=0.5,
            ),
        ]
    )


@pytest.fixture
def pkg_master() -> PackagingMaster:
    return PackagingMaster(
        packaging=[
            Packaging(
                id="jar", name="용기", type="jar", unit_price=800, moq=3000
            ),
            Packaging(
                id="box", name="박스", type="box", unit_price=200, moq=1000
            ),
        ]
    )


@pytest.fixture
def economics() -> Economics:
    return Economics(
        channel_fee_rate=0.30,
        shipping_cost=3000,
        return_rate=0.05,
        vat_rate=0.10,
        target_margin=0.40,
    )


def _formula(**over) -> Formula:
    data = {
        "product": "원가테스트",
        "slug": "cost-test",
        "version": 1,
        "product_type": "leave_on",
        "status": "개발중",
        "base_batch_g": 100,
        "fill_volume_ml": 100,
        "phases": [
            {
                "name": "A",
                "ingredients": [
                    {"id": "oilA", "percent": 50.0},
                    {"id": "oilB", "percent": 50.0},
                ],
            }
        ],
        "packaging": [
            {"id": "jar", "qty_per_unit": 1},
            {"id": "box", "qty_per_unit": 1},
        ],
    }
    data.update(over)
    return Formula.model_validate(data)


# ---------------------------------------------------------------------------
# 원료비 — 손 계산과 일치
# ---------------------------------------------------------------------------
def test_material_cost_matches_hand_calc(ing_master, pkg_master):
    # 개당 내용량 100ml, 부피 기준
    #  oilA: 50% × 100ml × 1.0 g/ml = 50g × 10원/g = 500원
    #  oilB: 50% × 100ml × 0.5 g/ml = 25g × 20원/g = 500원
    #  원료비 합계 = 1000원
    uc = unit_cost(
        _formula(), 5000, ingredients=ing_master, packaging=pkg_master
    )
    lines = {l.ref_id: l.cost for l in uc.material_lines}
    assert lines["oilA"] == pytest.approx(500.0)
    assert lines["oilB"] == pytest.approx(500.0)
    assert uc.material_cost == pytest.approx(1000.0)


def test_weight_based_material_cost(ing_master, pkg_master):
    # net_weight_g 기준(밀도 미사용): oilA 50% × 100g = 50g × 10 = 500
    f = _formula(fill_volume_ml=None, net_weight_g=100)
    uc = unit_cost(f, 5000, ingredients=ing_master, packaging=pkg_master)
    lines = {l.ref_id: l.cost for l in uc.material_lines}
    assert lines["oilA"] == pytest.approx(500.0)  # 밀도 무관
    assert lines["oilB"] == pytest.approx(20 * 50)  # 50g × 20원/g = 1000


def test_packaging_cost_consumed_basis(ing_master, pkg_master):
    uc = unit_cost(_formula(), 5000, ingredients=ing_master, packaging=pkg_master)
    # jar 800 + box 200 = 1000원 (개당, 실사용 기준)
    assert uc.packaging_cost == pytest.approx(1000.0)
    assert uc.unit_cost == pytest.approx(2000.0)  # 원료 1000 + 부자재 1000


# ---------------------------------------------------------------------------
# MOQ 미달 → 사장 재고
# ---------------------------------------------------------------------------
def test_dead_stock_when_below_moq(ing_master, pkg_master):
    # 1000개 생산: jar MOQ 3000 → 2000 사장, box MOQ 1000 → 0 사장
    uc = unit_cost(_formula(), 1000, ingredients=ing_master, packaging=pkg_master)
    dead = {d.packaging_id: d for d in uc.dead_stock}
    assert "jar" in dead
    assert dead["jar"].order_qty == 3000
    assert dead["jar"].dead_qty == 2000
    assert dead["jar"].dead_capital == pytest.approx(2000 * 800)
    # box: need 1000 == moq 1000 → 사장 재고 없음
    assert "box" not in dead
    assert uc.dead_stock_capital == pytest.approx(2000 * 800)


def test_no_dead_stock_when_above_moq(ing_master, pkg_master):
    uc = unit_cost(_formula(), 5000, ingredients=ing_master, packaging=pkg_master)
    assert uc.dead_stock == []
    assert uc.dead_stock_capital == 0


def test_missing_price_warns_not_silent():
    ings = IngredientMaster(
        ingredients=[
            Ingredient(id="oilA", name="오일A", inci="Oil A", category="에몰리언트")
        ]
    )
    pkgs = PackagingMaster(packaging=[Packaging(id="jar", name="용기", type="jar")])
    f = _formula(
        phases=[{"name": "A", "ingredients": [{"id": "oilA", "percent": 100.0}]}],
        packaging=[{"id": "jar", "qty_per_unit": 1}],
    )
    uc = unit_cost(f, 1000, ingredients=ings, packaging=pkgs)
    assert uc.material_cost == 0
    assert any("단가" in w for w in uc.warnings)


# ---------------------------------------------------------------------------
# price_simulator + 목표마진 역산 (순환 참조 없음)
# ---------------------------------------------------------------------------
def test_price_simulator_basic(economics):
    sim = price_simulator(2000, 34000, economics=economics)
    # 실매출 = 34000/1.1 = 30909.09
    assert sim.net_revenue == pytest.approx(34000 / 1.1, rel=1e-6)
    # 수수료 = 34000 × 0.3 = 10200
    assert sim.channel_fee == pytest.approx(10200)
    # 반품비 = 0.05 × (3000 + 2000) = 250
    assert sim.return_cost == pytest.approx(250)
    # 공헌이익 = 30909.09 - 10200 - 3000 - 2000 - 250
    expected = 34000 / 1.1 - 10200 - 3000 - 2000 - 250
    assert sim.contribution == pytest.approx(round(expected, 2), abs=0.01)


def test_min_price_for_margin_no_circular_reference(economics):
    # 목표 마진 40%의 최소 판매가를 역산한 뒤, 그 가격을 시뮬레이터에 넣으면
    # 마진이 정확히 40%가 나와야 한다(닫힌형, 순환 참조 없음).
    cost = 2500.0
    target = 0.40
    price = min_price_for_margin(cost, target, economics=economics)
    assert price is not None
    sim = price_simulator(cost, price, economics=economics)
    assert sim.margin_on_net == pytest.approx(target, abs=1e-4)


def test_min_price_for_margin_unreachable(economics):
    # 마진 목표가 너무 높으면(달성 불가) None
    assert min_price_for_margin(2000, 0.95, economics=economics) is None


def test_price_simulator_accepts_unitcost_object(ing_master, pkg_master, economics):
    uc = unit_cost(_formula(), 5000, ingredients=ing_master, packaging=pkg_master)
    sim = price_simulator(uc, 34000, economics=economics)
    assert sim.unit_cost == pytest.approx(uc.unit_cost)


# ---------------------------------------------------------------------------
# breakeven
# ---------------------------------------------------------------------------
def test_breakeven_rounds_up():
    assert breakeven(100000, 3000) == 34  # 33.3 → 34
    assert breakeven(90000, 3000) == 30


def test_breakeven_none_when_no_contribution():
    assert breakeven(100000, 0) is None
    assert breakeven(100000, -50) is None


# ---------------------------------------------------------------------------
# moq_bottleneck
# ---------------------------------------------------------------------------
def test_moq_bottleneck_identifies_binding_item(ing_master, pkg_master):
    # 1000개: jar MOQ 3000이 병목(box는 1000으로 딱 맞음)
    mb = moq_bottleneck(
        _formula(), 1000, ingredients=ing_master, packaging=pkg_master
    )
    assert mb.bottleneck is not None
    assert mb.bottleneck.packaging_id == "jar"
    assert mb.min_units_no_waste == 3000


def test_moq_bottleneck_total_upfront_capital(ing_master, pkg_master):
    mb = moq_bottleneck(
        _formula(), 1000, ingredients=ing_master, packaging=pkg_master
    )
    # 부자재 자본 = jar 3000×800 + box 1000×200 = 2,400,000 + 200,000 = 2,600,000
    assert mb.packaging_capital == pytest.approx(2600000)
    # 원료 자본 = 개당 원료비 1000 × 1000개 = 1,000,000
    assert mb.material_capital == pytest.approx(1000000)
    assert mb.total_upfront_capital == pytest.approx(3600000)


# ---------------------------------------------------------------------------
# 실데이터 로드 통합
# ---------------------------------------------------------------------------
def test_real_data_cost_runs(project_root):
    from brandlab.loader import BrandLab

    lab = BrandLab.load(project_root)
    cb = next(f for f in lab.formulas if f.slug == "cleansing-balm")
    uc = unit_cost(cb, 1000, ingredients=lab.ingredients, packaging=lab.packaging)
    assert uc.unit_cost > 0
    sim = price_simulator(uc, 34000, economics=lab.config.economics)
    assert sim.contribution != 0
    mb = moq_bottleneck(cb, 1000, ingredients=lab.ingredients, packaging=lab.packaging)
    assert mb.total_upfront_capital > 0
