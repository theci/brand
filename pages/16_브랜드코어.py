"""브랜드 코어 시트 페이지 — 9칸 작성 + 근거 자동 추출 + 자산 텍스트 내보내기.

마케팅의 뿌리. ⑤근거·⑦비주얼·⑧금지어는 제품 데이터에서 초안을 채운다.
완성한 자산 텍스트를 복사해 모든 마케팅 AI 프롬프트 앞에 붙인다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.brand_core import (
    asset_text,
    evidence_cards,
    save_brand_core,
    suggest_container,
)
from brandlab.core.models import BrandCore, BrandVisual
from brandlab.loader import load_ad_terms, load_all_stability, load_brand_core
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("브랜드 코어 시트 🎯")
st.caption(
    "마케팅의 뿌리. 9칸을 채우면 '브랜드 자산' 텍스트가 되어, 모든 마케팅 AI 프롬프트 앞에 붙습니다. "
    "⑤근거·⑦비주얼·⑧금지어는 제품 데이터에서 초안을 제안합니다."
)

lab = load_lab()
core = load_brand_core()


def _lines(s: str) -> list[str]:
    return [x.strip() for x in (s or "").splitlines() if x.strip()]


def _csv(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


# ⑤ 근거는 세션으로 관리(자동 추출 → 추가 시 텍스트에어리어에 반영)
if "core_evidence" not in st.session_state:
    st.session_state["core_evidence"] = "\n".join(core.evidence)

# --- 기본 정보 ---
c1, c2, c3 = st.columns(3)
brand_name = c1.text_input("브랜드명", value=core.brand_name or "", key="bc_name")
_refs = ["(미지정)"] + [f"{f.slug} v{f.version}" for f in lab.formulas]
_ref_idx = _refs.index(core.product_ref) if core.product_ref in _refs else 0
product_ref = c2.selectbox("기준 제품(근거 추출용)", _refs, index=_ref_idx, key="bc_ref")
one_liner = c3.text_input("⑨ 한 줄 소개(30자 이내)", value=core.one_liner or "", key="bc_one")

# --- ①~④ ---
entry = st.text_area(
    "① 카테고리 진입점 — 고객이 언제 우리를 떠올리는가 (한 줄에 하나, 3개 권장)",
    value="\n".join(core.entry_points), key="bc_entry", height=90,
)
a1, a2 = st.columns(2)
persona = a1.text_area("② 타깃 — 인물로 묘사", value=core.persona or "", key="bc_persona", height=90)
enemy = a2.text_area("③ 적 — 무엇에 반대하는가", value=core.enemy or "", key="bc_enemy", height=90)
promise = st.text_area("④ 약속 — 한 문장", value=core.promise or "", key="bc_promise", height=70)

# --- ⑤ 근거 (자동 추출) ---
st.subheader("⑤ 근거 — 증명 가능한 사실만")
selected_formula = None
if product_ref != "(미지정)":
    selected_formula = next(
        (f for f in lab.formulas if f"{f.slug} v{f.version}" == product_ref), None
    )
with st.expander("🔎 제품 데이터에서 근거 자동 추출", expanded=selected_formula is not None):
    if selected_formula is None:
        st.info("기준 제품을 선택하면 전성분·안정성·버전·HLB·공정에서 근거를 뽑아줍니다.")
    else:
        mask = st.checkbox("처방 % 가리기(영업비밀 보호)", value=False, key="bc_mask")
        cards = evidence_cards(
            selected_formula, lab, stability=load_all_stability(), mask_percent=mask
        )
        picked = st.multiselect(
            "추가할 근거 선택",
            [f"[{c.source}] {c.text}" for c in cards],
            key="bc_ev_pick",
        )
        if st.button("선택 근거를 ⑤에 추가", key="bc_ev_add"):
            add = "\n".join(p.split("] ", 1)[1] for p in picked)
            cur = st.session_state["core_evidence"].strip()
            st.session_state["core_evidence"] = (cur + "\n" + add).strip() if cur else add
            st.rerun()
evidence_text = st.text_area(
    "근거 목록 (한 줄에 하나)", key="core_evidence", height=120
)

# --- ⑥ 톤 / ⑧ 어휘 ---
t1, t2, t3 = st.columns(3)
tone = t1.text_input("⑥ 톤 형용사(쉼표)", value=", ".join(core.tone_adjectives), key="bc_tone")
vocab = t2.text_input("⑧ 애용어(쉼표)", value=", ".join(core.vocabulary), key="bc_vocab")
forbidden = t3.text_input("⑧ 금지어(쉼표)", value=", ".join(core.forbidden_words), key="bc_forb")

# 규제 금지어(참고 — ad_terms에서)
_reg_terms = [t.expression for t in load_ad_terms().terms]
if _reg_terms:
    st.caption("⑧ 규제 금지어(자동·참고): " + ", ".join(_reg_terms[:25]))

# --- ⑦ 비주얼 ---
st.subheader("⑦ 비주얼 코드")
if selected_formula is not None:
    _sc = suggest_container(selected_formula, lab)
    if _sc:
        st.caption(f"용기 제안: {_sc}")
v1, v2, v3 = st.columns(3)
main_color = v1.text_input("메인 컬러(HEX)", value=core.visual.main_color or "", key="bc_mc")
sub_color = v2.text_input("서브 컬러", value=core.visual.sub_color or "", key="bc_sc")
point_color = v3.text_input("포인트 컬러", value=core.visual.point_color or "", key="bc_pc")
v4, v5, v6 = st.columns(3)
container = v4.text_input("용기", value=core.visual.container or "", key="bc_cont")
texture = v5.text_input("제형 무드", value=core.visual.texture or "", key="bc_tex")
photo_note = v6.text_input("사진 톤(조명·색온도·배경)", value=core.visual.photo_note or "", key="bc_photo")

# --- 현재 값으로 코어 구성(저장·내보내기 공통) ---
current = BrandCore(
    brand_name=brand_name or None,
    product_ref=None if product_ref == "(미지정)" else product_ref,
    entry_points=_lines(entry),
    persona=persona or None,
    enemy=enemy or None,
    promise=promise or None,
    evidence=_lines(evidence_text),
    tone_adjectives=_csv(tone),
    vocabulary=_csv(vocab),
    forbidden_words=_csv(forbidden),
    visual=BrandVisual(
        main_color=main_color or None, sub_color=sub_color or None,
        point_color=point_color or None, container=container or None,
        texture=texture or None, photo_note=photo_note or None,
    ),
    one_liner=one_liner or None,
)

st.divider()
b1, b2 = st.columns(2)
if b1.button("💾 코어 시트 저장", type="primary", key="bc_save"):
    try:
        path = save_brand_core(current)
        st.success(f"저장됨: {path}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장 실패: {exc}")

_asset = asset_text(current, regulatory_forbidden=_reg_terms[:25])
b2.download_button(
    "⬇️ 브랜드 자산 텍스트 (.txt)", _asset, file_name="브랜드자산.txt", key="bc_export"
)
with st.expander("브랜드 자산 텍스트 미리보기 (프롬프트 앞에 붙여넣기)", expanded=True):
    st.code(_asset)
