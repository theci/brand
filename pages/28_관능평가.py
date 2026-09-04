"""시제품 관능·패널 평가 (STEP 5) — 시제품을 다수(타깃)에게 나눠 정량 피드백.

본생산(MOQ) 직전 수용도 게이트. 항목별 평균·약점을 보고 다음 버전에 반영하고,
강한 항목은 근거 카드로 승격한다. 점수는 주관적·소표본 → 내부 참고용(효능 표방 아님).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from brandlab.experiment_edit import (
    create_panel,
    delete_experiment,
    panel_path,
    set_panel_responses,
)
from brandlab.loader import iter_panel_paths, load_panel
from brandlab.panel import compare, improvement_hints, panel_to_evidence, summarize
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("시제품 관능·패널 평가 🧪")
st.caption(
    "확정 후보 시제품을 타깃/비타깃에게 나눠주고 5점 척도로 수용도를 받습니다. "
    "본생산 전 방향을 확정하는 게이트 — 점수는 주관적·소표본이라 내부 참고용입니다."
)
st.info(
    "표기: 🔒 **자동**(요약·비교·근거는 응답에서 자동 계산) · ✍️ **직접 입력**(평가 ID·항목·"
    "응답 점수). 칸 안 흐린 예시를 참고하세요."
)

_FORMULA_REFS = [""] + [f"{f.slug} v{f.version}" for f in load_lab().formulas]
_SEG_OPTS = ["타깃", "비타깃"]
_PRESET_ATTRS = ["촉촉함", "산뜻함_비끈적", "향", "발림성", "재구매의사"]

tab_new, tab_input, tab_report = st.tabs(["➕ 새 평가", "✏️ 응답 입력", "📊 요약·비교·근거"])

# ---------------------------------------------------------------------------
# 새 평가 생성
# ---------------------------------------------------------------------------
with tab_new:
    st.caption("평가 항목·척도·목표선을 정해 골격을 만듭니다. 응답은 '응답 입력' 탭에서 채웁니다.")
    c1, c2, c3 = st.columns(3)
    n_id = c1.text_input("✍️ 평가 ID", key="np_id", placeholder="예: daily-lotion-v2-panel1")
    n_ref = c2.selectbox("🔒 시제품(연결 처방)", _FORMULA_REFS, key="np_ref")
    n_file = c3.text_input("✍️ 파일명(.yaml 제외)", key="np_file", placeholder="예: daily-lotion-v2-panel1")
    c4, c5, c6 = st.columns(3)
    n_label = c4.text_input("✍️ 시료 코드(로트/배치, 선택)", key="np_label", placeholder="예: LOT-2026-03-A")
    n_date = c5.date_input("평가일", value=date.today(), key="np_date")
    n_scale = c6.number_input("척도 상한", min_value=2, max_value=10, value=5, step=1, key="np_scale")

    n_attrs = st.multiselect("평가 항목", _PRESET_ATTRS, default=_PRESET_ATTRS, key="np_attrs")
    n_extra = st.text_input("항목 추가(쉼표, 선택)", key="np_extra")
    attrs = list(n_attrs) + [s.strip() for s in n_extra.split(",") if s.strip()]

    st.markdown("**목표선(targets)** — 항목별 목표 평균(미달이면 약점). 비우면 목표 없음.")
    tgt_df = st.data_editor(
        pd.DataFrame([{"항목": a, "목표": None} for a in attrs]) if attrs
        else pd.DataFrame(columns=["항목", "목표"]),
        num_rows="fixed",
        width="stretch",
        disabled=["항목"],
        column_config={
            "목표": st.column_config.NumberColumn("목표", min_value=0.0, max_value=float(n_scale), step=0.5)
        },
        key="np_targets",
    )

    if st.button("평가 생성", type="primary", key="np_create"):
        try:
            if not n_id.strip() or not n_file.strip():
                st.error("평가 ID와 파일명을 입력하세요.")
            elif not attrs:
                st.error("평가 항목을 1개 이상 선택하세요.")
            else:
                targets = {}
                for _, r in tgt_df.iterrows():
                    v = pd.to_numeric(r["목표"], errors="coerce")
                    if not pd.isna(v):
                        targets[str(r["항목"])] = float(v)
                data: dict = {"test_id": n_id.strip(), "scale_max": int(n_scale), "attributes": attrs}
                if n_ref:
                    data["formula_ref"] = n_ref
                if n_label.strip():
                    data["sample_label"] = n_label.strip()
                data["test_date"] = n_date
                if targets:
                    data["targets"] = targets
                path = create_panel(data, path=panel_path(n_file.strip()))
                st.success(f"생성됨: experiments/panel/{path.name}")
                st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"생성 실패: {exc}")

    paths = iter_panel_paths()
    if paths:
        with st.expander("🗑️ 평가 파일 삭제"):
            pl = {p.name: p for p in paths}
            psel = st.selectbox("삭제할 파일", list(pl), key="pd_sel")
            if st.checkbox(f"정말 '{psel}' 삭제", key="pd_confirm") and st.button(
                "삭제", type="primary", key="pd_btn"
            ):
                try:
                    delete_experiment(pl[psel])
                    st.success(f"삭제됨: {psel}")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"삭제 실패: {exc}")

# ---------------------------------------------------------------------------
# 응답 입력
# ---------------------------------------------------------------------------
with tab_input:
    paths = iter_panel_paths()
    if not paths:
        st.info("experiments/panel/*.yaml 이 없습니다. '➕ 새 평가'에서 시작하세요.")
    else:
        pmap = {p.name: p for p in paths}
        fsel = st.selectbox("평가 파일", list(pmap), key="pi_sel")
        test = load_panel(pmap[fsel])
        st.caption(f"시제품: {test.formula_ref or '(미지정)'} · 척도 {test.scale_max}점 · 항목 {len(test.attributes)}개")

        rows = []
        for r in test.responses:
            row = {"panelist": r.panelist, "segment": r.segment}
            for a in test.attributes:
                row[a] = r.scores.get(a)
            row["comment"] = r.comment
            rows.append(row)
        _cols = ["panelist", "segment", *test.attributes, "comment"]
        colcfg = {
            "panelist": st.column_config.TextColumn("평가자"),
            "segment": st.column_config.SelectboxColumn("세그먼트", options=_SEG_OPTS, required=False),
            "comment": st.column_config.TextColumn("코멘트"),
        }
        for a in test.attributes:
            colcfg[a] = st.column_config.NumberColumn(
                a, min_value=0.0, max_value=float(test.scale_max), step=1.0
            )
        edited = st.data_editor(
            pd.DataFrame(rows) if rows else pd.DataFrame(columns=_cols),
            num_rows="dynamic",
            width="stretch",
            column_config=colcfg,
            key=f"pi_edit_{fsel}",
        )
        if st.button("응답 저장", type="primary", key=f"pi_save_{fsel}"):
            try:
                responses = []
                for _, r in edited.iterrows():
                    name = str(r.get("panelist") or "").strip()
                    if not name:
                        continue
                    scores = {}
                    for a in test.attributes:
                        v = pd.to_numeric(r.get(a), errors="coerce")
                        scores[a] = None if pd.isna(v) else float(v)
                    seg = r.get("segment")
                    seg = None if (seg is None or (isinstance(seg, float) and pd.isna(seg))) else str(seg)
                    cmt = r.get("comment")
                    cmt = "" if (cmt is None or (isinstance(cmt, float) and pd.isna(cmt))) else str(cmt)
                    responses.append({"panelist": name, "segment": seg, "scores": scores, "comment": cmt})
                set_panel_responses(pmap[fsel], responses)
                st.success("응답 저장됨 (.bak 백업)")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"저장 실패: {exc}")

# ---------------------------------------------------------------------------
# 요약·비교·근거
# ---------------------------------------------------------------------------
with tab_report:
    paths = iter_panel_paths()
    if not paths:
        st.info("먼저 평가를 만들고 응답을 입력하세요.")
    else:
        pmap = {p.name: p for p in paths}
        rsel = st.selectbox("평가 파일", list(pmap), key="pr_sel")
        test = load_panel(pmap[rsel])
        seg_label = st.radio("세그먼트", ["전체", *_SEG_OPTS], horizontal=True, key="pr_seg")
        seg = None if seg_label == "전체" else seg_label
        summ = summarize(test, segment=seg)

        m1, m2 = st.columns(2)
        m1.metric("응답 수", f"{summ.n_panelists}명")
        m2.metric("종합 평균", "—" if summ.overall_mean is None else f"{summ.overall_mean:.2f}/{test.scale_max}")

        st.subheader("항목별 결과")
        st.table([
            {
                "항목": s.attribute,
                "평균": "—" if s.mean is None else f"{s.mean:.2f}",
                "상위2박스": "—" if s.top_box is None else f"{s.top_box*100:.0f}%",
                "n": s.n,
                "목표": "—" if s.target is None else f"{s.target:.1f}",
                "충족": {True: "✅", False: "⚠️", None: "·"}[s.meets],
            }
            for s in summ.stats
        ])

        if summ.weak:
            st.warning("약점(목표 미달): " + ", ".join(summ.weak))
            st.markdown("**다음 버전 개선 힌트**")
            for h in improvement_hints(summ):
                st.markdown(f"- {h}")
        else:
            st.success("설정한 목표선을 모두 충족했습니다.")

        # 버전 비교 (같은 slug의 다른 파일과)
        with st.expander("🔀 버전 비교 (여러 평가 선택)"):
            others = st.multiselect(
                "비교할 평가 파일(2개 이상)", list(pmap),
                default=[rsel], key="pr_cmp",
            )
            if len(others) >= 2:
                comp = compare([load_panel(pmap[o]) for o in others], segment=seg)
                st.table([
                    {
                        "항목": row.attribute,
                        **{lbl: ("—" if row.means[lbl] is None else f"{row.means[lbl]:.2f}") for lbl in comp.labels},
                        "승자": row.winner or "동점",
                    }
                    for row in comp.rows
                ])
                ow = comp.overall_winner
                st.markdown(f"**종합 승자:** {ow or '동점/판정 불가'}")
            else:
                st.caption("2개 이상 선택하면 항목별 승자를 비교합니다.")

        # 근거 승격
        with st.expander("⭐ 근거 카드로 승격 (브랜드 코어 ⑤로)"):
            cc1, cc2, cc3 = st.columns(3)
            min_mean = cc1.number_input("최소 평균", min_value=0.0, max_value=float(test.scale_max),
                                        value=4.0, step=0.5, key="pr_mm")
            min_n = cc2.number_input("최소 표본 n", min_value=1, value=3, step=1, key="pr_mn")
            incent = cc3.checkbox("대가성(체험단)", key="pr_inc")
            cards = panel_to_evidence(
                test, min_mean=float(min_mean), min_n=int(min_n), segment=seg, incentivized=incent
            )
            if not cards:
                st.caption("조건을 만족하는 강한 항목이 없습니다(임계값을 낮추거나 응답을 더 모으세요).")
            else:
                picked = st.multiselect(
                    "승격할 근거 선택", [c.text for c in cards], default=[c.text for c in cards], key="pr_pick"
                )
                if picked:
                    st.caption("아래 텍스트를 복사해 **브랜드 코어 ⑤ 근거**에 붙여넣으세요.")
                    st.code("\n".join(picked))
            st.caption(
                "⚠️ 관능 결과를 마케팅에 쓸 때는 표본·방법을 함께 표기하고 문구검사(STEP 6)를 통과시키세요. "
                "대가성 체험단이면 뒷광고 표기가 필요합니다."
            )
