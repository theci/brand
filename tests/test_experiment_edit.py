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
    set_batch_actuals,
    set_doe_scores,
    set_stability_observations,
    stability_path,
)
from brandlab.loader import load_batch, load_doe, load_stability


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


def test_set_doe_scores_and_preserve_header(tmp_path):
    path = doe_path("hd", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 헤더 주석이 있는 DOE 파일
    path.write_text(
        "# 헤더 설명: 변수 A/B\n"
        "name: 점수테스트\n"
        "factors: [a, b]\n"
        "response_items: [y]\n"
        "runs:\n"
        "- run_id: 1\n  factor_values: {a: low, b: low}\n  scores: {y: null}\n"
        "- run_id: 2\n  factor_values: {a: high, b: low}\n  scores: {y: null}\n"
        "- run_id: 3\n  factor_values: {a: low, b: high}\n  scores: {y: null}\n"
        "- run_id: 4\n  factor_values: {a: high, b: high}\n  scores: {y: null}\n",
        encoding="utf-8",
    )
    set_doe_scores(path, {1: {"y": 3.0}, 2: {"y": 5.0}, 3: {"y": 2.0}, 4: {"y": 4.0}})
    design = load_doe(path)
    assert {r.run_id: r.scores["y"] for r in design.runs} == {1: 3.0, 2: 5.0, 3: 2.0, 4: 4.0}
    assert "# 헤더 설명" in path.read_text(encoding="utf-8")  # 헤더 보존


def test_set_stability_observations(tmp_path):
    path = stability_path("s", tmp_path)
    create_stability(
        {"sample_id": "S-1", "condition": "45C", "start_date": date(2026, 9, 1)}, path=path
    )
    set_stability_observations(
        path,
        [
            {"date": "2026-09-08", "외관": "양호", "판정": "적합"},
            {"date": "2026-09-15", "색": "미세 황변", "판정": "관찰", "비고": ""},
        ],
    )
    sample = load_stability(path)
    assert len(sample.observations) == 2
    assert sample.observations[0].외관 == "양호"
    assert sample.observations[1].판정 == "관찰"
    assert sample.observations[1].비고 is None  # 빈 필드 제외


def _write_batch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# 배치 헤더\n"
        "batch_id: DL-20260902-01\n"
        "formula_ref: daily-lotion v1\n"
        "date: 2026-09-02\n"
        "target_g: 100.0\n"
        "lines:\n"
        "- {id: water, target_g: 60.0}\n"
        "- {id: glycerin, target_g: 5.0}\n",
        encoding="utf-8",
    )


def test_set_batch_actuals(tmp_path):
    path = tmp_path / "batches" / "DL-20260902-01.yaml"
    _write_batch(path)
    set_batch_actuals(
        path,
        yield_g=92.5, ph=5.2, observations="냉각 후 약간 묽음",
        actuals_by_id={"water": 59.5, "glycerin": None},
    )
    rec = load_batch(path)
    assert rec.yield_g == 92.5 and rec.ph == 5.2
    assert rec.observations == "냉각 후 약간 묽음"
    assert rec.yield_percent == 92.5  # 92.5 / 100
    lines = {ln.id: ln.actual_g for ln in rec.lines}
    assert lines["water"] == 59.5 and lines["glycerin"] is None
    assert "# 배치 헤더" in path.read_text(encoding="utf-8")  # 헤더 보존


def test_set_batch_actuals_clears_blank(tmp_path):
    path = tmp_path / "batches" / "b.yaml"
    _write_batch(path)
    set_batch_actuals(path, yield_g=90.0)
    set_batch_actuals(path, yield_g=None, observations="  ")  # 비우면 제거
    rec = load_batch(path)
    assert rec.yield_g is None and rec.observations is None
