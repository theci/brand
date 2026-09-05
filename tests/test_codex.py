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


def test_codex_master_linked_entries_resolve(project_root):
    """마스터에 있는 id는 정상 연결되고, 학습 전용(마스터에 없는) 항목은 허용된다.

    도감은 계산용 마스터와 분리되어 '공용 팔레트 백과'로 넓게 성장할 수 있다.
    마스터에 없는 항목은 category로 분류되어야 브라우징에서 묶인다.
    """
    codex = load_codex(project_root / "data" / "ingredient_codex.yaml")
    master = load_ingredients(project_root / "data" / "ingredients.yaml").index()
    # 마스터에 연결된 항목은 실제로 그 원료를 가리킨다
    linked = [e for e in codex.entries if e.id in master]
    assert linked, "마스터 연동 항목이 하나도 없다"
    # 학습 전용(마스터에 없는) 항목은 분류(category)가 있어 카테고리 필터에 잡힌다
    learning_only = [e for e in codex.entries if e.id not in master]
    assert all(e.category for e in learning_only), (
        "학습 전용 항목은 category가 있어야 한다: "
        f"{[e.id for e in learning_only if not e.category]}"
    )


def test_codex_covers_scenario_formula(project_root):
    """시나리오 처방(daily-lotion v2) 원료는 모두 도감에 있어야 한다."""
    from brandlab.loader import load_formula

    codex = load_codex(project_root / "data" / "ingredient_codex.yaml").index()
    f = load_formula(project_root / "formulas" / "daily-lotion" / "v2.yaml")
    fids = {i.id for ph in f.phases for i in ph.ingredients}
    missing = sorted(fids - set(codex))
    assert missing == [], f"도감에 없는 처방 원료: {missing}"


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
