"""UI 헬퍼 및 원료 CoA/등급 필드 테스트 (Streamlit 페이지 자체는 제외)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from brandlab.loader import load_ingredients
from brandlab.models import Ingredient
from brandlab.ui import data_signature, ingredient_flags


# ---------------------------------------------------------------------------
# 모델 필드 기본값 (안전측)
# ---------------------------------------------------------------------------
def test_ingredient_coa_grade_defaults():
    ing = Ingredient(id="x", name="x", inci="X", category="에몰리언트")
    # 안전상 CoA는 기본 미보유(False), 화장품용은 기본 True
    assert ing.has_coa is False
    assert ing.cosmetic_grade is True


# ---------------------------------------------------------------------------
# 위험 플래그
# ---------------------------------------------------------------------------
def test_flags_none_for_clean_ingredient():
    ing = Ingredient(
        id="x", name="x", inci="X", category="에몰리언트",
        has_coa=True, cosmetic_grade=True,
    )
    assert ingredient_flags(ing) == []


def test_flags_candle_grade_and_no_coa():
    ing = Ingredient(
        id="c", name="캔들향", inci="Fragrance", category="착향제",
        has_coa=False, cosmetic_grade=False,
    )
    flags = ingredient_flags(ing)
    assert "화장품용 아님" in flags
    assert "CoA 없음" in flags


def test_real_data_flags(project_root):
    master = load_ingredients(project_root / "data" / "ingredients.yaml")
    idx = master.index()
    # 캔들용 향료는 화장품용 아님 플래그
    assert "화장품용 아님" in ingredient_flags(idx["candle-fragrance"])
    # CoA 없는 예시 원료
    assert "CoA 없음" in ingredient_flags(idx["sunflower-oil"])
    # 정상 원료는 플래그 없음
    assert ingredient_flags(idx["mct"]) == []


# ---------------------------------------------------------------------------
# 캐시 무효화 키 (mtime)
# ---------------------------------------------------------------------------
def test_data_signature_changes_on_mtime(tmp_path):
    (tmp_path / "data").mkdir()
    f = tmp_path / "data" / "a.yaml"
    f.write_text("brand_name: x\n", encoding="utf-8")

    sig1 = data_signature(tmp_path)
    assert sig1  # 비어있지 않음

    # mtime을 미래로 바꾸면 시그니처가 달라져야 함
    future = f.stat().st_mtime + 100
    os.utime(f, (future, future))
    sig2 = data_signature(tmp_path)
    assert sig1 != sig2


def test_data_signature_stable_without_change(project_root):
    assert data_signature(project_root) == data_signature(project_root)
