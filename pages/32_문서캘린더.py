"""🗓️ 문서 캘린더 — 그날 만들어지고 고쳐진 문서를 '월 달력'으로 되짚어 복습한다.

git 히스토리를 그대로 읽어(별도 저장 없음) 월(月) 그리드에 날짜별 활동을 표시하고,
날짜를 누르면 그날의 새/수정 문서를 아래에 펼친다. 표시만 담당하고 집계 로직은
brandlab.doc_history 에 있다.
"""

from __future__ import annotations

import calendar
from datetime import date

import streamlit as st

from brandlab.doc_history import folder_of, load_doc_history, title_of

_WEEKDAY = ["월", "화", "수", "목", "금", "토", "일"]

st.title("🗓️ 문서 캘린더")
st.caption(
    "그날 **새로 생기거나 고쳐진 문서**를 달력에서 되짚어 복습합니다. "
    "git 기록을 그대로 읽습니다(자동 최신). 날짜를 누르면 아래에 그날 문서가 펼쳐져요."
)

history = load_doc_history()

if not history:
    st.info(
        "표시할 이력이 없습니다. git 저장소가 아니거나 아직 docs/ 커밋이 없을 수 있어요. "
        "(이 화면은 커밋 기록을 읽어 만듭니다.)"
    )
    st.stop()

by_day = {d.day: d for d in history}  # date -> DayLog

# ── 폴더 필터(달력 강조·집계에 반영) ─────────────────────────
all_folders = sorted(
    {folder_of(p) for d in history for p in (d.added + d.modified + d.renamed + d.deleted) if folder_of(p)}
)
folder_pick = st.selectbox("폴더 필터", ["전체", *all_folders])


def _match(path: str) -> bool:
    return folder_pick == "전체" or folder_of(path) == folder_pick


def _counts(dl) -> tuple[int, int]:
    """(새 문서 수, 수정+이동 수) — 폴더 필터 적용."""
    added = sum(1 for p in dl.added if _match(p))
    modified = sum(1 for p in dl.modified + dl.renamed if _match(p))
    return added, modified


# ── 월 선택 (활동이 있는 달만) ────────────────────────────────
months = sorted({(d.day.year, d.day.month) for d in history}, reverse=True)
if "cal_ym" not in st.session_state or tuple(st.session_state.cal_ym) not in months:
    st.session_state.cal_ym = months[0]

cur_idx = months.index(tuple(st.session_state.cal_ym))
nav_prev, nav_lbl, nav_next = st.columns([1, 3, 1])
# months는 최신순 → 이전달 = 인덱스 +1, 다음달 = 인덱스 -1
if nav_prev.button("◀ 이전 달", disabled=cur_idx >= len(months) - 1, width="stretch"):
    st.session_state.cal_ym = months[cur_idx + 1]
    st.rerun()
if nav_next.button("다음 달 ▶", disabled=cur_idx <= 0, width="stretch"):
    st.session_state.cal_ym = months[cur_idx - 1]
    st.rerun()
year, month = st.session_state.cal_ym
nav_lbl.markdown(f"<h3 style='text-align:center;margin:0'>{year}년 {month}월</h3>", unsafe_allow_html=True)

# 이 달 요약
month_days = [d for d in history if (d.day.year, d.day.month) == (year, month)]
m_added = sum(_counts(d)[0] for d in month_days)
m_mod = sum(_counts(d)[1] for d in month_days)
active_days = sum(1 for d in month_days if sum(_counts(d)))
s1, s2, s3 = st.columns(3)
s1.metric("활동한 날", active_days)
s2.metric("✨ 새 문서", m_added)
s3.metric("✏️ 수정", m_mod)

st.divider()

# ── 요일 헤더 ────────────────────────────────────────────────
head_cols = st.columns(7)
for i, wd in enumerate(_WEEKDAY):
    color = "#c0392b" if i == 6 else ("#2471a3" if i == 5 else "inherit")
    head_cols[i].markdown(
        f"<div style='text-align:center;font-weight:700;color:{color}'>{wd}</div>",
        unsafe_allow_html=True,
    )

# ── 월 그리드 (월요일 시작) ──────────────────────────────────
weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
today = date.today()
for week in weeks:
    cols = st.columns(7)
    for i, dnum in enumerate(week):
        cell = cols[i]
        if dnum == 0:
            cell.markdown("&nbsp;", unsafe_allow_html=True)  # 빈 칸(전/다음 달)
            continue
        d = date(year, month, dnum)
        dl = by_day.get(d)
        added, modified = _counts(dl) if dl else (0, 0)
        is_today = d == today
        num_mark = f"**{dnum}**" + (" 🔵" if is_today else "")

        if added or modified:
            badge = " ".join(
                x for x in [f"✨{added}" if added else "", f"✏️{modified}" if modified else ""] if x
            )
            if cell.button(f"{dnum}\n\n{badge}", key=f"cal_{d.isoformat()}", width="stretch"):
                st.session_state.cal_sel = d.isoformat()
                st.rerun()
        else:
            faded = "#999" if not is_today else "#111"
            cell.markdown(
                f"<div style='text-align:center;color:{faded};padding:6px 0'>{num_mark}</div>",
                unsafe_allow_html=True,
            )

st.caption("✨ 새 문서 · ✏️ 수정(이동 포함) · 🔵 오늘. 숫자 버튼을 누르면 아래에 그날 문서가 열립니다.")

# ── 선택한 날 상세 ───────────────────────────────────────────
st.divider()
sel_iso = st.session_state.get("cal_sel")
sel = date.fromisoformat(sel_iso) if sel_iso else None
dl = by_day.get(sel) if sel else None

if dl is None:
    st.info("위 달력에서 **활동이 있는 날짜(✨/✏️ 표시)**를 눌러 그날 문서를 확인하세요.")
    st.stop()


def _line(path: str) -> str:
    fold = folder_of(path)
    tag = f"`{fold}` · " if fold else ""
    return f"- {tag}**{title_of(path)}**  \n  <small>{path}</small>"


wd = _WEEKDAY[dl.day.weekday()]
st.markdown(f"## 📅 {dl.day.isoformat()} ({wd})")

added = [p for p in dl.added if _match(p)]
renamed = [p for p in dl.renamed if _match(p)]
modified = [p for p in dl.modified if _match(p)]
deleted = [p for p in dl.deleted if _match(p)]

if dl.subjects:
    with st.container(border=True):
        st.caption("그날 한 일(커밋)")
        for s in dl.subjects:
            st.markdown(f"- {s}")

if added:
    st.markdown("**✨ 새 문서**")
    st.markdown("\n".join(_line(p) for p in added), unsafe_allow_html=True)
if renamed:
    st.markdown("**🔀 이동·개명**")
    st.markdown("\n".join(_line(p) for p in renamed), unsafe_allow_html=True)
if modified:
    st.markdown("**✏️ 수정된 문서**")
    st.markdown("\n".join(_line(p) for p in modified), unsafe_allow_html=True)
if deleted:
    st.markdown("**🗑️ 삭제**")
    st.markdown("\n".join(_line(p) for p in deleted), unsafe_allow_html=True)

st.caption("💡 복습 팁: '새 문서'를 열어 핵심 3줄을 요약해 보세요. 그게 곧 당신의 학습 노트가 됩니다.")
