"""전성분 표시 생성기 + 규정 체커.

법적 리스크와 직결되는 기능이므로 다음 원칙을 지킨다.
  - 규제 '수치'는 코드에 두지 않는다. 전부 data/regulatory/*.yaml 에서 읽는다.
  - 규제 데이터가 비어 있거나 오래되면(last_updated 기준) 조용히 통과시키지 않고 경고한다.
  - 모든 스크리닝 결과에는 면책 문구(DISCLAIMER)를 붙인다.

이 도구는 1차 스크리닝일 뿐 법적 판단이 아니다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from .models import (
    AllergenList,
    Formula,
    Ingredient,
    IngredientMaster,
    LabelingRules,
    LimitList,
    ProductType,
)

# 모든 출력 맨 아래에 반드시 붙일 면책 문구.
DISCLAIMER = (
    "※ 이 결과는 1차 스크리닝입니다. 법적 판단이 아니며, 출시 전 반드시 "
    "식약처 고시 원문과 대조하고 필요시 전문가 검토를 받으십시오."
)

# 공정 중 반응해 완제품 전성분이 원료와 달라지는 카테고리(도메인 분류, 규제 수치 아님).
REACTIVE_CATEGORIES = {"비누화제"}


# ---------------------------------------------------------------------------
# 결과 자료구조
# ---------------------------------------------------------------------------
@dataclass
class AllergenFinding:
    allergen_id: str
    name: str
    inci: str
    concentration_percent: float  # 완제품 중 농도(%)
    threshold_percent: float
    must_declare: bool
    sources: list[str]  # 이 알러젠을 기여한 원료명


@dataclass
class AllergenCheckResult:
    product_type: ProductType
    threshold_percent: float
    declared: list[AllergenFinding]  # 임계값 초과 → 성분명 표기 의무
    below_threshold: list[AllergenFinding]  # 존재하나 임계값 이하
    warnings: list[str] = field(default_factory=list)


@dataclass
class InciResult:
    ordered: list[tuple[str, float]]  # 함량 초과분: (INCI, 함량%) 내림차순
    unordered: list[tuple[str, float]]  # 1% 이하·착향제·착색제: 순서 무관
    allergen_inci: list[str]  # 별도 표기 의무 알러젠 INCI
    text: str  # 최종 전성분 표시 문자열
    warnings: list[str] = field(default_factory=list)


@dataclass
class LabelingRequirement:
    size_value: float | None
    size_unit: str | None  # "ml" | "g" | None
    tier: str  # "full" | "reduced" | "minimal" | "unknown"
    full_ingredient_list_required: bool
    required_items: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass
class LimitFinding:
    ingredient_id: str
    name: str
    percent: float  # 처방 내 합계 함량(%)
    max_percent: float
    product_type: ProductType | None
    reference: str | None
    exceeded: bool


@dataclass
class LimitCheckResult:
    has_data: bool  # limits.yaml에 데이터가 있는가
    findings: list[LimitFinding]
    violations: list[LimitFinding]
    warnings: list[str] = field(default_factory=list)


@dataclass
class FreshnessFinding:
    label: str
    last_updated: date | None
    age_days: int | None
    stale: bool
    missing: bool


@dataclass
class FreshnessResult:
    findings: list[FreshnessFinding]
    warnings: list[str] = field(default_factory=list)


@dataclass
class LabelScreening:
    formula_slug: str
    version: int
    inci: InciResult
    allergens: AllergenCheckResult
    requirement: LabelingRequirement
    limits: LimitCheckResult
    freshness: FreshnessResult
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
def _ingredient_index(
    ingredients: IngredientMaster | Mapping[str, Ingredient],
) -> dict[str, Ingredient]:
    if isinstance(ingredients, IngredientMaster):
        return ingredients.index()
    return dict(ingredients)


def _aggregated_percents(formula: Formula) -> dict[str, float]:
    """같은 원료가 여러 상에 나오면 함량을 합산한다."""
    agg: dict[str, float] = {}
    for fi in (i for p in formula.phases for i in p.ingredients):
        agg[fi.id] = agg.get(fi.id, 0.0) + fi.percent
    return agg


# ---------------------------------------------------------------------------
# 알러젠 판정
# ---------------------------------------------------------------------------
def allergen_check(
    formula: Formula,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    rules: LabelingRules,
    allergens_db: AllergenList,
) -> AllergenCheckResult:
    """완제품 중 알러젠 농도를 계산하고 표시 의무 여부를 판정한다.

    완제품 농도(%) = Σ (처방 내 원료 함량% × 원료 중 알러젠 함량% / 100)
    임계값(제품 형태별)은 labeling_rules.yaml에서 읽는다.
    """
    idx = _ingredient_index(ingredients)
    a_idx = allergens_db.index()
    threshold = rules.allergen_thresholds.for_type(formula.product_type)

    contrib: dict[str, dict] = {}
    warnings: list[str] = []
    for fi in (i for p in formula.phases for i in p.ingredients):
        ing = idx.get(fi.id)
        if ing is None:
            continue
        for ac in ing.allergens:
            conc = fi.percent * ac.percent / 100.0
            entry = contrib.setdefault(ac.id, {"conc": 0.0, "sources": []})
            entry["conc"] += conc
            if ing.name not in entry["sources"]:
                entry["sources"].append(ing.name)

    findings: list[AllergenFinding] = []
    for aid, e in contrib.items():
        a = a_idx.get(aid)
        if a is None:
            warnings.append(
                f"알러젠 id '{aid}'가 allergens.yaml에 없어 성분명을 확인할 수 없습니다."
            )
        conc = round(e["conc"], 6)
        findings.append(
            AllergenFinding(
                allergen_id=aid,
                name=a.name if a else aid,
                inci=a.inci if a else aid,
                concentration_percent=conc,
                threshold_percent=threshold,
                must_declare=conc > threshold,  # 고시: '초과' 시 표시
                sources=list(e["sources"]),
            )
        )

    findings.sort(key=lambda f: f.concentration_percent, reverse=True)
    declared = [f for f in findings if f.must_declare]
    below = [f for f in findings if not f.must_declare]

    return AllergenCheckResult(
        product_type=formula.product_type,
        threshold_percent=threshold,
        declared=declared,
        below_threshold=below,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 전성분 표시 문자열
# ---------------------------------------------------------------------------
def inci_list(
    formula: Formula,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    rules: LabelingRules,
    allergens_db: AllergenList | None = None,
) -> InciResult:
    """전성분 표시 문자열을 생성한다.

    - 함량 임계값(labeling_rules.ingredient_order_threshold_percent) '초과' 성분:
      함량 많은 순으로 정렬
    - 임계값 이하 성분·착향제·착색제: 순서 무관(안전하게 내림차순으로 배치)
    - allergens_db가 주어지면 표시 의무 알러젠 INCI를 뒤에 추가
    """
    idx = _ingredient_index(ingredients)
    order_threshold = rules.ingredient_order_threshold_percent
    agg = _aggregated_percents(formula)

    ordered: list[tuple[str, float]] = []
    unordered: list[tuple[str, float]] = []
    warnings: list[str] = []
    reactive = False

    for ing_id, percent in agg.items():
        ing = idx.get(ing_id)
        inci = ing.inci if ing else ing_id
        if ing and ing.category in REACTIVE_CATEGORIES:
            reactive = True
        order_free = percent <= order_threshold or (
            ing is not None and (ing.fragrance or ing.colorant)
        )
        if order_free:
            unordered.append((inci, percent))
        else:
            ordered.append((inci, percent))

    ordered.sort(key=lambda t: t[1], reverse=True)
    unordered.sort(key=lambda t: t[1], reverse=True)

    allergen_inci: list[str] = []
    if allergens_db is not None:
        result = allergen_check(formula, ingredients, rules, allergens_db)
        allergen_inci = [f.inci for f in result.declared]

    # 최종 문자열: 정렬군 + 순서무관군 + 알러젠(중복 제거, 순서 보존)
    names: list[str] = (
        [t[0] for t in ordered]
        + [t[0] for t in unordered]
        + allergen_inci
    )
    seen: set[str] = set()
    dedup: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            dedup.append(n)
    text = ", ".join(dedup)

    if reactive:
        warnings.append(
            "이 처방은 비누화 등 반응 공정을 포함합니다. 완제품 전성분은 투입 원료가 "
            "아니라 반응 생성물(예: Sodium Olivate)로 표기해야 하므로, 자동 생성된 "
            "이 목록을 그대로 사용하지 마십시오."
        )

    return InciResult(
        ordered=ordered,
        unordered=unordered,
        allergen_inci=allergen_inci,
        text=text,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 표시 의무(용량 기준)
# ---------------------------------------------------------------------------
def labeling_requirements(
    formula: Formula, rules: LabelingRules
) -> LabelingRequirement:
    """내용량(부피 또는 중량)으로 표시 의무 수준을 판정한다."""
    if formula.fill_volume_ml is not None:
        size = formula.fill_volume_ml
        unit = "ml"
        full_t = rules.full_labeling_volume_ml
        min_t = rules.minimal_labeling_volume_ml
    elif formula.net_weight_g is not None:
        size = formula.net_weight_g
        unit = "g"
        full_t = rules.full_labeling_weight_g
        min_t = rules.minimal_labeling_weight_g
    else:
        return LabelingRequirement(
            size_value=None,
            size_unit=None,
            tier="unknown",
            full_ingredient_list_required=True,
            required_items=["전성분(내용량 미상 → 안전하게 전성분 표시 권장)"],
            notes=[
                "내용량(fill_volume_ml 또는 net_weight_g)이 없어 표시 의무를 판정할 수 "
                "없습니다. 안전하게 전성분 표시를 권장합니다."
            ],
        )

    notes: list[str] = []
    if size > full_t:
        tier = "full"
        full_required = True
        items = ["전성분 전체"]
        notes.append(
            f"{size:g}{unit} > {full_t:g}{unit}: 전성분 표시 필수."
        )
    elif size <= min_t:
        tier = "minimal"
        full_required = False
        items = list(rules.minimal_items)
        notes.append(
            f"{size:g}{unit} ≤ {min_t:g}{unit}: 아래 항목만 표시(전성분 생략 가능)."
        )
    else:
        tier = "reduced"
        full_required = False
        items = list(rules.minimal_items)
        notes.append(
            f"{min_t:g}{unit} < {size:g}{unit} ≤ {full_t:g}{unit}: 전성분은 생략할 수 "
            "있으나, 알레르기 유발성분·사용상 제한 원료·타르색소·기능성 주성분 등 "
            "'특정 성분'은 반드시 표시해야 합니다. 해당 목록은 식약처 고시 원문을 "
            "확인하세요."
        )

    return LabelingRequirement(
        size_value=size,
        size_unit=unit,
        tier=tier,
        full_ingredient_list_required=full_required,
        required_items=items,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 배합한도 체크
# ---------------------------------------------------------------------------
def limit_check(
    formula: Formula,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    limits: LimitList,
) -> LimitCheckResult:
    """처방 함량을 limits.yaml의 배합한도와 대조한다.

    limits.yaml이 비어 있으면 조용히 통과시키지 않고 '규제 데이터 미입력'을 알린다.
    """
    idx = _ingredient_index(ingredients)
    agg = _aggregated_percents(formula)

    if not limits.limits:
        return LimitCheckResult(
            has_data=False,
            findings=[],
            violations=[],
            warnings=[
                "규제 데이터 미입력: limits.yaml에 배합한도가 없습니다. "
                "배합한도 검증을 수행하지 못했습니다(통과가 아님)."
            ],
        )

    findings: list[LimitFinding] = []
    for lim in limits.limits:
        # product_type이 지정된 한도는 해당 형태에만 적용
        if lim.product_type is not None and lim.product_type != formula.product_type:
            continue
        if lim.ingredient_id not in agg:
            continue
        percent = round(agg[lim.ingredient_id], 6)
        ing = idx.get(lim.ingredient_id)
        exceeded = percent > lim.max_percent
        findings.append(
            LimitFinding(
                ingredient_id=lim.ingredient_id,
                name=ing.name if ing else lim.ingredient_id,
                percent=percent,
                max_percent=lim.max_percent,
                product_type=lim.product_type,
                reference=lim.reference,
                exceeded=exceeded,
            )
        )

    violations = [f for f in findings if f.exceeded]
    warnings: list[str] = []
    for v in violations:
        warnings.append(
            f"배합한도 초과: {v.name} {v.percent:g}% > 한도 {v.max_percent:g}%"
            + (f" ({v.reference})" if v.reference else "")
        )
    return LimitCheckResult(
        has_data=True, findings=findings, violations=violations, warnings=warnings
    )


# ---------------------------------------------------------------------------
# 규제 데이터 최신성
# ---------------------------------------------------------------------------
def freshness_check(
    files: Mapping[str, date | None],
    stale_after_days: int,
    today: date | None = None,
) -> FreshnessResult:
    """규제 데이터 파일의 last_updated를 검사한다."""
    today = today or date.today()
    findings: list[FreshnessFinding] = []
    warnings: list[str] = []
    for label, last_updated in files.items():
        if last_updated is None:
            findings.append(
                FreshnessFinding(label, None, None, stale=True, missing=True)
            )
            warnings.append(
                f"{label}: last_updated 없음 — 규제 데이터 최신성을 확인할 수 없습니다."
            )
            continue
        age = (today - last_updated).days
        stale = age > stale_after_days
        findings.append(
            FreshnessFinding(label, last_updated, age, stale=stale, missing=False)
        )
        if stale:
            warnings.append(
                f"{label}: last_updated {last_updated.isoformat()} ({age}일 경과) — "
                f"{stale_after_days}일 초과. 식약처 고시 원문으로 갱신하세요."
            )
    return FreshnessResult(findings=findings, warnings=warnings)


# ---------------------------------------------------------------------------
# 통합 스크리닝
# ---------------------------------------------------------------------------
def screen(formula: Formula, lab, today: date | None = None) -> LabelScreening:
    """하나의 처방에 대해 전 항목을 스크리닝한다. (lab: BrandLab)"""
    inci = inci_list(formula, lab.ingredients, lab.labeling_rules, lab.allergens)
    allergens = allergen_check(
        formula, lab.ingredients, lab.labeling_rules, lab.allergens
    )
    requirement = labeling_requirements(formula, lab.labeling_rules)
    limits = limit_check(formula, lab.ingredients, lab.limits)
    freshness = freshness_check(
        {
            "labeling_rules.yaml": lab.labeling_rules.last_updated,
            "allergens.yaml": lab.allergens.last_updated,
            "limits.yaml": lab.limits.last_updated,
        },
        lab.labeling_rules.stale_after_days,
        today=today,
    )
    return LabelScreening(
        formula_slug=formula.slug,
        version=formula.version,
        inci=inci,
        allergens=allergens,
        requirement=requirement,
        limits=limits,
        freshness=freshness,
    )


__all__ = [
    "DISCLAIMER",
    "AllergenFinding",
    "AllergenCheckResult",
    "InciResult",
    "LabelingRequirement",
    "LimitFinding",
    "LimitCheckResult",
    "FreshnessFinding",
    "FreshnessResult",
    "LabelScreening",
    "allergen_check",
    "inci_list",
    "labeling_requirements",
    "limit_check",
    "freshness_check",
    "screen",
]
