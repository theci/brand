"""영양성분표 계산기.

배합비(%)와 원료의 100g당 영양성분으로 **완제품 영양성분표**를 만든다.
원리: 완제품 100g 중 원료 A가 p_A% → A는 p_A g → 기여 = (p_A/100) × A의 100g당 값.
percent 합계가 100이므로 각 원료 100g당 값을 (percent/100)로 가중합하면 완제품 100g당 값이 된다.

이 모듈은 레짐 무관 코어처럼 순수 계산만 한다(규제 판정은 regimes/food.py).
강조표시(무당류·저당 등) 임계값은 예시이며, 실제 표시기준 고시로 확인·교체해야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.models import Formula, IngredientMaster

# 강조표시 근사 임계값(완제품 100g 기준) — ※ 예시. 실제 표시기준 고시로 교체할 것.
_SUGAR_FREE_MAX_PER_100G = 0.5   # '무당류' 근사
_LOW_SUGAR_MAX_PER_100G = 5.0    # '저당' 근사
_LOW_SODIUM_MAX_PER_100G = 120.0  # '저나트륨' 근사(mg)


@dataclass
class NutritionValues:
    """영양성분 값 묶음(특정 기준량 기준)."""

    kcal: float = 0.0
    protein_g: float = 0.0
    fat_g: float = 0.0
    carb_g: float = 0.0
    sugar_g: float = 0.0
    sodium_mg: float = 0.0


@dataclass
class NutritionFacts:
    """완제품 영양성분표 계산 결과."""

    per_100g: NutritionValues
    serving_g: float | None = None
    per_serving: NutritionValues | None = None
    # 무당류/저당 등 강조표시 후보(예시 기준). 사람이 읽는 문장.
    emphasis_flags: list[str] = field(default_factory=list)
    # 영양성분이 없는 원료 등 계산 신뢰도 경고.
    warnings: list[str] = field(default_factory=list)


def _aggregate_percent(formula: Formula) -> dict[str, float]:
    agg: dict[str, float] = {}
    for fi in (i for p in formula.phases for i in p.ingredients):
        agg[fi.id] = agg.get(fi.id, 0.0) + fi.percent
    return agg


def nutrition_facts(
    formula: Formula, ingredients: IngredientMaster
) -> NutritionFacts:
    """완제품 100g(및 1회 제공량) 기준 영양성분표를 계산한다.

    - 원료에 nutrition이 없으면 그 원료 기여는 0으로 두고 warning을 남긴다
      (조용히 통과시키지 않는다).
    - formula.net_weight_g가 있으면 그 값을 1회 제공량(serving)으로 보고 함께 계산.
    """
    idx = ingredients.index()
    agg = _aggregate_percent(formula)

    per100 = NutritionValues()
    missing: list[str] = []
    for ing_id, pct in agg.items():
        ing = idx.get(ing_id)
        if ing is None or ing.nutrition is None:
            missing.append(ing_id)
            continue
        f = pct / 100.0
        n = ing.nutrition
        per100.kcal += f * n.kcal_per_100g
        per100.protein_g += f * n.protein_g
        per100.fat_g += f * n.fat_g
        per100.carb_g += f * n.carb_g
        per100.sugar_g += f * n.sugar_g
        per100.sodium_mg += f * n.sodium_mg

    warnings: list[str] = []
    if missing:
        warnings.append(
            f"영양성분이 없는 원료가 있어 계산에서 0으로 처리했습니다: {missing}. "
            "완제품 영양성분표가 실제보다 낮게 나올 수 있습니다."
        )

    # 1회 제공량(net_weight_g) 기준 환산
    serving_g = formula.net_weight_g
    per_serving: NutritionValues | None = None
    if serving_g:
        s = serving_g / 100.0
        per_serving = NutritionValues(
            kcal=per100.kcal * s,
            protein_g=per100.protein_g * s,
            fat_g=per100.fat_g * s,
            carb_g=per100.carb_g * s,
            sugar_g=per100.sugar_g * s,
            sodium_mg=per100.sodium_mg * s,
        )

    # 강조표시 후보(예시 기준) — 실제 표시기준 고시로 확인 필요.
    emphasis: list[str] = []
    if not missing:  # 결측이 있으면 강조표시 판단 보류
        if per100.sugar_g <= _SUGAR_FREE_MAX_PER_100G:
            emphasis.append("무당류 후보 (예시기준: 당류 ≤ 0.5g/100g · 고시 확인 필요)")
        elif per100.sugar_g <= _LOW_SUGAR_MAX_PER_100G:
            emphasis.append("저당 후보 (예시기준: 당류 ≤ 5g/100g · 고시 확인 필요)")
        if per100.sodium_mg <= _LOW_SODIUM_MAX_PER_100G:
            emphasis.append("저나트륨 후보 (예시기준: 나트륨 ≤ 120mg/100g · 고시 확인 필요)")

    return NutritionFacts(
        per_100g=per100,
        serving_g=serving_g,
        per_serving=per_serving,
        emphasis_flags=emphasis,
        warnings=warnings,
    )
