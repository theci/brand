"""처방 페이지 — 상별 표, 배치 크기 실시간 환산, 배치 지시서 다운로드."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from brandlab.batch import batch_sheet, scale
from brandlab.formula_edit import create_formula, delete_formula, formula_path
from brandlab.regimes import available
from brandlab.ui import load_lab, setup_korean_font

st.set_page_config(page_title="처방 · brand-lab", page_icon="🧪", layout="wide")
setup_korean_font()
st.title("처방")

lab = load_lab()
ing_ids = sorted(lab.ingredients.index())
pkg_ids = sorted(lab.packaging.index())

# ---------------------------------------------------------------------------
# 새 처방 생성
# ---------------------------------------------------------------------------
with st.expander("➕ 새 처방 생성"):
    st.caption("원료 표의 percent 합계가 100이어야 저장됩니다. 상(A·B…)별로 원료를 묶으세요.")
    c1, c2, c3 = st.columns(3)
    f_product = c1.text_input("제품명", key="nf_product")
    f_slug = c2.text_input("slug (폴더명, 예: my-cream)", key="nf_slug")
    f_version = c3.number_input("버전", min_value=1, value=1, step=1, key="nf_version")
    c4, c5, c6 = st.columns(3)
    f_regime = c4.selectbox("레짐", available(), key="nf_regime")
    f_ptype = c5.selectbox("제품형태", ["leave_on", "rinse_off"], key="nf_ptype")
    f_status = c6.selectbox("상태", ["개발중", "확정"], key="nf_status")
    c7, c8, c9 = st.columns(3)
    f_batch = c7.number_input("기준 배치(g)", min_value=1.0, value=100.0, step=10.0, key="nf_batch")
    f_category = c8.text_input("품목 카테고리(선택)", key="nf_cat")
    f_notes = c9.text_input("메모(선택)", key="nf_notes")
    c10, c11 = st.columns(2)
    f_fill = c10.text_input("충전 부피 ml(선택)", key="nf_fill")
    f_netw = c11.text_input("내용량 g(선택)", key="nf_netw")

    st.markdown("**원료 (상별)** — 행 추가/삭제 가능")
    ing_df = st.data_editor(
        pd.DataFrame([{"상": "A", "원료 id": None, "percent": 0.0, "공정(선택)": ""}]),
        num_rows="dynamic",
        width="stretch",
        column_config={
            "상": st.column_config.TextColumn("상", help="A/B/C 등 상 이름"),
            "원료 id": st.column_config.SelectboxColumn("원료 id", options=ing_ids),
            "percent": st.column_config.NumberColumn("percent", min_value=0.0, max_value=100.0, step=0.1),
            "공정(선택)": st.column_config.TextColumn("공정(선택)", help="그 상의 제조 공정 메모"),
        },
        key="nf_ing",
    )
    _total = float(pd.to_numeric(ing_df["percent"], errors="coerce").fillna(0).sum())
    (st.success if abs(_total - 100.0) < 0.01 else st.caption)(
        f"현재 percent 합계: {_total:.2f} (100이어야 저장 가능)"
    )

    st.markdown("**포장재 (선택)**")
    pkg_df = st.data_editor(
        pd.DataFrame({"포장재 id": pd.Series(dtype="object"), "개수": pd.Series(dtype="int")}),
        num_rows="dynamic",
        width="stretch",
        column_config={
            "포장재 id": st.column_config.SelectboxColumn("포장재 id", options=pkg_ids),
            "개수": st.column_config.NumberColumn("개수", min_value=1, step=1),
        },
        key="nf_pkg",
    )

    if st.button("처방 생성", type="primary", key="nf_create"):
        try:
            # 상별로 원료를 그룹핑(등장 순서 유지). 공정은 상별 첫 비어있지 않은 값.
            order: list[str] = []
            buckets: dict[str, dict] = {}
            for _, r in ing_df.iterrows():
                name = str(r["상"] or "").strip()
                iid = str(r["원료 id"] or "").strip()
                pct = pd.to_numeric(r["percent"], errors="coerce")
                if not name or not iid or pd.isna(pct):
                    continue
                if name not in buckets:
                    buckets[name] = {"name": name, "ingredients": []}
                    order.append(name)
                buckets[name]["ingredients"].append({"id": iid, "percent": float(pct)})
                proc = str(r.get("공정(선택)", "") or "").strip()
                if proc and "process" not in buckets[name]:
                    buckets[name]["process"] = proc
            phases = []
            for n in order:
                b = buckets[n]
                phase = {"name": b["name"]}
                if "process" in b:
                    phase["process"] = b["process"]
                phase["ingredients"] = b["ingredients"]
                phases.append(phase)

            packaging = []
            for _, r in pkg_df.iterrows():
                pid = str(r["포장재 id"] or "").strip()
                qty = pd.to_numeric(r["개수"], errors="coerce")
                if pid and not pd.isna(qty):
                    packaging.append({"id": pid, "qty_per_unit": int(qty)})

            data: dict = {
                "product": f_product.strip(),
                "slug": f_slug.strip(),
                "version": int(f_version),
                "regime": f_regime,
                "product_type": f_ptype,
                "status": f_status,
                "base_batch_g": float(f_batch),
                "phases": phases,
            }
            if f_category.strip():
                data["product_category"] = f_category.strip()
            if packaging:
                data["packaging"] = packaging
            if f_fill.strip():
                data["fill_volume_ml"] = float(f_fill)
            if f_netw.strip():
                data["net_weight_g"] = float(f_netw)
            if f_notes.strip():
                data["notes"] = f_notes.strip()

            if not phases:
                st.error("원료를 1개 이상 입력하세요.")
            else:
                path = create_formula(
                    data,
                    ingredient_ids=set(ing_ids),
                    packaging_ids=set(pkg_ids),
                )
                st.success(f"생성됨: formulas/{path.parent.name}/{path.name}")
                st.rerun()
        except Exception as exc:  # noqa: BLE001 — 사용자에게 사유 표시
            st.error(f"생성 실패: {exc}")

# ---------------------------------------------------------------------------
# 처방 삭제
# ---------------------------------------------------------------------------
with st.expander("🗑️ 처방 삭제"):
    if not lab.formulas:
        st.info("삭제할 처방이 없습니다.")
    else:
        del_opts = {
            f"{f.slug} v{f.version} — {f.product}": (f.slug, f.version)
            for f in lab.formulas
        }
        del_label = st.selectbox("삭제할 처방", list(del_opts), key="del_f_sel")
        del_slug, del_ver = del_opts[del_label]
        st.caption(
            "처방 파일(formulas/{}/v{}.yaml)이 삭제됩니다. "
            "배치·DOE 기록의 참조는 문자열이라 파일 로딩에는 영향 없습니다.".format(del_slug, del_ver)
        )
        confirm = st.checkbox(f"정말 '{del_slug} v{del_ver}' 를 삭제합니다", key="del_f_confirm")
        if st.button("삭제", type="primary", disabled=not confirm, key="del_f_btn"):
            try:
                delete_formula(formula_path(del_slug, del_ver))
                st.success(f"삭제됨: {del_slug} v{del_ver}")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"삭제 실패: {exc}")

if not lab.formulas:
    st.info("처방이 없습니다. 위 '➕ 새 처방 생성'에서 시작하세요.")
    st.stop()

options = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
label = st.selectbox("처방 선택", list(options))
formula = options[label]

c1, c2, c3 = st.columns(3)
c1.metric("제품 형태", formula.product_type.value)
c2.metric("상태", formula.status.value)
c3.metric("기준 배치", f"{formula.base_batch_g:g} g")

target = st.slider(
    "배치 크기 (g)",
    min_value=10,
    max_value=5000,
    value=int(formula.base_batch_g),
    step=10,
)

result = scale(formula, target, ingredients=lab.ingredients)

for phase in result.phases:
    st.subheader(f"상 {phase.name}")
    if phase.process:
        st.caption(f"공정: {phase.process}")
    rows = [
        {"원료": i.name, "목표 %": i.percent, "목표 g": round(i.grams, 2)}
        for i in phase.ingredients
    ]
    st.table(rows)
    st.caption(f"상 {phase.name} 소계: {phase.subtotal_g:.2f} g")

st.metric("전체 합계", f"{result.total_g:.2f} g", delta=f"목표 {target} g")

for w in result.warnings:
    st.warning(w)

md = batch_sheet(formula, target, ingredients=lab.ingredients)
st.download_button(
    "⬇️ 배치 지시서 (마크다운) 다운로드",
    data=md,
    file_name=f"batch-{formula.slug}-v{formula.version}-{target}g.md",
    mime="text/markdown",
)

with st.expander("배치 지시서 미리보기"):
    st.markdown(md)
