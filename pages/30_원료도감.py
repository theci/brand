"""원료 도감(백과) 페이지 — 원료를 처음 배우는 사람을 위한 학습용 지식.

ingredient_codex.yaml(사람이 읽는 백과)을 ingredients.yaml(계산용 마스터)과
id로 합쳐 한 화면에 보여준다. 백과는 궁금한 원료부터 하나씩 채우는 성격이라
'아직 백과 없는' 원료도 함께 안내한다.

※ 안전·함량·규제성 서술(needs_verification)은 '검증 필요'로 표시한다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.core.models import CodexEntry, Ingredient
from brandlab.loader import load_codex, load_ingredients
from brandlab.ui import ingredient_flags, setup_korean_font

setup_korean_font()
st.title("📚 원료 도감")
st.caption(
    "원료가 처음이라도 '이게 뭔지·왜 넣는지·어떻게 쓰는지'를 한 화면에서 익히는 학습용 백과입니다. "
    "계산용 데이터(단가·HLB·상한)는 원료 마스터와 자동 연동됩니다."
)
st.info(
    "표기: ⚠️ **검증 필요** = 안전·함량·규제성 서술은 예시이니 공급처 CoA/기술자료(TDS)·"
    "규제판정으로 확인하세요. 사용 %와 주의는 배합 전 반드시 재확인."
)

codex = load_codex()
master = load_ingredients().index()

if not codex.entries:
    st.warning("아직 도감 항목이 없습니다. `data/ingredient_codex.yaml`에 원료를 추가하세요.")
    st.stop()

# 도감 항목을 카테고리별로 묶는다. 마스터에 있으면 마스터 category 우선,
# 없으면(학습 전용) 항목의 category, 그것도 없으면 "(기타)".
def _cat(e: CodexEntry) -> str:
    ing = master.get(e.id)
    if ing:
        return ing.category
    return e.category or "(기타)"


entries = sorted(codex.entries, key=lambda e: (_cat(e), e.id))

# 검색 + 카테고리 필터
c1, c2 = st.columns([2, 1])
with c1:
    q = st.text_input(
        "🔎 검색 (이름·INCI·id·요약)",
        placeholder="예: 보습, 유화, glycerin …",
        key="cx_q",
    ).strip().lower()
with c2:
    cats = ["전체"] + sorted({_cat(e) for e in entries})
    cat_sel = st.selectbox("분류", cats, key="cx_cat")

st.caption(
    f"총 **{len(codex.entries)}종** · 마스터 연동 원료는 계산용 데이터가 함께 뜨고, "
    "📖 표시는 아직 처방/마스터에 없는 **학습 전용** 항목입니다(처방에 넣으면 자동 연결)."
)


def _matches(e: CodexEntry) -> bool:
    ing = master.get(e.id)
    if cat_sel != "전체" and _cat(e) != cat_sel:
        return False
    if not q:
        return True
    hay = " ".join(
        [e.id, e.summary, ing.name if ing else "", ing.inci if ing else ""]
    ).lower()
    return q in hay


shown = [e for e in entries if _matches(e)]
if not shown:
    st.warning("조건에 맞는 도감 항목이 없습니다.")
    st.stop()


def _label(e: CodexEntry) -> str:
    ing = master.get(e.id)
    name = ing.name if ing else e.id
    mark = "" if ing else "📖 "
    return f"{mark}{name}  ·  {_cat(e)}"


sel = st.selectbox("원료 선택", shown, format_func=_label, key="cx_sel")
ing = master.get(sel.id)


# --- 헤더 ---
st.markdown("---")
name = ing.name if ing else sel.id
st.subheader(name)
sub = [f"INCI: {ing.inci}"] if ing else []
sub.append(_cat(sel))
st.caption("  ·  ".join(sub))
st.markdown(f"**{sel.summary}**")

if sel.needs_verification:
    st.warning("⚠️ 아래 안전·함량·규제성 서술은 **검증 필요**한 예시입니다. 배합 전 CoA/TDS·규제판정으로 확인하세요.")

# 마스터에 없으면 학습 전용 항목 안내(에러 아님 — 정상)
if ing is None:
    st.info(
        f"📖 **학습 전용 항목** — `{sel.id}` 는 아직 원료 마스터/처방에 없습니다. "
        "이 처방에 실제로 쓰기로 하면 `원료` 페이지에서 등록하세요. 등록하면 오른쪽에 단가·HLB 등이 자동 연결됩니다."
    )

left, right = st.columns([2, 1], gap="large")


def _field(icon: str, title: str, value: str | None) -> None:
    if value:
        st.markdown(f"**{icon} {title}**")
        st.write(value)


def _list_field(icon: str, title: str, values: list[str]) -> None:
    if values:
        st.markdown(f"**{icon} {title}**")
        for v in values:
            st.markdown(f"- {v}")


with left:
    _field("🧭", "이게 뭔가", sel.what)
    _field("🎯", "왜 넣나 (기능)", sel.why)
    _field("✋", "사용감", sel.feel)
    if sel.typical_percent or sel.phase:
        st.markdown("**⚗️ 사용법**")
        if sel.typical_percent:
            st.write(f"대표 사용 범위: {sel.typical_percent}")
        if sel.phase:
            st.write(f"투입: {sel.phase}")
    _list_field("🤝", "궁합 좋은 조합", sel.pairs_with)
    _list_field("🚫", "피할 조합", sel.avoid_with)
    _field("⚠️", "주의", sel.cautions)
    _list_field("🔁", "대체 원료", sel.substitutes)
    _field("🌱", "초보 팁", sel.newbie_tip)
    if sel.sources:
        st.markdown("**🔗 근거**")
        for s in sel.sources:
            st.markdown(f"- {s}")


with right:
    st.markdown("**📊 계산용 데이터 (원료 마스터)**")
    if ing is None:
        st.write("📖 학습 전용 — 아직 마스터에 없어 단가·HLB 등은 없습니다.")
        st.caption("`원료` 페이지에서 등록하면 여기에 자동으로 채워집니다.")
    else:
        rows: list[tuple[str, str]] = []
        if ing.max_percent is not None:
            rows.append(("권장 상한", f"{ing.max_percent:g}%"))
        if ing.price_per_kg is not None:
            rows.append(("단가", f"{ing.price_per_kg:,.0f} 원/kg"))
        if ing.density is not None:
            rows.append(("밀도", f"{ing.density:g} g/ml"))
        if ing.hlb is not None:
            rows.append(("HLB", f"{ing.hlb:g}"))
        if ing.required_hlb is not None:
            rows.append(("required HLB", f"{ing.required_hlb:g}"))
        if ing.moisture_role:
            rows.append(("보습 역할", ing.moisture_role))
        if ing.cas:
            rows.append(("CAS", ing.cas))
        if ing.grade:
            rows.append(("등급", ing.grade))
        rows.append(("CoA(성적서)", "있음" if ing.has_coa else "없음 ⚠️"))
        rows.append(("화장품용", "예" if ing.cosmetic_grade else "아님 ⚠️"))
        for k, v in rows:
            st.markdown(f"- **{k}**: {v}")

        flags = ingredient_flags(ing)
        if flags:
            st.error("주의: " + " · ".join(flags))
        if ing.notes:
            st.caption(f"메모: {ing.notes}")

# --- 아직 백과 없는 원료 안내 ---
st.markdown("---")
missing = [i for i in master.values() if i.id not in codex.index()]
with st.expander(f"📝 아직 백과가 없는 원료 {len(missing)}종 (채우면 좋은 목록)"):
    if not missing:
        st.write("모든 마스터 원료에 백과가 있습니다. 👍")
    else:
        st.caption("`data/ingredient_codex.yaml`에 id로 항목을 추가하면 이 화면에 바로 나타납니다.")
        for i in sorted(missing, key=lambda x: (x.category, x.id)):
            st.markdown(f"- **{i.name}** (`{i.id}`) · {i.category}")
