"""실험 페이지 — DOE 주효과 플롯, 안정성 현황·밀린 관찰 알림."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

from brandlab.doe import (
    doe_analysis,
    interaction_plot,
    interpretation_sentences,
    main_effects_plot,
)
from brandlab.stability import stability_due, stability_summary
from brandlab.ui import (
    load_doe_designs,
    load_stability_samples,
    setup_korean_font,
)

st.set_page_config(page_title="실험 · brand-lab", page_icon="🔬", layout="wide")
setup_korean_font()
st.title("실험")

tab_doe, tab_stab = st.tabs(["DOE 분석", "안정성 시험"])

# ---------------------------------------------------------------------------
# DOE
# ---------------------------------------------------------------------------
with tab_doe:
    designs = load_doe_designs()
    if not designs:
        st.info("experiments/doe/*.yaml 이 없습니다.")
    else:
        fname = st.selectbox("DOE 파일", list(designs))
        design = designs[fname]
        analysis = doe_analysis(design)

        for w in analysis.warnings:
            st.warning(w)

        st.subheader("주효과")
        rows = []
        for factor in analysis.factors:
            row = {"인자": factor}
            for item in analysis.response_items:
                eff = analysis.main_effects[factor][item]
                row[item] = "—" if eff is None else round(eff, 2)
            rows.append(row)
        st.table(rows)

        st.subheader("해석")
        for s in interpretation_sentences(analysis):
            st.markdown(f"- {s}")

        # 플롯: 기존 함수가 PNG로 저장하므로 임시파일에 저장 후 표시
        tmp = Path(tempfile.mkdtemp())
        main_png = main_effects_plot(analysis, tmp / "main.png")
        inter_png = interaction_plot(analysis, tmp / "inter.png")
        col1, col2 = st.columns(2)
        col1.image(str(main_png), caption="주효과 플롯")
        col2.image(str(inter_png), caption="교호작용 플롯")

# ---------------------------------------------------------------------------
# 안정성
# ---------------------------------------------------------------------------
with tab_stab:
    samples = load_stability_samples()
    if not samples:
        st.info("experiments/stability/*.yaml 이 없습니다.")
    else:
        today = date.today()
        due = stability_due(samples, today=today)

        st.subheader("⏰ 밀린 관찰")
        if not due:
            st.success("밀린 관찰이 없습니다.")
        else:
            st.error(f"밀린 관찰 {len(due)}건 — 관찰일을 놓치면 그 시점 데이터가 사라집니다.")
            st.table(
                [
                    {
                        "시료": d.sample_id,
                        "조건": d.condition,
                        "주차": f"{d.week}주",
                        "예정일": d.due_date.isoformat(),
                        "지연(일)": d.days_overdue,
                    }
                    for d in due
                ]
            )

        st.subheader("조건별 현황")
        mark = {"done": "✓", "overdue": "✗", "upcoming": "·"}
        summary = stability_summary(samples)
        for condition, timelines in summary.items():
            st.markdown(f"**조건: {condition}**")
            rows = []
            for tl in timelines:
                row = {"시료": tl.sample_id}
                for cs in tl.checkpoints:
                    cell = mark.get(cs.status, "?")
                    if cs.status == "overdue":
                        cell += f" ({cs.days_overdue}d)"
                    row[f"{cs.week}주"] = cell
                rows.append(row)
            st.table(rows)
