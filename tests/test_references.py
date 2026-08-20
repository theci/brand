"""처방 참조 무결성 및 예시 데이터 전체 로드 테스트."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from brandlab.loader import (
    BrandLab,
    ReferenceIntegrityError,
    iter_formula_paths,
    load_formula,
)


def test_all_example_formulas_load(project_root, ingredient_ids, packaging_ids):
    paths = iter_formula_paths(project_root / "formulas")
    # 클렌징밤/립밤/페이스오일/비누 4종
    assert len(paths) >= 4
    for p in paths:
        f = load_formula(
            p, ingredient_ids=ingredient_ids, packaging_ids=packaging_ids
        )
        assert abs(f.total_percent - 100.0) <= 0.01


def test_brandlab_load_all(project_root):
    lab = BrandLab.load(project_root)
    slugs = {f.slug for f in lab.formulas}
    assert {"cleansing-balm", "lip-balm", "face-oil", "soap"} <= slugs


def _write_formula(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "vX.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_unknown_ingredient_reference_fails(tmp_path, ingredient_ids, packaging_ids):
    path = _write_formula(
        tmp_path,
        """
        product: 잘못된처방
        slug: bad
        version: 1
        product_type: leave_on
        status: 개발중
        base_batch_g: 100
        phases:
          - name: A
            ingredients:
              - { id: mct, percent: 50.0 }
              - { id: unobtainium-oil, percent: 50.0 }   # 존재하지 않는 원료
        """,
    )
    # 구조 검증(합계 100)은 통과하지만 참조 검증에서 실패해야 한다.
    with pytest.raises(ReferenceIntegrityError, match="unobtainium-oil"):
        load_formula(path, ingredient_ids=ingredient_ids, packaging_ids=packaging_ids)


def test_unknown_packaging_reference_fails(tmp_path, ingredient_ids, packaging_ids):
    path = _write_formula(
        tmp_path,
        """
        product: 포장오류처방
        slug: bad-pkg
        version: 1
        product_type: leave_on
        status: 개발중
        base_batch_g: 100
        phases:
          - name: A
            ingredients:
              - { id: mct, percent: 100.0 }
        packaging:
          - { id: nonexistent-box, qty_per_unit: 1 }   # 존재하지 않는 패키지
        """,
    )
    with pytest.raises(ReferenceIntegrityError, match="nonexistent-box"):
        load_formula(path, ingredient_ids=ingredient_ids, packaging_ids=packaging_ids)


def test_reference_check_skipped_when_ids_none(tmp_path):
    # ids를 주지 않으면 참조 검증은 건너뛴다(구조 검증만).
    path = _write_formula(
        tmp_path,
        """
        product: 참조검증생략
        slug: skip
        version: 1
        product_type: leave_on
        status: 개발중
        base_batch_g: 100
        phases:
          - name: A
            ingredients:
              - { id: ghost, percent: 100.0 }
        """,
    )
    f = load_formula(path)  # 예외 없이 로드됨
    assert f.ingredient_ids() == ["ghost"]
