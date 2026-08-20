"""레짐 추상화 테스트 (P9)."""

from __future__ import annotations

import pytest

from brandlab.core.models import Formula
from brandlab.loader import BrandLab, load_regime_info
from brandlab.regimes import (
    CostBreakdown,
    Finding,
    LabelSpec,
    Regime,
    UnsupportedRegimeError,
    available,
    get_regime,
    regime_for,
    register,
)
from brandlab.regimes.registry import UnknownRegimeError


@pytest.fixture
def cosmetic_formula(project_root) -> Formula:
    lab = BrandLab.load(project_root)
    return next(f for f in lab.formulas if f.slug == "cleansing-balm")


# ---------------------------------------------------------------------------
# 모델: regime 필드
# ---------------------------------------------------------------------------
def test_formula_regime_defaults_to_cosmetics(cosmetic_formula):
    assert cosmetic_formula.regime == "cosmetics"


def test_migrated_formulas_have_regime(project_root):
    lab = BrandLab.load(project_root)
    # 모든 처방의 regime이 등록된 레짐이어야 한다(화장품 + 화학제품안전법 혼재).
    assert all(f.regime in available() for f in lab.formulas)
    # 기존 화장품 처방은 여전히 cosmetics.
    assert next(f for f in lab.formulas if f.slug == "cleansing-balm").regime == "cosmetics"


# ---------------------------------------------------------------------------
# 화장품 레짐 — SKU 확장 0원, 갱신 없음
# ---------------------------------------------------------------------------
def test_cosmetics_regime_conforms_protocol(project_root):
    regime = get_regime("cosmetics", project_root)
    assert isinstance(regime, Regime)
    assert regime.code == "cosmetics"
    assert regime.law_name


def test_cosmetics_sku_expansion_is_zero(cosmetic_formula, project_root):
    regime = get_regime("cosmetics", project_root)
    assert regime.sku_expansion_cost(cosmetic_formula) == 0
    assert regime.renewal_period_years(cosmetic_formula) is None


def test_cosmetics_entry_cost_from_data(cosmetic_formula, project_root):
    regime = get_regime("cosmetics", project_root)
    cost = regime.entry_cost(cosmetic_formula)
    info = load_regime_info("cosmetics", project_root / "data" / "regulatory")
    assert isinstance(cost, CostBreakdown)
    assert cost.entry_cost == info.entry_cost  # 코드가 아니라 YAML에서 온 값


def test_cosmetics_validate_returns_findings(cosmetic_formula, project_root):
    findings = get_regime("cosmetics", project_root).validate(cosmetic_formula)
    assert all(isinstance(f, Finding) for f in findings)
    assert all(f.level in {"error", "warning", "info"} for f in findings)


def test_cosmetics_label_spec(cosmetic_formula, project_root):
    spec = get_regime("cosmetics", project_root).label_spec(cosmetic_formula)
    assert isinstance(spec, LabelSpec)
    assert spec.items
    assert any(i.key == "ingredients" for i in spec.items)


# ---------------------------------------------------------------------------
# 미지원 레짐 — 명시적 거부 (조용히 통과 금지)
# ---------------------------------------------------------------------------
def test_biocide_validate_returns_error(cosmetic_formula, project_root):
    regime = get_regime("biocide", project_root)
    findings = regime.validate(cosmetic_formula)
    assert any(f.level == "error" for f in findings)
    assert any("1인 창업 규모" in f.message for f in findings)


def test_quasi_drug_validate_returns_error(cosmetic_formula, project_root):
    findings = get_regime("quasi_drug", project_root).validate(cosmetic_formula)
    assert any(f.level == "error" for f in findings)


def test_unsupported_cost_raises(cosmetic_formula, project_root):
    regime = get_regime("biocide", project_root)
    with pytest.raises(UnsupportedRegimeError):
        regime.entry_cost(cosmetic_formula)
    with pytest.raises(UnsupportedRegimeError):
        regime.sku_expansion_cost(cosmetic_formula)


def test_regime_for_uses_formula_field(project_root):
    lab = BrandLab.load(project_root)
    f = lab.formulas[0].model_copy(update={"regime": "biocide"})
    regime = regime_for(f, project_root)
    assert regime.code == "biocide"


# ---------------------------------------------------------------------------
# 새 레짐 추가 = registry에 한 줄
# ---------------------------------------------------------------------------
class _DummyRegime:
    code = "demo"
    law_name = "데모법"
    display_name = "데모"

    def __init__(self, root=None):
        pass

    def validate(self, product):
        return [Finding("info", "demo.ok", "데모 레짐")]

    def label_spec(self, product):
        return LabelSpec(regime_code="demo")

    def entry_cost(self, product):
        return CostBreakdown(regime_code="demo", entry_cost=0)

    def lead_time_days(self, product):
        return 0

    def sku_expansion_cost(self, product):
        return 0

    def renewal_period_years(self, product):
        return None


def test_register_new_regime_one_line(cosmetic_formula):
    register("demo", _DummyRegime)  # ← 한 줄
    assert "demo" in available()
    regime = get_regime("demo")
    assert isinstance(regime, Regime)
    assert regime.validate(cosmetic_formula)[0].code == "demo.ok"


def test_unknown_regime_raises():
    with pytest.raises(UnknownRegimeError):
        get_regime("nonexistent-regime")
