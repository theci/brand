"""전성분 표시 생성기 + 규정 체커 테스트."""

from __future__ import annotations

from datetime import date

import pytest

from brandlab.labeling import (
    DISCLAIMER,
    allergen_check,
    freshness_check,
    inci_list,
    labeling_requirements,
    limit_check,
    screen,
)
from brandlab.loader import (
    BrandLab,
    load_allergens,
    load_ingredients,
    load_labeling_rules,
    load_limits,
)
from brandlab.models import (
    Allergen,
    AllergenContent,
    AllergenList,
    AllergenThresholds,
    Formula,
    Ingredient,
    IngredientMaster,
    LabelingRules,
    LimitList,
)


# ---------------------------------------------------------------------------
# 픽스처: 통제된 규칙/원료/알러젠
# ---------------------------------------------------------------------------
@pytest.fixture
def rules() -> LabelingRules:
    return LabelingRules(
        last_updated=date(2026, 8, 1),
        stale_after_days=180,
        ingredient_order_threshold_percent=1.0,
        allergen_thresholds=AllergenThresholds(leave_on=0.001, rinse_off=0.01),
        full_labeling_volume_ml=50,
        full_labeling_weight_g=50,
        minimal_labeling_volume_ml=10,
        minimal_labeling_weight_g=10,
        minimal_items=["명칭", "상호", "가격", "제조번호", "사용기한"],
        min_font_size_pt=5,
    )


@pytest.fixture
def allergens_db() -> AllergenList:
    return AllergenList(
        last_updated=date(2026, 8, 1),
        allergens=[
            Allergen(id="limonene", name="리모넨", inci="Limonene"),
            Allergen(id="linalool", name="리날룰", inci="Linalool"),
        ],
    )


@pytest.fixture
def ing_master() -> IngredientMaster:
    return IngredientMaster(
        ingredients=[
            Ingredient(id="oilA", name="오일A", inci="Oil A", category="에몰리언트"),
            Ingredient(id="oilB", name="오일B", inci="Oil B", category="에몰리언트"),
            Ingredient(id="thickener", name="점증제", inci="Thickener", category="점증제"),
            Ingredient(
                id="fragrance",
                name="향료",
                inci="Parfum",
                category="에센셜오일",
                fragrance=True,
                allergens=[AllergenContent(id="limonene", percent=5.0)],
            ),
        ]
    )


def _formula(**over) -> Formula:
    data = {
        "product": "테스트",
        "slug": "test",
        "version": 1,
        "product_type": "rinse_off",
        "status": "개발중",
        "base_batch_g": 100,
        "phases": [
            {
                "name": "A",
                "ingredients": [
                    {"id": "oilA", "percent": 60.0},
                    {"id": "oilB", "percent": 38.7},
                    {"id": "thickener", "percent": 1.0},
                    {"id": "fragrance", "percent": 0.3},
                ],
            }
        ],
    }
    data.update(over)
    return Formula.model_validate(data)


# ---------------------------------------------------------------------------
# inci_list — 함량 순 + 1% 경계
# ---------------------------------------------------------------------------
def test_inci_order_descending_above_threshold(ing_master, rules):
    result = inci_list(_formula(), ing_master, rules)
    # >1% 성분만 정렬군, 내림차순
    assert result.ordered == [("Oil A", 60.0), ("Oil B", 38.7)]


def test_inci_one_percent_boundary(ing_master, rules):
    # thickener 정확히 1.0% → 순서무관군 (1% '이하'), fragrance는 착향제 → 순서무관군
    result = inci_list(_formula(), ing_master, rules)
    ordered_names = [n for n, _ in result.ordered]
    unordered_names = [n for n, _ in result.unordered]
    assert "Thickener" in unordered_names
    assert "Thickener" not in ordered_names
    assert "Parfum" in unordered_names  # 착향제는 함량과 무관하게 순서무관군


def test_inci_boundary_just_above(ing_master, rules):
    # 1.01% 성분은 정렬군에 포함
    f = _formula(
        phases=[
            {
                "name": "A",
                "ingredients": [
                    {"id": "oilA", "percent": 60.0},
                    {"id": "oilB", "percent": 37.99},
                    {"id": "thickener", "percent": 1.01},
                    {"id": "fragrance", "percent": 1.0},
                ],
            }
        ]
    )
    result = inci_list(f, ing_master, rules)
    ordered_names = [n for n, _ in result.ordered]
    assert "Thickener" in ordered_names


def test_inci_appends_declarable_allergen(ing_master, rules, allergens_db):
    # 향료 0.3% × 리모넨 5% = 0.015% > rinse_off 0.01% → INCI 목록에 Limonene 추가
    result = inci_list(_formula(), ing_master, rules, allergens_db)
    assert "Limonene" in result.allergen_inci
    assert result.text.endswith("Limonene")


# ---------------------------------------------------------------------------
# allergen_check — 핵심: 향료 0.3% 안 리모넨 5%
# ---------------------------------------------------------------------------
def test_allergen_fragrance_limonene_declared_rinse_off(ing_master, rules, allergens_db):
    f = _formula(product_type="rinse_off")
    result = allergen_check(f, ing_master, rules, allergens_db)
    assert result.threshold_percent == 0.01
    declared_ids = {x.allergen_id for x in result.declared}
    assert "limonene" in declared_ids
    lim = next(x for x in result.declared if x.allergen_id == "limonene")
    assert lim.concentration_percent == pytest.approx(0.015)
    assert lim.must_declare
    assert "향료" in lim.sources


def test_allergen_below_threshold_not_declared(ing_master, rules, allergens_db):
    # 향료를 0.15%로 낮추면 리모넨 = 0.0075% < 0.01% → 표기 불필요
    f = _formula(
        phases=[
            {
                "name": "A",
                "ingredients": [
                    {"id": "oilA", "percent": 60.0},
                    {"id": "oilB", "percent": 38.85},
                    {"id": "thickener", "percent": 1.0},
                    {"id": "fragrance", "percent": 0.15},
                ],
            }
        ],
        product_type="rinse_off",
    )
    result = allergen_check(f, ing_master, rules, allergens_db)
    assert not result.declared
    below_ids = {x.allergen_id for x in result.below_threshold}
    assert "limonene" in below_ids


def test_allergen_threshold_differs_by_product_type(ing_master, rules, allergens_db):
    # 같은 0.0075%라도 leave_on(0.001%)에서는 표기 필요
    f = _formula(
        phases=[
            {
                "name": "A",
                "ingredients": [
                    {"id": "oilA", "percent": 60.0},
                    {"id": "oilB", "percent": 38.85},
                    {"id": "thickener", "percent": 1.0},
                    {"id": "fragrance", "percent": 0.15},
                ],
            }
        ],
        product_type="leave_on",
    )
    result = allergen_check(f, ing_master, rules, allergens_db)
    assert result.threshold_percent == 0.001
    assert any(x.allergen_id == "limonene" for x in result.declared)


# ---------------------------------------------------------------------------
# labeling_requirements — 용량 경계
# ---------------------------------------------------------------------------
def test_requirement_full_over_50(rules):
    req = labeling_requirements(_formula(fill_volume_ml=100), rules)
    assert req.tier == "full"
    assert req.full_ingredient_list_required


def test_requirement_minimal_10_or_less(rules):
    req = labeling_requirements(_formula(fill_volume_ml=10), rules)
    assert req.tier == "minimal"
    assert not req.full_ingredient_list_required
    assert req.required_items == rules.minimal_items


def test_requirement_reduced_between(rules):
    req = labeling_requirements(_formula(fill_volume_ml=30), rules)
    assert req.tier == "reduced"


def test_requirement_exactly_50_is_reduced(rules):
    # 50ml '초과'가 필수 → 정확히 50은 reduced 구간
    req = labeling_requirements(_formula(fill_volume_ml=50), rules)
    assert req.tier == "reduced"


def test_requirement_uses_weight_when_no_volume(rules):
    req = labeling_requirements(
        _formula(fill_volume_ml=None, net_weight_g=100), rules
    )
    assert req.size_unit == "g"
    assert req.tier == "full"


def test_requirement_unknown_size(rules):
    req = labeling_requirements(_formula(fill_volume_ml=None), rules)
    assert req.tier == "unknown"
    assert req.full_ingredient_list_required  # 안전측


# ---------------------------------------------------------------------------
# limit_check — 미입력 상태 명시
# ---------------------------------------------------------------------------
def test_limit_check_empty_reports_missing_data(ing_master):
    empty = LimitList(last_updated=date(2026, 8, 1), limits=[])
    result = limit_check(_formula(), ing_master, empty)
    assert result.has_data is False
    assert result.warnings
    assert "미입력" in result.warnings[0]


def test_limit_check_flags_exceed(ing_master):
    from brandlab.models import IngredientLimit

    limits = LimitList(
        last_updated=date(2026, 8, 1),
        limits=[IngredientLimit(ingredient_id="fragrance", max_percent=0.2)],
    )
    # fragrance 0.3% > 한도 0.2% → 초과
    result = limit_check(_formula(), ing_master, limits)
    assert result.has_data
    assert result.violations
    assert result.violations[0].ingredient_id == "fragrance"


def test_limit_check_product_type_scoped(ing_master):
    from brandlab.models import IngredientLimit

    limits = LimitList(
        last_updated=date(2026, 8, 1),
        limits=[
            IngredientLimit(
                ingredient_id="fragrance", max_percent=0.2, product_type="leave_on"
            )
        ],
    )
    # 처방은 rinse_off → leave_on 전용 한도는 적용되지 않음
    result = limit_check(_formula(product_type="rinse_off"), ing_master, limits)
    assert not result.violations


# ---------------------------------------------------------------------------
# freshness_check — 180일 경과
# ---------------------------------------------------------------------------
def test_freshness_stale_warns():
    result = freshness_check(
        {"limits.yaml": date(2026, 1, 1)},
        stale_after_days=180,
        today=date(2026, 8, 1),  # 212일 경과
    )
    assert result.warnings
    assert result.findings[0].stale


def test_freshness_fresh_no_warn():
    result = freshness_check(
        {"limits.yaml": date(2026, 7, 1)},
        stale_after_days=180,
        today=date(2026, 8, 1),  # 31일 경과
    )
    assert not result.warnings


def test_freshness_missing_warns():
    result = freshness_check(
        {"limits.yaml": None}, stale_after_days=180, today=date(2026, 8, 1)
    )
    assert result.warnings
    assert result.findings[0].missing


# ---------------------------------------------------------------------------
# 실데이터 통합 + 면책 문구
# ---------------------------------------------------------------------------
def test_screen_on_real_data(project_root):
    lab = BrandLab.load(project_root)
    face_oil = next(f for f in lab.formulas if f.slug == "face-oil")
    result = screen(face_oil, lab, today=date(2026, 8, 20))

    # 페이스오일(leave_on)의 라벤더 → linalool 등 표기 대상
    declared_inci = {f.inci for f in result.allergens.declared}
    assert "Linalool" in declared_inci
    assert result.disclaimer == DISCLAIMER
    assert result.inci.text  # 전성분 문자열 생성됨


def test_soap_reactive_warning(project_root):
    lab = BrandLab.load(project_root)
    soap = next(f for f in lab.formulas if f.slug == "soap")
    result = inci_list(soap, lab.ingredients, lab.labeling_rules, lab.allergens)
    assert any("비누화" in w for w in result.warnings)


def test_real_labeling_rules_load(project_root):
    rules = load_labeling_rules(
        project_root / "data" / "regulatory" / "cosmetics" / "labeling_rules.yaml"
    )
    # 규제 수치가 YAML에서 로드되는지 확인 (코드 하드코딩 아님)
    assert rules.ingredient_order_threshold_percent == 1.0
    assert rules.allergen_thresholds.rinse_off == 0.01
    assert rules.allergen_thresholds.leave_on == 0.001
