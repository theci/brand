"""처방 페이지 — 상별 표, 배치 크기 실시간 환산, 배치 지시서 다운로드."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from brandlab.batch import batch_sheet, scale
from brandlab.formula_edit import (
    create_formula,
    delete_formula,
    formula_path,
    next_version,
    update_formula,
)
from brandlab.regimes import available
from brandlab.templates import TEMPLATES, instantiate, list_templates
from brandlab.ui import load_lab, setup_korean_font

setup_korean_font()
st.title("처방")
st.info(
    "표기: 🔒 **자동/불러오기**(템플릿·수정 시 기존 값이 채워짐) · ✍️ **직접 입력**. "
    "초보라면 **🧩 템플릿에서 시작**을 추천 — 골격이 채워진 뒤 사전점검·수정으로 다듬으면 됩니다."
)

lab = load_lab()
ing_ids = sorted(lab.ingredients.index())
pkg_ids = sorted(lab.packaging.index())
_PTYPES = ["leave_on", "rinse_off"]
_STATUSES = ["개발중", "확정"]


def _phases_from_editor(df) -> list[dict]:
    """원료 편집표(상/원료 id/percent/공정)를 상별로 그룹핑한 phases 리스트로 변환."""
    order: list[str] = []
    buckets: dict[str, dict] = {}
    for _, r in df.iterrows():
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
    return phases


def _packaging_from_editor(df) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        pid = str(r["포장재 id"] or "").strip()
        qty = pd.to_numeric(r["개수"], errors="coerce")
        if pid and not pd.isna(qty):
            out.append({"id": pid, "qty_per_unit": int(qty)})
    return out


def _assemble(
    *, product, slug, version, regime, ptype, status, batch,
    phases, packaging, category, fill, netw, notes, parent_version=None,
) -> dict:
    """폼 입력을 처방 dict로 조립(선택 필드는 값이 있을 때만 포함)."""
    data: dict = {
        "product": product.strip(),
        "slug": slug.strip(),
        "version": int(version),
        "regime": regime,
        "product_type": ptype,
        "status": status,
        "base_batch_g": float(batch),
        "phases": phases,
    }
    if category.strip():
        data["product_category"] = category.strip()
    if packaging:
        data["packaging"] = packaging
    if fill.strip():
        data["fill_volume_ml"] = float(fill)
    if netw.strip():
        data["net_weight_g"] = float(netw)
    if notes.strip():
        data["notes"] = notes.strip()
    if parent_version is not None:
        data["parent_version"] = int(parent_version)
    return data

# ---------------------------------------------------------------------------
# 템플릿에서 시작 (초보 추천)
# ---------------------------------------------------------------------------
with st.expander("🧩 템플릿에서 시작 (초보 추천)"):
    st.caption("검증된 골격 처방으로 시작합니다. 생성 후 사전점검·수정으로 자유롭게 다듬으세요.")
    _tlabels = {f"{name} — {desc}": key for key, name, desc in list_templates()}
    _tlabel = st.selectbox("템플릿", list(_tlabels), key="tmpl_sel")
    _tkey = _tlabels[_tlabel]
    _t = TEMPLATES[_tkey]

    tc1, tc2, tc3 = st.columns(3)
    t_slug = tc1.text_input("slug (폴더명, 예: my-lotion)", key="tmpl_slug")
    t_version = tc2.number_input("버전", min_value=1, value=1, step=1, key="tmpl_ver")
    t_product = tc3.text_input("제품명(비우면 기본값)", key="tmpl_product")

    st.caption(
        f"레짐 {_t['regime']} · {_t['product_type']} · 기준 {_t.get('base_batch_g', 100)}g "
        f"· 상 {len(_t['phases'])}개"
    )
    _prev = [
        {"상": ph["name"], "원료": ", ".join(f"{i['id']} {i['percent']}%" for i in ph["ingredients"])}
        for ph in _t["phases"]
    ]
    st.table(_prev)

    if st.button("템플릿으로 생성", type="primary", key="tmpl_create"):
        try:
            if not t_slug.strip():
                st.error("slug을 입력하세요.")
            else:
                data = instantiate(
                    _tkey, slug=t_slug, version=int(t_version), product=t_product or None
                )
                path = create_formula(
                    data, ingredient_ids=set(ing_ids), packaging_ids=set(pkg_ids)
                )
                st.success(
                    f"생성됨: formulas/{path.parent.name}/{path.name} "
                    "— 사전점검에서 HLB·배합한도를 확인하세요."
                )
                st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"생성 실패: {exc}")

# ---------------------------------------------------------------------------
# 새 처방 생성
# ---------------------------------------------------------------------------
with st.expander("➕ 새 처방 생성"):
    st.caption("원료 표의 percent 합계가 100이어야 저장됩니다. 상(A·B…)별로 원료를 묶으세요.")
    c1, c2, c3 = st.columns(3)
    f_product = c1.text_input("✍️ 제품명", key="nf_product", placeholder="예: 오후 산뜻 보습 로션")
    f_slug = c2.text_input("✍️ slug (폴더명)", key="nf_slug", placeholder="예: daily-lotion")
    f_version = c3.number_input("버전", min_value=1, value=1, step=1, key="nf_version")
    c4, c5, c6 = st.columns(3)
    f_regime = c4.selectbox("🔒 레짐 (목록에서 선택)", available(), key="nf_regime")
    f_ptype = c5.selectbox("🔒 제품형태", ["leave_on", "rinse_off"], key="nf_ptype")
    f_status = c6.selectbox("🔒 상태", ["개발중", "확정"], key="nf_status")
    c7, c8, c9 = st.columns(3)
    f_batch = c7.number_input("기준 배치(g)", min_value=1.0, value=100.0, step=10.0, key="nf_batch")
    f_category = c8.text_input("✍️ 품목 카테고리(선택)", key="nf_cat", placeholder="예: 보습 로션")
    f_notes = c9.text_input("✍️ 메모(선택)", key="nf_notes", placeholder="예: 다축 보습 컨셉")
    c10, c11 = st.columns(2)
    f_fill = c10.text_input("✍️ 충전 부피 ml(선택)", key="nf_fill", placeholder="예: 50")
    f_netw = c11.text_input("✍️ 내용량 g(선택)", key="nf_netw", placeholder="예: 50")

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
            phases = _phases_from_editor(ing_df)
            if not phases:
                st.error("원료를 1개 이상 입력하세요.")
            else:
                data = _assemble(
                    product=f_product, slug=f_slug, version=f_version, regime=f_regime,
                    ptype=f_ptype, status=f_status, batch=f_batch, phases=phases,
                    packaging=_packaging_from_editor(pkg_df), category=f_category,
                    fill=f_fill, netw=f_netw, notes=f_notes,
                )
                path = create_formula(
                    data, ingredient_ids=set(ing_ids), packaging_ids=set(pkg_ids)
                )
                st.success(f"생성됨: formulas/{path.parent.name}/{path.name}")
                st.rerun()
        except Exception as exc:  # noqa: BLE001 — 사용자에게 사유 표시
            st.error(f"생성 실패: {exc}")

# ---------------------------------------------------------------------------
# 처방 수정 (기존 처방을 불러와 값 변경 → 새 버전 저장 or 현재 버전 덮어쓰기)
# ---------------------------------------------------------------------------
with st.expander("✏️ 처방 수정"):
    if not lab.formulas:
        st.info("수정할 처방이 없습니다.")
    else:
        edit_opts = {f"{f.slug} v{f.version} — {f.product}": f for f in lab.formulas}
        ef = edit_opts[st.selectbox("수정할 처방", list(edit_opts), key="edit_sel")]
        sv = f"{ef.slug}_v{ef.version}"  # 선택이 바뀌면 위젯 키가 바뀌어 값이 새로 채워짐
        st.caption(f"현재: {ef.slug} v{ef.version} · 레짐 {ef.regime}")

        c1, c2, c3 = st.columns(3)
        e_product = c1.text_input("제품명", value=ef.product, key=f"ep_product_{sv}")
        e_regime = c2.selectbox(
            "레짐", available(),
            index=available().index(ef.regime) if ef.regime in available() else 0,
            key=f"ep_regime_{sv}",
        )
        e_status = c3.selectbox(
            "상태", _STATUSES, index=_STATUSES.index(ef.status.value), key=f"ep_status_{sv}"
        )
        c4, c5, c6 = st.columns(3)
        e_ptype = c4.selectbox(
            "제품형태", _PTYPES, index=_PTYPES.index(ef.product_type.value), key=f"ep_ptype_{sv}"
        )
        e_batch = c5.number_input(
            "기준 배치(g)", min_value=1.0, value=float(ef.base_batch_g), step=10.0, key=f"ep_batch_{sv}"
        )
        e_category = c6.text_input("품목 카테고리(선택)", value=ef.product_category or "", key=f"ep_cat_{sv}")
        c7, c8, c9 = st.columns(3)
        e_fill = c7.text_input("충전 부피 ml(선택)", value="" if ef.fill_volume_ml is None else str(ef.fill_volume_ml), key=f"ep_fill_{sv}")
        e_netw = c8.text_input("내용량 g(선택)", value="" if ef.net_weight_g is None else str(ef.net_weight_g), key=f"ep_netw_{sv}")
        e_notes = c9.text_input("메모(선택)", value=ef.notes or "", key=f"ep_notes_{sv}")

        st.markdown("**원료 (상별)**")
        e_rows = []
        for ph in ef.phases:
            for j, ing in enumerate(ph.ingredients):
                e_rows.append({
                    "상": ph.name,
                    "원료 id": ing.id,
                    "percent": ing.percent,
                    "공정(선택)": (ph.process or "") if j == 0 else "",
                })
        e_ing_df = st.data_editor(
            pd.DataFrame(e_rows),
            num_rows="dynamic",
            width="stretch",
            column_config={
                "상": st.column_config.TextColumn("상"),
                "원료 id": st.column_config.SelectboxColumn("원료 id", options=ing_ids),
                "percent": st.column_config.NumberColumn("percent", min_value=0.0, max_value=100.0, step=0.1),
                "공정(선택)": st.column_config.TextColumn("공정(선택)"),
            },
            key=f"ep_ing_{sv}",
        )
        _et = float(pd.to_numeric(e_ing_df["percent"], errors="coerce").fillna(0).sum())
        (st.success if abs(_et - 100.0) < 0.01 else st.caption)(
            f"현재 percent 합계: {_et:.2f} (100이어야 저장 가능)"
        )

        st.markdown("**포장재 (선택)**")
        e_prows = [{"포장재 id": r.id, "개수": r.qty_per_unit} for r in ef.packaging]
        e_pkg_df = st.data_editor(
            pd.DataFrame(e_prows) if e_prows
            else pd.DataFrame({"포장재 id": pd.Series(dtype="object"), "개수": pd.Series(dtype="int")}),
            num_rows="dynamic",
            width="stretch",
            column_config={
                "포장재 id": st.column_config.SelectboxColumn("포장재 id", options=pkg_ids),
                "개수": st.column_config.NumberColumn("개수", min_value=1, step=1),
            },
            key=f"ep_pkg_{sv}",
        )

        _nv = next_version(ef.slug)
        save_mode = st.radio(
            "저장 방식",
            [f"새 버전으로 저장 (v{_nv}, 권장)", f"현재 버전 덮어쓰기 (v{ef.version})"],
            key=f"ep_mode_{sv}",
        )
        new_version_mode = save_mode.startswith("새 버전")
        if not new_version_mode:
            st.caption("⚠️ 덮어쓰기는 현재 파일을 바꿉니다(.bak 백업·검증 실패 시 롤백).")
        if st.button("수정 저장", type="primary", key=f"ep_save_{sv}"):
            try:
                phases = _phases_from_editor(e_ing_df)
                if not phases:
                    st.error("원료를 1개 이상 입력하세요.")
                else:
                    data = _assemble(
                        product=e_product, slug=ef.slug,
                        version=_nv if new_version_mode else ef.version,
                        regime=e_regime, ptype=e_ptype, status=e_status, batch=e_batch,
                        phases=phases, packaging=_packaging_from_editor(e_pkg_df),
                        category=e_category, fill=e_fill, netw=e_netw, notes=e_notes,
                        parent_version=ef.version if new_version_mode else None,
                    )
                    if new_version_mode:
                        path = create_formula(
                            data, ingredient_ids=set(ing_ids), packaging_ids=set(pkg_ids)
                        )
                        st.success(f"새 버전 저장됨: formulas/{path.parent.name}/{path.name}")
                    else:
                        update_formula(
                            data, ingredient_ids=set(ing_ids), packaging_ids=set(pkg_ids)
                        )
                        st.success(f"덮어쓰기 완료: {ef.slug} v{ef.version} (백업 .bak)")
                    st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"수정 실패: {exc}")

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
