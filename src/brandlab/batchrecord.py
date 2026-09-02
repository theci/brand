"""배치 기록(batch record).

벤치에서 실제로 만든 소량 배치의 '실측 결과'를 처방 버전에 연결해 남긴다.
  - new_batch_record : 처방을 목표 배치량으로 환산해 원료별 목표 무게를 채운 빈 기록을 만든다.
  - batch_summary    : 여러 배치 기록을 수율·pH 표로 요약한다.

실측 무게·회수량·pH는 사용자가 저울·pH미터로 측정해 채운다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date as date_cls

from .core.models import (
    BatchLine,
    BatchRecord,
    Formula,
    Ingredient,
    IngredientMaster,
)
from .core.scaling import scale


def _slug_prefix(slug: str) -> str:
    """슬러그 → 배치ID 접두어. 예: daily-toner → DT, fabric-spray → FS."""
    parts = [p for p in slug.replace("_", "-").split("-") if p]
    if not parts:
        return "BATCH"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return "".join(p[0] for p in parts).upper()


def make_batch_id(slug: str, on_date: date_cls, seq: int) -> str:
    """예: DT-20260902-01."""
    return f"{_slug_prefix(slug)}-{on_date:%Y%m%d}-{seq:02d}"


def new_batch_record(
    formula: Formula,
    grams: float,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    batch_id: str,
    on_date: date_cls,
) -> BatchRecord:
    """처방을 grams 배치로 환산해 원료별 목표 무게를 채운 빈 배치 기록을 만든다.

    actual_g·yield_g·ph는 None(미측정)으로 두어, 제조 후 사용자가 채운다.
    """
    result = scale(formula, grams, ingredients=ingredients)
    lines = [
        BatchLine(id=si.id, target_g=round(si.grams, 2), actual_g=None)
        for phase in result.phases
        for si in phase.ingredients
    ]
    return BatchRecord(
        batch_id=batch_id,
        formula_ref=f"{formula.slug} v{formula.version}",
        slug=formula.slug,
        version=formula.version,
        date=on_date,
        target_g=grams,
        yield_g=None,
        ph=None,
        lines=lines,
        observations=None,
        operator=None,
    )


def batch_record_to_yaml_dict(record: BatchRecord) -> dict:
    """YAML 저장용 dict. None 필드도 남겨 사용자가 채울 자리를 보여준다."""
    return {
        "batch_id": record.batch_id,
        "formula_ref": record.formula_ref,
        "slug": record.slug,
        "version": record.version,
        "date": record.date,
        "target_g": record.target_g,
        "yield_g": record.yield_g,  # ← 완성 후 무게(g) 기입
        "ph": record.ph,  # ← 측정 pH 기입 (피부제품 4.5~6.0 목표)
        "lines": [
            {"id": l.id, "target_g": l.target_g, "actual_g": l.actual_g}
            for l in record.lines
        ],
        "observations": record.observations,  # ← 외관·향·사용감 메모
        "operator": record.operator,
    }


@dataclass
class BatchSummaryRow:
    batch_id: str
    formula_ref: str
    date: date_cls
    target_g: float
    yield_g: float | None
    yield_percent: float | None
    ph: float | None
    ph_ok: bool | None  # 피부제품 4.5~6.0 기준. pH 미측정이면 None.
    observations: str | None


# 피부 도포 제품 권장 pH 범위(참고용). 제형에 따라 조정 가능.
SKIN_PH_MIN = 4.5
SKIN_PH_MAX = 6.0


def batch_summary(records: list[BatchRecord]) -> list[BatchSummaryRow]:
    """배치 기록들을 날짜순 요약 행으로 변환한다."""
    rows: list[BatchSummaryRow] = []
    for r in sorted(records, key=lambda x: (x.date, x.batch_id)):
        ph_ok = None if r.ph is None else (SKIN_PH_MIN <= r.ph <= SKIN_PH_MAX)
        rows.append(
            BatchSummaryRow(
                batch_id=r.batch_id,
                formula_ref=r.formula_ref,
                date=r.date,
                target_g=r.target_g,
                yield_g=r.yield_g,
                yield_percent=r.yield_percent,
                ph=r.ph,
                ph_ok=ph_ok,
                observations=r.observations,
            )
        )
    return rows


__all__ = [
    "make_batch_id",
    "new_batch_record",
    "batch_record_to_yaml_dict",
    "batch_summary",
    "BatchSummaryRow",
    "SKIN_PH_MIN",
    "SKIN_PH_MAX",
]
