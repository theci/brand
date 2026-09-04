"""배치기록 페이지 — 실측(수율·pH) 기록 요약 + 새 기록지 생성 (batchlog)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import yaml
import streamlit as st

from brandlab.batchrecord import (
    batch_record_to_yaml_dict,
    batch_summary,
    make_batch_id,
    new_batch_record,
)
from brandlab.experiment_edit import set_batch_actuals
from brandlab.loader import EXPERIMENTS_DIR, iter_batch_paths, load_all_batches, load_batch
from brandlab.ui import load_lab, setup_korean_font


def _s(x) -> str:
    return "" if x is None else str(x)


def _numf(s: str) -> float | None:
    s = (s or "").strip()
    return None if s == "" else float(s)


setup_korean_font()
st.title("배치 기록 (batchlog)")
st.caption("실제로 만든 배치의 실측 무게·수율·pH를 처방 버전에 연결해 남긴다.")
st.info(
    "표기: 🔒 **자동**(처방을 고르면 기록지가 자동 생성) · ✍️ **직접 입력**(제조 후 "
    "**[실측 입력]** 탭에서 수율·pH·관찰·원료별 실측을 화면에서 기입). 파일을 열 필요 없습니다."
)

lab = load_lab()

tab_summary, tab_actual, tab_new = st.tabs(["기록 요약", "✏️ 실측 입력", "새 기록지 생성"])

with tab_summary:
    rows = batch_summary(load_all_batches())
    if not rows:
        st.info("배치 기록이 없습니다. '새 기록지 생성' 탭에서 시작하세요.")
    else:
        st.table(
            [
                {
                    "배치ID": r.batch_id,
                    "처방": r.formula_ref,
                    "일자": r.date.isoformat(),
                    "목표g": r.target_g,
                    "회수g": f"{r.yield_g:g}" if r.yield_g is not None else "―",
                    "수율": f"{r.yield_percent:g}%" if r.yield_percent is not None else "―",
                    "pH": ("―" if r.ph is None else (f"✅ {r.ph:g}" if r.ph_ok else f"⚠ {r.ph:g}")),
                }
                for r in rows
            ]
        )
        st.caption("pH 기준: 피부 도포 제품 4.5~6.0 (✅ 정상 / ⚠ 범위 밖)")

with tab_actual:
    st.caption("제조가 끝난 배치를 골라 실측값을 **화면에서 바로** 입력합니다(.bak 백업·검증 실패 시 롤백).")
    paths = iter_batch_paths()
    if not paths:
        st.info("저장된 배치 기록이 없습니다. '새 기록지 생성'에서 먼저 만드세요.")
    else:
        pmap = {p.name: p for p in paths}
        fsel = st.selectbox("배치 파일", list(pmap), key="ba_sel")
        rec = load_batch(pmap[fsel])
        st.caption(
            f"처방 {rec.formula_ref} · 목표 {rec.target_g:g}g · 제조일 {rec.date.isoformat()}"
        )

        c1, c2, c3 = st.columns(3)
        y = c1.text_input("✍️ 수율 yield_g", value=_s(rec.yield_g), key=f"ba_y_{fsel}", placeholder="예: 92.5")
        ph_s = c2.text_input("✍️ pH", value=_s(rec.ph), key=f"ba_ph_{fsel}", placeholder="예: 5.2")
        op = c3.text_input("✍️ 작업자(선택)", value=rec.operator or "", key=f"ba_op_{fsel}", placeholder="예: 박수민")
        obs = st.text_area(
            "✍️ 관찰 메모 observations", value=rec.observations or "", key=f"ba_obs_{fsel}",
            placeholder="예: 냉각 후 약간 묽음",
        )

        edited = None
        if rec.lines:
            st.markdown("**원료별 실측 (선택)** — 목표 g는 고정, ✍️ 실측 g만 채우세요")
            edited = st.data_editor(
                pd.DataFrame(
                    [{"원료": ln.id, "목표 g": round(ln.target_g, 2), "실측 g": ln.actual_g}
                     for ln in rec.lines]
                ),
                num_rows="fixed",
                width="stretch",
                disabled=["원료", "목표 g"],
                column_config={
                    "실측 g": st.column_config.NumberColumn("✍️ 실측 g", min_value=0.0, step=0.1),
                },
                key=f"ba_lines_{fsel}",
            )

        if st.button("💾 실측 저장", type="primary", key=f"ba_save_{fsel}"):
            try:
                actuals: dict[str, float | None] = {}
                if edited is not None:
                    for _, r in edited.iterrows():
                        v = pd.to_numeric(r["실측 g"], errors="coerce")
                        actuals[str(r["원료"])] = None if pd.isna(v) else float(v)
                set_batch_actuals(
                    pmap[fsel],
                    yield_g=_numf(y), ph=_numf(ph_s),
                    observations=obs, operator=op,
                    actuals_by_id=actuals,
                )
                st.success("실측 저장됨 (.bak 백업). '기록 요약'에서 수율·pH를 확인하세요.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"저장 실패: {exc}")

with tab_new:
    if not lab.formulas:
        st.info("처방이 없습니다.")
        st.stop()
    options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
    formula = options[st.selectbox("처방 선택", list(options))]
    grams = st.number_input("목표 배치 크기(g)", min_value=1.0, value=100.0, step=10.0)

    today = date.today()
    existing = [p.name for p in iter_batch_paths()]
    prefix = make_batch_id(formula.slug, today, 0).rsplit("-", 1)[0]
    seq = sum(1 for n in existing if n.startswith(prefix)) + 1
    batch_id = make_batch_id(formula.slug, today, seq)

    record = new_batch_record(
        formula, float(grams), ingredients=lab.ingredients, batch_id=batch_id, on_date=today
    )
    yaml_text = yaml.safe_dump(
        batch_record_to_yaml_dict(record), allow_unicode=True, sort_keys=False
    )

    st.write(f"생성될 배치 ID: **{batch_id}**")
    st.code(yaml_text, language="yaml")
    st.caption(
        "저장한 뒤, 제조가 끝나면 **[✏️ 실측 입력]** 탭에서 수율·pH·관찰을 화면으로 채우세요 "
        "(파일을 직접 열 필요 없음)."
    )

    col1, col2 = st.columns(2)
    col1.download_button("YAML 내려받기", yaml_text, file_name=f"{batch_id}.yaml")
    if col2.button("experiments/batches/ 에 저장"):
        out_dir = EXPERIMENTS_DIR / "batches"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{batch_id}.yaml"
        if out_path.exists():
            st.error(f"이미 존재합니다: {out_path.name}")
        else:
            out_path.write_text(yaml_text, encoding="utf-8")
            st.success(f"저장됨: {out_path}")
