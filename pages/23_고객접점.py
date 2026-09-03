"""고객 접점·후기 페이지 (STEP 10) — 동봉카드·후기요청·재구매·후기→증거.

브랜드 톤으로 문구를 만들고, 내보내기 전 규제 게이트를 통과시킵니다.
대가성 후기 요청에는 뒷광고 표기가 자동으로 붙습니다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.loader import load_brand_core, load_reviews
from brandlab.touchpoints import (
    check_message,
    insert_card,
    repurchase_sequence,
    review_request,
    reviews_to_evidence,
)
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("고객 접점 · 후기 💬")
st.caption("배송→소비자→재구매. 문구는 규제 게이트를 통과해야 하고, 대가성 후기엔 뒷광고 표기가 붙습니다.")

lab = load_lab()
core = load_brand_core()

product_name = "제품"
if lab.formulas:
    opts = {f"{f.product} ({f.slug} v{f.version})": f for f in lab.formulas}
    sel = st.selectbox("제품 선택", list(opts))
    product_name = opts[sel].product


def _gate(text: str) -> None:
    """규제 게이트 결과 표시."""
    res = check_message(text, core)
    if res.ok:
        st.success("✅ 규제 게이트 통과 (high 위험 표현 없음)")
    else:
        c = res.counts_by_risk()
        st.error(f"⚠ 위험 표현 발견 — high {c['high']} / medium {c['medium']} / low {c['low']}")
        for f in res.findings[:10]:
            st.write(f"- [{f.risk}] '{f.expression}'" + (f" → {f.suggestion}" if f.suggestion else ""))
    st.caption(res.disclaimer)


tab_card, tab_req, tab_seq, tab_ev = st.tabs(["동봉 카드", "후기 요청", "재구매 시나리오", "후기 → 증거"])

with tab_card:
    text = insert_card(core, product_name)
    st.text_area("동봉 카드 문구", value=text, height=140, key="tp_card")
    _gate(st.session_state.get("tp_card", text))

with tab_req:
    incentive = st.checkbox("대가성(협찬·원고료) — 뒷광고 표기 자동 첨부", value=False)
    text = review_request(core, product_name, incentive=incentive)
    st.text_area("후기 요청 메시지", value=text, height=120, key="tp_req")
    if incentive:
        st.info("대가성 후기 요청입니다. 리뷰어가 협찬/원고료 사실을 표기하도록 안내 문구가 포함됩니다.")
    _gate(st.session_state.get("tp_req", text))

with tab_seq:
    st.caption("배송 후 경과일(D+n) 기준 카톡/문자 시나리오.")
    for s in repurchase_sequence(core, product_name):
        st.markdown(f"**D+{s.day} · {s.title}**")
        st.write(s.message)

with tab_ev:
    reviews = load_reviews().reviews
    cards = reviews_to_evidence(reviews)
    st.write(f"등록 후기 {len(reviews)}건 중, 근거로 쓸 수 있는(구매확인·★4↑) 후기 {len(cards)}건")
    if not cards:
        st.info("data/brand/reviews.yaml 에 verified 고평점 후기를 등록하면 근거 카드가 생깁니다.")
    else:
        for c in cards:
            st.markdown(f"- {c.text}")
        st.caption("이 문구들을 [브랜드 코어] ⑤ 근거에 붙여넣으면, 후기가 새 증거로 되먹여집니다.")
        st.warning("대가성(협찬) 후기를 광고에 인용할 때는 뒷광고 표기를 반드시 함께 노출하세요.")
