"""배치기록 페이지 — 실측(수율·pH) 기록 요약 + 새 기록지 생성 (batchlog)."""

from __future__ import annotations

from datetime import date

import yaml
import streamlit as st

from brandlab.batchrecord import (
    batch_record_to_yaml_dict,
    batch_summary,
    make_batch_id,
    new_batch_record,
)
from brandlab.loader import EXPERIMENTS_DIR, iter_batch_paths, load_all_batches
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("배치 기록 (batchlog)")
st.caption("실제로 만든 배치의 실측 무게·수율·pH를 처방 버전에 연결해 남긴다.")

lab = load_lab()

tab_summary, tab_new = st.tabs(["기록 요약", "새 기록지 생성"])

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
    st.caption("제조 후 actual_g / yield_g / ph / observations 를 채우세요.")

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
