"""사전점검 페이지 — 제조 전 HLB 유화 균형 + 배합한도 (check)."""

from __future__ import annotations

import streamlit as st

from brandlab.checks import check_formula
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("처방 사전점검 · HLB · 배합한도")
st.caption("제형을 만들기 전에, 유화가 깨질 위험과 배합한도 초과를 처방서 숫자로 미리 거른다.")

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
formula = options[st.selectbox("처방 선택", list(options))]

result = check_formula(formula, ingredients=lab.ingredients, limits=lab.limits)

# HLB
st.subheader("HLB 유화 균형")
h = result.hlb
if h.applicable:
    render = {"적합": st.success, "주의": st.warning, "위험": st.error}.get(h.verdict, st.info)
    render(f"**{h.verdict}** — {h.message}")
    c1, c2, c3 = st.columns(3)
    c1.metric("공급 HLB", h.supplied_hlb)
    c2.metric("요구 HLB", h.required_hlb)
    if h.gap is not None:
        c3.metric("차이(Δ)", f"{h.gap:+g}")
    st.caption(f"유화제: {', '.join(h.emulsifiers)}  ·  유상: {', '.join(h.oils)}")
else:
    st.info(h.message)
    st.caption("유화제에 `hlb`, 오일에 `required_hlb` 값을 넣으면 HLB 점검이 동작합니다.")

# 배합한도
st.subheader("배합한도 점검")
if not result.limit_findings:
    st.success("초과·근접(도달) 원료 없음")
else:
    st.table(
        [
            {"원료": f.name, "함량%": f.percent, "한도%": f.limit, "출처": f.source, "판정": f.status}
            for f in result.limit_findings
        ]
    )

# 종합
if result.ok:
    st.success("종합 사전점검: 통과 — 개발을 진행해도 되는 처방입니다.")
else:
    st.error("종합 사전점검: 확인 필요 — 위 항목을 조정하세요.")
