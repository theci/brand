"""제품표준서(dossier) 생성 — 흩어진 데이터를 1개 Markdown 문서로 컴파일.

처방·전성분·제조지시·품질규격(사전점검)·규제/표시·안정성·원가·배치이력을 모아
OEM 위탁제조사·식약처 제출 또는 사내 표준 문서로 쓸 수 있는 형태로 만든다.

계산은 기존 모듈을 그대로 재사용한다(중복 로직 없음):
  - screen()        : 전성분(INCI)·알러젠·표시의무·배합한도·규제데이터 최신성
  - batch_sheet()   : 상별 제조 지시서
  - check_formula() : HLB 유화 균형 + 배합한도 사전점검
  - unit_cost()     : 개당 원가(선택)

1차 스크리닝 결과이며 법적 판단이 아니다. 출시 전 관할기관·시험성적서 확인 필요.
"""

from __future__ import annotations

from datetime import date

from .batch import batch_sheet
from .checks import check_formula
from .core.costing import unit_cost
from .core.models import BatchRecord, Formula, ProductType, StabilitySample
from .labeling import screen
from .loader import load_regime_info


def _aggregated(formula: Formula) -> dict[str, float]:
    agg: dict[str, float] = {}
    for fi in (i for p in formula.phases for i in p.ingredients):
        agg[fi.id] = agg.get(fi.id, 0.0) + fi.percent
    return agg


def _regime_label(formula: Formula) -> str:
    try:
        info = load_regime_info(formula.regime)
        return f"{info.display_name} ({info.law_name})"
    except Exception:  # noqa: BLE001 — 레짐 데이터 없으면 코드만 표기
        return formula.regime


def _fill_text(formula: Formula) -> str:
    if formula.net_weight_g is not None:
        return f"{formula.net_weight_g:g} g"
    if formula.fill_volume_ml is not None:
        return f"{formula.fill_volume_ml:g} mL"
    return "미기재"


def _matches_formula(ref: str | None, formula: Formula) -> bool:
    """formula_ref 문자열이 이 처방(slug vN)을 가리키는지."""
    if not ref:
        return False
    return formula.slug in ref and f"v{formula.version}" in ref.replace(" ", "")


def build_dossier(
    formula: Formula,
    lab,
    *,
    units: int | None = None,
    stability: list[StabilitySample] | None = None,
    batches: list[BatchRecord] | None = None,
    today: date | None = None,
) -> str:
    """제품표준서 Markdown 문자열을 생성한다."""
    today = today or date.today()
    idx = lab.ingredients.index()
    agg = _aggregated(formula)
    L: list[str] = []

    # ── 표지 ──────────────────────────────────────────────
    L.append(f"# 제품표준서 — {formula.product} (v{formula.version})")
    L.append("")
    L.append(
        "> 자동 생성 문서(brand-lab). 1차 스크리닝이며 법적 판단이 아닙니다. "
        "출시 전 관할기관 확인·시험성적서가 필요합니다."
    )
    L.append(f"> 생성일: {today.isoformat()}")
    L.append("")

    # ── 1. 제품 개요 ──────────────────────────────────────
    L.append("## 1. 제품 개요")
    L.append("")
    L.append("| 항목 | 내용 |")
    L.append("|---|---|")
    L.append(f"| 제품명 | {formula.product} |")
    L.append(f"| 슬러그·버전 | {formula.slug} v{formula.version} |")
    L.append(f"| 적용 법(레짐) | {_regime_label(formula)} |")
    L.append(f"| 제품 형태 | {formula.product_type.value} |")
    if formula.product_category:
        L.append(f"| 품목 분류 | {formula.product_category} |")
    L.append(f"| 상태 | {formula.status.value} |")
    L.append(f"| 내용량 | {_fill_text(formula)} |")
    L.append(f"| 기준 배치 | {formula.base_batch_g:g} g |")
    if formula.parent_version:
        L.append(f"| 파생 원본 | v{formula.parent_version} |")
    L.append("")

    # ── 2. 전성분(INCI) ───────────────────────────────────
    scr = screen(formula, lab, today)
    L.append("## 2. 전성분 (INCI)")
    L.append("")
    L.append("**표시(안):**")
    L.append("")
    L.append("> " + (scr.inci.text or "(없음)"))
    L.append("")
    L.append("**성분 명세:**")
    L.append("")
    L.append("| # | 성분 | INCI | CAS | 기능 | 함량% |")
    L.append("|---|---|---|---|---|---|")
    for n, (ing_id, pct) in enumerate(
        sorted(agg.items(), key=lambda kv: kv[1], reverse=True), start=1
    ):
        ing = idx.get(ing_id)
        name = ing.name if ing else ing_id
        inci = ing.inci if ing else "―"
        cas = (ing.cas if ing and ing.cas else "―")
        cat = ing.category if ing else "―"
        L.append(f"| {n} | {name} | {inci} | {cas} | {cat} | {pct:g} |")
    if scr.inci.allergen_inci:
        L.append("")
        L.append("**알러젠 별도 표기 대상:** " + ", ".join(scr.inci.allergen_inci))
    L.append("")

    # ── 3. 제조 지시서 ────────────────────────────────────
    L.append("## 3. 제조 지시서 (기준 배치)")
    L.append("")
    L.append(batch_sheet(formula, formula.base_batch_g, ingredients=lab.ingredients))
    L.append("")

    # ── 4. 품질 규격 / 사전점검 ───────────────────────────
    chk = check_formula(formula, ingredients=lab.ingredients, limits=lab.limits)
    L.append("## 4. 품질 규격 · 사전점검")
    L.append("")
    if formula.regime == "cosmetics" and formula.product_type in (
        ProductType.LEAVE_ON,
        ProductType.RINSE_OFF,
    ):
        L.append("- **pH(피부 도포 제품 권장):** 4.5 ~ 6.0")
    if chk.hlb.applicable:
        L.append(
            f"- **HLB 유화 균형:** {chk.hlb.verdict} — 공급 {chk.hlb.supplied_hlb} / "
            f"요구 {chk.hlb.required_hlb}"
        )
    else:
        L.append("- **HLB 유화 균형:** 해당없음(비유화 처방 또는 HLB 데이터 없음)")
    if chk.limit_findings:
        L.append("- **배합한도 점검:**")
        for f in chk.limit_findings:
            L.append(
                f"  - {f.name}: {f.percent:g}% / 한도 {f.limit:g}% ({f.source}) → **{f.status}**"
            )
    else:
        L.append("- **배합한도 점검:** 초과·근접 원료 없음")
    L.append(f"- 종합 사전점검: {'통과' if chk.ok else '확인 필요'}")
    L.append("")

    # ── 5. 규제·표시 사항 ─────────────────────────────────
    req = scr.requirement
    L.append("## 5. 규제 · 표시 사항")
    L.append("")
    size = f"{req.size_value:g}{req.size_unit}" if req.size_value is not None else "미상"
    L.append(f"- 내용량 구분: **{req.tier}** (내용량 {size})")
    if req.required_items:
        L.append("- 필수 표시 항목: " + ", ".join(req.required_items))
    if scr.limits.has_data and scr.limits.findings:
        L.append("- 배합한도 근거:")
        for f in scr.limits.findings:
            ref = f" — 근거: {f.reference}" if f.reference else ""
            verdict = "초과" if f.exceeded else "적합"
            L.append(f"  - {f.name}: {f.percent:g}% / {f.max_percent:g}% ({verdict}){ref}")
    for w in scr.freshness.warnings:
        L.append(f"- ⚠ 규제데이터: {w}")
    L.append("")

    # ── 6. 안정성 시험 현황 ───────────────────────────────
    samples = [s for s in (stability or []) if _matches_formula(s.formula_ref, formula)]
    L.append("## 6. 안정성 시험 현황")
    L.append("")
    if not samples:
        L.append("- 등록된 안정성 시료 없음.")
    else:
        L.append("| 시료 | 조건 | 개시일 | 관찰 횟수 |")
        L.append("|---|---|---|---|")
        for s in samples:
            L.append(
                f"| {s.sample_id} | {s.condition.value} | {s.start_date.isoformat()} | "
                f"{len(s.observations)} |"
            )
    L.append("")

    # ── 7. 원가 요약 (선택) ───────────────────────────────
    if units is not None:
        L.append(f"## 7. 원가 요약 (수량 {units:,}개 기준)")
        L.append("")
        try:
            uc = unit_cost(formula, units, ingredients=lab.ingredients, packaging=lab.packaging)
            L.append(f"- 개당 원료비: {uc.material_cost:,.0f}원")
            L.append(f"- 개당 부자재비: {uc.packaging_cost:,.0f}원")
            L.append(f"- **개당 원가: {uc.unit_cost:,.0f}원**")
        except ValueError as exc:
            L.append(f"- 계산 불가: {exc}")
        L.append("")

    # ── 8. 배치 제조 이력 (선택) ──────────────────────────
    recs = [b for b in (batches or []) if _matches_formula(b.formula_ref, formula)]
    if recs:
        L.append("## 8. 배치 제조 이력")
        L.append("")
        L.append("| 배치ID | 일자 | 목표g | 회수g | 수율 | pH |")
        L.append("|---|---|---|---|---|---|")
        for b in sorted(recs, key=lambda x: (x.date, x.batch_id)):
            yg = f"{b.yield_g:g}" if b.yield_g is not None else "―"
            yp = f"{b.yield_percent:g}%" if b.yield_percent is not None else "―"
            ph = f"{b.ph:g}" if b.ph is not None else "―"
            L.append(f"| {b.batch_id} | {b.date.isoformat()} | {b.target_g:g} | {yg} | {yp} | {ph} |")
        L.append("")

    # ── 9. 개정 이력 ──────────────────────────────────────
    L.append("## 9. 개정 이력")
    L.append("")
    L.append("| 버전 | 파생원본 | 상태 |")
    L.append("|---|---|---|")
    L.append(
        f"| v{formula.version} | "
        f"{('v' + str(formula.parent_version)) if formula.parent_version else '―'} | "
        f"{formula.status.value} |"
    )
    L.append("")

    return "\n".join(L)


__all__ = ["build_dossier"]
