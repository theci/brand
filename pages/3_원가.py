"""원가 페이지 — 원가 내역, 손익, MOQ 병목, 판매가별 마진 곡선."""

from __future__ import annotations

import streamlit as st

from brandlab.cost import (
    breakeven,
    min_price_for_margin,
    moq_bottleneck,
    price_simulator,
    unit_cost,
)
from brandlab.ui import format_won, load_lab, setup_korean_font

st.set_page_config(page_title="원가 · brand-lab", page_icon="💰", layout="wide")
setup_korean_font()
st.title("원가 · 손익")

lab = load_lab()
econ = lab.config.economics
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
label = st.selectbox("처방 선택", list(options))
formula = options[label]

c1, c2 = st.columns(2)
units = c1.number_input("주문 수량", min_value=1, value=1000, step=100)
price = c2.number_input("판매가 (부가세 포함)", min_value=100, value=34000, step=1000)

uc = unit_cost(formula, int(units), ingredients=lab.ingredients, packaging=lab.packaging)
sim = price_simulator(uc, float(price), economics=econ)
mb = moq_bottleneck(formula, int(units), ingredients=lab.ingredients, packaging=lab.packaging)

# 원가 내역
st.subheader("개당 원가 내역")
crows = [
    {"구분": "원료", "항목": l.name, "내역": l.detail, "개당 원가": format_won(l.cost)}
    for l in uc.material_lines
] + [
    {"구분": "부자재", "항목": l.name, "내역": l.detail, "개당 원가": format_won(l.cost)}
    for l in uc.packaging_lines
]
st.table(crows)
m1, m2, m3 = st.columns(3)
m1.metric("원료비", format_won(uc.material_cost))
m2.metric("부자재비", format_won(uc.packaging_cost))
m3.metric("개당 원가", format_won(uc.unit_cost))
for w in uc.warnings:
    st.warning(w)

# 손익 요약
st.subheader("개당 손익")
srows = [
    {"항목": "실매출(부가세 제외)", "값": format_won(sim.net_revenue)},
    {"항목": "− 채널 수수료", "값": format_won(sim.channel_fee)},
    {"항목": "− 배송비", "값": format_won(sim.shipping)},
    {"항목": "− 개당 원가", "값": format_won(sim.unit_cost)},
    {"항목": "− 반품 비용", "값": format_won(sim.return_cost)},
    {"항목": "개당 공헌이익", "값": format_won(sim.contribution)},
]
st.table(srows)
k1, k2, k3 = st.columns(3)
k1.metric("마진율(실매출 대비)", f"{sim.margin_on_net:.1%}")
k2.metric("마진율(판매가 대비)", f"{sim.margin_on_price:.1%}")
if econ.target_margin is not None:
    mp = min_price_for_margin(uc, econ.target_margin, economics=econ)
    k3.metric(
        f"목표마진 {econ.target_margin:.0%} 최소판매가",
        format_won(mp) if mp else "달성 불가",
    )
for w in sim.warnings:
    st.error(w)

be = breakeven(mb.total_upfront_capital, sim.contribution)
if be is not None:
    st.write(f"손익분기 수량: **{be:,}개**")
    st.caption(
        f"고정비(총 선투입 자본) {format_won(mb.total_upfront_capital)} ÷ 공헌이익 "
        f"{format_won(sim.contribution)} 기준"
    )
else:
    st.write("손익분기: 달성 불가(공헌이익 ≤ 0)")

# MOQ 병목
st.subheader("MOQ 병목")
mrows = [
    {
        "부자재": it.name,
        "필요": it.need_qty,
        "MOQ": it.moq if it.moq else "-",
        "발주": it.order_qty,
        "사장재고": it.dead_qty,
        "자본": format_won(it.capital),
    }
    for it in mb.items
]
st.table(mrows)
if mb.bottleneck is not None:
    st.warning(
        f"초도 물량 병목: **{mb.bottleneck.name}** → 사장 재고 없이 만들려면 "
        f"최소 {mb.min_units_no_waste:,}개 생산 필요"
    )
st.write(
    f"총 선투입 자본: **{format_won(mb.total_upfront_capital)}** "
    f"(원료 {format_won(mb.material_capital)} + 부자재 {format_won(mb.packaging_capital)}) · "
    f"사장 재고 자본 {format_won(uc.dead_stock_capital)}"
)

# 판매가별 마진 곡선
st.subheader("판매가별 마진 곡선")
import matplotlib.pyplot as plt

lo = max(int(uc.unit_cost), 1000)
hi = max(int(price) * 2, lo * 3)
step = max((hi - lo) // 40, 1)
prices = list(range(lo, hi + step, step))
margins = [price_simulator(uc, float(p), economics=econ).margin_on_net * 100 for p in prices]

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(prices, margins, color="#2b8a3e")
ax.axhline(0, color="gray", linewidth=0.6)
if econ.target_margin is not None:
    ax.axhline(econ.target_margin * 100, color="#e8590c", linestyle="--",
               label=f"목표마진 {econ.target_margin:.0%}")
ax.axvline(price, color="#1c7ed6", linestyle=":", label=f"현재가 {format_won(price)}")
ax.set_xlabel("판매가 (원)")
ax.set_ylabel("마진율(실매출 대비) %")
ax.set_title("판매가에 따른 마진율")
ax.legend(fontsize=8)
fig.tight_layout()
st.pyplot(fig)

st.caption("가정: " + " / ".join(sim.assumptions))
