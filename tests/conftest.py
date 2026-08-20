"""pytest 공통 픽스처."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def ingredient_ids() -> set[str]:
    from brandlab.loader import load_ingredients

    return set(load_ingredients(PROJECT_ROOT / "data" / "ingredients.yaml").index())


@pytest.fixture
def packaging_ids() -> set[str]:
    from brandlab.loader import load_packaging

    return set(load_packaging(PROJECT_ROOT / "data" / "packaging.yaml").index())
