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

disc = load_discovery()


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
    num_rows="dynamic", key="persona_tbl", width="stretch",
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
    num_rows="dynamic", key="pain_tbl", width="stretch",
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
