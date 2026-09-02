"""장바구니(구매 목록) 생성 테스트."""

from __future__ import annotations

import pytest

from brandlab.core.models import (
    Formula,
    Ingredient,
    Inventory,
    InventoryIngredient,
    InventoryPackaging,
    Packaging,
)
from brandlab.shopping import shopping_list


def _formula():
    return Formula.model_validate(
        {
            "product": "테스트로션",
            "slug": "test-lotion",
            "version": 1,
            "product_type": "leave_on",
            "status": "개발중",
            "base_batch_g": 100,
            "fill_volume_ml": 50,
            "phases": [
                {
                    "name": "A",
                    "ingredients": [
                        {"id": "water", "percent": 90.0},
                        {"id": "glycerin", "percent": 10.0},
                    ],
                }
            ],
            "packaging": [{"id": "jar", "qty_per_unit": 1}],
        }
    )


IDX = {
    "water": Ingredient(id="water", name="정제수", inci="Water", category="용제", price_per_kg=500, density=1.0),
    "glycerin": Ingredient(id="glycerin", name="글리세린", inci="Glycerin", category="보습제", price_per_kg=4000, density=1.0),
}
PKG = {"jar": Packaging(id="jar", name="병", type="jar", unit_price=800, moq=3000)}


def test_units_mode_subtracts_stock_and_rounds_packs():
    # 1000개 × 50ml × 10% × density1 = 5000g 글리세린 필요
    inv = Inventory(
        ingredients=[
            InventoryIngredient(id="glycerin", on_hand_g=500, pack_size_g=1000, pack_price=4500)
        ]
    )
    sl = shopping_list(_formula(), ingredients=IDX, packaging=PKG, inventory=inv, units=1000)
    gly = next(l for l in sl.ingredients if l.id == "glycerin")
    assert gly.need_g == 5000
    assert gly.on_hand_g == 500
    assert gly.short_g == 4500
    # 부족 4500 → 1000g 팩 5개 = 5000g, 비용 5 × 4500
    assert gly.packs == 5
    assert gly.buy_g == 5000
    assert gly.cost == 22500


def test_units_mode_packaging_moq_and_deadstock():
    inv = Inventory(packaging=[InventoryPackaging(id="jar", on_hand=200)])
    sl = shopping_list(_formula(), ingredients=IDX, packaging=PKG, inventory=inv, units=1000)
    jar = sl.packaging[0]
    assert jar.need_units == 1000
    assert jar.on_hand == 200
    assert jar.short == 800
    assert jar.order_qty == 3000  # MOQ
    assert jar.dead_qty == 2200
    assert jar.cost == 3000 * 800


def test_no_inventory_buys_everything():
    sl = shopping_list(_formula(), ingredients=IDX, packaging=PKG, units=100)
    gly = next(l for l in sl.ingredients if l.id == "glycerin")
    assert gly.on_hand_g == 0
    assert gly.short_g == gly.need_g


def test_grams_mode_ingredients_only():
    sl = shopping_list(_formula(), ingredients=IDX, packaging=PKG, grams=100)
    assert sl.mode == "grams"
    assert sl.packaging == []
    gly = next(l for l in sl.ingredients if l.id == "glycerin")
    assert gly.need_g == 10.0  # 10% of 100g


def test_stock_covers_need_means_no_buy():
    inv = Inventory(ingredients=[InventoryIngredient(id="glycerin", on_hand_g=1000)])
    sl = shopping_list(_formula(), ingredients=IDX, packaging=PKG, inventory=inv, grams=100)
    gly = next(l for l in sl.ingredients if l.id == "glycerin")
    assert gly.short_g == 0
    assert gly.buy_g == 0
    assert gly.cost == 0


def test_requires_exactly_one_of_units_grams():
    with pytest.raises(ValueError):
        shopping_list(_formula(), ingredients=IDX, packaging=PKG)
    with pytest.raises(ValueError):
        shopping_list(_formula(), ingredients=IDX, packaging=PKG, units=10, grams=10)
