"""마스터/설정/규제 데이터 로드 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from brandlab.loader import (
    load_allergens,
    load_config,
    load_ingredients,
    load_limits,
    load_packaging,
)


def test_load_ingredients_ok(project_root):
    master = load_ingredients(project_root / "data" / "ingredients.yaml")
    # 요구사항: 20종 이상
    assert len(master.ingredients) >= 20
    # 필수 INCI 원료가 존재하는지 스팟 체크
    idx = master.index()
    assert idx["mct"].inci == "Caprylic/Capric Triglyceride"
    assert idx["beeswax"].inci == "Cera Alba (Beeswax)"
    assert idx["polysorbate-80"].inci == "Polysorbate 80"


def test_ingredient_ids_unique(project_root):
    master = load_ingredients(project_root / "data" / "ingredients.yaml")
    ids = [i.id for i in master.ingredients]
    assert len(ids) == len(set(ids))


def test_duplicate_ingredient_id_fails():
    from brandlab.models import IngredientMaster

    data = {
        "ingredients": [
            {"id": "mct", "name": "A", "inci": "A", "category": "에몰리언트"},
            {"id": "mct", "name": "B", "inci": "B", "category": "에몰리언트"},
        ]
    }
    with pytest.raises(ValidationError):
        IngredientMaster.model_validate(data)


def test_load_packaging_ok(project_root):
    master = load_packaging(project_root / "data" / "packaging.yaml")
    assert "jar-50ml" in master.index()


def test_load_config_ok(project_root):
    cfg = load_config(project_root / "data" / "config.yaml")
    assert cfg.brand_name
    assert cfg.default_batch_g > 0


def test_load_regulatory_ok(project_root):
    allergens = load_allergens(project_root / "data" / "regulatory" / "cosmetics" / "allergens.yaml")
    limits = load_limits(project_root / "data" / "regulatory" / "cosmetics" / "limits.yaml")
    assert "linalool" in allergens.index()
    assert all(lim.max_percent > 0 for lim in limits.limits)
