"""배치 계산 엔진.

처방(Formula)을 임의 배치 크기로 환산(scale)하고, 배치 지시서(batch_sheet)를
마크다운으로 출력하며, 스케일업 리스크(scale_report)를 정성적으로 경고한다.

물성을 정량 예측하지 않는다. scale_report는 "파일럿 배치가 필요한가"를
판단하기 위한 정성적 경고만 제공한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date as date_cls

from .models import Formula, Ingredient, IngredientMaster

# 목표 g을 소수 2자리(0.01g)까지 계산한다.
ROUND_DECIMALS = 2

# 신뢰성 있게 계량 가능한 최소 질량(g).
# 저울 최소 분해능이 0.001g이므로, 그 100배(~0.1g) 미만은 상대 오차가 커
# "이 배치 크기에서는 계량 불가"로 경고한다. 필요 시 함수 인자로 조정 가능.
DEFAULT_MIN_WEIGHABLE_G = 0.1

# 스케일업 리스크 판정용 카테고리 집합.
# 데이터는 한글 카테고리를 쓰지만 영문 표기도 함께 매칭한다.
WAX_BUTTER_CATEGORIES = {"왁스", "버터", "wax", "butter"}
EMULSIFIER_CATEGORIES = {"계면활성제", "유화제", "emulsifier", "surfactant"}

# 왁스/버터 합계가 이 비율(%)을 초과하면 냉각 속도 리스크 경고.
WAX_BUTTER_RISK_THRESHOLD = 10.0


# ---------------------------------------------------------------------------
# 결과 자료구조
# ---------------------------------------------------------------------------
@dataclass
class ScaledIngredient:
    id: str
    name: str
    percent: float
    grams: float
    weighable: bool  # min_weighable_g 이상이면 True


@dataclass
class ScaledPhase:
    name: str
    process: str | None
    ingredients: list[ScaledIngredient]
    subtotal_g: float


@dataclass
class ScaleResult:
    product: str
    slug: str
    version: int
    target_g: float
    phases: list[ScaledPhase]
    total_g: float
    total_ok: bool  # 합계가 target_g와 (반올림 오차 내에서) 일치하는가
    warnings: list[str]

    @property
    def unweighable(self) -> list[ScaledIngredient]:
        return [i for p in self.phases for i in p.ingredients if not i.weighable]


@dataclass
class ScaleReport:
    slug: str
    version: int
    from_g: float
    to_g: float
    wax_butter_percent: float
    emulsifier_ingredients: list[str]
    risk_level: str  # "낮음" | "높음"
    warnings: list[str]

    @property
    def has_emulsifier(self) -> bool:
        return bool(self.emulsifier_ingredients)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
def _as_index(
    ingredients: IngredientMaster | Mapping[str, Ingredient] | None,
) -> dict[str, Ingredient]:
    if ingredients is None:
        return {}
    if isinstance(ingredients, IngredientMaster):
        return ingredients.index()
    return dict(ingredients)


# ---------------------------------------------------------------------------
# 1. scale
# ---------------------------------------------------------------------------
def scale(
    formula: Formula,
    target_g: float,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient] | None = None,
    min_weighable_g: float = DEFAULT_MIN_WEIGHABLE_G,
) -> ScaleResult:
    """처방을 target_g 배치 크기로 환산한다.

    - 각 원료의 목표 g을 소수 2자리까지 계산
    - 상(phase)별 소계와 전체 합계를 내고, 합계가 target_g와 일치하는지 검증
    - min_weighable_g 미만으로 떨어지는 원료는 "계량 불가" 경고
    """
    if target_g <= 0:
        raise ValueError(f"target_g는 0보다 커야 합니다: {target_g}")

    idx = _as_index(ingredients)
    warnings: list[str] = []
    scaled_phases: list[ScaledPhase] = []
    n_ingredients = 0

    for phase in formula.phases:
        scaled_ings: list[ScaledIngredient] = []
        subtotal = 0.0
        for fi in phase.ingredients:
            n_ingredients += 1
            grams = round(fi.percent / 100.0 * target_g, ROUND_DECIMALS)
            weighable = grams >= min_weighable_g
            name = idx[fi.id].name if fi.id in idx else fi.id
            scaled_ings.append(
                ScaledIngredient(
                    id=fi.id,
                    name=name,
                    percent=fi.percent,
                    grams=grams,
                    weighable=weighable,
                )
            )
            subtotal += grams
            if not weighable:
                warnings.append(
                    f"'{name}' ({fi.percent:g}%) → {grams:.2f}g: "
                    f"이 배치 크기({target_g:g}g)에서는 계량 불가 "
                    f"(최소 계량 {min_weighable_g:g}g). 배치를 키우거나 프리믹스로 계량하세요."
                )
        subtotal = round(subtotal, ROUND_DECIMALS)
        scaled_phases.append(
            ScaledPhase(
                name=phase.name,
                process=phase.process,
                ingredients=scaled_ings,
                subtotal_g=subtotal,
            )
        )

    total_g = round(sum(p.subtotal_g for p in scaled_phases), ROUND_DECIMALS)

    # 반올림 누적 오차 허용치: 원료 수 × 0.005g + target의 0.01%(처방 합계 허용오차)
    tolerance = n_ingredients * 0.005 + max(0.01, 0.0001 * target_g)
    total_ok = abs(total_g - target_g) <= tolerance
    if not total_ok:
        warnings.append(
            f"합계 불일치: 환산 합계 {total_g:.2f}g ≠ 목표 {target_g:g}g "
            f"(허용오차 {tolerance:.3f}g 초과)"
        )

    return ScaleResult(
        product=formula.product,
        slug=formula.slug,
        version=formula.version,
        target_g=target_g,
        phases=scaled_phases,
        total_g=total_g,
        total_ok=total_ok,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 2. batch_sheet
# ---------------------------------------------------------------------------
def batch_sheet(
    formula: Formula,
    target_g: float,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient] | None = None,
    batch_no: str | None = None,
    batch_date: date_cls | str | None = None,
    min_weighable_g: float = DEFAULT_MIN_WEIGHABLE_G,
) -> str:
    """배치 지시서를 마크다운 문자열로 반환한다.

    상별 원료/목표%/목표g 표, 공정 순서(process), 실측g 빈 칸,
    배치번호·날짜 자리를 포함한다.
    """
    result = scale(
        formula, target_g, ingredients=ingredients, min_weighable_g=min_weighable_g
    )

    no = batch_no if batch_no else "________________"
    if batch_date is None:
        date_str = "____-__-__"
    elif isinstance(batch_date, date_cls):
        date_str = batch_date.isoformat()
    else:
        date_str = str(batch_date)

    lines: list[str] = []
    lines.append(f"# 배치 지시서 — {formula.product} (v{formula.version})")
    lines.append("")
    lines.append(f"- 처방: `{formula.slug}` v{formula.version} ({formula.status.value})")
    lines.append(f"- 제품 형태: {formula.product_type.value}")
    lines.append(f"- 목표 배치: **{target_g:g} g**")
    lines.append(f"- 배치번호: {no}")
    lines.append(f"- 제조일자: {date_str}")
    lines.append(f"- 제조자: ________________")
    lines.append("")

    for phase in result.phases:
        lines.append(f"## 상 {phase.name}")
        lines.append("")
        lines.append(f"- 공정: {phase.process or '________________________________'}")
        lines.append("")
        lines.append("| 원료 | 목표 % | 목표 g | 실측 g |")
        lines.append("| --- | ---: | ---: | ---: |")
        for ing in phase.ingredients:
            flag = "" if ing.weighable else " ⚠️"
            lines.append(
                f"| {ing.name}{flag} | {ing.percent:g} | {ing.grams:.2f} | |"
            )
        lines.append(f"| **상 {phase.name} 소계** | | **{phase.subtotal_g:.2f}** | |")
        lines.append("")

    lines.append("| **전체 합계** | | **{:.2f}** | |".format(result.total_g))
    lines.append("")

    if result.warnings:
        lines.append("## ⚠️ 경고")
        lines.append("")
        for w in result.warnings:
            lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. scale_report
# ---------------------------------------------------------------------------
def scale_report(
    formula: Formula,
    from_g: float,
    to_g: float,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
) -> ScaleReport:
    """스케일업 리스크를 정성적으로 평가한다.

    - 왁스/버터 카테고리 합계 비율이 10%를 넘으면 냉각 속도 리스크 경고
    - 유화제(계면활성제) 카테고리가 있으면 별도 경고
    - 둘 다 없으면(단순 오일/알코올 용액) "스케일업 리스크 낮음"

    물성을 정량 예측하지 않는 정성적 경고다.
    """
    idx = _as_index(ingredients)

    wax_butter_percent = 0.0
    emulsifier_ingredients: list[str] = []
    for fi in (i for p in formula.phases for i in p.ingredients):
        ing = idx.get(fi.id)
        category = ing.category if ing else None
        if category in WAX_BUTTER_CATEGORIES:
            wax_butter_percent += fi.percent
        if category in EMULSIFIER_CATEGORIES:
            emulsifier_ingredients.append(ing.name if ing else fi.id)

    wax_butter_percent = round(wax_butter_percent, 4)
    warnings: list[str] = []

    if wax_butter_percent > WAX_BUTTER_RISK_THRESHOLD:
        warnings.append(
            f"왁스/버터 계열이 {wax_butter_percent:g}% (>{WAX_BUTTER_RISK_THRESHOLD:g}%)입니다. "
            f"배치가 커지면 냉각 속도가 느려져 왁스 결정 구조가 달라지고 "
            f"경도·발림이 변할 수 있습니다. 파일럿 배치 필수."
        )

    if emulsifier_ingredients:
        joined = ", ".join(dict.fromkeys(emulsifier_ingredients))
        warnings.append(
            f"유화제 계열 원료({joined})가 있습니다. 교반 강도·냉각 프로파일이 "
            f"유화 안정성에 영향을 줄 수 있으니 스케일업 시 파일럿으로 확인하세요."
        )

    if warnings:
        risk_level = "높음"
    else:
        risk_level = "낮음"
        warnings.append(
            "스케일업 리스크 낮음: 왁스/버터·유화제가 없는 단순 오일/알코올 용액은 "
            "배치 크기에 물성이 크게 민감하지 않습니다."
        )

    return ScaleReport(
        slug=formula.slug,
        version=formula.version,
        from_g=from_g,
        to_g=to_g,
        wax_butter_percent=wax_butter_percent,
        emulsifier_ingredients=list(dict.fromkeys(emulsifier_ingredients)),
        risk_level=risk_level,
        warnings=warnings,
    )


__all__ = [
    "ROUND_DECIMALS",
    "DEFAULT_MIN_WEIGHABLE_G",
    "WAX_BUTTER_RISK_THRESHOLD",
    "ScaledIngredient",
    "ScaledPhase",
    "ScaleResult",
    "ScaleReport",
    "scale",
    "batch_sheet",
    "scale_report",
]
