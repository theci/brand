"""재고 유통/개봉 기한 계산 테스트."""

from __future__ import annotations

from datetime import date

from brandlab.core.models import Inventory, InventoryIngredient
from brandlab.inventory import (
    effective_expiry,
    expiry_status,
    inventory_rows,
)


def _item(**kw) -> InventoryIngredient:
    base = {"id": "x", "on_hand_g": 100}
    base.update(kw)
    return InventoryIngredient(**base)


def test_effective_expiry_uses_earliest():
    # 유통기한만
    assert effective_expiry(_item(expiry=date(2027, 1, 1))) == date(2027, 1, 1)
    # 개봉후 사용기한만 (2026-08-01 + 6개월 = 2027-02-01)
    assert effective_expiry(_item(opened=date(2026, 8, 1), pao_months=6)) == date(2027, 2, 1)
    # 둘 다 → 더 빠른 쪽
    both = _item(expiry=date(2027, 1, 1), opened=date(2026, 8, 1), pao_months=6)
    assert effective_expiry(both) == date(2027, 1, 1)
    # 정보 없음
    assert effective_expiry(_item()) is None


def test_add_months_month_end():
    # 1/31 + 1개월 = 2/28 (말일 보정)
    item = _item(opened=date(2026, 1, 31), pao_months=1)
    assert effective_expiry(item) == date(2026, 2, 28)


def test_expiry_status():
    today = date(2026, 9, 2)
    assert expiry_status(_item(expiry=date(2026, 7, 10)), today)[0] == "만료"
    assert expiry_status(_item(expiry=date(2026, 9, 20)), today)[0] == "임박"
    assert expiry_status(_item(expiry=date(2027, 1, 1)), today)[0] == "신선"
    assert expiry_status(_item(), today) == (None, None)


def test_shipped_inventory_references_valid_ids():
    from brandlab.inventory import unknown_inventory_ids
    from brandlab.loader import load_inventory, load_ingredients, load_packaging

    inv = load_inventory()
    unknown = unknown_inventory_ids(
        inv, load_ingredients().index(), load_packaging().index()
    )
    assert unknown == [], f"inventory.yaml이 존재하지 않는 id 참조: {unknown}"


def test_inventory_rows_sorted_by_severity():
    inv = Inventory(
        ingredients=[
            _item(id="fresh", expiry=date(2027, 1, 1)),
            _item(id="expired", expiry=date(2026, 1, 1)),
            _item(id="near", expiry=date(2026, 9, 20)),
        ]
    )
    rows = inventory_rows(inv, {}, date(2026, 9, 2))
    assert [r.id for r in rows] == ["expired", "near", "fresh"]
