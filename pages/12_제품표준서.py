"""제품표준서 페이지 — 처방·전성분·제조·규제·안정성·원가를 1문서로 (dossier)."""

from __future__ import annotations

import streamlit as st

from brandlab.dossier import build_dossier
from brandlab.loader import load_all_batches, load_all_stability
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("제품표준서 (dossier)")
st.caption("처방·전성분·제조지시·품질규격·규제·안정성·원가·배치이력을 1개 문서로 컴파일한다.")

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
formula = options[st.selectbox("처방 선택", list(options))]

c1, c2 = st.columns(2)
include_cost = c1.checkbox("원가 요약 포함", value=True)
units = c2.number_input("원가 기준 수량", min_value=1, value=1000, step=100) if include_cost else None

md = build_dossier(
    formula,
    lab,
    units=int(units) if units else None,
    stability=load_all_stability(),
    batches=load_all_batches(),
)

st.download_button(
    "제품표준서 내려받기 (.md)",
    md,
    file_name=f"제품표준서_{formula.slug}_v{formula.version}.md",
)
st.divider()
st.markdown(md)
