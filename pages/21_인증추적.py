"""인증·시험 추적 페이지(STEP 11 · 출시 준비).

레짐별 필수 관문 체크리스트에 제품별 진행 상태를 얹어, '팔기 위해 뭘 언제까지'를 추적한다.
기한 지난 미완료 관문은 홈 대시보드 '밀린 인증'으로 올라간다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from brandlab.certification import (
    gates_with_status,
    progress,
    replace_product_entries,
    save_cert_status,
)
from brandlab.core.models import CertStatusEntry
from brandlab.loader import load_cert_checklist, load_cert_status
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("인증·시험 추적 ✅ (출시 준비)")
st.caption(
    "실제로 팔기 위한 관문(등록·시험·표시·생산)을 추적합니다. 상품등록 전에 완료하세요. "
    "⚠️ 관문·비용·기한은 예시 — 식약처·환경부 등 공식 기준으로 반드시 확인."
)

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
formula = options[st.selectbox("제품 선택", list(options))]
pref = f"{formula.slug} v{formula.version}"

checklist = load_cert_checklist(formula.regime)
if checklist is None:
    st.warning(f"'{formula.regime}' 레짐의 관문 체크리스트가 없습니다(data/regulatory/{formula.regime}/checklist.yaml).")
    st.stop()

status = load_cert_status()
done, total = progress(pref, checklist, status)
st.progress(done / total if total else 0.0, text=f"완료 {done} / {total} 관문")

rows = gates_with_status(pref, checklist, status)
df = pd.DataFrame([
    {
        "관문": r.gate.title,
        "분류": r.gate.category,
        "안내": r.gate.note or "",
        "상태": (r.entry.status.value if r.entry else "대기"),
        "기한": (r.entry.due_date if r.entry else None),
        "비용": (r.entry.cost if r.entry else None),
        "담당": (r.entry.owner if r.entry else ""),
        "메모": (r.entry.note if r.entry else ""),
    }
    for r in rows
])
edited = st.data_editor(
    df,
    num_rows="fixed",
    width="stretch",
    disabled=["관문", "분류", "안내"],
    column_config={
        "상태": st.column_config.SelectboxColumn("상태", options=["대기", "진행", "완료"]),
        "기한": st.column_config.DateColumn("기한"),
        "비용": st.column_config.NumberColumn("비용(원)", min_value=0, step=10000),
    },
    key=f"cert_{pref}",
)

if st.button("💾 진행 상태 저장", type="primary"):
    try:
        entries = []
        for i, (_, r) in enumerate(edited.iterrows()):
            gate = checklist.gates[i]
            due = r["기한"]
            if due is not None and not (isinstance(due, float) and pd.isna(due)):
                due = due.date() if hasattr(due, "date") else due
            else:
                due = None
            cost = r["비용"]
            cost = None if pd.isna(cost) else int(cost)
            entries.append(CertStatusEntry(
                product_ref=pref, gate_key=gate.key, status=str(r["상태"]),
                due_date=due, cost=cost,
                owner=(str(r["담당"]).strip() or None),
                note=(str(r["메모"]).strip() or None),
            ))
        new = replace_product_entries(status, pref, entries)
        path = save_cert_status(new)
        st.success(f"저장됨: {path}")
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장 실패: {exc}")

st.caption("기한을 넣으면 홈 대시보드가 '밀린 인증'으로 알려줍니다. (통과=합법 아님, 최종은 관할기관 확인)")
