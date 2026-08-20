"""처방 페이지 — 상별 표, 배치 크기 실시간 환산, 배치 지시서 다운로드."""

from __future__ import annotations

import streamlit as st

from brandlab.batch import batch_sheet, scale
from brandlab.ui import load_lab, setup_korean_font

st.set_page_config(page_title="처방 · brand-lab", page_icon="🧪", layout="wide")
setup_korean_font()
st.title("처방")

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
label = st.selectbox("처방 선택", list(options))
formula = options[label]

c1, c2, c3 = st.columns(3)
c1.metric("제품 형태", formula.product_type.value)
c2.metric("상태", formula.status.value)
c3.metric("기준 배치", f"{formula.base_batch_g:g} g")

target = st.slider(
    "배치 크기 (g)",
    min_value=10,
    max_value=5000,
    value=int(formula.base_batch_g),
    step=10,
)

result = scale(formula, target, ingredients=lab.ingredients)

for phase in result.phases:
    st.subheader(f"상 {phase.name}")
    if phase.process:
        st.caption(f"공정: {phase.process}")
    rows = [
        {"원료": i.name, "목표 %": i.percent, "목표 g": round(i.grams, 2)}
        for i in phase.ingredients
    ]
    st.table(rows)
    st.caption(f"상 {phase.name} 소계: {phase.subtotal_g:.2f} g")

st.metric("전체 합계", f"{result.total_g:.2f} g", delta=f"목표 {target} g")

for w in result.warnings:
    st.warning(w)

md = batch_sheet(formula, target, ingredients=lab.ingredients)
st.download_button(
    "⬇️ 배치 지시서 (마크다운) 다운로드",
    data=md,
    file_name=f"batch-{formula.slug}-v{formula.version}-{target}g.md",
    mime="text/markdown",
)

with st.expander("배치 지시서 미리보기"):
    st.markdown(md)
