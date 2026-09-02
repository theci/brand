"""라벨 페이지 — 제품의 레짐(적용 법)에 따라 화면을 분기한다.

- cosmetics(화장품법): 전성분 문자열·알러젠 판정·표시 의무·배합한도 (리치 뷰)
- 그 외 레짐(chemical_safety 등): 레짐 검증(validate) + 표시 필수항목(label_spec)
- 미지원 레짐(biocide·quasi_drug): 거부 사유 표시

백엔드는 이미 regime_for(formula)로 레짐을 추상화한다. 이 페이지는 그 추상화를
UI까지 확장해, 화장품이 아닌 제품에 화장품 전용 로직을 잘못 적용하지 않도록 한다.
새 레짐(예: food/식품)을 추가하면 별도 수정 없이 아래 '레짐 뷰'가 흡수한다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.food import nutrition_facts
from brandlab.labeling import screen
from brandlab.regimes import UnsupportedRegimeError, regime_for
from brandlab.regimes.registry import UnknownRegimeError
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("라벨 스크리닝")


def render_cosmetics(formula, lab) -> None:
    """화장품법 리치 뷰: 전성분·알러젠·표시의무·배합한도."""
    result = screen(formula, lab)

    # 규제 데이터 최신성
    for w in result.freshness.warnings:
        st.warning(f"규제데이터: {w}")

    # 전성분 문자열 (st.code = 복사 버튼 내장)
    st.subheader("전성분 표시(안)")
    st.code(result.inci.text or "(없음)", language="text")
    for w in result.inci.warnings:
        st.warning(w)

    # 알러젠 판정
    st.subheader(
        f"알러젠 판정 (임계값 {result.allergens.threshold_percent:g}% / "
        f"{result.allergens.product_type.value})"
    )
    arows = [
        {
            "성분": f.name,
            "INCI": f.inci,
            "완제품 농도%": f.concentration_percent,
            "표기": "표기 필요" if f.must_declare else "이하",
        }
        for f in [*result.allergens.declared, *result.allergens.below_threshold]
    ]
    st.table(arows or [{"성분": "해당 없음", "INCI": "", "완제품 농도%": "", "표기": ""}])
    for w in result.allergens.warnings:
        st.warning(w)

    # 표시 의무
    req = result.requirement
    size = f"{req.size_value:g}{req.size_unit}" if req.size_value is not None else "미상"
    st.subheader("표시 의무")
    st.write(f"내용량 **{size}** → 구분: **{req.tier}**")
    st.write("표시 항목: " + ", ".join(req.required_items))
    for n in req.notes:
        st.caption(n)

    # 배합한도
    st.subheader("배합한도 체크")
    if not result.limits.has_data:
        st.error(result.limits.warnings[0])
    else:
        lrows = [
            {
                "원료": f.name,
                "함량%": f.percent,
                "한도%": f.max_percent,
                "판정": "초과" if f.exceeded else "적합",
            }
            for f in result.limits.findings
        ]
        st.table(lrows or [{"원료": "대조 대상 없음", "함량%": "", "한도%": "", "판정": ""}])
        for w in result.limits.warnings:
            st.warning(w)

    st.error(result.disclaimer)


def render_regime(regime, formula) -> None:
    """화장품이 아닌 레짐의 뷰: 검증(validate) + 표시 필수항목(label_spec)."""
    st.info(
        f"이 제품은 화장품이 아니라 **{regime.display_name}**({regime.law_name})입니다. "
        "전성분·알러젠 대신 이 법의 검증·표시기준을 적용합니다."
    )

    # 레짐 검증 결과 (금지/제한물질, 경제성 경고 등)
    st.subheader("레짐 검증")
    findings = regime.validate(formula)
    if not findings:
        st.success("특이사항 없음 (등록된 규칙 기준).")
    for f in findings:
        msg = f.message + (f"\n\n근거: {f.reference}" if f.reference else "")
        if f.level == "error":
            st.error(msg)
        elif f.level == "warning":
            st.warning(msg)
        else:
            st.info(msg)

    # 표시 필수 기재 항목
    st.subheader("라벨 필수 기재 항목")
    try:
        spec = regime.label_spec(formula)
    except UnsupportedRegimeError as exc:
        st.error(str(exc))
        return
    rows = [
        {
            "항목": it.label,
            "필수": "필수" if it.required else "선택",
            "비고": it.note or "",
        }
        for it in spec.items
    ]
    st.table(rows or [{"항목": "(표시 항목 데이터 없음)", "필수": "", "비고": ""}])
    for n in spec.notes:
        st.caption(n)

    st.error(
        "이 결과는 1차 스크리닝입니다. 법적 판단이 아니며, 출시 전 반드시 "
        "관할 기관 고시 원문과 대조하고 전문가 검토를 받으십시오."
    )


def render_food(formula, lab, regime) -> None:
    """식품 뷰: 영양성분표(계산) + 레짐 검증(알레르기·등급) + 표시 필수항목."""
    facts = nutrition_facts(formula, lab.ingredients)

    st.subheader("영양성분표 (원료 영양의 가중합 · 계산값)")
    serving = formula.net_weight_g
    p, s = facts.per_100g, facts.per_serving
    items = [
        ("열량(kcal)", p.kcal, s.kcal if s else None),
        ("단백질(g)", p.protein_g, s.protein_g if s else None),
        ("지방(g)", p.fat_g, s.fat_g if s else None),
        ("탄수화물(g)", p.carb_g, s.carb_g if s else None),
        ("당류(g)", p.sugar_g, s.sugar_g if s else None),
        ("나트륨(mg)", p.sodium_mg, s.sodium_mg if s else None),
    ]
    rows = []
    for name, v100, vs in items:
        row = {"항목": name, "100g당": round(v100, 1)}
        if s is not None:
            row[f"1회 제공량({serving:g}g)"] = round(vs, 1)
        rows.append(row)
    st.table(rows)

    for flag in facts.emphasis_flags:
        st.success(f"강조표시 후보: {flag}")
    for w in facts.warnings:
        st.warning(w)

    # 이어서 표준 레짐 뷰(알레르기·등급 검증 + 식품 표시 필수항목)
    render_regime(regime, formula)


lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
label = st.selectbox("처방 선택", list(options))
formula = options[label]

regime_code = getattr(formula, "regime", "cosmetics")

# 레짐 배지 — 어떤 법이 적용되는지 먼저 알린다.
try:
    regime = regime_for(formula)
    st.caption(
        f"레짐: **{regime.display_name}** · {regime.law_name} · 코드 `{regime_code}`"
    )
except UnknownRegimeError as exc:
    st.error(str(exc))
    st.stop()

# 레짐에 따라 화면 분기: 화장품 리치 뷰 / 식품 영양성분 뷰 / 그 외 레짐 뷰.
if regime_code == "cosmetics":
    render_cosmetics(formula, lab)
elif regime_code == "food":
    render_food(formula, lab, regime)
else:
    render_regime(regime, formula)
