"""화학제품안전법 레짐 테스트 (P10)."""

from __future__ import annotations

import pytest

from brandlab.core.models import Formula
from brandlab.loader import BrandLab, load_chemical_safety_fees
from brandlab.regimes import get_regime


def _chem_formula(category: str, **over) -> Formula:
    data = {
        "product": "테스트생활화학제품",
        "slug": "chem-test",
        "version": 1,
        "regime": "chemical_safety",
        "product_category": category,
        "product_type": "leave_on",  # placeholder (화학제품안전법 미사용)
        "status": "개발중",
        "base_batch_g": 100,
        "phases": [
            {
                "name": "A",
                "ingredients": [
                    {"id": "ethanol", "percent": 80.0},
                    {"id": "water", "percent": 20.0},
                ],
            }
        ],
    }
    data.update(over)
    return Formula.model_validate(data)


@pytest.fixture
def chem(project_root):
    return get_regime("chemical_safety", project_root)


# ---------------------------------------------------------------------------
# SKU 확장 비용 — 화장품과 정반대
# ---------------------------------------------------------------------------
def test_diffuser_sku_expansion_3_is_810000(chem):
    # 방향제_지속방출형 시험비 270,000 → SKU 3개 = 810,000
    f = _chem_formula("방향제_지속방출형")
    assert chem.sku_expansion_cost(f) == 270000
    assert chem.sku_expansion_cost(f) * 3 == 810000


def test_cosmetics_sku_expansion_3_is_zero(project_root):
    # 대비: 화장품 SKU 3개 = 0원
    cosm = get_regime("cosmetics", project_root)
    lab = BrandLab.load(project_root)
    f = next(x for x in lab.formulas if x.slug == "cleansing-balm")
    assert cosm.sku_expansion_cost(f) * 3 == 0


def test_entry_cost_and_lead_time_from_fees(chem, project_root):
    fees = load_chemical_safety_fees(project_root / "data" / "regulatory")
    f = _chem_formula("방향제_비분사형")
    cost = chem.entry_cost(f)
    assert cost.entry_cost == fees.categories["방향제_비분사형"].fee
    assert chem.lead_time_days(f) == fees.categories["방향제_비분사형"].lead_time_days


def test_renewal_is_3_years(chem):
    f = _chem_formula("방향제_지속방출형")
    assert chem.renewal_period_years(f) == 3


# ---------------------------------------------------------------------------
# 경제성 경고
# ---------------------------------------------------------------------------
def test_fabric_softener_surfactant_cost_warning(chem):
    # 섬유유연제 계면활성제 함유(1,970,000원) → 진입비용 과도 warning
    f = _chem_formula("섬유유연제_계면활성제_함유")
    findings = chem.validate(f)
    assert any(
        x.code == "chem.cost.high" and x.level == "warning" for x in findings
    )


def test_long_lead_time_warning(chem):
    # 세탁세제(40일) → 시험 기간 장기 warning
    f = _chem_formula("세탁세제_계면활성제_미함유")
    findings = chem.validate(f)
    assert any(x.code == "chem.leadtime.long" for x in findings)


def test_short_lead_time_no_warning(chem):
    # 방향제_지속방출형(9일) → 기간 경고 없음
    f = _chem_formula("방향제_지속방출형")
    findings = chem.validate(f)
    assert not any(x.code == "chem.leadtime.long" for x in findings)


# ---------------------------------------------------------------------------
# 금지·제한물질 미입력 → 경고 (조용히 통과 금지)
# ---------------------------------------------------------------------------
def test_empty_substance_data_warns(chem):
    f = _chem_formula("방향제_비분사형")
    findings = chem.validate(f)
    assert any(x.code == "chem.substances.no_data" for x in findings)


# ---------------------------------------------------------------------------
# 품목 코드 문제
# ---------------------------------------------------------------------------
def test_missing_category_error(chem):
    f = _chem_formula("방향제_비분사형")
    f = f.model_copy(update={"product_category": None})
    findings = chem.validate(f)
    assert any(x.code == "chem.category.missing" and x.level == "error" for x in findings)


def test_unknown_category_error(chem):
    f = _chem_formula("존재하지않는품목")
    findings = chem.validate(f)
    assert any(x.code == "chem.category.unknown" for x in findings)


def test_cost_raises_on_missing_category(chem):
    f = _chem_formula("방향제_비분사형").model_copy(update={"product_category": None})
    with pytest.raises(ValueError):
        chem.sku_expansion_cost(f)


# ---------------------------------------------------------------------------
# 라벨 스펙 — 화장품과 다른 필수 항목
# ---------------------------------------------------------------------------
def test_label_spec_has_report_number(chem):
    f = _chem_formula("방향제_비분사형")
    spec = chem.label_spec(f)
    keys = {i.key for i in spec.items}
    assert "report_number" in keys        # 신고번호 자리
    assert "safety_conformity" in keys    # 안전기준 적합확인
    assert "child_protection" in keys     # 어린이보호포장 여부


# ---------------------------------------------------------------------------
# 실데이터 예시 처방
# ---------------------------------------------------------------------------
def test_example_chem_formulas_loaded(project_root):
    lab = BrandLab.load(project_root)
    chem_formulas = [f for f in lab.formulas if f.regime == "chemical_safety"]
    slugs = {f.slug for f in chem_formulas}
    assert {"room-spray", "fabric-deodorizer"} <= slugs
    chem = get_regime("chemical_safety", project_root)
    for f in chem_formulas:
        assert chem.sku_expansion_cost(f) > 0  # 화장품과 달리 0이 아님
