"""이미지 프롬프트 빌더(STEP 10) — 나노바나나 6블록 + xlsx 키워드 팔레트.

제품 데이터·브랜드 코어로 Subject/Concept 초안을 잡고, 카테고리별 키워드를 골라
완성된 영어 프롬프트를 만든다. 제품 실물은 실촬영 — 가드가 자동 삽입된다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.loader import load_brand_core, load_prompt_keywords
from brandlab.prompt_builder import (
    PRESETS,
    assemble,
    compose_blocks,
    product_hints,
)
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("이미지 프롬프트 빌더 🖼️")
st.caption(
    "나노바나나 6블록 + 키워드 팔레트로 영어 프롬프트를 만듭니다. "
    "제품 실물(형태·색·제형)은 실촬영 필수 — 배경·무드만 AI. '제품 변경 금지' 가드가 자동 삽입됩니다."
)

lab = load_lab()
lib = load_prompt_keywords()
core = load_brand_core()

# 제품 선택(선택) → Subject/Concept 자동 초안
opts = ["(없음)"] + [f"{f.slug} v{f.version} — {f.product}" for f in lab.formulas]
sel_prod = st.selectbox("제품(선택 — Subject/Concept 자동 초안)", opts)
hints = {"subject": "", "concept": "", "styling": "", "aesthetic": ""}
if sel_prod != "(없음)":
    formula = next(f for f in lab.formulas if f"{f.slug} v{f.version} — {f.product}" == sel_prod)
    hints = product_hints(formula, lab, core)

# 프리셋
p1, p2 = st.columns([3, 1])
preset = p1.selectbox("프리셋(선택)", ["(없음)"] + list(PRESETS))
_CATS = ["angle", "lighting", "composition", "texture", "color", "aesthetic"]
if preset != "(없음)" and p2.button("프리셋 적용"):
    sel = PRESETS[preset]
    for cat in _CATS:
        st.session_state[f"kw_{cat}"] = sel.get(cat, [])
    st.rerun()

# Subject / Concept
c1, c2 = st.columns(2)
subject = c1.text_input("Subject (등장·제품)", value=hints["subject"], key="pb_subject")
concept = c2.text_input("Concept (콘셉트·주제)", value=hints["concept"], key="pb_concept")


def _kw(cat: str, label: str) -> list[str]:
    items = lib.get(cat)
    ko = {k.en: k.ko for k in items}
    return st.multiselect(
        label, [k.en for k in items],
        format_func=lambda e: f"{e} · {ko.get(e, '')}", key=f"kw_{cat}",
    )


st.markdown("**Composition** — 앵글 + 구도")
a1, a2 = st.columns(2)
with a1:
    ang = _kw("angle", "앵글(Angle)")
with a2:
    comp = _kw("composition", "구도(Composition)")

st.markdown("**Styling** — 질감 + 자유 입력(헤어·메이크업·의상)")
s1, s2 = st.columns(2)
with s1:
    tex = _kw("texture", "질감(Texture)")
styling_extra = s2.text_input("스타일 자유 입력", key="pb_styling_extra")

st.markdown("**Lighting & Background** — 조명 + 컬러")
l1, l2 = st.columns(2)
with l1:
    lit = _kw("lighting", "조명(Lighting)")
with l2:
    col = _kw("color", "컬러(Color)")

st.markdown("**Aesthetic & Brand Context**")
aes = _kw("aesthetic", "무드(Aesthetic)")

real_product = st.checkbox(
    "제품 실물이 등장 (실촬영 필수 — 제품 변경 금지 가드 삽입)", value=True
)

if st.button("프롬프트 생성", type="primary"):
    blocks = compose_blocks(
        subject=subject, concept=concept,
        angle=ang, lighting=lit, composition=comp, texture=tex,
        color=col, aesthetic=aes or ([hints["aesthetic"]] if hints["aesthetic"] else []),
        styling_extra=styling_extra,
    )
    prompt = assemble(blocks, real_product=real_product)
    st.subheader("완성 프롬프트 (복사해서 나노바나나에 붙여넣기)")
    st.code(prompt)
    st.download_button(
        "⬇️ 프롬프트 (.txt)", prompt,
        file_name=f"prompt_{sel_prod.split(' ')[0] if sel_prod != '(없음)' else 'image'}.txt",
    )
    st.caption(
        "⚠️ 제품 실물 형태·색·제형은 반드시 실촬영을 참조 이미지로 업로드하세요. "
        "AI가 제품을 새로 그리면 허위·과장 광고가 될 수 있습니다."
    )
