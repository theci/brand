"""상품 등록(STEP 9) — 상세페이지·리스팅 자료 생성 + 규제 검수 게이트.

제품 데이터 + 브랜드 코어 → 상품명·전성분·사용법·근거·촬영컷·배경 프롬프트·카피 생성 프롬프트.
이미지 원칙: 제품 실물은 실촬영, AI는 배경만. 마케팅 텍스트는 규제 검수 게이트를 통과시켜 내보낸다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.adcopy import highlight_html
from brandlab.compliance import compliance_check
from brandlab.listing import build_listing, listing_markdown, save_listing
from brandlab.loader import load_all_stability, load_brand_core
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("상품 등록 자료 📝")
st.caption(
    "제품 데이터 + 브랜드 코어로 상세페이지·리스팅 자료를 만듭니다. "
    "제품 실물 이미지는 실촬영 필수 — AI는 배경만. 카피는 규제 검수 게이트를 통과시켜 내보내세요."
)

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다. 먼저 처방을 만드세요.")
    st.stop()

core = load_brand_core()
options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
formula = options[st.selectbox("제품 선택", list(options))]
mask = st.checkbox("근거의 처방 % 가리기(영업비밀 보호)", value=True)

L = build_listing(formula, lab, core, stability=load_all_stability(), mask_percent=mask)
for w in L.warnings:
    st.warning(w)

c1, c2, c3 = st.columns(3)
c1.metric("상품명 후보", f"{len(L.product_names)}개")
c2.metric("용량", L.volume or "-")
c3.metric("근거 카드", f"{len(L.evidence)}개")

st.subheader("기본 정보")
st.write("**상품명 후보**: " + " · ".join(L.product_names))
st.write("**한 줄 소개**: " + (L.one_liner or "_(브랜드 코어에서 작성)_"))

st.subheader("전성분 (표시 순서)")
st.code(L.inci_text or "(전성분 생성 실패)")

g1, g2 = st.columns(2)
with g1:
    st.subheader("사용법")
    st.write(L.usage)
with g2:
    st.subheader("주의사항")
    for c in L.caution:
        st.write(f"- {c}")

st.subheader("검증된 근거 (창작 금지)")
if L.evidence:
    for e in L.evidence:
        st.write(f"- {e}")
else:
    st.info("근거가 없습니다. 브랜드 코어에서 근거를 추출·저장하세요.")

st.subheader("📸 실촬영 컷 리스트 (제품 실물은 AI 금지)")
for s in L.shot_list:
    st.write(f"- {s}")

st.subheader("🖼️ 배경 연출 AI 프롬프트 (제품은 실촬영, 배경만)")
for i, p in enumerate(L.background_prompts, 1):
    st.code(f"{i}. {p}")

st.subheader("✍️ 상세페이지 카피 생성 프롬프트 (외부 AI에 붙여넣기)")
st.code(L.copy_prompt)

d1, d2 = st.columns(2)
_md = listing_markdown(L)
d1.download_button("⬇️ 리스팅 자료 (.md)", _md, file_name=f"상품등록_{L.slug}_v{L.version}.md")
if d2.button("💾 listings/ 에 저장", type="primary"):
    try:
        path = save_listing(L)
        st.success(f"저장됨: {path}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장 실패: {exc}")

st.divider()
st.subheader("🛡️ 규제 검수 게이트")
st.caption(
    "AI가 만든 카피(또는 직접 쓴 문구)를 여기 붙여 검사하세요. 화장품법 표현 + 브랜드 금지어를 "
    "함께 봅니다. high 위험이 없어야 '통과'입니다. (통과=합법 아님, 1차 스크리닝)"
)
text = st.text_area("검사할 마케팅 문구", height=160, key="gate_text")
if text.strip():
    res = compliance_check(text, forbidden_words=core.forbidden_words)
    counts = res.counts_by_risk()
    if res.ok:
        st.success(f"✅ 통과 — high 위험 표현 없음 (주의 {counts['medium']} · 참고 {counts['low']})")
    else:
        st.error(f"❌ 확인 필요 — high 위험 {counts['high']}건. 아래 강조 표현을 고치세요.")
    st.markdown(highlight_html(text, res.findings), unsafe_allow_html=True)
    if res.findings:
        st.table([
            {"표현": f.matched_text, "분류": f.category, "위험": f.risk,
             "대체안": f.suggestion or "-"}
            for f in res.findings
        ])
    for w in res.warnings:
        st.warning(w)
    st.caption(res.disclaimer)
