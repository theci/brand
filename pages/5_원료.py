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

with st.expander("🔎 PubChem 원료 자동채움 (CAS·밀도)"):
    from brandlab.ingredient_edit import set_ingredient_fields
    from brandlab.loader import DATA_DIR, load_ingredients
    from brandlab.pubchem import PubChemError, fetch_pubchem, http_get_json

    st.caption("무인증 공개 DB(PubChem)에서 CAS·밀도를 조회해 비어 있는 칸을 채웁니다.")
    ing_options = {f"{i.name} ({i.id})": i for i in ings}
    target = ing_options[st.selectbox("원료 선택", list(ing_options), key="enrich_sel")]
    force = st.checkbox("이미 값이 있어도 덮어쓰기", key="enrich_force")

    if st.button("PubChem 조회"):
        with st.spinner("PubChem 조회 중…"):
            try:
                st.session_state["enrich_result"] = (
                    target.id,
                    fetch_pubchem(name=target.inci, cas=target.cas, get_json=http_get_json),
                )
            except PubChemError as exc:
                st.session_state["enrich_result"] = (target.id, None)
                st.error(f"조회 실패: {exc}")

    res = st.session_state.get("enrich_result")
    if res and res[0] == target.id and res[1] is not None:
        data = res[1]
        if not data.found:
            st.warning("PubChem에서 찾지 못했습니다(고분자·혼합물·복합 INCI명일 수 있음).")
        else:
            proposals: dict[str, object] = {}

            def _plan(field, current, suggested):
                if suggested is None:
                    return "―"
                if current is not None and not force:
                    return "유지(값 있음)"
                proposals[field] = suggested
                return "✅ 채움 대상"

            st.table(
                [
                    {"필드": "CAS", "현재": target.cas or "―", "PubChem": data.cas or "―",
                     "반영": _plan("cas", target.cas, data.cas)},
                    {"필드": "density", "현재": target.density or "―", "PubChem": data.density or "―",
                     "반영": _plan("density", target.density, data.density)},
                    {"필드": "분자량", "현재": "―", "PubChem": data.molecular_weight or "―", "반영": "정보"},
                    {"필드": "분자식", "현재": "―", "PubChem": data.molecular_formula or "―", "반영": "정보"},
                ]
            )
            if data.source_url:
                st.caption(f"출처: {data.source_url}")

            if proposals and st.button("ingredients.yaml에 채우기(저장)"):
                path = DATA_DIR / "ingredients.yaml"
                original = path.read_text(encoding="utf-8")
                new_text, applied = set_ingredient_fields(original, target.id, proposals)
                path.write_text(new_text, encoding="utf-8")
                try:
                    load_ingredients(path)
                except Exception as exc:  # noqa: BLE001 — 검증 실패면 롤백
                    path.write_text(original, encoding="utf-8")
                    st.error(f"검증 실패로 되돌렸습니다: {exc}")
                else:
                    st.success("갱신: " + ", ".join(f"{k}={v}" for k, v in applied.items()))
                    st.rerun()
            elif not proposals:
                st.info("채울 새 값이 없습니다(이미 채워져 있음).")

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
