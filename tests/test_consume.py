"""배치 → 재고 차감(consume) 및 inventory.yaml 쓰기 테스트."""

from __future__ import annotations

from datetime import date

from brandlab.consume import consume_batch, line_usage
from brandlab.core.models import (
    BatchLine,
    BatchRecord,
    Ingredient,
    Inventory,
    InventoryIngredient,
)
from brandlab.inventory_edit import apply_consumption


def _batch(lines):
    return BatchRecord(
        batch_id="DL-20260902-01",
        formula_ref="daily-lotion v1",
        date=date(2026, 9, 2),
        target_g=100.0,
        lines=[BatchLine(**l) for l in lines],
    )


IDX = {
    "glycerin": Ingredient(id="glycerin", name="글리세린", inci="Glycerin", category="보습"),
    "water": Ingredient(id="water", name="정제수", inci="Water", category="용제"),
}


def test_uses_actual_when_present_else_target():
    usage = line_usage(
        _batch(
            [
                {"id": "glycerin", "target_g": 5.0, "actual_g": 4.8},
                {"id": "water", "target_g": 70.0, "actual_g": None},
            ]
        )
    )
    assert usage == {"glycerin": 4.8, "water": 70.0}


def test_same_id_summed():
    usage = line_usage(
        _batch(
            [
                {"id": "glycerin", "target_g": 5.0, "actual_g": None},
                {"id": "glycerin", "target_g": 2.0, "actual_g": None},
            ]
        )
    )
    assert usage == {"glycerin": 7.0}


def test_deducts_from_inventory():
    inv = Inventory(ingredients=[InventoryIngredient(id="glycerin", on_hand_g=500)])
    r = consume_batch(
        _batch([{"id": "glycerin", "target_g": 5.0, "actual_g": 4.8}]), inv, IDX
    )
    assert r.updates == {"glycerin": 495.2}
    line = r.lines[0]
    assert line.before_g == 500 and line.after_g == 495.2
    assert r.warnings == []


def test_over_use_floors_to_zero_and_warns():
    inv = Inventory(ingredients=[InventoryIngredient(id="glycerin", on_hand_g=3.0)])
    r = consume_batch(_batch([{"id": "glycerin", "target_g": 5.0}]), inv, IDX)
    assert r.updates == {"glycerin": 0.0}
    assert r.warnings  # 초과 사용 경고 존재
    assert r.lines[0].note == "보유량 부족 → 0"


def test_unknown_in_inventory_is_skipped_with_warning():
    inv = Inventory(ingredients=[InventoryIngredient(id="glycerin", on_hand_g=500)])
    r = consume_batch(_batch([{"id": "water", "target_g": 70.0}]), inv, IDX)
    assert r.updates == {}  # 재고에 없어 차감 대상 아님
    assert r.warnings
    assert r.lines[0].before_g is None and r.lines[0].note


def test_apply_consumption_preserves_comments_and_updates():
    text = (
        "# 재고 파일 주석\n"
        "last_updated: 2026-09-02\n\n"
        "ingredients:\n"
        "  - id: glycerin\n"
        "    on_hand_g: 500          # 인라인 주석 보존 확인\n"
        "    pack_size_g: 1000\n"
    )
    out = apply_consumption(text, {"glycerin": 495.2}, date(2026, 9, 20))
    assert "# 재고 파일 주석" in out
    assert "인라인 주석 보존 확인" in out
    assert "on_hand_g: 495.2" in out
    assert "last_updated: 2026-09-20" in out
    assert "pack_size_g: 1000" in out
