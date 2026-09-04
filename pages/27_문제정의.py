"""문제 정의 페이지 (STEP 0 기획) — 발견을 종합해 문제 문장으로.

자동 초안 → 편집 → 저장. 하류(포지셔닝·브랜드코어)로 넘어갈 프리필을 미리 보여준다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.core.models import ProblemStatement
from brandlab.discovery import (
    draft_problem_statement,
    primary_persona,
    rank_pains,
    save_problem,
    to_brandcore_inputs,
    to_positioning_inputs,
)
from brandlab.loader import load_discovery
from brandlab.ui import setup_korean_font

setup_korean_font()
st.title("문제 정의 🎯")
st.caption("페르소나·페인·조사를 하나의 문제 문장으로 종합합니다. 이게 개발이 풀어야 할 과녁입니다.")
st.info(
    "표기: 🔒 **자동**(버튼으로 채워짐·수정 가능) · ✍️ **직접 입력**(칸 안 흐린 예시 참고). "
    "먼저 **[✨ 문제 문장 자동 초안]** 을 누르면 문제 문장이 채워지고, 나머지를 다듬으면 됩니다."
)

disc = load_discovery()
prob = disc.problem
persona_ids = [p.id for p in disc.personas.personas]

if not persona_ids:
    st.info("먼저 [페르소나] 페이지에서 페르소나를 등록하세요.")
    st.stop()

# 최우선 페인 요약(읽기)
ranked = rank_pains(disc.personas)
if ranked:
    top = ranked[0]
    st.write(f"최우선 페인: **{top.pain.desc}** (점수 {top.score}, {top.persona_name})")

# 자동 초안
prim = primary_persona(disc)
if st.button("✨ 문제 문장 자동 초안") and prim is not None:
    st.session_state["prob_statement"] = draft_problem_statement(prim)

# --- 편집 폼 ---
_ref_opts = ["(미지정)"] + persona_ids
_idx = _ref_opts.index(prob.persona_ref) if prob.persona_ref in _ref_opts else 0
persona_ref = st.selectbox("🔒 대상 페르소나 (목록에서 선택)", _ref_opts, index=_idx)
core_pain = st.text_input(
    "✍️ 핵심 페인", value=prob.core_pain or "",
    placeholder="예: 오후 당김 + 끈적임(덧바름 불가)",
)
statement = st.text_area(
    "🔒 문제 문장 (자동 초안 → 다듬기)",
    value=st.session_state.get("prob_statement", prob.statement or ""),
    height=90, key="prob_statement",
    placeholder="예: 냉난방 사무실 30대는 '오후 당김' 문제를 겪는다. 지금은 대형 브랜드 수분크림을 쓰지만 끈적이고 흡수가 느려 화장이 밀린다.",
)
c1, c2 = st.columns(2)
hypothesis = c1.text_area(
    "✍️ 가설 — 이걸 풀면 ~", value=prob.hypothesis or "", height=90,
    placeholder="예: 다축 보습 + 가벼운 유상으로 '산뜻한 지속 보습'을 만들면 덧바름 불만이 해결된다",
)
success_metric = c2.text_area(
    "✍️ 성공 기준(지표)", value=prob.success_metric or "", height=90,
    placeholder="예: 사용 4주 후 '오후 당김' 관능점수 개선 + 덧바름 만족 후기",
)

if st.button("💾 문제 정의 저장", type="primary"):
    new = ProblemStatement(
        persona_ref=None if persona_ref == "(미지정)" else persona_ref,
        core_pain=core_pain.strip() or None,
        statement=(statement or "").strip() or None,
        hypothesis=hypothesis.strip() or None,
        success_metric=success_metric.strip() or None,
    )
    try:
        path = save_problem(new)
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장 실패: {exc}")
    else:
        st.success(f"저장됨: {path}")

# --- 하류 프리필 미리보기 ---
st.divider()
st.subheader("하류로 넘어갈 프리필 (미리보기)")
st.caption("기획 데이터가 포지셔닝·브랜드코어로 이렇게 채워집니다. (실제 반영 버튼은 각 페이지에 연결 예정)")
pos_in = to_positioning_inputs(disc)
core_in = to_brandcore_inputs(disc)
cc1, cc2 = st.columns(2)
with cc1:
    st.markdown("**→ 포지셔닝**")
    st.write({k: (v if not isinstance(v, list) else [getattr(x, "axis", x) for x in v]) for k, v in pos_in.items()})
with cc2:
    st.markdown("**→ 브랜드 코어**")
    st.write(core_in)
