"""문구 검사 페이지 — 광고표현 도메인(레짐)별로 규칙을 골라 검사한다.

같은 마케팅 문구라도 제품이 무엇이냐에 따라 적용되는 광고 규제가 다르다
(화장품=화장품법 표시광고, 식품=식품표시광고법, …). 그래서 검사에 쓸
'광고표현 도메인'을 먼저 고르고, 해당 레짐의 ad_terms.yaml로 검사한다.

도메인은 data/regulatory/<레짐>/ad_terms.yaml 존재로 자동 탐색한다.
새 레짐(예: food)의 ad_terms.yaml을 추가하면 코드 수정 없이 선택지에 나타난다.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from brandlab.adcopy import highlight_html
from brandlab.compliance import compliance_check
from brandlab.loader import (
    PROJECT_ROOT,
    load_ad_terms,
    load_brand_core,
    load_regime_info,
)
from brandlab.ui import setup_korean_font

setup_korean_font()
st.title("상세페이지 문구 검사")

reg_dir = Path(PROJECT_ROOT) / "data" / "regulatory"

# 광고표현 도메인 자동 탐색: ad_terms.yaml 이 있는 레짐만 선택지에 오른다.
domains = sorted(p.parent.name for p in reg_dir.glob("*/ad_terms.yaml"))
if not domains:
    st.error(
        "광고표현 데이터를 찾지 못했습니다. "
        "data/regulatory/<레짐>/ad_terms.yaml 을 추가하세요."
    )
    st.stop()


def domain_label(code: str) -> str:
    """레짐 코드를 사람이 읽는 이름으로. regime.yaml 이 없으면 코드 그대로."""
    try:
        info = load_regime_info(code, reg_dir)
        return f"{info.display_name} ({code})"
    except Exception:
        return code


label_to_code = {domain_label(c): c for c in domains}
chosen_label = st.selectbox("광고표현 도메인(레짐)", list(label_to_code))
regime_code = label_to_code[chosen_label]

if len(domains) == 1:
    st.caption(
        "현재 등록된 광고표현 도메인은 화장품뿐입니다. "
        "다른 레짐(예: 식품)의 ad_terms.yaml 을 추가하면 여기서 선택할 수 있습니다."
    )

terms = load_ad_terms(reg_dir / regime_code / "ad_terms.yaml")
st.caption(
    f"'{chosen_label}' 기준 · 등록된 표현 {len(terms.terms)}건 "
    + (f"· 데이터 갱신 {terms.last_updated}" if terms.last_updated else "")
)

# 브랜드 코어의 금지어까지 함께 검사한다(STEP9 규제 검수 게이트와 동일 엔진).
core = load_brand_core()
use_brand = st.checkbox(
    "브랜드 금지어도 함께 검사(브랜드 코어)", value=bool(core.forbidden_words)
)
if core.forbidden_words:
    st.caption("브랜드 금지어: " + ", ".join(core.forbidden_words))
else:
    st.caption("브랜드 코어에 금지어가 없습니다(STEP10 브랜드 코어에서 ⑧ 금지어를 채우세요).")
st.caption("※ 이 검사는 STEP9 상품등록의 '규제 검수 게이트'와 같은 엔진입니다.")

sample = "미백 효과가 뛰어난 크림. 주름개선과 염증 완화에 도움을 주고, 하루만에 완벽한 피부로."
text = st.text_area("상세페이지 문구 입력", value=sample, height=200)

result = compliance_check(
    text,
    terms=terms,
    forbidden_words=core.forbidden_words if use_brand else None,
)

for w in result.warnings:
    st.warning(w)

counts = result.counts_by_risk()
c1, c2, c3 = st.columns(3)
c1.metric("high", counts["high"])
c2.metric("medium", counts["medium"])
c3.metric("low", counts["low"])

if text.strip():
    if result.ok:
        st.success("✅ 통과 — high 위험 표현 없음 (통과=합법 아님, 1차 스크리닝)")
    else:
        st.error(f"❌ 확인 필요 — high 위험 {counts['high']}건. 아래 강조 표현을 고치세요.")

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
