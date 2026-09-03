"""오늘·진행 (시작) — 데일리 루틴 진행 트래커.

커리큘럼 12주를 하루하루 퀘스트로. 전체 지도·마일스톤·3줄 보고를 한 페이지에.
완료 기반 진행(날짜 강제 아님) — 결석해도 안 밀린다. 상태는 progress.yaml에 저장.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from brandlab.core.models import DailyReport
from brandlab.curriculum import (
    add_report,
    current_position,
    days_since_report,
    milestone_status,
    prefill_next,
    save_progress,
    set_start_date,
    streak,
    toggle_quest,
)
from brandlab.loader import load_curriculum, load_progress
from brandlab.ui import setup_korean_font

setup_korean_font()
st.title("오늘·진행 🎯")
st.caption("커리큘럼 12주를 하루하루 퀘스트로. 목표는 완벽이 아니라 **지속** — 결석해도 다시 오면 됩니다.")

cur = load_curriculum()
prog = load_progress()
today = date.today()

pos = current_position(cur, prog, today)
strk = streak(prog, today)
dsr = days_since_report(prog, today)

c1, c2, c3 = st.columns(3)
c1.metric("경과", f"D+{pos.day_index}" if pos.day_index is not None else "D+—")
c2.metric("현재 막", pos.act.title if pos.act else "시작 전")
c3.metric("스트릭", f"{strk}일 🔥" if strk else "0일")

if dsr is not None and dsr >= 2:
    st.warning(f"⚠️ 마지막 보고 {dsr}일 전 — **10분 법칙**으로 딱 10분만 복귀하세요. (연속 2회 결석 금지)")

with st.expander("🚩 시작일(D0) 설정", expanded=prog.start_date is None):
    d0 = st.date_input("장비·원료 세팅이 끝난 날 = D0", value=prog.start_date or today, key="d0")
    if st.button("D0 저장", key="save_d0"):
        save_progress(set_start_date(prog, d0))
        st.success("저장됨")
        st.rerun()

st.divider()
tab_map, tab_ms, tab_report = st.tabs(["🗺️ 전체 지도", "🏅 마일스톤", "📝 3줄 보고"])

# ---------------------------------------------------------------------------
# 전체 지도 — 막별 퀘스트 체크리스트
# ---------------------------------------------------------------------------
with tab_map:
    st.caption("퀘스트를 체크하면 바로 저장됩니다. 다음에 뭘 할지는 홈이 짚어줘요.")
    done_set = set(prog.done)
    ms = {m.act.id: m for m in milestone_status(cur, prog)}
    for a in cur.acts:
        stat = ms[a.id]
        icon = "🏅" if stat.earned else "📍"
        opened = pos.act is not None and a.id == pos.act.id
        with st.expander(f"{icon} {a.title} · {a.weeks} · {stat.done}/{stat.total}", expanded=opened):
            st.caption(f"🎯 {a.goal}")
            st.caption(f"🏅 {a.milestone.badge} — {a.milestone.dod}")
            for q in [x for x in cur.quests if x.act == a.id]:
                kind_icon = "🖥️" if q.kind == "desk" else "🧪"
                est = f"  ·  ⏱ {q.est_min}분" if q.est_min else ""
                checked = st.checkbox(
                    f"{kind_icon} {q.text}{est}", value=q.id in done_set, key=f"map_{q.id}"
                )
                if checked != (q.id in done_set):
                    save_progress(toggle_quest(prog, q.id, checked))
                    st.rerun()

# ---------------------------------------------------------------------------
# 마일스톤
# ---------------------------------------------------------------------------
with tab_ms:
    st.caption("각 막을 다 끝내면 🏅 배지 획득. 손에 잡히는 결과물이 동기가 됩니다.")
    for m in milestone_status(cur, prog):
        ratio = (m.done / m.total) if m.total else 0.0
        badge = "🏅 획득!" if m.earned else f"⬜ 진행 중 ({m.done}/{m.total})"
        st.progress(ratio, text=f"{m.act.milestone.badge} — {badge}")
        st.caption(f"완료 조건(DoD): {m.act.milestone.dod}")

# ---------------------------------------------------------------------------
# 3줄 보고
# ---------------------------------------------------------------------------
with tab_report:
    st.caption("딱 3줄. 보고의 목적은 기록이 아니라 **끊기지 않게 하는 것**. 같은 날짜는 덮어써집니다.")
    default_kind = "lab" if today.weekday() >= 5 else "desk"
    with st.form("report_form"):
        rdate = st.date_input("날짜", value=today, key="r_date")
        did = st.text_area("오늘 한 것", key="r_did", height=70)
        blocked = st.text_input("막힌 것/질문", key="r_blocked")
        nxt = st.text_input(
            "내일 할 것 (다음 퀘스트를 자동으로 넣어뒀어요)",
            value=prefill_next(cur, prog, kind=default_kind),
            key="r_next",
        )
        ten = st.checkbox("10분 법칙으로 출석(짧게라도 함)", key="r_ten")
        if st.form_submit_button("보고 저장", type="primary"):
            rep = DailyReport(
                date=rdate,
                did=did.strip(),
                blocked=blocked.strip() or None,
                next=nxt.strip() or None,
                ten_min=ten,
            )
            save_progress(add_report(prog, rep))
            st.success("보고 저장됨 — 스트릭 유지! 🔥")
            st.rerun()

    if prog.reports:
        st.markdown("**보고 로그**")
        st.dataframe(
            [
                {
                    "날짜": r.date.isoformat(),
                    "한 것": r.did,
                    "막힌 것": r.blocked or "",
                    "내일": r.next or "",
                    "10분": "✓" if r.ten_min else "",
                }
                for r in sorted(prog.reports, key=lambda r: r.date, reverse=True)
            ],
            width="stretch",
            hide_index=True,
        )
    if today.weekday() == 6:
        st.info("🧭 일요일이에요 — **주간 회고 5분**: 이번 주 한 것 / 배운 것 / 다음 주 각오.")
