"""디자인 브리프(design brief) 생성 — 피그마·외주에 넘길 사양서.

그래픽 디자인 툴이 아니다. "무엇을 반드시 담아야 하는가(규제 표기)·어떤 톤인가
(브랜드·페르소나)·용기 규격은 무엇인가"를 1개 Markdown 사양서로 컴파일한다.

재사용(중복 로직 없음):
  - labeling.screen : 전성분(INCI)·표시의무 필수기재·알러젠·배합한도
  - 브랜드 코어      : 비주얼 코드(컬러·용기·제형무드·사진톤)·톤·금지어
  - 기획(Discovery) : 타깃 페르소나·문제 정의 (Phase 11 상류 → 브리프에 자동 반영)
  - packaging       : 용기 규격

1차 스크리닝이며 법적 판단이 아니다. 라벨 표기는 출시 전 관할기관 확인 필수.
"""

from __future__ import annotations

from datetime import date

from .core.models import BrandCore, Discovery, Formula
from .discovery import primary_persona
from .labeling import screen
from .loader import load_regime_info


def _regime_label(formula: Formula) -> str:
    try:
        info = load_regime_info(formula.regime)
        return f"{info.display_name} ({info.law_name})"
    except Exception:  # noqa: BLE001
        return formula.regime


def _fill_text(formula: Formula) -> str:
    if formula.net_weight_g is not None:
        return f"{formula.net_weight_g:g} g"
    if formula.fill_volume_ml is not None:
        return f"{formula.fill_volume_ml:g} mL"
    return "미기재"


def build_brief(
    formula: Formula,
    lab,
    *,
    core: BrandCore | None = None,
    discovery: Discovery | None = None,
    today: date | None = None,
) -> str:
    """디자인 브리프 Markdown 문자열을 생성한다."""
    today = today or date.today()
    core = core or BrandCore()
    discovery = discovery or Discovery()
    scr = screen(formula, lab, today)
    vis = core.visual
    L: list[str] = []

    # ── 표지 ──
    L.append(f"# 디자인 브리프 — {formula.product} (v{formula.version})")
    L.append("")
    L.append("> 피그마·외주 디자이너에게 넘기는 **사양서**입니다(그래픽 제작 아님).")
    L.append("> 반드시 담아야 할 것(규제 표기)·브랜드 톤·용기 규격을 정의합니다.")
    L.append(f"> 생성일: {today.isoformat()} · 1차 스크리닝(법적 판단 아님)")
    L.append("")

    # ── 1. 제품 개요 ──
    L.append("## 1. 제품 개요")
    L.append("")
    L.append("| 항목 | 내용 |")
    L.append("|---|---|")
    L.append(f"| 제품명 | {formula.product} |")
    L.append(f"| 버전 | {formula.slug} v{formula.version} |")
    L.append(f"| 적용 법(레짐) | {_regime_label(formula)} |")
    if formula.product_category:
        L.append(f"| 품목 분류 | {formula.product_category} |")
    L.append(f"| 내용량 | {_fill_text(formula)} |")
    L.append("")

    # ── 2. 컨셉·톤 컨텍스트 (기획 + 브랜드 코어) ──
    L.append("## 2. 컨셉 · 톤 (디자인 방향)")
    L.append("")
    persona = primary_persona(discovery)
    if persona is not None:
        L.append(f"- **타깃 페르소나:** {persona.one_line or persona.name}")
        if persona.context:
            L.append(f"  - 상황: {persona.context}")
    if discovery.problem.statement:
        L.append(f"- **해결할 문제:** {discovery.problem.statement}")
    if core.promise:
        L.append(f"- **브랜드 약속:** {core.promise}")
    if core.persona and persona is None:
        L.append(f"- **타깃:** {core.persona}")
    if core.tone_adjectives:
        L.append(f"- **톤 형용사:** {', '.join(core.tone_adjectives)}")
    if core.forbidden_words:
        L.append(f"- **금지어(카피·표기 금지):** {', '.join(core.forbidden_words)}")
    if persona is None and not core.promise and not core.tone_adjectives:
        L.append("- (기획·브랜드 코어가 비어 있음 — [페르소나]·[브랜드 코어]를 먼저 채우면 이 섹션이 채워집니다.)")
    L.append("")

    # ── 3. 라벨 법정 필수 기재 (핵심) ──
    L.append("## 3. 라벨 법정 필수 기재 ⚠")
    L.append("")
    req = scr.requirement
    size = f"{req.size_value:g}{req.size_unit}" if req.size_value is not None else "미상"
    L.append(f"- 표시 면적 구분: **{req.tier}** (내용량 {size})")
    if req.required_items:
        L.append("- **필수 기재 항목(디자인에 반드시 배치):**")
        for it in req.required_items:
            L.append(f"  - [ ] {it}")
    for n in req.notes:
        L.append(f"  - 참고: {n}")
    L.append("")
    L.append("### 전성분 표시(안)")
    L.append("")
    L.append("> " + (scr.inci.text or "(없음)"))
    if scr.inci.allergen_inci:
        L.append("")
        L.append("**알러젠 별도 표기 대상:** " + ", ".join(scr.inci.allergen_inci))
    if scr.allergens.declared:
        L.append("")
        L.append("**표기 의무 알러젠(완제품 농도):**")
        for f in scr.allergens.declared:
            L.append(f"- {f.name} ({f.inci}) — {f.concentration_percent:g}%")
    for w in scr.freshness.warnings:
        L.append(f"\n⚠ 규제데이터: {w}")
    L.append("")

    # ── 4. 용기·포장 규격 ──
    L.append("## 4. 용기 · 포장 규격")
    L.append("")
    pidx = lab.packaging.index()
    if not formula.packaging:
        L.append("- (포장재 미지정)")
    else:
        L.append("| 포장재 | 종류 | 용량/재질 | 개당 수량 |")
        L.append("|---|---|---|---|")
        for ref in formula.packaging:
            pkg = pidx.get(ref.id)
            if pkg is None:
                L.append(f"| {ref.id} | ? | ? | {ref.qty_per_unit} |")
                continue
            vol = f"{pkg.volume_ml:g}mL" if pkg.volume_ml else "-"
            mat = pkg.material or "-"
            L.append(f"| {pkg.name} | {pkg.type} | {vol} / {mat} | {ref.qty_per_unit} |")
    L.append("")

    # ── 5. 비주얼 코드 ──
    L.append("## 5. 비주얼 코드")
    L.append("")
    vrows = [
        ("메인 컬러", vis.main_color),
        ("서브 컬러", vis.sub_color),
        ("포인트 컬러", vis.point_color),
        ("용기", vis.container),
        ("제형 무드", vis.texture),
        ("타이틀 폰트", vis.font_title),
        ("본문 폰트", vis.font_body),
        ("사진 톤(조명·색온도·배경)", vis.photo_note),
    ]
    if any(v for _, v in vrows):
        L.append("| 항목 | 값 |")
        L.append("|---|---|")
        for k, v in vrows:
            if v:
                L.append(f"| {k} | {v} |")
    else:
        L.append("- (브랜드 코어의 ⑦ 비주얼을 채우면 컬러·용기·사진 톤이 여기 반영됩니다.)")
    L.append("")

    # ── 6. 디자이너 체크리스트 ──
    L.append("## 6. 디자이너 확인 체크리스트")
    L.append("")
    L.append("- [ ] 위 **필수 기재 항목**을 모두 배치했는가")
    L.append("- [ ] 전성분 표시(안)을 그대로 반영했는가(임의 수정 금지)")
    L.append("- [ ] 알러젠 표기 대상을 포함했는가")
    L.append("- [ ] 용기 규격(용량·재질)에 맞는 라벨 크기인가")
    L.append("- [ ] 금지어를 카피·표기에 쓰지 않았는가")
    L.append("- [ ] 최소 글자 크기 등 표시 규정을 지켰는가(관할기관 기준 확인)")
    L.append("")

    return "\n".join(L)


__all__ = ["build_brief"]
