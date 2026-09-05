"""브랜드 코어 시트 — 근거 자동 추출 · 자산 텍스트 · 저장.

마케팅 가이드의 '브랜드 코어 시트 9칸' 중 ⑤근거·⑦비주얼·⑧금지어를 제품 데이터에서 초안 생성한다.
- 근거(Evidence)는 **지어내지 않고 데이터에서 나온 사실**만: 주요 성분·전성분 수·안정성·버전이력·HLB·제조방식.
- 처방 전체 %는 영업비밀이라 노출하지 않는다(mask_percent로 히어로 성분 %까지 가릴 수 있음).

자산 텍스트(asset_text)는 모든 마케팅 AI 프롬프트 앞에 붙일 '브랜드 자산' 블록이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .checks import check_formula
from .core.models import BrandCore, Formula
from .loader import DATA_DIR

# 근거의 '주요 성분'에서 제외할 범용 베이스(물·용제)
_GENERIC = {"water", "purified-water", "ethanol", "dpg", "ipm"}


@dataclass
class EvidenceCard:
    text: str
    source: str  # 전성분 | 처방 | 안정성 | 버전이력 | 사전점검 | 제조


def _aggregate(formula: Formula) -> dict[str, float]:
    agg: dict[str, float] = {}
    for ph in formula.phases:
        for i in ph.ingredients:
            agg[i.id] = agg.get(i.id, 0.0) + i.percent
    return agg


def evidence_cards(
    formula: Formula, lab, *, stability=None, mask_percent: bool = False
) -> list[EvidenceCard]:
    """제품 데이터에서 검증된 근거 카드 목록을 뽑는다."""
    idx = lab.ingredients.index()
    agg = _aggregate(formula)
    stars = sorted(
        ((i, p) for i, p in agg.items() if i not in _GENERIC),
        key=lambda x: x[1],
        reverse=True,
    )
    cards: list[EvidenceCard] = []

    # 주요 성분(전성분에서 범용 베이스 제외 상위)
    names = [idx[i].name for i, _ in stars[:4] if i in idx]
    if names:
        cards.append(EvidenceCard(f"주요 성분: {' · '.join(names)}", "전성분"))

    # 전성분 공개 수
    cards.append(EvidenceCard(f"전성분 {len(agg)}종 전 공개", "전성분"))

    # 히어로 성분(대표 1종) — % 노출은 mask로 제어
    if stars and stars[0][0] in idx:
        hid, hpct = stars[0]
        hname = idx[hid].name
        text = f"{hname} 배합" if mask_percent else f"{hname} {hpct:g}% 배합"
        cards.append(EvidenceCard(text, "처방"))

    # 안정성 — 이 처방을 참조하는 시료
    if stability:
        mine = [s for s in stability if s.formula_ref and formula.slug in s.formula_ref]
        if mine:
            conds = " · ".join(sorted({s.condition.value for s in mine}))
            nobs = sum(len(s.observations) for s in mine)
            cards.append(
                EvidenceCard(f"{conds} 조건 안정성 시험 진행(관찰 {nobs}회)", "안정성")
            )

    # 버전 개선 이력(실패담·비하인드 재료)
    vers = sorted(f.version for f in lab.formulas if f.slug == formula.slug)
    if len(vers) > 1:
        cards.append(
            EvidenceCard(f"v{vers[0]}→v{vers[-1]} 개발 개선 이력(비하인드)", "버전이력")
        )

    # HLB 균형(유화 제품)
    try:
        res = check_formula(formula, ingredients=lab.ingredients, limits=lab.limits)
        if res.hlb.applicable:
            n = len(res.hlb.emulsifiers)
            cards.append(
                EvidenceCard(
                    f"유화제 {n}종으로 HLB 균형(사전점검 {res.hlb.verdict})", "사전점검"
                )
            )
    except Exception:  # noqa: BLE001 — 근거 추출 실패는 조용히 건너뜀
        pass

    # 제조 방식(공정 특징)
    procs = " ".join(ph.process or "" for ph in formula.phases)
    if "상온" in procs and "가열" not in procs:
        cards.append(EvidenceCard("가열 없이 상온 블렌딩 공정", "제조"))
    elif "유화" in procs or "70" in procs:
        cards.append(EvidenceCard("70~75℃ 가온 유화 공정", "제조"))

    return cards


def suggest_container(formula: Formula, lab) -> str | None:
    """비주얼 코드용 용기 제안(첫 포장재 이름)."""
    if formula.packaging:
        pkg = lab.packaging.index().get(formula.packaging[0].id)
        return pkg.name if pkg else formula.packaging[0].id
    return None


def _bullet(items: list[str]) -> str:
    return "\n".join(f"  - {x}" for x in items) if items else "  - (미작성)"


def asset_text(core: BrandCore, *, regulatory_forbidden: list[str] | None = None) -> str:
    """모든 마케팅 프롬프트 앞에 붙일 '브랜드 자산' 텍스트 블록."""
    v = core.visual
    visual_bits = []
    if v.main_color:
        visual_bits.append(f"메인 {v.main_color}")
    if v.sub_color:
        visual_bits.append(f"서브 {v.sub_color}")
    if v.point_color:
        visual_bits.append(f"포인트 {v.point_color}")
    if v.container:
        visual_bits.append(f"용기 {v.container}")
    if v.texture:
        visual_bits.append(f"제형 {v.texture}")
    if v.photo_note:
        visual_bits.append(f"사진 {v.photo_note}")

    lines = [
        "[브랜드 자산 — 이 정보를 기준으로 작업할 것]",
        f"브랜드: {core.brand_name or '(미작성)'}",
        f"한 줄 소개: {core.one_liner or '(미작성)'}",
        f"기준 제품: {core.product_ref or '(미지정)'}",
        "① 카테고리 진입점:",
        _bullet(core.entry_points),
        f"② 타깃: {core.persona or '(미작성)'}",
        f"③ 적(반대하는 것): {core.enemy or '(미작성)'}",
        f"④ 약속: {core.promise or '(미작성)'}",
        "⑤ 근거(증명 가능한 사실만):",
        _bullet(core.evidence),
        f"⑥ 톤: {', '.join(core.tone_adjectives) or '(미작성)'}",
        f"⑦ 비주얼: {' / '.join(visual_bits) or '(미작성)'}",
        f"⑧ 애용어: {', '.join(core.vocabulary) or '(없음)'}",
        f"⑧ 금지어(브랜드): {', '.join(core.forbidden_words) or '(없음)'}",
        f"⑩ 차별점(우리 비법): {core.differentiation_note or '(미작성)'}",
        f"   차별화 층: {', '.join(core.differentiators) or '(미선택)'}",
    ]
    if regulatory_forbidden:
        lines.append(f"⑧ 금지어(화장품법 규제): {', '.join(regulatory_forbidden)}")
    lines.append("")
    lines.append("[준수] 화장품법 의약품 오인·기능성 표방·최상급 표현 금지. 근거 없는 효능 단정 금지.")
    return "\n".join(lines) + "\n"


def save_brand_core(
    core: BrandCore, path: Path | str = DATA_DIR / "brand" / "core.yaml"
) -> Path:
    """브랜드 코어 시트를 YAML로 저장한다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = core.model_dump(exclude_none=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


__all__ = [
    "EvidenceCard",
    "evidence_cards",
    "suggest_container",
    "asset_text",
    "save_brand_core",
]
