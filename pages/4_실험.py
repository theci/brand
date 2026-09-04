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
from brandlab.doe_optimize import recommend
from brandlab.experiment_edit import (
    create_doe,
    create_stability,
    delete_experiment,
    doe_path,
    full_factorial_runs,
    set_doe_scores,
    set_stability_observations,
    stability_path,
)
from brandlab.loader import (
    iter_doe_paths,
    iter_stability_paths,
    load_stability,
)
from brandlab.stability import stability_due, stability_summary
from brandlab.ui import (
    load_doe_designs,
    load_lab,
    load_stability_samples,
    setup_korean_font,
)

setup_korean_font()
st.title("실험")
st.info(
    "표기: 🔒 **자동**(런 골격·관찰 예정일이 자동 생성) · ✍️ **직접 입력**(설계 이름·평가항목·"
    "시료 ID 등). 점수·관찰값은 생성 후 표에서 채웁니다."
)

_FORMULA_REFS = [""] + [f"{f.slug} v{f.version}" for f in load_lab().formulas]


def _cell(v):
    """표 셀 값을 문자열 또는 None으로 정리(빈칸/NaN → None)."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    return s or None


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
        d_name = c1.text_input("✍️ 설계 이름", key="nd_name", placeholder="예: 로션 점도 최적화")
        d_ref = c2.selectbox("🔒 연결 처방(선택)", _FORMULA_REFS, key="nd_ref")
        d_file = c3.text_input("✍️ 파일명(.yaml 제외)", key="nd_file", placeholder="예: lotion-viscosity-doe")

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
        d_items_raw = st.text_input(
            "✍️ 평가항목 (쉼표로 구분)", key="nd_items", placeholder="예: 점도, 발림성, 촉촉함"
        )

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

        with st.expander("✏️ 점수 입력/수정"):
            st.caption("factor_values(회색)는 읽기전용. 각 평가항목 점수를 입력하고 저장하세요.")
            _rows = []
            for run in design.runs:
                row = {"run_id": run.run_id}
                for fac in design.factors:
                    row[fac] = str(run.factor_values.get(fac, ""))
                for item in design.response_items:
                    row[item] = run.scores.get(item)
                _rows.append(row)
            _edited = st.data_editor(
                pd.DataFrame(_rows),
                num_rows="fixed",
                width="stretch",
                disabled=["run_id"] + design.factors,
                column_config={
                    item: st.column_config.NumberColumn(item, min_value=0.0, step=1.0)
                    for item in design.response_items
                },
                key=f"doe_scores_{fname}",
            )
            _dpath = {p.name: p for p in iter_doe_paths()}.get(fname)
            if st.button("점수 저장", type="primary", key=f"doe_scores_save_{fname}"):
                try:
                    new_scores = {}
                    for _, r in _edited.iterrows():
                        sc = {}
                        for item in design.response_items:
                            v = pd.to_numeric(r[item], errors="coerce")
                            sc[item] = None if pd.isna(v) else float(v)
                        new_scores[r["run_id"]] = sc
                    set_doe_scores(_dpath, new_scores)
                    st.success("점수 저장됨 (.bak 백업)")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"저장 실패: {exc}")

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

        st.subheader("🎯 추천 조합 (최적화)")
        st.caption(
            "각 평가항목의 목표(최대/최소)와 가중치를 정하면, desirability로 최고 관측 런을 고르고 "
            "주효과로 다음에 시도할 조합을 추천합니다. (관능 점수 기반 — 참고용)"
        )
        _goal_df = st.data_editor(
            pd.DataFrame([
                {
                    "평가항목": it,
                    "목표": ("min" if any(k in it for k in ("끈적", "산패", "위험", "자극")) else "max"),
                    "가중치": 1.0,
                }
                for it in design.response_items
            ]),
            num_rows="fixed",
            width="stretch",
            disabled=["평가항목"],
            column_config={
                "목표": st.column_config.SelectboxColumn("목표", options=["max", "min"]),
                "가중치": st.column_config.NumberColumn("가중치", min_value=0.0, step=0.5),
            },
            key=f"doe_goals_{fname}",
        )
        _goals = {r["평가항목"]: r["목표"] for _, r in _goal_df.iterrows()}
        _weights = {r["평가항목"]: float(r["가중치"]) for _, r in _goal_df.iterrows()}
        _rec = recommend(design, _goals, _weights)
        for w in _rec.warnings:
            st.caption("· " + w)

        st.markdown("**추천 최적 조합** (다음 실험 후보)")
        _opt_rows = []
        for c in _rec.factor_choices:
            val = ""
            if design.levels and c.factor in design.levels and c.level in ("low", "high"):
                lv = design.levels[c.factor].get(c.level)
                val = f"{lv:g}" if isinstance(lv, (int, float)) else ""
            _opt_rows.append(
                {"인자": c.factor, "추천 수준": c.level, "수준값": val, "영향도": c.influence}
            )
        st.table(_opt_rows)
        st.caption("무관 = 상충(가중치로 조정)/영향 미미. 영향도 +면 high·−면 low 유리.")

        if _rec.best_run is not None:
            _fv = ", ".join(f"{k}={v}" for k, v in _rec.best_run.factor_values.items())
            st.markdown(
                f"**최고 관측 런**: #{_rec.best_run.run_id} "
                f"(desirability {_rec.best_run.desirability}) — {_fv}"
            )
        with st.expander("런 랭킹 (desirability)"):
            st.table([
                {"순위": i + 1, "run_id": r.run_id, "desirability": r.desirability,
                 **{k: v for k, v in r.factor_values.items()}}
                for i, r in enumerate(_rec.ranked)
                if r.desirability is not None
            ])

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
        s_id = c1.text_input("✍️ 시료 ID", key="ns_id", placeholder="예: DL-001")
        s_ref = c2.selectbox("🔒 연결 처방(선택)", _FORMULA_REFS, key="ns_ref")
        c3, c4, c5 = st.columns(3)
        s_cond = c3.selectbox("조건", [c.value for c in StabilityCondition], key="ns_cond")
        s_start = c4.date_input("시작일", value=date.today(), key="ns_start")
        s_file = c5.text_input("✍️ 파일명(.yaml 제외)", key="ns_file", placeholder="예: daily-lotion-stability")
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
        _OBS_COLS = ["date", "외관", "분리", "색", "냄새", "경도", "판정", "비고"]
        with st.expander("✏️ 관찰 기록 입력/수정"):
            st.caption("행을 추가해 관찰을 기록하세요. date는 필수(관찰 예정: 시작일 기준 1/2/4/8주).")
            _spaths = {p.name: p for p in iter_stability_paths()}
            _osel = st.selectbox("시료 파일", list(_spaths), key="obs_sel")
            _osample = load_stability(_spaths[_osel])
            _orows = [
                {"date": o.date, "외관": o.외관, "분리": o.분리, "색": o.색,
                 "냄새": o.냄새, "경도": o.경도, "판정": o.판정, "비고": o.비고}
                for o in _osample.observations
            ]
            _oedit = st.data_editor(
                pd.DataFrame(_orows) if _orows else pd.DataFrame(columns=_OBS_COLS),
                num_rows="dynamic",
                width="stretch",
                column_config={"date": st.column_config.DateColumn("date")},
                key=f"obs_edit_{_osel}",
            )
            if st.button("관찰 저장", type="primary", key=f"obs_save_{_osel}"):
                try:
                    obs = []
                    for _, r in _oedit.iterrows():
                        d = r["date"]
                        if d is None or (isinstance(d, float) and pd.isna(d)):
                            continue
                        try:
                            if pd.isna(d):
                                continue
                        except (TypeError, ValueError):
                            pass
                        d = d.date() if hasattr(d, "date") else d
                        obs.append({
                            "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                            "외관": _cell(r.get("외관")), "분리": _cell(r.get("분리")),
                            "색": _cell(r.get("색")), "냄새": _cell(r.get("냄새")),
                            "경도": _cell(r.get("경도")), "판정": _cell(r.get("판정")),
                            "비고": _cell(r.get("비고")),
                        })
                    set_stability_observations(_spaths[_osel], obs)
                    st.success("관찰 저장됨 (.bak 백업)")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"저장 실패: {exc}")

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
