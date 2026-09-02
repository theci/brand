"""templates: 제형 템플릿이 검증된 골격 처방을 만드는지 테스트."""

from __future__ import annotations

import pytest

from brandlab.checks import check_formula
from brandlab.core.models import Formula
from brandlab.loader import BrandLab
from brandlab.templates import TEMPLATES, instantiate, list_templates


def test_list_templates():
    keys = {k for k, _, _ in list_templates()}
    assert keys == set(TEMPLATES)


@pytest.mark.parametrize("key", list(TEMPLATES))
def test_template_is_valid_formula_with_real_refs(key):
    lab = BrandLab.load()
    ing_ids = set(lab.ingredients.index())
    pkg_ids = set(lab.packaging.index())
    data = instantiate(key, slug=f"tmpl-{key}", version=1)

    # 1) 구조(percent 합계 100 포함) 검증
    f = Formula.model_validate(data)
    assert abs(f.total_percent - 100.0) < 0.01

    # 2) 참조 무결성 — 템플릿이 실제 마스터 원료/포장만 참조
    assert set(f.ingredient_ids()) <= ing_ids, f"{key}: 없는 원료 참조"
    assert {p.id for p in f.packaging} <= pkg_ids, f"{key}: 없는 포장 참조"


def test_lotion_template_passes_hlb():
    # 로션 템플릿은 HLB 균형을 맞춘 골격이라 사전점검 '위험'이 아니어야 한다.
    lab = BrandLab.load()
    f = Formula.model_validate(instantiate("basic-lotion", slug="tmpl-lotion", version=1))
    res = check_formula(f, ingredients=lab.ingredients, limits=lab.limits)
    assert res.hlb.verdict in {"적합", "주의"}
    assert res.hlb.verdict != "위험"


def test_instantiate_custom_product_name():
    data = instantiate("face-oil", slug="my-oil", version=2, product="장미 페이스 오일")
    assert data["product"] == "장미 페이스 오일"
    assert data["slug"] == "my-oil"
    assert data["version"] == 2


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        instantiate("nope", slug="x")
