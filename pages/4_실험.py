"""실험 페이지 — DOE 주효과 플롯, 안정성 현황·밀린 관찰 알림."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from brandlab.core.models import StabilityCondition
from brandlab.doe import (
    doe_analysis,
    interaction_plot,
    interpretation_sentences,
    main_effects_plot,
)
from brandlab.experiment_edit import (
    create_doe,
    create_stability,
    delete_experiment,
    doe_path,
    full_factorial_runs,
    stability_path,
)
from brandlab.loader import iter_doe_paths, iter_stability_paths
from brandlab.stability import stability_due, stability_summary
from brandlab.ui import (
    load_doe_designs,
    load_lab,
    load_stability_samples,
    setup_korean_font,
)

st.set_page_config(page_title="실험 · brand-lab", page_icon="🔬", layout="wide")
setup_korean_font()
st.title("실험")

_FORMULA_REFS = [""] + [f"{f.slug} v{f.version}" for f in load_lab().formulas]

tab_doe, tab_stab = st.tabs(["DOE 분석", "안정성 시험"])

# ---------------------------------------------------------------------------
# DOE
# ---------------------------------------------------------------------------
with tab_doe:
    with st.expander("➕ 새 DOE 설계 생성"):
        st.caption(
            "인자·수준·평가항목을 정하면 2^k 완전요인 런 골격을 자동 생성합니다. "
            "점수(scores)는 빈칸으로 만들어지며, 벤치 실험 후 채웁니다."
        )
        c1, c2, c3 = st.columns(3)
        d_name = c1.text_input("설계 이름", key="nd_name")
        d_ref = c2.selectbox("연결 처방(선택)", _FORMULA_REFS, key="nd_ref")
        d_file = c3.text_input("파일명(.yaml 제외)", key="nd_file")

        st.markdown("**인자·수준** — 2~4개 권장. low/high 값은 표시용(선택)")
        fac_df = st.data_editor(
            pd.DataFrame([{"인자": "", "low": None, "high": None}]),
            num_rows="dynamic",
            width="stretch",
            column_config={
                "인자": st.column_config.TextColumn("인자(영문 키 권장)"),
                "low": st.column_config.NumberColumn("low"),
                "high": st.column_config.NumberColumn("high"),
            },
            key="nd_factors",
        )
        d_items_raw = st.text_input("평가항목 (쉼표로 구분, 예: 발향강도, 지속력)", key="nd_items")

        factors = [str(r["인자"]).strip() for _, r in fac_df.iterrows() if str(r["인자"]).strip()]
        items = [s.strip() for s in d_items_raw.split(",") if s.strip()]
        if factors and items:
            st.caption(f"→ 인자 {len(factors)}개 · 평가항목 {len(items)}개 → 런 **{2**len(factors)}개** 생성 예정")

        if st.button("DOE 생성", type="primary", key="nd_create"):
            try:
                if not d_name.strip() or not d_file.strip():
                    st.error("설계 이름과 파일명을 입력하세요.")
                elif not factors:
                    st.error("인자를 1개 이상 입력하세요.")
                elif not items:
                    st.error("평가항목을 1개 이상 입력하세요.")
                else:
                    levels = {}
                    for _, r in fac_df.iterrows():
                        name = str(r["인자"]).strip()
                        lo = pd.to_numeric(r["low"], errors="coerce")
                        hi = pd.to_numeric(r["high"], errors="coerce")
                        if name and not pd.isna(lo) and not pd.isna(hi):
                            levels[name] = {"low": float(lo), "high": float(hi)}
                    data: dict = {"name": d_name.strip()}
                    if d_ref:
                        data["formula_ref"] = d_ref
                    data["factors"] = factors
                    if levels:
                        data["levels"] = levels
                    data["response_items"] = items
                    data["runs"] = full_factorial_runs(factors, items)
                    path = create_doe(data, path=doe_path(d_file.strip()))
                    st.success(f"생성됨: experiments/doe/{path.name}")
                    st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"생성 실패: {exc}")

    doe_paths = iter_doe_paths()
    if doe_paths:
        with st.expander("🗑️ DOE 파일 삭제"):
            dl = {p.name: p for p in doe_paths}
            dsel = st.selectbox("삭제할 DOE 파일", list(dl), key="dd_sel")
            if st.checkbox(f"정말 '{dsel}' 삭제", key="dd_confirm") and st.button(
                "삭제", type="primary", key="dd_btn"
            ):
                try:
                    delete_experiment(dl[dsel])
                    st.success(f"삭제됨: {dsel}")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"삭제 실패: {exc}")

    designs = load_doe_designs()
    if not designs:
        st.info("experiments/doe/*.yaml 이 없습니다. 위 '➕ 새 DOE 설계 생성'에서 시작하세요.")
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
    with st.expander("➕ 새 안정성 시료 등록"):
        st.caption(
            "시료ID·조건·시작일만 넣으면 관찰 예정일(1/2/4/8주)은 자동 계산됩니다. "
            "관찰 기록은 이후 YAML에 채웁니다."
        )
        c1, c2 = st.columns(2)
        s_id = c1.text_input("시료 ID (예: RD-001)", key="ns_id")
        s_ref = c2.selectbox("연결 처방(선택)", _FORMULA_REFS, key="ns_ref")
        c3, c4, c5 = st.columns(3)
        s_cond = c3.selectbox("조건", [c.value for c in StabilityCondition], key="ns_cond")
        s_start = c4.date_input("시작일", value=date.today(), key="ns_start")
        s_file = c5.text_input("파일명(.yaml 제외)", key="ns_file")
        if st.button("안정성 시료 등록", type="primary", key="ns_create"):
            try:
                if not s_id.strip() or not s_file.strip():
                    st.error("시료 ID와 파일명을 입력하세요.")
                else:
                    data: dict = {"sample_id": s_id.strip()}
                    if s_ref:
                        data["formula_ref"] = s_ref
                    data["condition"] = s_cond
                    data["start_date"] = s_start
                    path = create_stability(data, path=stability_path(s_file.strip()))
                    st.success(f"등록됨: experiments/stability/{path.name}")
                    st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"등록 실패: {exc}")

    stab_paths = iter_stability_paths()
    if stab_paths:
        with st.expander("🗑️ 안정성 파일 삭제"):
            sl = {p.name: p for p in stab_paths}
            ssel = st.selectbox("삭제할 안정성 파일", list(sl), key="sd_sel")
            if st.checkbox(f"정말 '{ssel}' 삭제", key="sd_confirm") and st.button(
                "삭제", type="primary", key="sd_btn"
            ):
                try:
                    delete_experiment(sl[ssel])
                    st.success(f"삭제됨: {ssel}")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"삭제 실패: {exc}")

    samples = load_stability_samples()
    if not samples:
        st.info("experiments/stability/*.yaml 이 없습니다. 위 '➕ 새 안정성 시료 등록'에서 시작하세요.")
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
