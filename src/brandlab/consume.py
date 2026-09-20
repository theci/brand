"""배치 소비 → 재고 차감.

벤치에서 만든 배치(BatchRecord)가 실제로 쓴 원료량만큼 재고(Inventory)의
보유량(on_hand_g)을 줄인다. 이걸 배치마다 돌리면 inventory.yaml이 실제와
계속 일치하고, 장바구니(shopping) 결과가 늘 최신 상태가 된다.

- 소비량: 배치 줄의 actual_g(실측)가 있으면 그것을, 없으면 target_g(목표)를 쓴다.
- 재고에 없는 원료: 차감할 대상이 없으므로 건너뛰고 경고에 남긴다.
- 보유량보다 많이 쓴 경우: 0으로 막고(음수 금지) 경고한다(재고 기록 누락 신호).

순수 계산만 한다. 파일 쓰기는 inventory_edit.apply_consumption 이 담당한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .core.models import BatchRecord, Ingredient, Inventory


@dataclass
class ConsumeLine:
    id: str
    name: str
    used_g: float
    before_g: float | None  # 재고 미등록이면 None
    after_g: float | None
    note: str | None = None


@dataclass
class ConsumeResult:
    batch_id: str
    lines: list[ConsumeLine]
    # 실제로 파일에 반영할 {원료 id: 차감 후 보유량(g)} (재고 등록분만)
    updates: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_used_g(self) -> float:
        return round(sum(l.used_g for l in self.lines), 2)


def line_usage(batch: BatchRecord) -> dict[str, float]:
    """배치의 원료별 소비량(g). actual_g 우선, 없으면 target_g. 같은 id는 합산."""
    usage: dict[str, float] = {}
    for l in batch.lines:
        used = l.actual_g if l.actual_g is not None else l.target_g
        usage[l.id] = usage.get(l.id, 0.0) + used
    return usage


def consume_batch(
    batch: BatchRecord,
    inventory: Inventory,
    ingredient_index: Mapping[str, Ingredient] | None = None,
) -> ConsumeResult:
    """배치가 쓴 만큼 재고를 차감한 결과를 계산한다(파일은 안 건드림)."""
    idx = ingredient_index or {}
    inv_idx = inventory.ingredient_index()

    lines: list[ConsumeLine] = []
    updates: dict[str, float] = {}
    warnings: list[str] = []

    for ing_id, used in line_usage(batch).items():
        name = idx[ing_id].name if ing_id in idx else ing_id
        stock = inv_idx.get(ing_id)

        if stock is None:
            lines.append(ConsumeLine(ing_id, name, round(used, 2), None, None, "재고 미등록 — 차감 생략"))
            warnings.append(f"'{name}'({ing_id})은(는) 재고에 없어 차감하지 못했습니다.")
            continue

        before = stock.on_hand_g
        after = before - used
        note = None
        if after < 0:
            warnings.append(
                f"'{name}'({ing_id}) 보유 {before:g}g < 사용 {used:g}g → 0으로 처리(재고 기록 확인 필요)."
            )
            after = 0.0
            note = "보유량 부족 → 0"
        after = round(after, 2)
        updates[ing_id] = after
        lines.append(ConsumeLine(ing_id, name, round(used, 2), round(before, 2), after, note))

    return ConsumeResult(batch_id=batch.batch_id, lines=lines, updates=updates, warnings=warnings)


__all__ = ["ConsumeLine", "ConsumeResult", "line_usage", "consume_batch"]
