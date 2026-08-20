"""배치 계산 엔진 테스트."""

from __future__ import annotations

import pytest

from brandlab.batch import batch_sheet, scale, scale_report
from brandlab.loader import load_formula, load_ingredients
from brandlab.models import Formula


@pytest.fixture
def ingredients(project_root):
    return load_ingredients(project_root / "data" / "ingredients.yaml")


@pytest.fixture
def cleansing_balm(project_root, ingredient_ids, packaging_ids):
    return load_formula(
        project_root / "formulas" / "cleansing-balm" / "v1.yaml",
        ingredient_ids=ingredient_ids,
        packaging_ids=packaging_ids,
    )


@pytest.fixture
def face_oil(project_root, ingredient_ids, packaging_ids):
    return load_formula(
        project_root / "formulas" / "face-oil" / "v1.yaml",
        ingredient_ids=ingredient_ids,
        packaging_ids=packaging_ids,
    )


# ---------------------------------------------------------------------------
# scale
# ---------------------------------------------------------------------------
def test_scale_100_to_500_is_exactly_5x(cleansing_balm, ingredients):
    at100 = scale(cleansing_balm, 100, ingredients=ingredients)
    at500 = scale(cleansing_balm, 500, ingredients=ingredients)

    g100 = {i.id: i.grams for p in at100.phases for i in p.ingredients}
    g500 = {i.id: i.grams for p in at500.phases for i in p.ingredients}

    assert g100.keys() == g500.keys()
    for ing_id, grams in g100.items():
        assert g500[ing_id] == pytest.approx(grams * 5)

    # 100g 처방이므로 percent 값 == 100g 목표 g
    assert g100["mct"] == pytest.approx(40.0)
    assert g500["mct"] == pytest.approx(200.0)


def test_scale_total_matches_target(cleansing_balm, ingredients):
    result = scale(cleansing_balm, 500, ingredients=ingredients)
    assert result.total_ok
    assert result.total_g == pytest.approx(500.0)
    # 상별 소계 합 == 전체 합계
    assert sum(p.subtotal_g for p in result.phases) == pytest.approx(result.total_g)


def test_scale_rejects_nonpositive(cleansing_balm):
    with pytest.raises(ValueError):
        scale(cleansing_balm, 0)


def _formula_with_trace(percent_trace: float) -> Formula:
    """미량 원료 하나가 있는 처방(합계 100)."""
    return Formula.model_validate(
        {
            "product": "미량테스트",
            "slug": "trace",
            "version": 1,
            "product_type": "leave_on",
            "status": "개발중",
            "base_batch_g": 100,
            "phases": [
                {
                    "name": "A",
                    "ingredients": [
                        {"id": "mct", "percent": 100 - percent_trace},
                        {"id": "tocopherol", "percent": percent_trace},
                    ],
                }
            ],
        }
    )


def test_scale_below_resolution_warns():
    # 0.3% 원료 → 10g 배치 → 0.03g → 계량 불가 경고
    formula = _formula_with_trace(0.3)
    result = scale(formula, 10)

    trace = next(i for p in result.phases for i in p.ingredients if i.id == "tocopherol")
    assert trace.grams == pytest.approx(0.03)
    assert not trace.weighable
    assert result.unweighable  # 경고 대상 존재
    assert any("계량 불가" in w for w in result.warnings)


def test_scale_trace_ok_at_large_batch():
    # 같은 0.3% 원료라도 1000g 배치면 3.0g → 계량 가능
    formula = _formula_with_trace(0.3)
    result = scale(formula, 1000)
    trace = next(i for p in result.phases for i in p.ingredients if i.id == "tocopherol")
    assert trace.grams == pytest.approx(3.0)
    assert trace.weighable
    assert not result.unweighable


# ---------------------------------------------------------------------------
# scale_report
# ---------------------------------------------------------------------------
def _wax_formula(wax_percent: float) -> Formula:
    return Formula.model_validate(
        {
            "product": "왁스테스트",
            "slug": "waxy",
            "version": 1,
            "product_type": "leave_on",
            "status": "개발중",
            "base_batch_g": 100,
            "phases": [
                {
                    "name": "A",
                    "ingredients": [
                        {"id": "beeswax", "percent": wax_percent},
                        {"id": "mct", "percent": 100 - wax_percent},
                    ],
                }
            ],
        }
    )


def test_scale_report_wax_warning(ingredients):
    # 왁스 21% > 10% → 스케일업 경고
    formula = _wax_formula(21.0)
    report = scale_report(formula, 100, 1000, ingredients=ingredients)
    assert report.wax_butter_percent == pytest.approx(21.0)
    assert report.risk_level == "높음"
    assert any("파일럿 배치 필수" in w for w in report.warnings)


def test_scale_report_wax_under_threshold_no_warning(ingredients):
    # 왁스 8% ≤ 10% → 왁스 경고 없음(단순 용액 취급)
    formula = _wax_formula(8.0)
    report = scale_report(formula, 100, 1000, ingredients=ingredients)
    assert report.risk_level == "낮음"
    assert not any("냉각 속도" in w for w in report.warnings)


def test_scale_report_emulsifier_warning(cleansing_balm, ingredients):
    # 클렌징밤: 계면활성제(폴리소르베이트80/올리브리퀴드) 존재
    report = scale_report(cleansing_balm, 100, 500, ingredients=ingredients)
    assert report.has_emulsifier
    assert report.risk_level == "높음"
    assert any("유화제" in w for w in report.warnings)


def test_scale_report_low_risk_simple_solution(face_oil, ingredients):
    # 페이스오일: 오일/산화방지제만 → 리스크 낮음
    report = scale_report(face_oil, 100, 1000, ingredients=ingredients)
    assert report.risk_level == "낮음"
    assert not report.has_emulsifier
    assert report.wax_butter_percent == 0
    assert any("리스크 낮음" in w for w in report.warnings)


# ---------------------------------------------------------------------------
# batch_sheet
# ---------------------------------------------------------------------------
def test_batch_sheet_contents(cleansing_balm, ingredients):
    md = batch_sheet(cleansing_balm, 500, ingredients=ingredients, batch_no="B-001")
    assert "# 배치 지시서" in md
    assert "B-001" in md
    assert "제조일자" in md
    assert "실측 g" in md           # 손으로 적을 빈 칸 컬럼
    assert "상 A" in md
    assert "70~75도" in md          # process 필드 출력
    assert "200.00" in md           # mct 40% of 500g
    assert "전체 합계" in md
