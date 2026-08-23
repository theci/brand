"""식품 레짐 확장 테스트 (P-Food-1~3).

- P-Food-1: Ingredient.nutrition / food_grade 필드, 하위호환
- P-Food-2: FoodRegime (등록·검증·표시항목·비용)
- P-Food-3: nutrition_facts 계산
"""

from __future__ import annotations

import pytest

from brandlab.adcopy import lint
from brandlab.advisor import classify, compare, feasibility
from brandlab.core.models import Formula, ProductIntent
from brandlab.food import nutrition_facts
from brandlab.loader import BrandLab, load_ad_terms, load_food_allergens
from brandlab.regimes import Regime, available, get_regime
from brandlab.regimes.base import Finding, LabelSpec


def _mk_formula(ingredients: list[dict], *, regime: str = "food") -> Formula:
    """테스트용 최소 처방(합계 100)."""
    return Formula.model_validate(
        {
            "product": "테스트",
            "slug": "t",
            "version": 1,
            "regime": regime,
            "product_type": "leave_on",
            "status": "개발중",
            "base_batch_g": 100,
            "phases": [{"name": "A", "ingredients": ingredients}],
        }
    )


# ---------------------------------------------------------------------------
# P-Food-1: 코어 모델 확장 + 하위호환
# ---------------------------------------------------------------------------
def test_food_ingredient_has_nutrition(project_root):
    lab = BrandLab.load(project_root)
    idx = lab.ingredients.index()
    allulose = idx["allulose"]
    assert allulose.food_grade is True
    assert allulose.nutrition is not None
    assert allulose.nutrition.kcal_per_100g == 20


def test_cosmetic_ingredient_nutrition_is_none(project_root):
    # 기존 화장품 원료는 nutrition 없음(하위호환) — 선택 필드라 로드에 영향 없음.
    idx = BrandLab.load(project_root).ingredients.index()
    assert idx["glycerin"].nutrition is None
    assert idx["glycerin"].food_grade is False


def test_all_data_still_loads(project_root):
    # 코어 모델 변경 후에도 전체 데이터가 로드되어야 한다(회귀 방지).
    lab = BrandLab.load(project_root)
    slugs = {f.slug for f in lab.formulas}
    assert "low-sugar-jelly" in slugs
    assert "shampoo-bar" in slugs  # 기존 처방도 그대로


# ---------------------------------------------------------------------------
# P-Food-2: FoodRegime
# ---------------------------------------------------------------------------
def test_food_regime_registered():
    assert "food" in available()


def test_food_regime_conforms_protocol(project_root):
    regime = get_regime("food", project_root)
    assert isinstance(regime, Regime)
    assert regime.code == "food"
    assert regime.law_name


def test_food_sku_expansion_zero(project_root):
    regime = get_regime("food", project_root)
    jelly = next(f for f in BrandLab.load(project_root).formulas if f.slug == "low-sugar-jelly")
    assert regime.sku_expansion_cost(jelly) == 0
    assert regime.renewal_period_years(jelly) is None


def test_food_validate_clean_formula(project_root):
    regime = get_regime("food", project_root)
    jelly = next(f for f in BrandLab.load(project_root).formulas if f.slug == "low-sugar-jelly")
    findings = regime.validate(jelly)
    assert all(isinstance(f, Finding) for f in findings)
    # 젤리는 전부 food_grade 원료 → 등급 error가 없어야 한다.
    assert not any(f.code == "food.grade.not_food" for f in findings)
    # 금지/제한물질 데이터는 빈 껍데기 → '미입력' 경고가 있어야 한다(통과 아님).
    assert any(f.code == "food.substances.no_data" for f in findings)


def test_food_validate_rejects_non_food_grade(project_root):
    # 화장품 원료(글리세린, food_grade=False)를 식품 처방에 쓰면 error.
    regime = get_regime("food", project_root)
    f = _mk_formula([{"id": "glycerin", "percent": 100.0}])
    findings = regime.validate(f)
    assert any(f.code == "food.grade.not_food" and f.level == "error" for f in findings)


def test_food_validate_allergen_info(project_root):
    regime = get_regime("food", project_root)
    f = _mk_formula([{"id": "whey-protein-isolate", "percent": 100.0}])
    findings = regime.validate(f)
    allergen = [x for x in findings if x.code == "food.allergen.declare"]
    assert allergen and "milk" in allergen[0].message


def test_food_label_spec_is_food_shaped(project_root):
    spec = get_regime("food", project_root).label_spec(
        next(f for f in BrandLab.load(project_root).formulas if f.slug == "low-sugar-jelly")
    )
    assert isinstance(spec, LabelSpec)
    keys = {i.key for i in spec.items}
    assert "nutrition" in keys   # 영양성분표 (화장품 전성분과 다름)
    assert "allergen" in keys
    assert "ingredients" not in keys or "nutrition" in keys  # 식품형 표시


# ---------------------------------------------------------------------------
# P-Food-3: 영양성분 계산
# ---------------------------------------------------------------------------
def test_nutrition_facts_per_100g(project_root):
    lab = BrandLab.load(project_root)
    jelly = next(f for f in lab.formulas if f.slug == "low-sugar-jelly")
    facts = nutrition_facts(jelly, lab.ingredients)
    # 손계산: kcal = 0.25*20 + 0.08*335 + 0.10*200 = 51.8
    assert facts.per_100g.kcal == pytest.approx(51.8, abs=0.01)
    assert facts.per_100g.protein_g == pytest.approx(6.8, abs=0.01)   # 0.08*85
    assert facts.per_100g.sugar_g == pytest.approx(4.6, abs=0.01)     # 0.10*46
    assert facts.per_100g.sodium_mg == pytest.approx(4.22, abs=0.01)
    assert not facts.warnings  # 모든 원료에 nutrition 있음


def test_nutrition_facts_per_serving(project_root):
    lab = BrandLab.load(project_root)
    jelly = next(f for f in lab.formulas if f.slug == "low-sugar-jelly")
    facts = nutrition_facts(jelly, lab.ingredients)
    assert facts.serving_g == 30
    assert facts.per_serving is not None
    assert facts.per_serving.kcal == pytest.approx(51.8 * 0.3, abs=0.01)  # 15.54


def test_nutrition_facts_emphasis_low_sugar(project_root):
    lab = BrandLab.load(project_root)
    jelly = next(f for f in lab.formulas if f.slug == "low-sugar-jelly")
    facts = nutrition_facts(jelly, lab.ingredients)
    # 당류 4.6g/100g ≤ 5 → 저당 후보. 나트륨 4.22mg ≤ 120 → 저나트륨 후보.
    joined = " ".join(facts.emphasis_flags)
    assert "저당" in joined
    assert "저나트륨" in joined


def test_nutrition_facts_missing_warns(project_root):
    # nutrition 없는 원료(글리세린)가 섞이면 경고를 남긴다(조용히 0 처리 금지).
    lab = BrandLab.load(project_root)
    f = _mk_formula(
        [{"id": "allulose", "percent": 50.0}, {"id": "glycerin", "percent": 50.0}]
    )
    facts = nutrition_facts(f, lab.ingredients)
    assert facts.warnings
    assert "glycerin" in facts.warnings[0]


# ---------------------------------------------------------------------------
# P-Food-4: 건강기능식품 레짐 + advise 규칙 (일반식품 vs 건기식)
# ---------------------------------------------------------------------------
def test_hff_regime_registered_and_conforms(project_root):
    assert "health_functional_food" in available()
    regime = get_regime("health_functional_food", project_root)
    assert isinstance(regime, Regime)
    assert regime.code == "health_functional_food"


def test_classify_ingest_nourish_is_food(project_root):
    res = classify(ProductIntent(use="ingest", claims=["nourish"]), root=project_root)
    assert {c.regime_code for c in res.candidates} == {"food"}


def test_classify_ingest_functional_is_hff(project_root):
    res = classify(ProductIntent(use="ingest", claims=["blood_sugar"]), root=project_root)
    assert {c.regime_code for c in res.candidates} == {"health_functional_food"}


def test_compare_food_vs_hff_cost_gap(project_root):
    # 같은 섭취 제품이라도 '영양(일반식품)' vs '혈당(건기식)'은 비용이 천지차.
    intent = ProductIntent(use="ingest", claims=["nourish", "blood_sugar"])
    result = compare(intent, sku_count=3, horizon_years=5, root=project_root)
    rows = {r.candidate.regime_code: r for r in result.rows}
    assert "food" in rows and "health_functional_food" in rows
    assert rows["health_functional_food"].total_regulatory_cost == 3_000_000
    assert rows["food"].total_regulatory_cost < rows["health_functional_food"].total_regulatory_cost
    assert result.cheapest.candidate.regime_code == "food"
    assert "저렴" in result.summary


def test_feasibility_ingest_food_ok(project_root):
    r = feasibility(ProductIntent(use="ingest", claims=["nourish"]), root=project_root)
    assert r.verdict == "OK"


def test_feasibility_ingest_functional_caution(project_root):
    # 건기식 단독 경로 → 진입비용(제조업 허가) 임계 초과 → 예산 없어도 CAUTION.
    r = feasibility(ProductIntent(use="ingest", claims=["immune"]), root=project_root)
    assert r.verdict == "CAUTION"
    assert any("임계" in x or "초과" in x for x in r.reasons)


def test_hff_validate_warns_high_cost_and_burden(project_root):
    regime = get_regime("health_functional_food", project_root)
    f = _mk_formula([{"id": "allulose", "percent": 100.0}], regime="health_functional_food")
    findings = regime.validate(f)
    assert any(x.code == "hff.cost.high" and x.level == "warning" for x in findings)
    assert any(x.code == "hff.burden" for x in findings)
    # 식품용 원료라 등급 error는 없어야 한다.
    assert not any(x.code == "hff.grade.not_food" for x in findings)


# ---------------------------------------------------------------------------
# P-Food-5: 식품 알레르기 데이터 + 광고표현(식품표시광고법)
# ---------------------------------------------------------------------------
def test_food_allergens_loads(project_root):
    lst = load_food_allergens(project_root / "data" / "regulatory")
    idx = lst.index()
    assert "milk" in idx and idx["milk"].name == "우유"


def test_food_ad_terms_flags_functional_claims(project_root):
    terms = load_ad_terms(
        project_root / "data" / "regulatory" / "food" / "ad_terms.yaml"
    )
    r = lint("면역력 높이는 다이어트 젤리, 혈당 관리에 좋아요", terms)
    highs = {f.expression for f in r.findings if f.risk == "high"}
    assert {"면역력", "다이어트", "혈당"} <= highs


def test_food_validate_maps_allergen_name(project_root):
    # 원료의 food_allergen_ids(milk)가 한글명(우유)으로 매핑돼 안내되는지.
    regime = get_regime("food", project_root)
    f = _mk_formula([{"id": "whey-protein-isolate", "percent": 100.0}])
    msg = next(
        x.message for x in regime.validate(f) if x.code == "food.allergen.declare"
    )
    assert "우유" in msg and "milk" in msg
