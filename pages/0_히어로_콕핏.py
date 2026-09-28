"""히어로 개발 콕핏 — 제품 하나(sebum-calm-cream)만 집중 개발하는 단일 페이지.

무거운 플랫폼(600처방·STEP 0~11·수십 페이지)을 걷어내고, **지금 이 제품을 위해
무엇을 할지** 하나만 보여준다. 배치 레시피·원료 상태·다음 한 걸음.
로직은 전부 기존 모듈 재사용(표시만).
"""

from __future__ import annotations

import streamlit as st

from brandlab.checks import check_formula
from brandlab.core.costing import unit_cost
from brandlab.loader import (
    load_all_batches,
    load_all_stability,
    load_brand_core,
    load_inventory,
)
from brandlab.stability import sample_status
from brandlab.ui import load_lab, setup_korean_font

HERO_SLUG = "sebum-calm-cream"
BATCH_G = 100  # 첫 배치 기준(벤치 시트와 동일)
# 처방 슬롯 → 실제 보유 대체 원료(사둔 것)
SUBSTITUTE = {"pentylene-glycol": "propanediol", "centella-extract": "madecassoside"}

setup_korean_font()
lab = load_lab()

# 히어로 최신 버전 처방
heros = sorted(
    (f for f in lab.formulas if f.slug == HERO_SLUG),
    key=lambda f: f.version,
)
if not heros:
    st.error(f"히어로 처방({HERO_SLUG})을 찾을 수 없습니다.")
    st.stop()
hero = heros[-1]

ing_idx = {i.id: i for i in lab.ingredients.ingredients}
inv = load_inventory()
inv_idx = inv.ingredient_index()


def _held_g(ing_id: str) -> tuple[float, str]:
    """처방 슬롯 기준 보유량(대체 포함)과 상태 라벨."""
    for cand in (ing_id, SUBSTITUTE.get(ing_id)):
        if cand and cand in inv_idx:
            it = inv_idx[cand]
            note = it.notes or ""
            if it.on_hand_g and it.on_hand_g > 0:
                return it.on_hand_g, ("배송중" if "배송중" in note else "보유")
    return 0.0, "부족"


core = load_brand_core()
st.title(f"🎯 {(core.brand_name if core else '') or '다도기'} · {hero.product}")
st.caption(
    f"히어로 개발 콕핏 — 이 제품(`{hero.slug}` v{hero.version}) 하나만. "
    "여기서 시작해서 여기서 끝냅니다. 다른 페이지는 필요할 때만."
)

# 처방 원료 집계(상 순서 유지)
phase_rows = [
    (ph.name, fi.id, fi.percent) for ph in hero.phases for fi in ph.ingredients
]
readiness = {fi_id: _held_g(fi_id) for _, fi_id, _ in phase_rows}
missing = [fi_id for fi_id, (g, s) in readiness.items() if s == "부족"]
incoming = [fi_id for fi_id, (g, s) in readiness.items() if s == "배송중"]

hero_batches = [b for b in load_all_batches() if b.slug == HERO_SLUG]
hero_stab = [
    s for s in load_all_stability() if (s.formula_ref or "").startswith(HERO_SLUG)
]

# ── ① 다음 한 걸음 ─────────────────────────────────────────
st.markdown("## 👉 다음 한 걸음")
if missing:
    names = ", ".join(ing_idx[m].name if m in ing_idx else m for m in missing)
    st.warning(f"**원료 확보 먼저** — 아직 없는 것: {names}")
elif incoming:
    names = ", ".join(ing_idx[m].name if m in ing_idx else m for m in incoming)
    st.info(f"**원료 배송 대기 중** ({names}) — 도착하면 아래 레시피로 **{BATCH_G}g 배치**를 만드세요.")
elif not hero_batches:
    st.success(
        f"**✅ 원료 준비 완료 → 오늘 {BATCH_G}g 배치를 만드세요.** "
        "아래 레시피 그대로. 만든 뒤 통 2개(①사용 ②2주 관찰)로 소분."
    )
else:
    st.success(
        f"**제조 완료({len(hero_batches)}배치).** 다음 → 안정성 1·2·4·8주 관찰 입력 + "
        "같은 고민 5~10명에게 관능 피드백."
    )

st.divider()

# ── ② 배치 레시피 (100g) ───────────────────────────────────
st.markdown(f"## 🧪 배치 레시피 ({BATCH_G}g · %=g)")
st.caption(
    "전날: **히알루론산**을 정제수 일부(~20g)에 조금씩 뿌려 하룻밤 불리기. "
    "가열·유화는 클린벤치 밖, 충전만 안에서."
)
cur_phase = None
for ph_name, fi_id, pct in phase_rows:
    if ph_name != cur_phase:
        st.markdown(f"**{ph_name}**")
        cur_phase = ph_name
    name = ing_idx[fi_id].name if fi_id in ing_idx else fi_id
    g = pct * BATCH_G / 100
    sub = SUBSTITUTE.get(fi_id)
    _, status = readiness[fi_id]
    icon = {"보유": "✅", "배송중": "🚚", "부족": "🔴"}[status]
    sub_txt = ""
    if sub and sub in inv_idx and inv_idx[sub].on_hand_g > 0:
        sub_name = ing_idx[sub].name if sub in ing_idx else sub
        sub_txt = f"  _(→ {sub_name}로 대체)_"
    st.markdown(f"- {icon} {name} **{g:g} g**{sub_txt}")

st.markdown(
    "**순서:** A수상 70~75℃ 용해 → B유상 70~75℃ 용해 → 온도 ±5℃ 맞춰 합쳐 "
    "**호모 2~4분** → 저속 냉각교반 40℃ → **C 투입**(마데카소사이드·판테놀·녹차·페녹시·헥산다이올) "
    "→ **pH 4.5~6.0** → 소분."
)

# 처방 건강 체크(간단)
try:
    chk = check_formula(hero, ingredients=lab.ingredients)
    tot = sum(p for _, _, p in phase_rows)
    hlb_ok = "적합" if (chk.hlb.supplied_hlb or 0) >= (chk.hlb.required_hlb or 0) else "확인"
    uc = unit_cost(hero, 1000, ingredients=lab.ingredients, packaging=lab.packaging)
    st.caption(
        f"합계 {tot:g}% · HLB {hlb_ok}(공급 {chk.hlb.supplied_hlb}/요구 {chk.hlb.required_hlb}) "
        f"· 개당원가 약 {uc.unit_cost:,.0f}원(1,000개)"
    )
except Exception as exc:  # noqa: BLE001
    st.caption(f"처방 체크 생략: {exc}")

st.divider()

# ── ③ 원료 체크리스트 ──────────────────────────────────────
st.markdown("## 📦 원료 상태")
ready_n = sum(1 for _, (_, s) in readiness.items() if s != "부족")
st.caption(f"{ready_n}/{len(readiness)} 확보 (🚚 배송중 {len(incoming)} · 🔴 부족 {len(missing)})")
rows = []
seen = set()
for _, fi_id, _ in phase_rows:
    if fi_id in seen:
        continue
    seen.add(fi_id)
    g, status = readiness[fi_id]
    name = ing_idx[fi_id].name if fi_id in ing_idx else fi_id
    src_id = fi_id if fi_id in inv_idx else SUBSTITUTE.get(fi_id, fi_id)
    src = (inv_idx[src_id].notes or "").split(".")[0] if src_id in inv_idx else "-"
    rows.append(
        {"원료": name, "상태": {"보유": "✅", "배송중": "🚚", "부족": "🔴"}[status],
         "보유(g)": f"{g:g}", "출처·메모": src}
    )
st.dataframe(rows, width="stretch", hide_index=True)

st.divider()

# ── ④ 만든 뒤 ─────────────────────────────────────────────
st.markdown("## 🔬 만든 뒤")
c1, c2 = st.columns(2)


def _link(path: str, label: str, icon: str) -> None:
    try:
        st.page_link(path, label=label, icon=icon)
    except Exception:  # noqa: BLE001 — 네비 컨텍스트 없을 때(테스트 등) 캡션으로 대체
        st.caption(f"{icon} {label} ({path})")


with c1:
    st.markdown(f"**제조 기록** — {len(hero_batches)}배치")
    _link("pages/9_배치기록.py", "배치기록 입력 →", "🧾")
with c2:
    if hero_stab:
        overdue = sum(
            1 for s in hero_stab for cs in sample_status(s) if cs.status == "overdue"
        )
        st.markdown(f"**안정성 시료** — {len(hero_stab)}종 (지연 {overdue})")
    else:
        st.markdown("**안정성 시료** — 없음")
    _link("pages/4_실험.py", "안정성·실험 →", "🔬")

st.caption(
    "이 페이지 = 이 제품만의 콕핏. 브랜딩·마케팅·디자인은 **개발이 끝난 뒤**에. "
    "지금은 만들고, 써보고, 5~10명 반응 받기."
)
