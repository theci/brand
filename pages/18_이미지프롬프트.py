"""이미지 프롬프트 빌더(STEP 10) — 나노바나나 장면 레시피 + 6블록 팔레트.

두 모드:
  1) 장면 레시피 — 촬영 장면을 고르면 제품·브랜드 데이터로 멀티블록 프로 프롬프트 자동 생성
  2) 직접 조립  — 6블록 + 키워드 팔레트. '프로 상세' 모드면 hint 문장·카메라·컬러스킴까지 확장
제품 실물은 실촬영 — 가드가 자동 삽입된다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.loader import load_brand_core, load_prompt_keywords
from brandlab.prompt_builder import (
    PRESETS,
    REF_BRANDS,
    SCENES,
    assemble,
    compose_blocks,
    compose_rich,
    product_hints,
    scene_prompt,
)
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("이미지 프롬프트 빌더 🖼️")
st.caption(
    "나노바나나용 '프로 수준' 영어 프롬프트를 만듭니다. "
    "제품 실물(형태·색·제형)은 실촬영 필수 — 배경·무드만 AI. '제품 변경 금지' 가드가 자동 삽입됩니다."
)
st.info(
    "표기: 🔒 **자동**(제품·브랜드 코어에서 Subject/Concept·컬러가 채워짐) · ✍️ **직접 선택/입력**"
    "(장면·키워드·스타일). '장면 레시피' 모드는 고르기만 하면 프롬프트가 자동 완성됩니다."
)

lab = load_lab()
lib = load_prompt_keywords()
core = load_brand_core()

opts = ["(없음)"] + [f"{f.slug} v{f.version} — {f.product}" for f in lab.formulas]


def _pick_formula(sel: str):
    if sel == "(없음)":
        return None
    return next(f for f in lab.formulas if f"{f.slug} v{f.version} — {f.product}" == sel)


mode = st.radio(
    "빌더 모드",
    ["장면 레시피 (추천)", "직접 조립 (6블록 팔레트)"],
    horizontal=True,
)

# ──────────────────────────────────────────────────────────────────────────
# 모드 1: 장면 레시피
# ──────────────────────────────────────────────────────────────────────────
if mode.startswith("장면"):
    st.markdown(
        "촬영 **장면**을 고르면 제품·브랜드 코어를 넣어 Subject/Composition/Lighting/"
        "Texture & Detail/Color Scheme/Camera & Perspective/Aesthetic 블록을 자동으로 채웁니다."
    )
    sel_prod = st.selectbox("제품 (브랜드 코어와 함께 프롬프트에 반영)", opts)
    formula = _pick_formula(sel_prod)

    scene_key = st.selectbox(
        "장면",
        list(SCENES),
        format_func=lambda k: f"{k} — {SCENES[k].shot}",
    )
    rec = SCENES[scene_key]
    badges = []
    badges.append("🟢 실촬영 참조컷" if rec.real_product else "🔵 배경/오브젝트 생성 가능")
    if rec.needs_model:
        badges.append("👤 모델 참조 이미지 필요")
    st.caption(" · ".join(badges))

    if st.button("프롬프트 생성", type="primary"):
        prompt = scene_prompt(scene_key, formula=formula, lab=lab, core=core)
        st.subheader("완성 프롬프트 (복사해서 나노바나나에 붙여넣기)")
        st.code(prompt)
        st.download_button(
            "⬇️ 프롬프트 (.txt)",
            prompt,
            file_name=f"prompt_{sel_prod.split(' ')[0] if sel_prod != '(없음)' else 'scene'}.txt",
        )
        if rec.real_product:
            st.caption(
                "⚠️ 제품 실물 형태·색·제형은 반드시 실촬영을 참조 이미지로 업로드하세요. "
                "AI가 제품을 새로 그리면 허위·과장 광고가 될 수 있습니다."
            )

# ──────────────────────────────────────────────────────────────────────────
# 모드 2: 직접 조립 (6블록 팔레트)
# ──────────────────────────────────────────────────────────────────────────
else:
    sel_prod = st.selectbox("제품(선택 — Subject/Concept 자동 초안)", opts)
    hints = {"subject": "", "concept": "", "styling": "", "aesthetic": ""}
    formula = _pick_formula(sel_prod)
    if formula is not None:
        hints = product_hints(formula, lab, core)

    p1, p2 = st.columns([3, 1])
    preset = p1.selectbox("프리셋(선택)", ["(없음)"] + list(PRESETS))
    _CATS = ["angle", "lighting", "composition", "texture", "color", "aesthetic"]
    if preset != "(없음)" and p2.button("프리셋 적용"):
        sel = PRESETS[preset]
        for cat in _CATS:
            st.session_state[f"kw_{cat}"] = sel.get(cat, [])
        st.rerun()

    c1, c2 = st.columns(2)
    subject = c1.text_input("Subject (등장·제품)", value=hints["subject"], key="pb_subject")
    concept = c2.text_input("Concept (콘셉트·주제)", value=hints["concept"], key="pb_concept")

    def _kw(cat: str, label: str) -> list[str]:
        items = lib.get(cat)
        ko = {k.en: k.ko for k in items}
        return st.multiselect(
            label,
            [k.en for k in items],
            format_func=lambda e: f"{e} · {ko.get(e, '')}",
            key=f"kw_{cat}",
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
    ref = st.selectbox(
        "레퍼런스 브랜드 톤(선택)",
        ["(없음)"] + list(REF_BRANDS),
        format_func=lambda k: k if k == "(없음)" else f"{k} · {REF_BRANDS[k]}",
    )

    o1, o2 = st.columns(2)
    rich = o1.checkbox(
        "프로 상세 모드 (hint 문장·카메라·컬러스킴·품질 지시어 확장)", value=True
    )
    real_product = o2.checkbox(
        "제품 실물이 등장 (실촬영 필수 — 제품 변경 금지 가드 삽입)", value=True
    )

    if st.button("프롬프트 생성", type="primary"):
        aes_sel = aes or ([hints["aesthetic"]] if hints["aesthetic"] else [])
        if rich:
            brand_colors = [
                c for c in (core.visual.main_color, core.visual.sub_color, core.visual.point_color) if c
            ]
            blocks = compose_rich(
                subject=subject,
                concept=concept,
                lib=lib,
                angle=ang,
                lighting=lit,
                composition=comp,
                texture=tex,
                color=col,
                aesthetic=aes_sel,
                styling_extra=styling_extra,
                brand_colors=brand_colors,
                ref_brands=REF_BRANDS.get(ref, ""),
            )
        else:
            blocks = compose_blocks(
                subject=subject,
                concept=concept,
                angle=ang,
                lighting=lit,
                composition=comp,
                texture=tex,
                color=col,
                aesthetic=aes_sel,
                styling_extra=styling_extra,
            )
        prompt = assemble(blocks, real_product=real_product)
        st.subheader("완성 프롬프트 (복사해서 나노바나나에 붙여넣기)")
        st.code(prompt)
        st.download_button(
            "⬇️ 프롬프트 (.txt)",
            prompt,
            file_name=f"prompt_{sel_prod.split(' ')[0] if sel_prod != '(없음)' else 'image'}.txt",
        )
        st.caption(
            "⚠️ 제품 실물 형태·색·제형은 반드시 실촬영을 참조 이미지로 업로드하세요. "
            "AI가 제품을 새로 그리면 허위·과장 광고가 될 수 있습니다."
        )
