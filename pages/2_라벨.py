"""라벨 페이지 — 전성분 문자열, 알러젠 판정, 표시 의무, 배합한도 체크."""

from __future__ import annotations

import streamlit as st

from brandlab.labeling import screen
from brandlab.ui import load_lab, setup_korean_font

st.set_page_config(page_title="라벨 · brand-lab", page_icon="🏷", layout="wide")
setup_korean_font()
st.title("라벨 스크리닝")

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
label = st.selectbox("처방 선택", list(options))
formula = options[label]

result = screen(formula, lab)

# 규제 데이터 최신성
for w in result.freshness.warnings:
    st.warning(f"규제데이터: {w}")

# 전성분 문자열 (st.code = 복사 버튼 내장)
st.subheader("전성분 표시(안)")
st.code(result.inci.text or "(없음)", language="text")
for w in result.inci.warnings:
    st.warning(w)

# 알러젠 판정
st.subheader(
    f"알러젠 판정 (임계값 {result.allergens.threshold_percent:g}% / "
    f"{result.allergens.product_type.value})"
)
arows = [
    {
        "성분": f.name,
        "INCI": f.inci,
        "완제품 농도%": f.concentration_percent,
        "표기": "표기 필요" if f.must_declare else "이하",
    }
    for f in [*result.allergens.declared, *result.allergens.below_threshold]
]
st.table(arows or [{"성분": "해당 없음", "INCI": "", "완제품 농도%": "", "표기": ""}])
for w in result.allergens.warnings:
    st.warning(w)

# 표시 의무
req = result.requirement
size = f"{req.size_value:g}{req.size_unit}" if req.size_value is not None else "미상"
st.subheader("표시 의무")
st.write(f"내용량 **{size}** → 구분: **{req.tier}**")
st.write("표시 항목: " + ", ".join(req.required_items))
for n in req.notes:
    st.caption(n)

# 배합한도
st.subheader("배합한도 체크")
if not result.limits.has_data:
    st.error(result.limits.warnings[0])
else:
    lrows = [
        {
            "원료": f.name,
            "함량%": f.percent,
            "한도%": f.max_percent,
            "판정": "초과" if f.exceeded else "적합",
        }
        for f in result.limits.findings
    ]
    st.table(lrows or [{"원료": "대조 대상 없음", "함량%": "", "한도%": "", "판정": ""}])
    for w in result.limits.warnings:
        st.warning(w)

st.error(result.disclaimer)
