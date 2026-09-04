"""사전점검 페이지 — 제조 전 HLB 유화 균형 + 배합한도 (check)."""

from __future__ import annotations

import streamlit as st

from brandlab.checks import (
    check_formula,
    compatibility_check,
    formulation_balance,
    preservation_check,
)
from brandlab.loader import load_incompatibilities
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("처방 사전점검 · HLB · 배합한도 · 유수분")
st.caption("제형을 만들기 전에, 유화 위험·배합한도·유수분(제형) 밸런스를 처방서 숫자로 미리 본다.")

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
formula = options[st.selectbox("처방 선택", list(options))]

result = check_formula(formula, ingredients=lab.ingredients, limits=lab.limits)

# HLB
st.subheader("HLB 유화 균형")
h = result.hlb
if h.applicable:
    render = {"적합": st.success, "주의": st.warning, "위험": st.error}.get(h.verdict, st.info)
    render(f"**{h.verdict}** — {h.message}")
    c1, c2, c3 = st.columns(3)
    c1.metric("공급 HLB", h.supplied_hlb)
    c2.metric("요구 HLB", h.required_hlb)
    if h.gap is not None:
        c3.metric("차이(Δ)", f"{h.gap:+g}")
    st.caption(f"유화제: {', '.join(h.emulsifiers)}  ·  유상: {', '.join(h.oils)}")
else:
    st.info(h.message)
    st.caption("유화제에 `hlb`, 오일에 `required_hlb` 값을 넣으면 HLB 점검이 동작합니다.")

# 배합한도
st.subheader("배합한도 점검")
if not result.limit_findings:
    st.success("초과·근접(도달) 원료 없음")
else:
    st.table(
        [
            {"원료": f.name, "함량%": f.percent, "한도%": f.limit, "출처": f.source, "판정": f.status}
            for f in result.limit_findings
        ]
    )

# 원료 상용성(충돌)
st.subheader("원료 상용성(충돌)")
compat = compatibility_check(formula, ingredients=lab.ingredients, rules=load_incompatibilities())
if not compat:
    st.success("알려진 충돌 규칙에 걸리는 원료 조합 없음")
else:
    sev_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}
    for c in compat:
        st.warning(
            f"{sev_icon.get(c.severity, '⚠')} **{', '.join(c.a_names)} × {', '.join(c.b_names)}** — {c.reason}"
        )
        if c.advice:
            st.caption(f"→ {c.advice}")
st.caption("일반 통용 규칙 기반의 1차 경고입니다. 최종은 상용성·안정성 시험으로 확인하세요.")

# 보존 시스템
st.subheader("보존 시스템")
pres = preservation_check(formula, ingredients=lab.ingredients)
render_p = {"양호": st.success, "주의": st.warning, "위험": st.error, "해당없음": st.info}.get(
    pres.verdict, st.info
)
render_p(f"**{pres.verdict}**" + (" (무수)" if pres.verdict == "해당없음" else ""))
for cmt in pres.comments:
    st.caption(cmt)

# 제형·유수분 밸런스
st.subheader("제형 · 유수분 밸런스")
bal = formulation_balance(formula, ingredients=lab.ingredients)
c1, c2, c3 = st.columns(3)
c1.metric("유상(oil)", f"{bal.oil_pct:g}%")
c2.metric("수상(water)", f"{bal.water_pct:g}%")
c3.metric("텍스처", bal.texture)
st.caption("텍스처 기준(유상%): <8 라이트 · 8~18 로션 · 18~30 크림 · 30~50 리치 · >50 밤")

st.write("**보습 3축**")
b1, b2, b3, b4 = st.columns(4)
b1.metric("휴멕턴트", f"{bal.humectant_pct:g}%", help="수분을 끌어당김(글리세린·HA·판테놀)")
b2.metric("에몰리언트", f"{bal.emollient_pct:g}%", help="발림·매끈(오일·에스터·지방알코올)")
b3.metric("옥클루시브", f"{bal.occlusive_pct:g}%", help="수분 잠금(왁스·버터·실리콘)")
b4.metric("유화제", f"{bal.emulsifier_pct:g}%", help="물·기름 결합")

try:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 1.8))
    axes = ["휴멕턴트", "에몰리언트", "옥클루시브"]
    vals = [bal.humectant_pct, bal.emollient_pct, bal.occlusive_pct]
    ax.barh(axes, vals, color=["#1c7ed6", "#2b8a3e", "#e8590c"])
    ax.invert_yaxis()
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:g}%", va="center", fontsize=8)
    ax.set_xlabel("% (처방 대비)")
    fig.tight_layout()
    st.pyplot(fig)
except Exception:  # noqa: BLE001 — 차트 실패가 페이지를 막지 않게
    pass

for cmt in bal.comments:
    st.info(cmt)

# 종합
if result.ok:
    st.success("종합 사전점검: 통과 — 개발을 진행해도 되는 처방입니다.")
else:
    st.error("종합 사전점검: 확인 필요 — 위 항목을 조정하세요.")
