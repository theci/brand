"""master_edit: 마스터 데이터 추가·삭제(주석 보존, 검증·롤백) 테스트."""

from __future__ import annotations

import pytest
import yaml

from brandlab.loader import load_ingredients, load_packaging
from brandlab.master_edit import (
    append_item,
    delete_item,
    render_ingredient_block,
    render_packaging_block,
    save_with_backup,
)

ING_YAML = """\
# 원료 마스터 (주석)
ingredients:
  # --- 오일 ---
  - id: mct
    name: 카프릴릭/카프릭 트리글리세라이드
    inci: Caprylic/Capric Triglyceride
    category: 에몰리언트
    price_per_kg: 15000

  - id: glycerin
    name: 글리세린
    inci: Glycerin
    category: 보습제
"""

PKG_YAML = """\
# 패키지 마스터 (주석)
packaging:
  - id: jar-50ml
    name: 50ml 유리 자
    type: jar
    volume_ml: 50
"""


def test_render_ingredient_block_parses_back():
    block = render_ingredient_block(
        {"id": "shea", "name": "시어버터", "inci": "Butyrospermum Parkii Butter",
         "category": "왁스", "price_per_kg": 20000.0, "has_coa": True}
    )
    parsed = yaml.safe_load(block)  # `- {...}` → 리스트 1개
    assert parsed[0]["id"] == "shea"
    assert parsed[0]["has_coa"] is True
    # None/빈 값 필드는 렌더링에서 제외
    assert "density" not in parsed[0]


def test_append_ingredient_roundtrips_and_keeps_comments(tmp_path):
    path = tmp_path / "ingredients.yaml"
    path.write_text(ING_YAML, encoding="utf-8")
    block = render_ingredient_block(
        {"id": "shea", "name": "시어버터", "inci": "Butyrospermum Parkii Butter",
         "category": "왁스"}
    )
    new_text = append_item(path.read_text(encoding="utf-8"), block)
    path.write_text(new_text, encoding="utf-8")

    master = load_ingredients(path)
    ids = set(master.index())
    assert {"mct", "glycerin", "shea"} <= ids
    # 기존 주석 보존
    assert "# 원료 마스터 (주석)" in new_text
    assert "# --- 오일 ---" in new_text


def test_delete_middle_item_keeps_others(tmp_path):
    path = tmp_path / "ingredients.yaml"
    path.write_text(ING_YAML, encoding="utf-8")
    new_text = delete_item(path.read_text(encoding="utf-8"), "mct")
    path.write_text(new_text, encoding="utf-8")

    master = load_ingredients(path)
    ids = set(master.index())
    assert ids == {"glycerin"}
    assert "# 원료 마스터 (주석)" in new_text  # 상단 주석 유지


def test_delete_missing_raises():
    with pytest.raises(KeyError):
        delete_item(ING_YAML, "does-not-exist")


def test_packaging_add_and_delete(tmp_path):
    path = tmp_path / "packaging.yaml"
    path.write_text(PKG_YAML, encoding="utf-8")
    block = render_packaging_block(
        {"id": "tube-10ml", "name": "10ml 튜브", "type": "tube", "volume_ml": 10.0}
    )
    path.write_text(append_item(path.read_text(encoding="utf-8"), block), encoding="utf-8")
    assert set(load_packaging(path).index()) == {"jar-50ml", "tube-10ml"}

    path.write_text(delete_item(path.read_text(encoding="utf-8"), "jar-50ml"), encoding="utf-8")
    assert set(load_packaging(path).index()) == {"tube-10ml"}


def test_save_with_backup_creates_backup(tmp_path):
    path = tmp_path / "ingredients.yaml"
    path.write_text(ING_YAML, encoding="utf-8")
    block = render_ingredient_block(
        {"id": "shea", "name": "시어버터", "inci": "X", "category": "왁스"}
    )
    save_with_backup(path, append_item(ING_YAML, block), load_ingredients)
    assert (tmp_path / "ingredients.yaml.bak").exists()
    assert set(load_ingredients(path).index()) == {"mct", "glycerin", "shea"}


def test_save_with_backup_rolls_back_on_invalid(tmp_path):
    path = tmp_path / "ingredients.yaml"
    path.write_text(ING_YAML, encoding="utf-8")
    # 중복 id를 추가 → 전체 검증(unique id)에서 실패해야 하고, 원문으로 롤백되어야 한다.
    dup = render_ingredient_block(
        {"id": "mct", "name": "중복", "inci": "X", "category": "테스트"}
    )
    with pytest.raises(Exception):
        save_with_backup(path, append_item(ING_YAML, dup), load_ingredients)
    # 롤백되어 원문 그대로
    assert path.read_text(encoding="utf-8") == ING_YAML
    assert set(load_ingredients(path).index()) == {"mct", "glycerin"}
