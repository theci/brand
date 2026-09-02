"""배치 기록(batch record) 테스트."""

from __future__ import annotations

from datetime import date

from brandlab.batchrecord import (
    batch_summary,
    make_batch_id,
    new_batch_record,
)
from brandlab.core.models import BatchRecord, Formula, Ingredient


def _formula():
    return Formula.model_validate(
        {
            "product": "테스트토너",
            "slug": "daily-toner",
            "version": 1,
            "product_type": "leave_on",
            "status": "개발중",
            "base_batch_g": 100,
            "fill_volume_ml": 100,
            "phases": [
                {
                    "name": "A",
                    "ingredients": [
                        {"id": "water", "percent": 95.0},
                        {"id": "glycerin", "percent": 5.0},
                    ],
                }
            ],
        }
    )


IDX = {
    "water": Ingredient(id="water", name="정제수", inci="Water", category="용제"),
    "glycerin": Ingredient(id="glycerin", name="글리세린", inci="Glycerin", category="보습제"),
}


def test_make_batch_id_format():
    assert make_batch_id("daily-toner", date(2026, 9, 2), 1) == "DT-20260902-01"
    assert make_batch_id("soap", date(2026, 9, 2), 3) == "SO-20260902-03"


def test_new_batch_record_targets_sum_to_grams():
    f = _formula()
    rec = new_batch_record(
        f, 200.0, ingredients=IDX, batch_id="DT-20260902-01", on_date=date(2026, 9, 2)
    )
    assert rec.target_g == 200.0
    assert rec.yield_g is None
    assert rec.ph is None
    total = sum(l.target_g for l in rec.lines)
    assert abs(total - 200.0) < 0.01
    assert all(l.actual_g is None for l in rec.lines)
    water = next(l for l in rec.lines if l.id == "water")
    assert abs(water.target_g - 190.0) < 0.01


def test_yield_percent_property():
    rec = BatchRecord(
        batch_id="B1",
        formula_ref="test v1",
        date=date(2026, 9, 2),
        target_g=100.0,
        yield_g=92.5,
    )
    assert rec.yield_percent == 92.5


def test_yield_percent_none_when_not_measured():
    rec = BatchRecord(
        batch_id="B1", formula_ref="test v1", date=date(2026, 9, 2), target_g=100.0
    )
    assert rec.yield_percent is None


def test_batch_summary_ph_flag():
    recs = [
        BatchRecord(
            batch_id="B1", formula_ref="t v1", date=date(2026, 9, 2), target_g=100.0, ph=5.2
        ),
        BatchRecord(
            batch_id="B2", formula_ref="t v1", date=date(2026, 9, 3), target_g=100.0, ph=8.0
        ),
        BatchRecord(
            batch_id="B3", formula_ref="t v1", date=date(2026, 9, 4), target_g=100.0
        ),
    ]
    rows = {r.batch_id: r for r in batch_summary(recs)}
    assert rows["B1"].ph_ok is True
    assert rows["B2"].ph_ok is False
    assert rows["B3"].ph_ok is None
