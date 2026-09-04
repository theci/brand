"""처방 사전점검(check) 테스트: HLB 균형 + 배합한도."""

from __future__ import annotations

from brandlab.checks import (
    check_formula,
    compatibility_check,
    formulation_balance,
    moisture_role,
    preservation_check,
)
from brandlab.core.models import (
    Formula,
    IncompatibilityRule,
    IncompatibilityRules,
    IncompatMatch,
    Ingredient,
    IngredientLimit,
    LimitList,
)


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


# ---------------------------------------------------------------------------
# 제형·유수분 밸런스
# ---------------------------------------------------------------------------
def _bing(id_, category, **kw):
    return Ingredient(id=id_, name=id_, inci=id_, category=category, **kw)


def test_formulation_balance_cream():
    ings = _idx(
        _bing("water", "용제"),
        _bing("glycerin", "보습제"),
        _bing("squalane", "에몰리언트", required_hlb=12),
        _bing("beeswax", "왁스"),
        _bing("emul", "계면활성제", hlb=10),
    )
    f = _formula([("water", 75.0), ("glycerin", 5.0), ("squalane", 12.0), ("beeswax", 3.0), ("emul", 5.0)])
    b = formulation_balance(f, ingredients=ings)
    assert b.oil_pct == 20.0 and b.water_pct == 80.0
    assert "크림" in b.texture
    assert b.humectant_pct == 5.0
    assert b.emollient_pct == 12.0
    assert b.occlusive_pct == 3.0
    assert b.emulsifier_pct == 5.0


def test_moisture_role_override_and_occlusive_axis():
    # 카테고리는 에몰리언트지만 moisture_role=occlusive로 지정 → 옥클루시브 축에 잡힘
    dime = _bing("dime", "에몰리언트", moisture_role="occlusive")
    assert moisture_role(dime) == "occlusive"
    ings = _idx(_bing("water", "용제"), dime)
    f = _formula([("water", 90.0), ("dime", 10.0)])
    b = formulation_balance(f, ingredients=ings)
    assert b.occlusive_pct == 10.0 and b.emollient_pct == 0.0
    assert b.oil_pct == 10.0


def test_formulation_balance_anhydrous_or_waterless_comment():
    ings = _idx(_bing("water", "용제"), _bing("glycerin", "보습제"))
    f = _formula([("water", 95.0), ("glycerin", 5.0)])
    b = formulation_balance(f, ingredients=ings)
    assert b.oil_pct == 0.0
    assert any("유상 0%" in c for c in b.comments)


def test_humectant_without_occlusive_warns():
    ings = _idx(_bing("water", "용제"), _bing("glycerin", "보습제"), _bing("emul", "계면활성제", hlb=10))
    f = _formula([("water", 88.0), ("glycerin", 10.0), ("emul", 2.0)])
    b = formulation_balance(f, ingredients=ings)
    assert any("잠금" in c for c in b.comments)  # 휴멕턴트↑ 옥클루시브↓ 경고


# ---------------------------------------------------------------------------
# 보존 시스템 점검
# ---------------------------------------------------------------------------
def test_preservation_good():
    ings = _idx(_bing("water", "용제"), _bing("phenoxy", "보존제"), _bing("hexanediol", "보습제"), _bing("gly", "보습제"))
    f = _formula([("water", 90.0), ("phenoxy", 1.0), ("hexanediol", 2.0), ("gly", 7.0)])
    r = preservation_check(f, ingredients=ings)
    assert r.is_water_based and r.verdict == "양호" and r.ok


def test_preservation_missing_is_danger():
    ings = _idx(_bing("water", "용제"), _bing("gly", "보습제"))
    f = _formula([("water", 95.0), ("gly", 5.0)])
    r = preservation_check(f, ingredients=ings)
    assert r.verdict == "위험" and not r.ok


def test_preservation_anhydrous_na():
    ings = _idx(_bing("wax", "왁스"), _bing("oil", "에몰리언트"))
    f = _formula([("wax", 40.0), ("oil", 60.0)])
    r = preservation_check(f, ingredients=ings)
    assert not r.is_water_based and r.verdict == "해당없음" and r.ok


def test_preservation_single_warns():
    ings = _idx(_bing("water", "용제"), _bing("phenoxy", "보존제"), _bing("gly", "보습제"))
    f = _formula([("water", 90.0), ("phenoxy", 1.0), ("gly", 9.0)])
    r = preservation_check(f, ingredients=ings)
    assert r.verdict == "주의"  # 단일 보존제·보조 없음


def test_preservation_booster_only_danger():
    ings = _idx(_bing("water", "용제"), _bing("hexanediol", "보습제"), _bing("gly", "보습제"))
    f = _formula([("water", 90.0), ("hexanediol", 2.0), ("gly", 8.0)])
    r = preservation_check(f, ingredients=ings)
    assert r.verdict == "위험" and r.boosters


# ---------------------------------------------------------------------------
# 원료 상용성(충돌) 점검
# ---------------------------------------------------------------------------
_NIAC_VITC = IncompatibilityRules(rules=[
    IncompatibilityRule(
        id="niac-vitc",
        a=IncompatMatch(ids=["niacinamide"]),
        b=IncompatMatch(inci_contains=["ascorbic acid"]),
        severity="medium",
        reason="테스트 충돌",
    )
])


def test_compat_conflict_fires():
    ings = _idx(
        _bing("water", "용제"),
        _bing("niacinamide", "진정"),
        Ingredient(id="vitc", name="비타민C", inci="Ascorbic Acid", category="항산화"),
    )
    f = _formula([("water", 90.0), ("niacinamide", 5.0), ("vitc", 5.0)])
    res = compatibility_check(f, ingredients=ings, rules=_NIAC_VITC)
    assert len(res) == 1 and res[0].rule_id == "niac-vitc"
    assert "니아신아마이드" not in res[0].a_names  # 이름 기준(name="niacinamide")
    assert res[0].b_names == ["비타민C"]


def test_compat_no_conflict_when_one_side_absent():
    ings = _idx(_bing("water", "용제"), _bing("niacinamide", "진정"))
    f = _formula([("water", 95.0), ("niacinamide", 5.0)])
    assert compatibility_check(f, ingredients=ings, rules=_NIAC_VITC) == []


def test_compat_empty_rules():
    ings = _idx(_bing("water", "용제"))
    f = _formula([("water", 100.0)])
    assert compatibility_check(f, ingredients=ings, rules=IncompatibilityRules()) == []


def test_shipped_rules_no_false_positive_on_real_formulas():
    from brandlab.loader import BrandLab, load_incompatibilities

    lab = BrandLab.load()
    rules = load_incompatibilities()
    for f in lab.formulas:
        res = compatibility_check(f, ingredients=lab.ingredients, rules=rules)
        assert res == [], f"{f.slug} v{f.version} 오탐: {[c.rule_id for c in res]}"
