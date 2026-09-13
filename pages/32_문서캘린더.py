"""🗓️ 문서 캘린더 — 그날 만들어지고 고쳐진 문서를 날짜별로 되짚어 복습한다.

git 히스토리를 그대로 읽어(별도 저장 없음) 날짜별로 새 문서/수정 문서를 보여준다.
표시만 담당하고 집계 로직은 brandlab.doc_history 에 있다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.doc_history import folder_of, load_doc_history, title_of

_WEEKDAY = ["월", "화", "수", "목", "금", "토", "일"]

st.title("🗓️ 문서 캘린더")
st.caption(
    "그날 **새로 생기거나 고쳐진 문서**를 날짜별로 모아, 배운 내용을 복습하기 쉽게 합니다. "
    "git 기록을 그대로 읽습니다(자동 최신)."
)

history = load_doc_history()

if not history:
    st.info(
        "표시할 이력이 없습니다. git 저장소가 아니거나 아직 docs/ 커밋이 없을 수 있어요. "
        "(이 화면은 커밋 기록을 읽어 만듭니다.)"
    )
    st.stop()

# ── 요약 지표 ──────────────────────────────────────────────
total_days = len(history)
total_added = sum(len(d.added) for d in history)
total_modified = sum(len(d.modified) + len(d.renamed) for d in history)
m1, m2, m3 = st.columns(3)
m1.metric("기록된 날", total_days)
m2.metric("새 문서(누적)", total_added)
m3.metric("수정(누적)", total_modified)

# ── 필터 ───────────────────────────────────────────────────
folders = sorted({folder_of(p) for d in history for p in (d.added + d.modified + d.renamed + d.deleted) if folder_of(p)})
c1, c2 = st.columns([2, 1])
query = c1.text_input("🔎 문서명 검색", placeholder="예: 원료, 학습, 크림").strip()
folder_pick = c2.selectbox("폴더", ["전체", *folders])


def _match(path: str) -> bool:
    if folder_pick != "전체" and folder_of(path) != folder_pick:
        return False
    if query and query.lower() not in title_of(path).lower():
        return False
    return True


def _line(path: str) -> str:
    fold = folder_of(path)
    tag = f"`{fold}` · " if fold else ""
    return f"- {tag}**{title_of(path)}**  \n  <small>{path}</small>"


st.divider()

shown = 0
for day in history:
    added = [p for p in day.added if _match(p)]
    modified = [p for p in day.modified if _match(p)]
    renamed = [p for p in day.renamed if _match(p)]
    deleted = [p for p in day.deleted if _match(p)]
    if not (added or modified or renamed or deleted):
        continue
    shown += 1

    wd = _WEEKDAY[day.day.weekday()]
    head = f"### 📅 {day.day.isoformat()} ({wd})"
    counts = []
    if added:
        counts.append(f"✨ 새 {len(added)}")
    if modified or renamed:
        counts.append(f"✏️ 수정 {len(modified) + len(renamed)}")
    if deleted:
        counts.append(f"🗑️ 삭제 {len(deleted)}")
    st.markdown(f"{head}  ·  " + " · ".join(counts))

    if day.subjects:
        with st.container(border=True):
            st.caption("그날 한 일(커밋)")
            for s in day.subjects:
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

    st.divider()

if shown == 0:
    st.warning("검색·필터 조건에 맞는 문서가 없습니다.")

st.caption("💡 복습 팁: 그날 '새 문서'를 열어 핵심 3줄을 요약해 보세요. 이게 곧 당신의 학습 노트가 됩니다.")
