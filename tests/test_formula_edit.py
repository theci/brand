"""formula_edit: 처방 파일 생성·삭제(검증·롤백·참조) 테스트."""

from __future__ import annotations

import pytest

from brandlab.formula_edit import create_formula, delete_formula, formula_path
from brandlab.loader import load_formula

ING_IDS = {"water", "glycerin", "dpg"}
PKG_IDS = {"jar-50ml"}


def _valid_data(slug="my-test", version=1):
    return {
        "product": "테스트 제품",
        "slug": slug,
        "version": version,
        "regime": "cosmetics",
        "product_type": "leave_on",
        "status": "개발중",
        "base_batch_g": 100.0,
        "phases": [
            {
                "name": "A",
                "process": "상온 혼합",
                "ingredients": [
                    {"id": "water", "percent": 60.0},
                    {"id": "glycerin", "percent": 40.0},
                ],
            }
        ],
    }


def test_create_and_load(tmp_path):
    path = create_formula(
        _valid_data(), ingredient_ids=ING_IDS, packaging_ids=PKG_IDS, formulas_dir=tmp_path
    )
    assert path == formula_path("my-test", 1, tmp_path)
    assert path.exists()
    f = load_formula(path, ingredient_ids=ING_IDS, packaging_ids=PKG_IDS)
    assert f.slug == "my-test"
    assert abs(f.total_percent - 100.0) < 0.01


def test_percent_not_100_rejected_no_file(tmp_path):
    data = _valid_data()
    data["phases"][0]["ingredients"][1]["percent"] = 30.0  # 합계 90
    with pytest.raises(Exception):
        create_formula(data, ingredient_ids=ING_IDS, packaging_ids=PKG_IDS, formulas_dir=tmp_path)
    assert not formula_path("my-test", 1, tmp_path).exists()  # 롤백/미생성


def test_missing_ingredient_rejected(tmp_path):
    data = _valid_data()
    data["phases"][0]["ingredients"][0]["id"] = "nope"
    with pytest.raises(ValueError):
        create_formula(data, ingredient_ids=ING_IDS, packaging_ids=PKG_IDS, formulas_dir=tmp_path)
    assert not formula_path("my-test", 1, tmp_path).exists()


def test_duplicate_file_rejected(tmp_path):
    create_formula(_valid_data(), ingredient_ids=ING_IDS, packaging_ids=PKG_IDS, formulas_dir=tmp_path)
    with pytest.raises(FileExistsError):
        create_formula(_valid_data(), ingredient_ids=ING_IDS, packaging_ids=PKG_IDS, formulas_dir=tmp_path)


def test_packaging_ref_checked(tmp_path):
    data = _valid_data()
    data["packaging"] = [{"id": "ghost-box", "qty_per_unit": 1}]
    with pytest.raises(ValueError):
        create_formula(data, ingredient_ids=ING_IDS, packaging_ids=PKG_IDS, formulas_dir=tmp_path)


def test_delete_removes_file_and_empty_dir(tmp_path):
    path = create_formula(_valid_data(), ingredient_ids=ING_IDS, packaging_ids=PKG_IDS, formulas_dir=tmp_path)
    slug_dir = path.parent
    delete_formula(path)
    assert not path.exists()
    assert not slug_dir.exists()  # 빈 슬러그 폴더도 제거


def test_delete_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        delete_formula(formula_path("nope", 1, tmp_path))
