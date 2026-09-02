"""experiment_edit: DOE·안정성 파일 생성·삭제 테스트."""

from __future__ import annotations

from datetime import date

import pytest

from brandlab.experiment_edit import (
    create_doe,
    create_stability,
    delete_experiment,
    doe_path,
    full_factorial_runs,
    stability_path,
)
from brandlab.loader import load_doe, load_stability


def test_full_factorial_2factors():
    runs = full_factorial_runs(["a", "b"], ["y"])
    assert len(runs) == 4
    # 표준 순서: 첫 인자가 가장 빨리 바뀜
    assert runs[0]["factor_values"] == {"a": "low", "b": "low"}
    assert runs[1]["factor_values"] == {"a": "high", "b": "low"}
    assert runs[2]["factor_values"] == {"a": "low", "b": "high"}
    assert runs[3]["factor_values"] == {"a": "high", "b": "high"}
    assert runs[0]["scores"] == {"y": None}


def test_full_factorial_3factors_count():
    assert len(full_factorial_runs(["a", "b", "c"], ["y1", "y2"])) == 8


def _doe_data():
    factors = ["fragrance", "dpg", "ipm"]
    items = ["발향강도", "지속력"]
    return {
        "name": "테스트 스크리닝",
        "formula_ref": "reed-diffuser",
        "factors": factors,
        "levels": {"fragrance": {"low": 15, "high": 25}},
        "response_items": items,
        "runs": full_factorial_runs(factors, items),
    }


def test_create_doe_and_load(tmp_path):
    path = doe_path("my-doe", tmp_path)
    create_doe(_doe_data(), path=path)
    assert path.exists()
    design = load_doe(path)
    assert design.name == "테스트 스크리닝"
    assert len(design.runs) == 8


def test_create_doe_duplicate_rejected(tmp_path):
    path = doe_path("my-doe", tmp_path)
    create_doe(_doe_data(), path=path)
    with pytest.raises(FileExistsError):
        create_doe(_doe_data(), path=path)


def test_create_doe_invalid_rolls_back(tmp_path):
    path = doe_path("bad", tmp_path)
    bad = _doe_data()
    bad["factors"] = []  # min_length=1 위반
    with pytest.raises(Exception):
        create_doe(bad, path=path)
    assert not path.exists()


def _stab_data():
    return {
        "sample_id": "RD-001",
        "formula_ref": "reed-diffuser v1",
        "condition": "45C",
        "start_date": date(2026, 9, 1),
    }


def test_create_stability_and_load(tmp_path):
    path = stability_path("RD-001-45C", tmp_path)
    create_stability(_stab_data(), path=path)
    assert path.exists()
    sample = load_stability(path)
    assert sample.sample_id == "RD-001"
    assert sample.condition.value == "45C"
    assert sample.observations == []


def test_create_stability_bad_condition_rolls_back(tmp_path):
    path = stability_path("bad", tmp_path)
    bad = _stab_data()
    bad["condition"] = "80C"  # enum 위반
    with pytest.raises(Exception):
        create_stability(bad, path=path)
    assert not path.exists()


def test_delete_experiment(tmp_path):
    path = doe_path("my-doe", tmp_path)
    create_doe(_doe_data(), path=path)
    delete_experiment(path)
    assert not path.exists()


def test_delete_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        delete_experiment(doe_path("nope", tmp_path))
