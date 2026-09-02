"""버전비교 페이지 — 처방 v1↔v2 원료·함량·개당원가 변화 (diff)."""

from __future__ import annotations

import streamlit as st

from brandlab.diff import formula_diff
from brandlab.ui import format_won, load_lab, setup_korean_font

setup_korean_font()
st.title("처방 버전 비교 (diff)")
st.caption("무엇을 바꿔서 원가가 어떻게 달라졌는지 한 표로. 개선 이력을 추적한다.")

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

slugs = sorted({f.slug for f in lab.formulas})
slug = st.selectbox("처방(슬러그)", slugs)
versions = sorted(f.version for f in lab.formulas if f.slug == slug)
if len(versions) < 2:
    st.info(f"'{slug}'은 버전이 1개뿐입니다. 비교하려면 v2 이상이 필요합니다.")
    st.stop()

c1, c2, c3 = st.columns(3)
v_old = c1.selectbox("이전 버전", versions, index=0)
v_new = c2.selectbox("비교 버전", versions, index=len(versions) - 1)
units = c3.number_input("원가 비교 수량", min_value=1, value=1000, step=100)

old = next(f for f in lab.formulas if f.slug == slug and f.version == v_old)
new = next(f for f in lab.formulas if f.slug == slug and f.version == v_new)
d = formula_diff(old, new, ingredients=lab.ingredients, packaging=lab.packaging, cost_units=int(units))

for w in d.warnings:
    st.warning(w)

st.subheader("원료 함량 변화")


def _pct(x):
    return f"{x:g}" if x is not None else "―"


st.table(
    [
        {
            "원료": l.name,
            f"v{v_old} %": _pct(l.old_percent),
            f"v{v_new} %": _pct(l.new_percent),
            "Δ": f"{l.delta:+g}" if l.delta is not None else "",
            "변화": l.change,
        }
        for l in d.lines
    ]
)

st.subheader("개당 원가 변화")
c = d.cost
if c.note:
    st.warning(c.note)
else:
    st.table(
        [
            {
                "항목": "개당 원료비",
                f"v{v_old}": format_won(c.old_material),
                f"v{v_new}": format_won(c.new_material),
                "Δ": f"{c.material_delta:+,.0f}원" if c.material_delta is not None else "-",
            },
            {
                "항목": "개당 원가",
                f"v{v_old}": format_won(c.old_unit),
                f"v{v_new}": format_won(c.new_unit),
                "Δ": f"{c.unit_delta:+,.0f}원" if c.unit_delta is not None else "-",
            },
        ]
    )
