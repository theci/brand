"""포지셔닝 페이지(STEP 0 · 전략) — '뾰족함'을 강제해 포지셔닝 문장을 조립한다.

모든 STEP의 뿌리. 수치적 차별점은 제품 데이터 근거에서 제안한다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from brandlab.core.models import ComparisonRow, Positioning
from brandlab.discovery import to_positioning_inputs
from brandlab.loader import load_discovery, load_positioning
from brandlab.positioning import (
    build_statement,
    comparison_summary,
    save_positioning,
    suggest_metrics,
    variants,
)
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("포지셔닝 🎯 (전략)")
st.caption(
    "뾰족함이 모든 것의 뿌리입니다. '우리는 [타겟]에게 [경쟁]이 못 푼 [페인]을 "
    "[신물질/공정]으로 [수치적 이익]으로 해결하는 유일한 [카테고리]다' — 이 문장을 데이터로 완성하세요."
)
st.info(
    "표기: 🔒 **자동/프리필**(제품 선택·[프리필] 버튼으로 채워짐) · ✍️ **직접 입력**(칸 안 흐린 예시 참고). "
    "**[기획에서 프리필]** 은 앞 STEP(페르소나·문제정의) 값을 **빈 칸에만** 채웁니다. 아래 문장은 칸을 채우면 **자동 조립**돼요."
)

lab = load_lab()
pos = load_positioning()

# 기획(Discovery)에서 프리필 — 페르소나·페인·경쟁 빈틈을 빈 칸에만 채운다
_pre = to_positioning_inputs(load_discovery())
if _pre:
    _keys = ", ".join(k for k in _pre if k != "comparison")
    st.info(f"🧩 기획에서 프리필 가능: {_keys}" + (" + 경쟁 비교표" if "comparison" in _pre else ""))
    if st.button("기획에서 프리필 (빈 칸만 채움)"):
        _data = pos.model_dump()
        for _k, _v in _pre.items():
            if _k == "comparison":
                if not pos.comparison:
                    _data["comparison"] = [r.model_dump() for r in _v]
                    st.session_state.pop("pos_comp", None)  # data_editor 재초기화
            elif not _data.get(_k):
                _data[_k] = _v
        pos = Positioning(**_data)
        st.success("기획에서 프리필했습니다. 아래에서 검토·수정 후 저장하세요.")

# 근거 추출 기준 제품
opts = ["(없음)"] + [f"{f.slug} v{f.version}" for f in lab.formulas]
_idx = opts.index(pos.product_ref) if pos.product_ref in opts else 0
product_ref = st.selectbox(
    "🔒 근거 기준 제품 (선택하면 아래 '수치적 차별점 후보'가 자동으로 뜸)", opts, index=_idx
)
selected = None
if product_ref != "(없음)":
    selected = next((f for f in lab.formulas if f"{f.slug} v{f.version}" == product_ref), None)

# 구성 요소
c1, c2 = st.columns(2)
target = c1.text_input("✍️ 타겟 (인물로)", value=pos.target or "", placeholder="예: 냉난방 사무실 30대")
competitor = c2.text_input(
    "✍️ 경쟁/기존 방식 (현상으로 — 실명 지양)", value=pos.competitor or "",
    placeholder="예: A사 수분크림(끈적임)",
)
c3, c4 = st.columns(2)
pain = c3.text_input("✍️ 페인 포인트", value=pos.pain or "", placeholder="예: 오후 당김")
tech = c4.text_input(
    "✍️ 우리만의 신물질/신공정", value=pos.tech or "",
    placeholder="예: 다축 보습(글리세린+히알루론산+판테놀)",
)
c5, c6 = st.columns(2)
metric_benefit = c5.text_input(
    "✍️ 수치적 이익/성능 (핵심!)", value=pos.metric_benefit or "",
    placeholder="예: 오후 4시 당김 개선·끈적임 없음",
)
category = c6.text_input(
    "✍️ 카테고리 (작은 시장)", value=pos.category or "", placeholder="예: 사무실용 산뜻 보습 로션",
)
entry = st.text_area(
    "✍️ 카테고리 진입점 — 고객이 우리를 떠올리는 상황 (한 줄에 하나)",
    value="\n".join(pos.entry_situations), height=80,
    placeholder="예: 오후에 볼이 당길 때\n메이크업 위 덧바를 때",
)

# 수치적 차별점 후보(제품 데이터 근거)
if selected is not None:
    with st.expander("🔎 수치적 차별점 후보 (제품 데이터 근거)", expanded=not metric_benefit):
        metrics = suggest_metrics(selected, lab)
        if metrics:
            for m in metrics:
                st.write(f"- {m}")
            st.caption("위 사실을 '수치적 이익/성능' 칸에 활용하세요. 검증 가능한 숫자가 뾰족함을 만듭니다.")
        else:
            st.info("숫자 있는 근거가 없습니다. DOE·안정성·처방을 채우면 후보가 늘어납니다.")

# 경쟁 비교표
st.subheader("경쟁 비교표 — 우리 vs 기존")
comp_df = st.data_editor(
    pd.DataFrame(
        [{"비교 축": r.axis, "우리": r.ours, "경쟁": r.theirs, "우리 우위": r.ours_wins}
         for r in pos.comparison]
        or [{"비교 축": "", "우리": "", "경쟁": "", "우리 우위": False}]
    ),
    num_rows="dynamic",
    width="stretch",
    column_config={
        "비교 축": st.column_config.TextColumn("비교 축", help="무엇으로 비교하나. 예: 끈적임 / 흡수 속도 / 지속력"),
        "우리": st.column_config.TextColumn("우리", help="우리 제품. 예: 산뜻·빠른 흡수"),
        "경쟁": st.column_config.TextColumn("경쟁", help="경쟁/기존. 예: 끈적임·흡수 느림"),
        "우리 우위": st.column_config.CheckboxColumn("우리 우위", help="이 축에서 우리가 이기면 체크"),
    },
    key="pos_comp",
)
comparison = [
    ComparisonRow(
        axis=str(r["비교 축"]).strip(),
        ours=str(r["우리"] or "").strip(),
        theirs=str(r["경쟁"] or "").strip(),
        ours_wins=bool(r["우리 우위"]),
    )
    for _, r in comp_df.iterrows()
    if str(r["비교 축"]).strip()
]

# 현재 포지셔닝 구성
current = Positioning(
    product_ref=None if product_ref == "(없음)" else product_ref,
    target=target or None,
    competitor=competitor or None,
    pain=pain or None,
    tech=tech or None,
    metric_benefit=metric_benefit or None,
    category=category or None,
    entry_situations=[x.strip() for x in entry.splitlines() if x.strip()],
    comparison=comparison,
)

_summary = comparison_summary(current)
if _summary:
    st.caption(f"우리 우위 요약: {_summary}")

st.divider()
st.subheader("포지셔닝 문장")
st.success(build_statement(current))
st.markdown("**변형 3안**")
for v in variants(current):
    st.write(f"- {v}")

if st.button("💾 포지셔닝 저장", type="primary"):
    try:
        path = save_positioning(current)
        st.success(f"저장됨: {path} — 브랜드 코어(③적·④약속)에 이 포지셔닝을 반영하세요.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장 실패: {exc}")

st.caption("이 포지셔닝이 브랜드 코어·상품등록·마케팅 프롬프트의 뿌리가 됩니다.")
