"""규제판정 페이지 — 제품 의도 → 레짐 분류·비용비교·적합성 (advise)."""

from __future__ import annotations

import streamlit as st

from brandlab.advisor import classify, compare, feasibility
from brandlab.core.models import ProductIntent
from brandlab.ui import format_won, setup_korean_font

setup_korean_font()
st.title("규제 판정 (RegimeAdvisor)")
st.caption("제품 의도(용도·기능·제형)로 적용 법(레짐)을 분류하고, 경로별 규제비용을 비교한다.")
st.info(
    "표기: ✍️ **직접 선택**(위 용도·제형·기능) → 🔒 **자동 판정**(아래 레짐·비용·적합성). "
    "칸 제목에 마우스를 올리면 각 옵션의 **뜻**이 보여요."
)

c1, c2, c3 = st.columns(3)
use = c1.selectbox(
    "✍️ 용도", ["body", "space", "fabric", "surface"],
    help="body=몸(화장품) · space=공간(디퓨저) · fabric=섬유 · surface=표면. 예: 로션→body",
)
form = c2.selectbox(
    "✍️ 제형", ["liquid", "solid", "spray", "sustained_release"],
    help="liquid=액체 · solid=고체 · spray=스프레이 · sustained_release=서방(디퓨저). 예: 로션→liquid",
)
claims = c3.multiselect(
    "✍️ 기능(복수)",
    ["fragrance", "cleanse", "deodorize", "moisturize", "sanitize"],
    default=["fragrance"],
    help="fragrance=발향 · cleanse=세정 · deodorize=탈취 · moisturize=보습 · sanitize=살균"
    "(⚠️ 넣으면 살생물제로 승격). 예: 로션→moisturize",
)
c4, c5, c6 = st.columns(3)
skus = c4.number_input("예상 SKU 수", min_value=1, value=5)
years = c5.number_input("검토 기간(년)", min_value=1, value=5)
budget_on = c6.checkbox("예산 지정")
budget = c6.number_input("총 예산(원)", min_value=0, value=1_000_000, step=100_000) if budget_on else None

intent = ProductIntent(use=use, claims=list(claims), form=form)
cls = classify(intent)
cmp = compare(intent, int(skus), int(years))
feas = feasibility(intent, budget=int(budget) if budget is not None else None, sku_count=int(skus), horizon_years=int(years))

st.subheader("가능한 레짐 / 카테고리")
if not cls.candidates:
    st.warning("분류 후보 없음")
else:
    st.table(
        [{"레짐": c.regime_code, "카테고리": c.label, "비고": c.note or ""} for c in cls.candidates]
    )
for w in cls.warnings:
    st.warning(w)

if cmp.rows:
    st.subheader("규제비용 비교")
    st.table(
        [
            {
                "경로": r.candidate.label + ("  ⭐" if r is cmp.cheapest else ""),
                "등록비": format_won(r.registration_cost) if r.supported else "―",
                f"SKU×{int(skus)}": format_won(r.sku_expansion_total) if r.supported else "―",
                "갱신비": format_won(r.renewal_cost) if r.supported else "―",
                "총 규제비용": format_won(r.total_regulatory_cost) if r.supported else "미지원",
                "기간(일)": str(r.lead_time_days) if r.supported else "―",
            }
            for r in cmp.rows
        ]
    )
    st.success(cmp.summary)

st.subheader("적합성")
render = {"OK": st.success, "CAUTION": st.warning, "REJECT": st.error}.get(feas.verdict, st.info)
render(f"판정: {feas.verdict}")
for r in feas.reasons:
    st.write(f"• {r}")

st.info(cls.disclaimer)
