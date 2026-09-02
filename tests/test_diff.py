"""처방 버전 비교(diff) 테스트."""

from __future__ import annotations

from brandlab.core.models import Formula, Ingredient
from brandlab.diff import formula_diff


def _ing(id_, price=10000, density=1.0):
    return Ingredient(
        id=id_, name=id_, inci=id_, category="test", price_per_kg=price, density=density
    )


def _formula(version, pairs):
    return Formula.model_validate(
        {
            "product": "테스트",
            "slug": "test",
            "version": version,
            "product_type": "leave_on",
            "status": "개발중",
            "base_batch_g": 100,
            "fill_volume_ml": 100,
            "phases": [
                {"name": "A", "ingredients": [{"id": i, "percent": p} for i, p in pairs]}
            ],
        }
    )


IDX = {
    "water": _ing("water", price=0),
    "glycerin": _ing("glycerin", price=3000),
    "ha": _ing("ha", price=200000),
    "panthenol": _ing("panthenol", price=30000),
}


def test_classifies_added_removed_changed_unchanged():
    old = _formula(1, [("water", 95.0), ("glycerin", 5.0)])
    new = _formula(2, [("water", 93.9), ("glycerin", 5.0), ("ha", 0.1), ("panthenol", 1.0)])
    d = formula_diff(old, new, ingredients=IDX)
    change = {l.id: l.change for l in d.lines}
    assert change["ha"] == "신규"
    assert change["panthenol"] == "신규"
    assert change["glycerin"] == "유지"
    assert change["water"] == "감량"


def test_removed_ingredient_detected():
    old = _formula(1, [("water", 95.0), ("glycerin", 5.0)])
    new = _formula(2, [("water", 100.0)])
    d = formula_diff(old, new, ingredients=IDX)
    change = {l.id: l.change for l in d.lines}
    assert change["glycerin"] == "삭제"
    gly = next(l for l in d.lines if l.id == "glycerin")
    assert gly.new_percent is None
    assert gly.delta is None


def test_delta_value():
    old = _formula(1, [("water", 95.0), ("glycerin", 5.0)])
    new = _formula(2, [("water", 92.0), ("glycerin", 8.0)])
    d = formula_diff(old, new, ingredients=IDX)
    gly = next(l for l in d.lines if l.id == "glycerin")
    assert gly.change == "증량"
    assert gly.delta == 3.0


def test_cost_delta_rises_when_adding_expensive_ingredient():
    old = _formula(1, [("water", 100.0)])
    new = _formula(2, [("water", 99.0), ("ha", 1.0)])
    d = formula_diff(old, new, ingredients=IDX, cost_units=1000)
    assert d.cost.note is None
    assert d.cost.material_delta is not None
    assert d.cost.material_delta > 0


def test_different_slug_warns():
    old = _formula(1, [("water", 100.0)])
    new = Formula.model_validate(
        {
            "product": "다른제품",
            "slug": "other",
            "version": 1,
            "product_type": "leave_on",
            "status": "개발중",
            "base_batch_g": 100,
            "fill_volume_ml": 100,
            "phases": [{"name": "A", "ingredients": [{"id": "water", "percent": 100}]}],
        }
    )
    d = formula_diff(old, new, ingredients=IDX)
    assert any("슬러그" in w for w in d.warnings)
