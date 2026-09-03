"""자금 6:4 대시보드(Phase 10) 테스트."""

from __future__ import annotations

from brandlab.budget import save_budget, summarize
from brandlab.core.models import Budget, Expense
from brandlab.loader import load_budget


def _budget(expenses, total=10_000_000, target=0.6, burn=None):
    return Budget(
        total_capital=total, target_product_ratio=target, monthly_burn=burn,
        expenses=[Expense(**e) for e in expenses],
    )


def test_ratio_and_remaining():
    b = _budget([
        {"category": "제품", "amount": 6_000_000},
        {"category": "마케팅", "amount": 4_000_000},
    ])
    s = summarize(b)
    assert s.product_ratio == 0.6 and s.marketing_ratio == 0.4
    assert s.total_spent == 10_000_000 and s.remaining == 0
    assert s.deviation == 0.0
    assert not s.warnings  # 6:4 정확 → 경고 없음


def test_product_heavy_warns():
    b = _budget([
        {"category": "제품", "amount": 7_500_000},
        {"category": "마케팅", "amount": 2_500_000},
    ])
    s = summarize(b)
    assert s.product_ratio == 0.75
    assert any("제품 편중" in w for w in s.warnings)


def test_marketing_heavy_warns():
    b = _budget([
        {"category": "제품", "amount": 3_000_000},
        {"category": "마케팅", "amount": 7_000_000},
    ])
    s = summarize(b)
    assert any("마케팅 과다" in w for w in s.warnings)


def test_runway_and_overspend():
    b = _budget(
        [{"category": "제품", "amount": 8_000_000}, {"category": "마케팅", "amount": 4_000_000}],
        total=10_000_000, burn=1_000_000,
    )
    s = summarize(b)
    assert s.remaining == -2_000_000
    assert any("적자" in w for w in s.warnings)
    # 런웨이 = 잔액/월소진 = -2 → 음수, 3개월 미만 경고
    assert s.runway_months == -2.0
    assert any("런웨이" in w for w in s.warnings)


def test_empty_budget_no_ratio():
    s = summarize(Budget())
    assert s.product_ratio is None
    assert s.deviation is None
    assert s.total_spent == 0


def test_save_roundtrip(tmp_path):
    b = _budget([{"category": "제품", "amount": 100}], burn=50)
    p = tmp_path / "budget.yaml"
    save_budget(b, p)
    b2 = load_budget(p)
    assert b2.total_capital == 10_000_000
    assert b2.expenses[0].category == "제품"


def test_shipped_example_is_product_heavy():
    s = summarize(load_budget())  # data/brand/budget.yaml
    assert s.product_ratio == 0.75
    assert any("제품 편중" in w for w in s.warnings)
    assert s.runway_months is not None
