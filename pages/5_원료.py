"""원료 페이지 — ingredients.yaml 조회·검색.

CoA 없는 원료, 화장품용 아닌 원료를 붉게 표시한다
(캔들용 향료를 화장품에 쓰는 실수 방지).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from brandlab.core.models import Ingredient
from brandlab.loader import DATA_DIR, load_ingredients
from brandlab.master_edit import (
    append_item,
    delete_item,
    render_ingredient_block,
    save_with_backup,
)
from brandlab.ui import ingredient_flags, load_lab, setup_korean_font


def _num(s: str) -> float | None:
    """빈 문자열이면 None, 아니면 float. 형식이 틀리면 ValueError."""
    s = (s or "").strip()
    return None if s == "" else float(s)

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

ING_PATH = DATA_DIR / "ingredients.yaml"

with st.expander("➕ 새 원료 등록"):
    with st.form("add_ingredient"):
        st.caption("id·이름·INCI·분류는 필수. 나머지는 비워두면 생략됩니다.")
        c1, c2 = st.columns(2)
        new_id = c1.text_input("id (고유 슬러그, 예: shea-butter)")
        new_name = c2.text_input("원료명(한글)")
        c3, c4 = st.columns(2)
        new_inci = c3.text_input("INCI 표준명")
        new_category = c4.text_input("분류(예: 에몰리언트, 유화제, 방부제)")

        c5, c6, c7 = st.columns(3)
        new_price = c5.text_input("단가(원/kg)")
        new_density = c6.text_input("밀도(g/ml)")
        new_max = c7.text_input("권장상한(%)")
        c8, c9, c10 = st.columns(3)
        new_hlb = c8.text_input("HLB(유화제만)")
        new_req_hlb = c9.text_input("required HLB(오일만)")
        new_cas = c10.text_input("CAS")
        c11, c12 = st.columns(2)
        new_grade = c11.text_input("등급(cosmetic/candle/food 등)")
        new_supplier = c12.text_input("공급처")
        new_notes = st.text_input("메모")

        c13, c14, c15, c16, c17 = st.columns(5)
        new_coa = c13.checkbox("CoA 보유", value=False)
        new_cosmetic = c14.checkbox("화장품용", value=True)
        new_food = c15.checkbox("식품용", value=False)
        new_fragrance = c16.checkbox("착향제", value=False)
        new_colorant = c17.checkbox("착색제", value=False)

        submitted = st.form_submit_button("등록")
    if submitted:
        try:
            fields = {
                "id": new_id.strip(),
                "name": new_name.strip(),
                "inci": new_inci.strip(),
                "category": new_category.strip(),
                "max_percent": _num(new_max),
                "price_per_kg": _num(new_price),
                "density": _num(new_density),
                "hlb": _num(new_hlb),
                "required_hlb": _num(new_req_hlb),
                "has_coa": new_coa,
                "cosmetic_grade": new_cosmetic,
                "grade": new_grade.strip() or None,
                "cas": new_cas.strip() or None,
                "fragrance": new_fragrance,
                "colorant": new_colorant,
                "food_grade": new_food,
                "supplier": new_supplier.strip() or None,
                "notes": new_notes.strip() or None,
            }
            # 1) 단일 항목 pydantic 검증 (필수·타입·범위)
            Ingredient.model_validate({k: v for k, v in fields.items() if v is not None})
            if fields["id"] in lab.ingredients.index():
                st.error(f"이미 존재하는 id입니다: {fields['id']}")
            else:
                block = render_ingredient_block(fields)
                original = ING_PATH.read_text(encoding="utf-8")
                # 2) 백업 + 쓰기 + 전체 재검증(중복 id 등) + 실패 시 롤백
                save_with_backup(ING_PATH, append_item(original, block), load_ingredients)
                st.success(f"등록됨: {fields['id']}  (백업: ingredients.yaml.bak)")
                st.rerun()
        except Exception as exc:  # noqa: BLE001 — 사용자에게 사유 표시
            st.error(f"등록 실패: {exc}")

with st.expander("🗑️ 원료 삭제"):
    if not ings:
        st.info("삭제할 원료가 없습니다.")
    else:
        del_options = {f"{i.name} ({i.id})": i.id for i in ings}
        del_label = st.selectbox("삭제할 원료", list(del_options), key="del_ing_sel")
        del_id = del_options[del_label]
        # 처방이 참조 중이면 삭제 금지(참조 무결성 보호)
        users = [
            f"{f.slug} v{f.version}"
            for f in lab.formulas
            if del_id in f.ingredient_ids()
        ]
        if users:
            st.warning(
                f"이 원료를 사용하는 처방이 있어 삭제할 수 없습니다: {', '.join(users)}. "
                "먼저 해당 처방에서 제거하세요."
            )
        else:
            confirm = st.checkbox(f"정말 '{del_id}' 를 삭제합니다", key="del_ing_confirm")
            if st.button("삭제", type="primary", disabled=not confirm, key="del_ing_btn"):
                try:
                    original = ING_PATH.read_text(encoding="utf-8")
                    save_with_backup(
                        ING_PATH, delete_item(original, del_id), load_ingredients
                    )
                    st.success(f"삭제됨: {del_id}  (백업: ingredients.yaml.bak)")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"삭제 실패: {exc}")

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
