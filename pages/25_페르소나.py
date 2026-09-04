"""페르소나·JTBD 페이지 (STEP 0 기획) — 타깃·페인 편집 + 우선순위 랭킹.

페인 점수 = 심각도 × 빈도. 이 데이터가 포지셔닝·브랜드코어로 프리필된다.
"""

from __future__ import annotations

from collections import defaultdict

import streamlit as st

from brandlab.core.models import Persona, PainPoint, PersonaBook
from brandlab.discovery import rank_pains, save_personas
from brandlab.loader import load_discovery
from brandlab.ui import setup_korean_font

setup_korean_font()
st.title("페르소나 · JTBD 🧑")
st.caption("타깃 고객과 그들의 페인을 정의합니다. 페인 점수 = 심각도 × 빈도 → 우선순위 랭킹.")
st.info(
    "✍️ **이 화면은 모두 직접 입력**입니다(자동 채움 없음). 각 칸 제목(헤더)에 마우스를 올리면 "
    "**예시**가 떠요. 예시는 `산뜻보습로션` 시나리오 기준입니다."
)

disc = load_discovery()

# 표 칸별 예시(툴팁) — '무슨 단어를 넣을지' 막힐 때 헤더에 마우스를 올리면 보인다.
_PERSONA_COLS = {
    "id": st.column_config.TextColumn("id", help="영문·하이픈 고유 이름표. 예: dry-office-30s"),
    "name": st.column_config.TextColumn("name", help="사람이 읽는 이름. 예: 건조한 사무직 30대"),
    "one_line": st.column_config.TextColumn(
        "one_line", help="한 줄 정의(포지셔닝 '타깃'으로 감). 예: 냉난방 사무실에서 하루 종일 당김을 느끼는 30대 직장인"),
    "context": st.column_config.TextColumn("context", help="상황. 예: 실내 근무 8시간, 냉난방 상시, 점심 후 화장 들뜸"),
    "jobs(쉼표)": st.column_config.TextColumn("jobs(쉼표)", help="고객이 시키는 일(JTBD), 쉼표로. 예: 바쁜 아침 빠른 흡수, 메이크업 위 덧바름"),
    "current_solution": st.column_config.TextColumn("current_solution", help="지금 쓰는 대안. 예: 대형 브랜드 수분크림"),
    "dissatisfaction": st.column_config.TextColumn("dissatisfaction", help="그 대안의 불만(문제의 씨앗). 예: 끈적이고 흡수가 느려 화장이 밀림"),
    "priority": st.column_config.NumberColumn("priority", help="타깃 우선순위 1~5. 예: 5", min_value=1, max_value=5, step=1),
}
_PAIN_COLS = {
    "persona_id": st.column_config.TextColumn("persona_id", help="위 페르소나 id로 연결. 예: dry-office-30s"),
    "desc": st.column_config.TextColumn("desc", help="페인 묘사. 예: 오후만 되면 볼이 당기고 각질이 인다"),
    "severity": st.column_config.NumberColumn("severity", help="심각도 1~5. 예: 5", min_value=1, max_value=5, step=1),
    "frequency": st.column_config.NumberColumn("frequency", help="빈도 1~5. 예: 4", min_value=1, max_value=5, step=1),
    "source_ref": st.column_config.TextColumn("source_ref", help="근거 출처 id(선택, 시장·경쟁 조사의 출처). 예: src-review-oy"),
}


def _csv(s) -> list[str]:
    return [x.strip() for x in str(s or "").split(",") if x.strip()]


def _int(v, default=3) -> int:
    try:
        return max(1, min(5, int(float(v))))
    except (TypeError, ValueError):
        return default


# --- 우선순위 랭킹 (읽기) ---
ranked = rank_pains(disc.personas)
if ranked:
    st.subheader("🔥 페인 우선순위")
    st.table(
        [
            {"순위": i, "페르소나": r.persona_name, "페인": r.pain.desc,
             "심각도": r.pain.severity, "빈도": r.pain.frequency, "점수": r.score}
            for i, r in enumerate(ranked, 1)
        ]
    )

# --- 페르소나 편집 ---
st.subheader("페르소나 (행 추가/삭제 가능)")
persona_rows = st.data_editor(
    [
        {
            "id": p.id, "name": p.name, "one_line": p.one_line or "",
            "context": p.context or "", "jobs(쉼표)": ", ".join(p.jobs),
            "current_solution": p.current_solution or "",
            "dissatisfaction": p.dissatisfaction or "", "priority": p.priority,
        }
        for p in disc.personas.personas
    ]
    or [{"id": "", "name": "", "one_line": "", "context": "", "jobs(쉼표)": "",
         "current_solution": "", "dissatisfaction": "", "priority": 3}],
    num_rows="dynamic", key="persona_tbl", width="stretch", column_config=_PERSONA_COLS,
)

# --- 페인 편집 (persona_id로 연결) ---
st.subheader("페인 (persona_id로 페르소나에 연결)")
pain_rows = st.data_editor(
    [
        {"persona_id": p.id, "desc": pain.desc, "severity": pain.severity,
         "frequency": pain.frequency, "source_ref": pain.source_ref or ""}
        for p in disc.personas.personas for pain in p.pains
    ]
    or [{"persona_id": "", "desc": "", "severity": 3, "frequency": 3, "source_ref": ""}],
    num_rows="dynamic", key="pain_tbl", width="stretch", column_config=_PAIN_COLS,
)

if st.button("💾 페르소나 저장", type="primary"):
    pains_by_pid: dict[str, list[PainPoint]] = defaultdict(list)
    for r in pain_rows:
        pid = str(r.get("persona_id") or "").strip()
        desc = str(r.get("desc") or "").strip()
        if not pid or not desc:
            continue
        pains_by_pid[pid].append(
            PainPoint(
                desc=desc, severity=_int(r.get("severity")), frequency=_int(r.get("frequency")),
                source_ref=str(r.get("source_ref") or "").strip() or None,
            )
        )
    personas: list[Persona] = []
    seen: set[str] = set()
    for r in persona_rows:
        pid = str(r.get("id") or "").strip()
        name = str(r.get("name") or "").strip()
        if not pid or not name or pid in seen:
            continue
        seen.add(pid)
        personas.append(
            Persona(
                id=pid, name=name,
                one_line=str(r.get("one_line") or "").strip() or None,
                context=str(r.get("context") or "").strip() or None,
                jobs=_csv(r.get("jobs(쉼표)")),
                current_solution=str(r.get("current_solution") or "").strip() or None,
                dissatisfaction=str(r.get("dissatisfaction") or "").strip() or None,
                priority=_int(r.get("priority")),
                pains=pains_by_pid.get(pid, []),
            )
        )
    try:
        path = save_personas(PersonaBook(personas=personas))
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장 실패: {exc}")
    else:
        st.success(f"저장됨: {path}  (페르소나 {len(personas)}명). 새로고침하면 랭킹에 반영됩니다.")

st.info("💡 페인을 채우면 [문제 정의]에서 문제 문장이 자동 초안되고, [포지셔닝]·[브랜드 코어]로 프리필됩니다.")
