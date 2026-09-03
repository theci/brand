"""디자인 브리프 페이지 (STEP 9) — 피그마·외주에 넘길 사양서.

규제 표기(필수기재·전성분·알러젠) + 용기 규격 + 브랜드 톤 + 기획(페르소나·문제)을
1개 Markdown으로 컴파일해 내려받는다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.design_brief import build_brief
from brandlab.loader import load_brand_core, load_discovery
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("디자인 브리프 🎨")
st.caption("디자인 툴이 아닙니다. 무엇을 담아야 하는지(규제)·톤·용기 규격을 사양서로 정리해 외주에 넘깁니다.")

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
formula = options[st.selectbox("처방 선택", list(options))]

core = load_brand_core()
disc = load_discovery()

if not (core.promise or core.tone_adjectives or disc.personas.personas):
    st.info("💡 [페르소나]·[브랜드 코어]를 먼저 채우면 브리프의 컨셉·톤·비주얼이 자동으로 채워집니다.")

md = build_brief(formula, lab, core=core, discovery=disc)

st.download_button(
    "디자인 브리프 내려받기 (.md)",
    md,
    file_name=f"디자인브리프_{formula.slug}_v{formula.version}.md",
)
st.divider()
st.markdown(md)
