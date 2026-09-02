"""ingredients.yaml 필드 안전 갱신 테스트(주석·형식 보존)."""

from __future__ import annotations

import pytest

from brandlab.ingredient_edit import set_ingredient_fields

SAMPLE = """ingredients:
  - id: foo
    name: 푸
    inci: Foo
    category: 용제
    # 이 주석은 유지되어야 한다
    notes: hello
  - id: bar
    name: 바
    inci: Bar
    category: 용제
    density: 0.9   # 기존 밀도
"""


def test_insert_missing_fields_preserves_comments():
    out, applied = set_ingredient_fields(SAMPLE, "foo", {"cas": "56-81-5", "density": 1.26})
    assert applied == {"cas": "56-81-5", "density": 1.26}
    assert 'cas: "56-81-5"' in out
    assert "density: 1.26" in out
    # 주석과 다른 원료 블록은 그대로
    assert "# 이 주석은 유지되어야 한다" in out
    assert "id: bar" in out
    # 삽입 위치가 foo 블록 안(=bar 앞)인지 확인
    assert out.index('cas: "56-81-5"') < out.index("id: bar")


def test_replace_existing_field_keeps_inline_comment():
    out, applied = set_ingredient_fields(SAMPLE, "bar", {"density": 1.05})
    assert applied == {"density": 1.05}
    assert "density: 1.05   # 기존 밀도" in out
    # foo의 density는 없어야(bar만 건드림)
    assert out.count("density:") == 1


def test_none_values_skipped():
    out, applied = set_ingredient_fields(SAMPLE, "foo", {"cas": None, "density": 1.0})
    assert "cas" not in applied
    assert applied == {"density": 1.0}


def test_unknown_id_raises():
    with pytest.raises(KeyError):
        set_ingredient_fields(SAMPLE, "nope", {"cas": "56-81-5"})


def test_trailing_newline_preserved():
    out, _ = set_ingredient_fields(SAMPLE, "foo", {"cas": "56-81-5"})
    assert out.endswith("\n")
