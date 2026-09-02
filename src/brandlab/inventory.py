"""원료·포장 재고와 유통/개봉기한 계산.

- effective_expiry : 유통기한(미개봉)과 '개봉일+개봉후 사용개월' 중 빠른 날짜.
- expiry_status    : 오늘 기준 만료/임박/신선 판정.
- inventory_rows   : 표시용 행 생성(원료 한글명·보유량·기한·상태).

재고 파일(inventory.yaml)은 선택 데이터다. 없으면 빈 재고로 다룬다.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from .core.models import (
    Ingredient,
    Inventory,
    InventoryIngredient,
    Packaging,
)

# 유통기한 '임박' 판정 기준(일). 이 일수 이내면 임박 경고.
DEFAULT_NEAR_DAYS = 30


def _add_months(d: date, months: int) -> date:
    """날짜에 개월을 더한다(말일 보정). 예: 1/31 + 1개월 = 2/28."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def effective_expiry(item: InventoryIngredient) -> date | None:
    """미개봉 유통기한과 개봉후 사용기한 중 더 빠른 날짜."""
    candidates: list[date] = []
    if item.expiry is not None:
        candidates.append(item.expiry)
    if item.opened is not None and item.pao_months is not None:
        candidates.append(_add_months(item.opened, item.pao_months))
    if not candidates:
        return None
    return min(candidates)


def expiry_status(
    item: InventoryIngredient, today: date, near_days: int = DEFAULT_NEAR_DAYS
) -> tuple[str | None, int | None]:
    """(상태, 남은 일수). 기한 정보가 없으면 (None, None)."""
    eff = effective_expiry(item)
    if eff is None:
        return None, None
    days = (eff - today).days
    if days < 0:
        return "만료", days
    if days <= near_days:
        return "임박", days
    return "신선", days


@dataclass
class InventoryRow:
    id: str
    name: str
    on_hand_g: float
    effective_expiry: date | None
    status: str | None  # "만료" | "임박" | "신선" | None
    days_left: int | None


def inventory_rows(
    inventory: Inventory,
    ingredient_index: dict[str, Ingredient],
    today: date,
    near_days: int = DEFAULT_NEAR_DAYS,
) -> list[InventoryRow]:
    """재고 원료를 상태 심각도(만료→임박→신선→미상) 순으로 정렬해 반환."""
    rows: list[InventoryRow] = []
    for item in inventory.ingredients:
        ing = ingredient_index.get(item.id)
        name = ing.name if ing else item.id
        status, days = expiry_status(item, today, near_days)
        rows.append(
            InventoryRow(
                id=item.id,
                name=name,
                on_hand_g=item.on_hand_g,
                effective_expiry=effective_expiry(item),
                status=status,
                days_left=days,
            )
        )

    order = {"만료": 0, "임박": 1, "신선": 2, None: 3}
    rows.sort(key=lambda r: (order.get(r.status, 3), r.days_left if r.days_left is not None else 10**9))
    return rows


def unknown_inventory_ids(
    inventory: Inventory,
    ingredient_index: dict[str, Ingredient],
    packaging_index: dict[str, Packaging],
) -> list[str]:
    """재고가 참조하는데 마스터에 없는 id 목록(검증·경고용)."""
    missing = [i.id for i in inventory.ingredients if i.id not in ingredient_index]
    missing += [p.id for p in inventory.packaging if p.id not in packaging_index]
    return sorted(set(missing))


__all__ = [
    "DEFAULT_NEAR_DAYS",
    "InventoryRow",
    "effective_expiry",
    "expiry_status",
    "inventory_rows",
    "unknown_inventory_ids",
]
