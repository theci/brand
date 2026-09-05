"""원료 도감(백과) 로드·검증 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from brandlab.loader import load_codex, load_ingredients
from brandlab.models import IngredientCodex


def test_load_codex_ok(project_root):
    codex = load_codex(project_root / "data" / "ingredient_codex.yaml")
    assert len(codex.entries) >= 5
    idx = codex.index()
    # 스팟 체크: 대표 원료의 요약이 채워져 있어야 한다
    assert "glycerin" in idx
    assert idx["glycerin"].summary


def test_codex_ids_exist_in_master(project_root):
    """도감의 모든 id는 원료 마스터에 실제로 존재해야 한다(고아 방지)."""
    codex = load_codex(project_root / "data" / "ingredient_codex.yaml")
    master = load_ingredients(project_root / "data" / "ingredients.yaml").index()
    orphans = [e.id for e in codex.entries if e.id not in master]
    assert orphans == [], f"마스터에 없는 도감 id: {orphans}"


def test_codex_entries_need_verification_default(project_root):
    """안전·함량 서술은 기본적으로 검증 필요로 표시되어야 한다."""
    codex = load_codex(project_root / "data" / "ingredient_codex.yaml")
    assert all(e.needs_verification for e in codex.entries)


def test_duplicate_codex_id_fails():
    data = {
        "entries": [
            {"id": "mct", "summary": "A"},
            {"id": "mct", "summary": "B"},
        ]
    }
    with pytest.raises(ValidationError):
        IngredientCodex.model_validate(data)


def test_missing_codex_file_returns_empty(tmp_path):
    codex = load_codex(tmp_path / "does_not_exist.yaml")
    assert codex.entries == []
