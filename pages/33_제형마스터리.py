"""제형 마스터리 — 셰프처럼 원료·제형 감각을 8주에 익힌다.

아키타입 지도 + 원료 팔레트를 커리큘럼으로. 핵심은 '이번 주 포커스' —
지금 익힐 제형·원료와 남은 읽기/제조 퀘스트를 짚어준다. 데일리 루틴과 별개 진행
(progress_mastery.yaml). 완료 기반이라 결석해도 안 밀린다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.curriculum import (
    MASTERY_PROGRESS_PATH,
    load_mastery,
    milestone_status,
    toggle_quest,
    save_progress,
    weekly_focus,
)
from brandlab.loader import load_progress
from brandlab.ui import setup_korean_font

setup_korean_font()
st.title("제형 마스터리 🧑‍🍳")
st.caption(
    "609 레시피를 14 제형으로 압축한 지도와 원료 팔레트를 8주에 손에 익힙니다. "
    "목표는 암기가 아니라 **감각** — '이 원료는 이런 느낌이니 이 제형으로'가 떠오르게."
)
st.caption(
    "📖 교재: `docs/커리큘럼/제형_아키타입_지도.md` · `docs/커리큘럼/원료_팔레트.md`"
)

cur = load_mastery()
prog = load_progress(MASTERY_PROGRESS_PATH)


def _save(new_prog):
    save_progress(new_prog, MASTERY_PROGRESS_PATH)
    st.rerun()


done_set = set(prog.done)
total = len(cur.quests)
done_n = sum(1 for q in cur.quests if q.id in done_set)
wf = weekly_focus(cur, prog)

c1, c2, c3 = st.columns(3)
c1.metric("현재 막", wf.act.title.split(" — ")[0] if wf else "—")
c2.metric("이번 주", f"{wf.week}주차 {wf.done_in_week}/{wf.total_in_week}" if wf and not wf.all_done else "—")
c3.metric("전체 진도", f"{done_n}/{total}")
st.progress(done_n / total if total else 0.0)

st.divider()

# ---------------------------------------------------------------------------
# ⭐ 이번 주 포커스 — 지금 익힐 제형·원료 + 남은 퀘스트
# ---------------------------------------------------------------------------
st.subheader("⭐ 이번 주 포커스")
if wf is None:
    st.info("커리큘럼을 불러오지 못했습니다.")
elif wf.all_done:
    st.success("🎉 8주 전 과정 완료! 이제 히어로를 실제로 세상에 내보낼 차례입니다.")
    st.caption(f"마지막 막: {wf.act.title} — {wf.act.milestone.badge}")
else:
    st.markdown(f"### {wf.act.title} · {wf.week}주차")
    st.caption(f"🎯 {wf.act.goal}")
    st.caption(f"🏅 목표 배지: **{wf.act.milestone.badge}** — {wf.act.milestone.dod}")

    col_d, col_l = st.columns(2)
    with col_d:
        st.markdown("**🖥️ 읽기 · 설계**")
        if not wf.desk:
            st.caption("이번 주 읽기·설계 완료 ✅")
        for q in wf.desk:
            est = f"  ·  ⏱ {q.est_min}분" if q.est_min else ""
            if st.checkbox(f"{q.text}{est}", value=False, key=f"wf_{q.id}"):
                _save(toggle_quest(prog, q.id, True))
    with col_l:
        st.markdown("**🧪 제조 · 사용감 일지**")
        if not wf.lab:
            st.caption("이번 주 제조 완료 ✅")
        for q in wf.lab:
            if st.checkbox(q.text, value=False, key=f"wf_{q.id}"):
                _save(toggle_quest(prog, q.id, True))

    if not wf.desk and not wf.lab:
        st.success("이번 주 퀘스트를 다 끝냈어요 — 다음 주로 넘어갑니다! 🔥")

st.divider()
tab_map, tab_ms = st.tabs(["🗺️ 8주 전체 지도", "🏅 마일스톤"])

# ---------------------------------------------------------------------------
# 전체 지도 — 막·주차별 퀘스트 체크리스트
# ---------------------------------------------------------------------------
with tab_map:
    st.caption("체크하면 바로 저장됩니다. 순서대로 밟는 걸 권하지만, 필요하면 건너뛰어도 됩니다.")
    ms = {m.act.id: m for m in milestone_status(cur, prog)}
    for a in cur.acts:
        stat = ms[a.id]
        icon = "🏅" if stat.earned else "📍"
        opened = wf is not None and not wf.all_done and a.id == wf.act.id
        with st.expander(
            f"{icon} {a.title} · {a.weeks} · {stat.done}/{stat.total}", expanded=opened
        ):
            st.caption(f"🎯 {a.goal}")
            for q in [x for x in cur.quests if x.act == a.id]:
                kind_icon = "🖥️" if q.kind == "desk" else "🧪"
                wk = f"W{q.week} " if q.week else ""
                est = f"  ·  ⏱ {q.est_min}분" if q.est_min else ""
                checked = st.checkbox(
                    f"{wk}{kind_icon} {q.text}{est}",
                    value=q.id in done_set,
                    key=f"map_{q.id}",
                )
                if checked != (q.id in done_set):
                    _save(toggle_quest(prog, q.id, checked))

# ---------------------------------------------------------------------------
# 마일스톤
# ---------------------------------------------------------------------------
with tab_ms:
    st.caption("각 막을 끝내면 🏅 배지. 손에 잡히는 결과물(설계·시제·일지)이 동기가 됩니다.")
    for m in milestone_status(cur, prog):
        ratio = (m.done / m.total) if m.total else 0.0
        badge = "🏅 획득!" if m.earned else f"⬜ 진행 중 ({m.done}/{m.total})"
        st.progress(ratio, text=f"{m.act.milestone.badge} — {badge}")
        st.caption(f"완료 조건(DoD): {m.act.milestone.dod}")
