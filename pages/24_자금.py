"""자금 6:4 대시보드 (STEP 7) — 제품 60 : 마케팅 40, 런웨이·편차.

사업 전체 자금 배분 시야. 회계 툴이 아니며, 6:4 규칙 편차와 런웨이만 본다.
"""

from __future__ import annotations

from datetime import date as date_cls

import matplotlib.pyplot as plt
import streamlit as st

from brandlab.budget import CATEGORIES, MARKETING, PRODUCT, save_budget, summarize
from brandlab.core.models import Budget, Expense
from brandlab.loader import load_budget
from brandlab.ui import format_won, setup_korean_font

setup_korean_font()
st.title("자금 6:4 💰")
st.caption("제품 60 : 마케팅 40 목표 대비 편차와 런웨이를 봅니다. (배송·회계는 외부 도구)")
st.info(
    "표기: 🔒 **자동**(비중·런웨이·경고는 아래에서 자동 계산) · ✍️ **직접 입력**(총 자본·월 소진·"
    "지출 내역). 지출은 category만 목록에서 고르고 금액·메모는 직접 적으세요."
)

budget = load_budget()


def _num(v, default=0.0) -> float:
    try:
        return max(0.0, float(v))
    except (TypeError, ValueError):
        return default


def _date(v):
    if isinstance(v, date_cls):
        return v
    s = str(v or "").strip()
    try:
        return date_cls.fromisoformat(s) if s else None
    except ValueError:
        return None


c1, c2, c3 = st.columns(3)
total_capital = c1.number_input("✍️ 총 자본(원)", min_value=0, value=int(budget.total_capital),
                                step=100000, help="굴릴 수 있는 전체 자본. 예: 10000000")
target = c2.slider("✍️ 제품 목표 비중", 0.0, 1.0, float(budget.target_product_ratio), 0.05,
                   help="제품:마케팅 목표 비율. 예: 0.6 = 6:4")
monthly_burn = c3.number_input("✍️ 월 소진(원, 런웨이용)", min_value=0,
                               value=int(budget.monthly_burn or 0), step=100000,
                               help="월평균 지출. 예: 800000")

st.subheader("지출 내역")
exp_rows = st.data_editor(
    [{"category": e.category, "amount": e.amount, "note": e.note or "",
      "spent_on": e.spent_on.isoformat() if e.spent_on else ""} for e in budget.expenses]
    or [{"category": "제품", "amount": 0, "note": "", "spent_on": ""}],
    num_rows="dynamic", width="stretch", key="budget_exp",
    column_config={
        "category": st.column_config.SelectboxColumn("category", options=list(CATEGORIES), help="제품/마케팅/기타 중 선택"),
        "amount": st.column_config.NumberColumn("amount", help="금액(원). 예: 3600000", min_value=0),
        "note": st.column_config.TextColumn("note", help="메모. 예: OEM 시생산비 / 상세페이지 촬영"),
        "spent_on": st.column_config.TextColumn("spent_on", help="지출일(선택). 예: 2026-03-01"),
    },
)

current = Budget(
    total_capital=float(total_capital),
    target_product_ratio=float(target),
    monthly_burn=float(monthly_burn) or None,
    expenses=[
        Expense(category=str(r.get("category") or "기타"), amount=_num(r.get("amount")),
                note=str(r.get("note") or "").strip() or None, spent_on=_date(r.get("spent_on")))
        for r in exp_rows if _num(r.get("amount")) > 0
    ],
)

if st.button("💾 자금 저장", type="primary"):
    try:
        path = save_budget(current)
        st.success(f"저장됨: {path}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장 실패: {exc}")

s = summarize(current)

st.divider()
m1, m2, m3, m4 = st.columns(4)
m1.metric("총 자본", format_won(s.total_capital))
m2.metric("총 지출", format_won(s.total_spent))
m3.metric("잔액", format_won(s.remaining))
m4.metric("런웨이", f"{s.runway_months:g}개월" if s.runway_months is not None else "—")

if s.product_ratio is not None:
    r1, r2 = st.columns(2)
    r1.metric("제품 비중(실제)", f"{s.product_ratio:.0%}", f"목표 {s.target_product_ratio:.0%}")
    r2.metric("마케팅 비중(실제)", f"{s.marketing_ratio:.0%}", f"목표 {1 - s.target_product_ratio:.0%}")

for w in s.warnings:
    st.warning(w)
if not s.warnings:
    st.success("6:4 배분·런웨이 양호.")

# 지출 구성 막대
if s.total_spent > 0:
    fig, ax = plt.subplots(figsize=(6, 2.6))
    cats = ["제품", "마케팅", "기타"]
    vals = [s.product_spent, s.marketing_spent, s.other_spent]
    ax.barh(cats, vals, color=["#2b8a3e", "#1c7ed6", "#adb5bd"])
    ax.set_xlabel("지출(원)")
    ax.invert_yaxis()
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:,.0f}", va="center", fontsize=8)
    fig.tight_layout()
    st.pyplot(fig)

st.caption("철학: 자본 6:4(제품:마케팅). 마케팅은 결국 제품력으로 수렴하므로 제품 투자가 뿌리.")
