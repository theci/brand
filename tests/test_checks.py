"""처방 사전점검(check) 테스트: HLB 균형 + 배합한도."""

from __future__ import annotations

from brandlab.checks import check_formula
from brandlab.core.models import Formula, Ingredient, IngredientLimit, LimitList


def _formula(pairs, product_type="leave_on"):
    return Formula.model_validate(
        {
            "product": "테스트",
            "slug": "test",
            "version": 1,
            "product_type": product_type,
            "status": "개발중",
            "base_batch_g": 100,
            "fill_volume_ml": 100,
            "phases": [
                {"name": "A", "ingredients": [{"id": i, "percent": p} for i, p in pairs]}
            ],
        }
    )


def _idx(*ings):
    return {i.id: i for i in ings}


def test_hlb_match_is_ok():
    ings = _idx(
        Ingredient(id="water", name="w", inci="w", category="용제"),
        Ingredient(id="emul", name="e", inci="e", category="유화제", hlb=10.0),
        Ingredient(id="oil", name="o", inci="o", category="에몰리언트", required_hlb=10.0),
    )
    f = _formula([("water", 85.0), ("emul", 5.0), ("oil", 10.0)])
    r = check_formula(f, ingredients=ings)
    assert r.hlb.applicable is True
    assert r.hlb.verdict == "적합"
    assert r.hlb.supplied_hlb == 10.0
    assert r.hlb.required_hlb == 10.0


def test_hlb_mismatch_is_risky():
    ings = _idx(
        Ingredient(id="water", name="w", inci="w", category="용제"),
        Ingredient(id="emul", name="e", inci="e", category="유화제", hlb=4.0),
        Ingredient(id="oil", name="o", inci="o", category="에몰리언트", required_hlb=12.0),
    )
    f = _formula([("water", 85.0), ("emul", 5.0), ("oil", 10.0)])
    r = check_formula(f, ingredients=ings)
    assert r.hlb.verdict == "위험"
    assert r.ok is False


def test_hlb_skipped_when_no_emulsifier():
    ings = _idx(
        Ingredient(id="water", name="w", inci="w", category="용제"),
        Ingredient(id="gly", name="g", inci="g", category="보습제"),
    )
    f = _formula([("water", 95.0), ("gly", 5.0)])
    r = check_formula(f, ingredients=ings)
    assert r.hlb.applicable is False
    assert r.hlb.verdict == "해당없음"


def test_limit_over_from_ingredient_max_percent():
    ings = _idx(
        Ingredient(id="water", name="w", inci="w", category="용제"),
        Ingredient(id="pres", name="보존제", inci="p", category="보존제", max_percent=1.0),
    )
    f = _formula([("water", 98.0), ("pres", 2.0)])
    r = check_formula(f, ingredients=ings)
    over = [x for x in r.limit_findings if x.id == "pres" and x.status == "초과"]
    assert over
    assert r.ok is False


def test_limit_from_regulatory_list_respects_product_type():
    ings = _idx(
        Ingredient(id="water", name="w", inci="w", category="용제"),
        Ingredient(id="x", name="x", inci="x", category="기타"),
    )
    limits = LimitList(
        limits=[IngredientLimit(ingredient_id="x", max_percent=0.5, product_type="leave_on")]
    )
    # leave_on 제품이면 한도 적용 → 초과
    f_on = _formula([("water", 98.0), ("x", 2.0)], product_type="leave_on")
    r_on = check_formula(f_on, ingredients=ings, limits=limits)
    assert any(x.id == "x" and x.status == "초과" for x in r_on.limit_findings)

    # rinse_off 제품이면 이 한도는 적용 안 됨
    f_off = _formula([("water", 98.0), ("x", 2.0)], product_type="rinse_off")
    r_off = check_formula(f_off, ingredients=ings, limits=limits)
    assert not any(x.id == "x" for x in r_off.limit_findings)
