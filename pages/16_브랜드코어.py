"""브랜드 코어 시트 페이지 — 9칸 작성 + 근거 자동 추출 + 자산 텍스트 내보내기.

마케팅의 뿌리. ⑤근거·⑦비주얼·⑧금지어는 제품 데이터에서 초안을 채운다.
완성한 자산 텍스트를 복사해 모든 마케팅 AI 프롬프트 앞에 붙인다.
"""

from __future__ import annotations

import re

import streamlit as st

from brandlab.brand_core import (
    asset_text,
    evidence_cards,
    save_brand_core,
    suggest_container,
)
from brandlab.core.models import BrandCore, BrandVisual
from brandlab.discovery import to_brandcore_inputs
from brandlab.loader import (
    load_ad_terms,
    load_all_stability,
    load_brand_core,
    load_discovery,
)
from brandlab.prompt_builder import MOODBOARD_KINDS, moodboard_prompt
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("브랜드 코어 시트 🎯")
st.caption(
    "마케팅의 뿌리. 9칸을 채우면 '브랜드 자산' 텍스트가 되어, 모든 마케팅 AI 프롬프트 앞에 붙습니다. "
    "⑤근거·⑦비주얼·⑧금지어는 제품 데이터에서 초안을 제안합니다."
)
st.info(
    "표기: 🔒 **자동/프리필**(①②③은 [프리필] 버튼, ⑤ 근거는 제품에서 추출) · ✍️ **직접 입력**"
    "(칸 안 흐린 예시 참고). 예시는 `산뜻보습로션` 시나리오 기준입니다."
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

# 기획(Discovery)에서 프리필 — ② 타깃·③ 적·① 진입점을 빈 칸에만 채운다
_ci = to_brandcore_inputs(load_discovery())
if _ci:
    if st.button("🧩 기획에서 프리필 (② 타깃·③ 적·① 진입점, 빈 칸만)"):
        if _ci.get("persona") and not (st.session_state.get("bc_persona") or "").strip():
            st.session_state["bc_persona"] = _ci["persona"]
        if _ci.get("enemy") and not (st.session_state.get("bc_enemy") or "").strip():
            st.session_state["bc_enemy"] = _ci["enemy"]
        if _ci.get("entry_points") and not (st.session_state.get("bc_entry") or "").strip():
            st.session_state["bc_entry"] = "\n".join(_ci["entry_points"])
        st.rerun()

# --- 기본 정보 ---
c1, c2, c3 = st.columns(3)
brand_name = c1.text_input("✍️ 브랜드명", value=core.brand_name or "", key="bc_name", placeholder="예: 오후(OHU)")
_refs = ["(미지정)"] + [f"{f.slug} v{f.version}" for f in lab.formulas]
_ref_idx = _refs.index(core.product_ref) if core.product_ref in _refs else 0
product_ref = c2.selectbox("🔒 기준 제품(근거 추출용)", _refs, index=_ref_idx, key="bc_ref")
one_liner = c3.text_input(
    "✍️ ⑨ 한 줄 소개(30자 이내)", value=core.one_liner or "", key="bc_one",
    placeholder="예: 산뜻하게, 오후까지",
)

# --- ①~④ ---
entry = st.text_area(
    "🔒 ① 카테고리 진입점 — 고객이 언제 우리를 떠올리는가 (한 줄에 하나, 3개 권장)",
    value="\n".join(core.entry_points), key="bc_entry", height=90,
    placeholder="예: 오후에 볼이 당길 때\n메이크업 위 덧바를 때",
)
a1, a2 = st.columns(2)
persona = a1.text_area(
    "🔒 ② 타깃 — 인물로 묘사", value=core.persona or "", key="bc_persona", height=90,
    placeholder="예: 냉난방 사무실에서 오후만 되면 당김을 느끼는 30대 직장인",
)
enemy = a2.text_area(
    "🔒 ③ 적 — 무엇에 반대하는가", value=core.enemy or "", key="bc_enemy", height=90,
    placeholder="예: 끈적여서 덧바를 수 없는 무거운 수분크림",
)
promise = st.text_area(
    "✍️ ④ 약속 — 한 문장", value=core.promise or "", key="bc_promise", height=70,
    placeholder="예: 산뜻하게, 오후까지",
)

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

# --- ⑩ 차별점 (문제해결 '비법'이 어느 층에 사는가) ---
st.subheader("⑩ 차별점 — 우리의 문제해결 '비법'은 어느 층에 있나")
st.caption(
    "화장품 원료는 대부분 공개된 공용 팔레트라 누구나 같은 걸 산다. "
    "1인 창업의 차별점은 신소재가 아니라 아래 네 층의 조합에서 나온다."
)
with st.expander("💡 왜 신소재가 아니라 '조합'인가 (읽고 고르기)"):
    st.markdown(
        "- **문제 정의** — 희귀 원료보다 *좁은 타깃의 안 풀린 페인*을 정확히 아는 것이 강하다.\n"
        "- **처방 설계** — 같은 원료로 *다른 사용감·컨셉*을 만든다"
        "(예: 글리세린 증량 대신 판테놀로 '진정' 축 추가 = 산뜻보습로션 USP).\n"
        "- **브랜드·서사·신뢰** — 비율로 복제 안 되는 유일한 층(왜 만들었나·투명성·근거).\n"
        "- **니치·실행·고객 친밀도** — 큰 브랜드가 무시하는 마이크로 세그먼트를 더 살뜰히.\n\n"
        "⚠️ **함정:** '이 히어로 성분 하나면 팔린다'(마법의 원료)는 착각. "
        "신소재는 남도 곧 사서 오래 못 가는 '양념'이지 해자가 아니다. "
        "고른 층은 브랜드 자산 텍스트 ⑩에 담겨 마케팅 프롬프트로 이어진다."
    )
_DIFF_LAYERS = [
    "문제 정의 — 좁은 타깃의 안 풀린 페인",
    "처방 설계 — 같은 원료, 다른 사용감·컨셉 조합",
    "브랜드·서사·신뢰 — 복제 안 되는 이유·근거",
    "니치·실행·고객 친밀도 — 큰 브랜드가 무시하는 세그먼트",
]
_diff_default = [d for d in core.differentiators if d in _DIFF_LAYERS]
differentiators = st.multiselect(
    "✍️ 우리 차별점이 사는 층 (해당되는 것 모두 — 1~2개에 집중 권장)",
    _DIFF_LAYERS, default=_diff_default, key="bc_diff",
)
differentiation_note = st.text_input(
    "✍️ 한 줄 요약 — '우리 비법은 ~'",
    value=core.differentiation_note or "", key="bc_diff_note",
    placeholder="예: 산뜻 보습을 글리세린 증량이 아니라 '보습+진정 다축'으로 푼다",
)

# --- ⑥ 톤 / ⑧ 어휘 ---
t1, t2, t3 = st.columns(3)
tone = t1.text_input("✍️ ⑥ 톤 형용사(쉼표)", value=", ".join(core.tone_adjectives), key="bc_tone", placeholder="예: 담백한, 정직한")
vocab = t2.text_input("✍️ ⑧ 애용어(쉼표)", value=", ".join(core.vocabulary), key="bc_vocab", placeholder="예: 산뜻, 지속, 가벼운")
forbidden = t3.text_input("✍️ ⑧ 금지어(쉼표)", value=", ".join(core.forbidden_words), key="bc_forb", placeholder="예: 완벽, 최고, 미백")

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
main_color = v1.text_input("✍️ 메인 컬러(HEX)", value=core.visual.main_color or "", key="bc_mc", placeholder="예: EAE0D5 (# 없이도 OK)")
sub_color = v2.text_input("✍️ 서브 컬러", value=core.visual.sub_color or "", key="bc_sc", placeholder="예: 6B705C")
point_color = v3.text_input("✍️ 포인트 컬러", value=core.visual.point_color or "", key="bc_pc", placeholder="예: C97C5D")
v4, v5, v6 = st.columns(3)
container = v4.text_input("✍️ 용기", value=core.visual.container or "", key="bc_cont", placeholder="예: 유리 에어리스 50mL")
texture = v5.text_input("✍️ 제형 무드", value=core.visual.texture or "", key="bc_tex", placeholder="예: matte, soft-touch")
photo_note = v6.text_input("✍️ 사진 톤(조명·색온도·배경)", value=core.visual.photo_note or "", key="bc_photo", placeholder="예: 자연광, 따뜻한 색온도, 미니멀 배경")

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
    differentiators=differentiators,
    differentiation_note=differentiation_note or None,
)

# --- 브랜딩 느낌 미리보기 (비용 투입 전 빠르게) ---
st.divider()
st.subheader("🎨 브랜딩 느낌 미리보기 — 비용 투입 전 빠르게 확인")
st.caption(
    "이미지 생성은 외부 도구에서 합니다. 여기선 ⓐ 팔레트를 즉석에서 보고, "
    "ⓑ 브랜딩 느낌 확인용 무드보드 프롬프트를 만들어 붙여넣기만 하면 됩니다(제품 실물 불필요)."
)


def _css_color(v: str | None) -> str | None:
    """HEX(#없이 3/6/8자리)면 #을 붙이고, 그 외(#포함 hex·named color)는 그대로."""
    if not v:
        return None
    v = v.strip()
    if re.fullmatch(r"[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8}", v):
        return "#" + v
    return v


_palette = [("메인", main_color), ("서브", sub_color), ("포인트", point_color)]
_shown = [(lbl, css) for lbl, hx in _palette if (css := _css_color(hx))]
if _shown:
    cols = st.columns(len(_shown))
    for col, (lbl, css) in zip(cols, _shown):
        col.markdown(
            f"<div style='height:64px;border-radius:8px;border:1px solid #ccc;background:{css}'></div>"
            f"<div style='text-align:center;margin-top:4px'><b>{lbl}</b><br><code>{css}</code></div>",
            unsafe_allow_html=True,
        )
    _bar = "".join(f"<span style='flex:1;background:{css}'></span>" for _, css in _shown)
    st.markdown(
        f"<div style='display:flex;height:28px;border-radius:6px;overflow:hidden;margin-top:8px'>{_bar}</div>",
        unsafe_allow_html=True,
    )
else:
    st.caption("⑦ 비주얼에 메인/서브/포인트 컬러(HEX)를 넣으면 여기서 팔레트를 바로 봅니다.")

mk1, mk2 = st.columns([3, 1])
mb_kind = mk1.selectbox("무드보드 종류", list(MOODBOARD_KINDS), key="bc_mb_kind")
if mk2.button("무드보드 프롬프트", key="bc_mb_gen"):
    st.session_state["bc_mb_out"] = moodboard_prompt(current, kind=mb_kind)
if st.session_state.get("bc_mb_out"):
    st.caption(
        "외부 이미지 도구(나노바나나 등)에 붙여넣어 느낌을 확인하세요. "
        "제품 실물이 없으므로 자유 컨셉 생성입니다(제품 촬영 프롬프트는 STEP 10 '이미지 프롬프트')."
    )
    st.code(st.session_state["bc_mb_out"])
    st.download_button(
        "⬇️ 무드보드 프롬프트 (.txt)", st.session_state["bc_mb_out"],
        file_name="브랜드무드보드_prompt.txt", key="bc_mb_dl",
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
