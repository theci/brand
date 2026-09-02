"""조향 페이지 — 블렌드 계량표·노트 피라미드·IFRA + 숙성 알림 (fragrance)."""

from __future__ import annotations

import streamlit as st

from brandlab.fragrance import blend_sheet, ifra_check, maceration_due, note_pyramid
from brandlab.loader import load_all_fragrances, load_aroma_materials
from brandlab.ui import setup_korean_font

st.set_page_config(page_title="조향 · brand-lab", page_icon="🌸", layout="wide")
setup_korean_font()
st.title("조향 (fragrance)")
st.caption("희석 배율을 반영한 계량표 + 노트 피라미드 + IFRA 사용한도 체크.")

fragrances = load_all_fragrances()
if not fragrances:
    st.info("향 처방이 없습니다. formulas/fragrance/*.yaml 을 추가하세요.")
    st.stop()
materials = load_aroma_materials()

options = {f"{fr.name} v{fr.version}": fr for fr in fragrances}
fr = options[st.selectbox("향 처방 선택", list(options))]

sheet = blend_sheet(fr, materials)
pyramid = note_pyramid(fr, materials)
ifra = ifra_check(fr, materials)

c1, c2, c3 = st.columns(3)
c1.metric("총량(g)", f"{sheet.총량_g:g}")
c2.metric("농도(%)", f"{sheet.concentration_percent:g}")
c3.metric("향 원액(g)", f"{sheet.concentrate_g:g}")

st.subheader("계량표")
st.table(
    [
        {
            "어코드": r.accord,
            "원료": r.name,
            "희석%": r.dilution,
            "parts": r.parts,
            "원액 g": r.neat_g,
            "계량 g": r.weigh_g,
        }
        for r in sheet.rows
    ]
)
st.write(
    f"희석액 계량 합계 **{sheet.total_weigh_g:g}g** · 추가 에탄올 **{sheet.ethanol_to_add_g:g}g** · "
    f"기타(물 등) {sheet.other_g:g}g"
)
for w in sheet.warnings:
    st.warning(w)

st.subheader("노트 피라미드")
p = pyramid.ratios
st.write(f"Top {p['top']:g}% · Middle {p['middle']:g}% · Base {p['base']:g}%")

st.subheader("IFRA 체크")
st.table(
    [
        {
            "원료": f.name,
            "사용률%": f.usage_percent,
            "한도%": f"{f.limit_percent:g}" if f.limit_percent is not None else "―",
            "판정": ("한도없음" if f.limit_percent is None else ("초과" if f.over else "적합")),
        }
        for f in ifra.findings
    ]
)
for w in ifra.warnings:
    st.warning(w)

st.divider()
st.subheader("숙성 완료 · 시향 필요")
due = maceration_due(fragrances)
if not due:
    st.success("시향이 필요한 처방이 없습니다.")
else:
    st.table(
        [
            {
                "향": s.name,
                "버전": f"v{s.version}",
                "숙성완료일": s.ready_date.isoformat() if s.ready_date else "―",
                "경과(일)": s.days,
            }
            for s in due
        ]
    )
