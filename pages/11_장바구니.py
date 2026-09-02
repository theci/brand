"""장바구니 페이지 — 재고 차감 후 구매 목록 (shopping)."""

from __future__ import annotations

import streamlit as st

from brandlab.loader import load_inventory
from brandlab.shopping import shopping_list
from brandlab.ui import format_won, load_lab, setup_korean_font

setup_korean_font()
st.title("장바구니 (shopping)")
st.caption("생산에 필요한 양에서 재고를 빼고, 부족분만 공급사 팩·MOQ 단위로 올려 구매 목록을 만든다.")

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
formula = options[st.selectbox("처방 선택", list(options))]

mode = st.radio("구매 기준", ["생산 수량(개)", "배치 크기(g)"], horizontal=True)
if mode.startswith("생산"):
    amount = st.number_input("생산 수량(개)", min_value=1, value=1000, step=100)
    units, grams = int(amount), None
else:
    amount = st.number_input("배치 크기(g)", min_value=1.0, value=100.0, step=10.0)
    units, grams = None, float(amount)

try:
    sl = shopping_list(
        formula,
        ingredients=lab.ingredients,
        packaging=lab.packaging,
        inventory=load_inventory(),
        units=units,
        grams=grams,
    )
except ValueError as exc:
    st.error(str(exc))
    st.stop()

st.subheader("원료 구매")


def _buy(l):
    if l.buy_g <= 0:
        return "구매 불필요"
    if l.packs is not None:
        return f"{l.packs}팩 ({l.buy_g:g}g)"
    return f"{l.buy_g:g}g"


st.table(
    [
        {
            "원료": l.name,
            "필요g": l.need_g,
            "보유g": l.on_hand_g,
            "부족g": l.short_g,
            "구매": _buy(l),
            "비용": format_won(l.cost),
        }
        for l in sl.ingredients
    ]
)
for l in sl.ingredients:
    if l.note:
        st.caption(f"⚠ {l.name}: {l.note}")

if sl.packaging:
    st.subheader("포장 구매")
    st.table(
        [
            {
                "포장재": l.name,
                "필요": l.need_units,
                "보유": l.on_hand,
                "부족": l.short,
                "발주": l.order_qty,
                "사장재고": l.dead_qty,
                "비용": format_won(l.cost),
            }
            for l in sl.packaging
        ]
    )

c1, c2, c3 = st.columns(3)
c1.metric("원료비", format_won(sl.material_cost))
c2.metric("포장비", format_won(sl.packaging_cost))
c3.metric("총 예상 구매액", format_won(sl.total_cost))
for w in sl.warnings:
    st.caption(f"· {w}")
