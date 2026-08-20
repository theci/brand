"""처방(Formula) 검증 로직 테스트: percent 합계, 필수 필드."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from brandlab.models import Formula, ProductType


def _base(**overrides):
    """percent 합계 100인 최소 유효 처방 dict."""
    data = {
        "product": "테스트",
        "slug": "test",
        "version": 1,
        "product_type": "leave_on",
        "status": "개발중",
        "base_batch_g": 100,
        "phases": [
            {
                "name": "A",
                "ingredients": [
                    {"id": "mct", "percent": 60.0},
                    {"id": "jojoba-oil", "percent": 40.0},
                ],
            }
        ],
    }
    data.update(overrides)
    return data


def test_valid_formula_sum_100():
    f = Formula.model_validate(_base())
    assert f.total_percent == pytest.approx(100.0)
    assert f.product_type is ProductType.LEAVE_ON


def test_sum_within_tolerance_ok():
    # 100.005 는 ±0.01 이내 → 통과
    data = _base(
        phases=[
            {
                "name": "A",
                "ingredients": [
                    {"id": "mct", "percent": 60.005},
                    {"id": "jojoba-oil", "percent": 40.0},
                ],
            }
        ]
    )
    f = Formula.model_validate(data)
    assert abs(f.total_percent - 100.0) <= 0.01


def test_sum_too_low_fails():
    data = _base(
        phases=[{"name": "A", "ingredients": [{"id": "mct", "percent": 99.0}]}]
    )
    with pytest.raises(ValidationError, match="합계"):
        Formula.model_validate(data)


def test_sum_too_high_fails():
    data = _base(
        phases=[
            {
                "name": "A",
                "ingredients": [
                    {"id": "mct", "percent": 60.0},
                    {"id": "jojoba-oil", "percent": 40.5},
                ],
            }
        ]
    )
    with pytest.raises(ValidationError, match="합계"):
        Formula.model_validate(data)


def test_sum_just_outside_tolerance_fails():
    # 100.02 는 ±0.01 초과 → 실패
    data = _base(
        phases=[
            {
                "name": "A",
                "ingredients": [
                    {"id": "mct", "percent": 60.02},
                    {"id": "jojoba-oil", "percent": 40.0},
                ],
            }
        ]
    )
    with pytest.raises(ValidationError):
        Formula.model_validate(data)


def test_product_type_required():
    data = _base()
    del data["product_type"]
    with pytest.raises(ValidationError, match="product_type"):
        Formula.model_validate(data)


def test_invalid_product_type_value_fails():
    with pytest.raises(ValidationError):
        Formula.model_validate(_base(product_type="wash_off"))


def test_negative_percent_fails():
    data = _base(
        phases=[
            {
                "name": "A",
                "ingredients": [
                    {"id": "mct", "percent": -1.0},
                    {"id": "jojoba-oil", "percent": 101.0},
                ],
            }
        ]
    )
    with pytest.raises(ValidationError):
        Formula.model_validate(data)
