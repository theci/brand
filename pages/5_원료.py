"""원료 페이지 — ingredients.yaml 조회·검색.

CoA 없는 원료, 화장품용 아닌 원료를 붉게 표시한다
(캔들용 향료를 화장품에 쓰는 실수 방지).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from brandlab.ui import ingredient_flags, load_lab, setup_korean_font

st.set_page_config(page_title="원료 · brand-lab", page_icon="📦", layout="wide")
setup_korean_font()
st.title("원료")

lab = load_lab()
ings = lab.ingredients.ingredients

query = st.text_input("검색 (원료명 / INCI / id / 분류)", "").strip().lower()


def _matches(ing) -> bool:
    if not query:
        return True
    hay = " ".join(
        [ing.id, ing.name, ing.inci, ing.category, ing.grade or ""]
    ).lower()
    return query in hay


filtered = [ing for ing in ings if _matches(ing)]

flagged = [ing for ing in filtered if ingredient_flags(ing)]
if flagged:
    st.error(
        f"⚠️ 주의 원료 {len(flagged)}종: 화장품용 아님 또는 CoA 없음 (아래 붉은 행). "
        "화장품 처방에 쓰기 전 반드시 확인하세요."
    )

rows = []
for ing in filtered:
    flags = ingredient_flags(ing)
    rows.append(
        {
            "원료명": ing.name,
            "INCI": ing.inci,
            "분류": ing.category,
            "등급": ing.grade or "-",
            "단가(원/kg)": ing.price_per_kg if ing.price_per_kg is not None else "-",
            "CoA": "O" if ing.has_coa else "✗ 없음",
            "화장품용": "O" if ing.cosmetic_grade else "✗ 아님",
            "경고": ", ".join(flags) if flags else "",
        }
    )

if not rows:
    st.info("검색 결과가 없습니다.")
    st.stop()

df = pd.DataFrame(rows)
flag_mask = [bool(ingredient_flags(ing)) for ing in filtered]


def _highlight(row):
    color = "background-color: #fde0e0" if flag_mask[row.name] else ""
    return [color] * len(row)


st.dataframe(
    df.style.apply(_highlight, axis=1),
    width="stretch",
    hide_index=True,
)

st.caption(
    f"총 {len(filtered)}종 표시 · 붉은 행 = 화장품용 아님 또는 CoA 없음. "
    "CoA·등급 값은 data/ingredients.yaml에서 관리합니다."
)
