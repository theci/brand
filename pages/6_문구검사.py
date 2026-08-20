"""문구 검사 페이지 — 상세페이지 문구에서 금지·주의 표현 하이라이트."""

from __future__ import annotations

import streamlit as st

from brandlab.adcopy import highlight_html, lint
from brandlab.ui import load_ad_terms, setup_korean_font

st.set_page_config(page_title="문구검사 · brand-lab", page_icon="📝", layout="wide")
setup_korean_font()
st.title("상세페이지 문구 검사")

terms = load_ad_terms()
st.caption(
    f"등록된 표현 {len(terms.terms)}건 "
    + (f"· 데이터 갱신 {terms.last_updated}" if terms.last_updated else "")
)

sample = "미백 효과가 뛰어난 크림. 주름개선과 염증 완화에 도움을 주고, 하루만에 완벽한 피부로."
text = st.text_area("상세페이지 문구 입력", value=sample, height=200)

result = lint(text, terms)

for w in result.warnings:
    st.warning(w)

counts = result.counts_by_risk()
c1, c2, c3 = st.columns(3)
c1.metric("high", counts["high"])
c2.metric("medium", counts["medium"])
c3.metric("low", counts["low"])

st.subheader("하이라이트")
if text.strip():
    html = highlight_html(text, result.findings)
    st.markdown(
        f'<div style="line-height:1.9;font-size:1.05rem">{html}</div>',
        unsafe_allow_html=True,
    )
    st.caption("🟥 high · 🟧 medium · 🟨 low")
else:
    st.info("문구를 입력하세요.")

if result.findings:
    st.subheader("발견된 표현")
    st.table(
        [
            {
                "위치": f.start,
                "표현": f.expression,
                "매칭": f.matched_text,
                "카테고리": f.category,
                "위험도": f.risk,
                "대체안": f.suggestion or "-",
                "근거": f.reference or "-",
            }
            for f in result.findings
        ]
    )
elif text.strip():
    st.success("등록된 문제 표현을 찾지 못했습니다.")

st.error(result.disclaimer)
