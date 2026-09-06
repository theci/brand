"""빠른 시험 로그(QuickTrial/TrialLog) 로드·저장 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from brandlab.experiment_edit import save_trials
from brandlab.loader import load_trials
from brandlab.models import TrialLog


def test_load_missing_returns_empty(tmp_path):
    log = load_trials(tmp_path / "nope.yaml")
    assert isinstance(log, TrialLog)
    assert log.trials == []


def test_save_creates_file_and_roundtrip(tmp_path):
    path = tmp_path / "trials.yaml"
    rows = [
        {"date": "2026-09-07", "base": "daily-lotion v2", "changed": "잔탄 0.3→0.4",
         "emulsion_ok": True, "ph": 5.2, "sensory": "산뜻", "verdict": "keeper"},
        {"date": "2026-09-07", "changed": "글리세린 8%", "emulsion_ok": True,
         "issues": "끈적임", "verdict": "접기"},
    ]
    save_trials(rows, path)
    assert path.exists()
    log = load_trials(path)
    assert len(log.trials) == 2
    assert log.trials[0].verdict == "keeper"
    assert log.trials[0].emulsion_ok is True
    assert log.trials[1].verdict == "접기"


def test_save_drops_empty_rows(tmp_path):
    path = tmp_path / "trials.yaml"
    rows = [
        {"date": "2026-09-07", "changed": "테스트", "verdict": "튜닝"},
        {"date": None, "base": "", "changed": "  ", "verdict": None},  # 완전히 빈 행
    ]
    save_trials(rows, path)
    log = load_trials(path)
    assert len(log.trials) == 1
    assert log.trials[0].changed == "테스트"


def test_save_empty_list_writes_empty_log(tmp_path):
    path = tmp_path / "trials.yaml"
    save_trials([], path)
    assert load_trials(path).trials == []


def test_ph_out_of_range_fails():
    with pytest.raises(ValidationError):
        TrialLog.model_validate({"trials": [{"ph": 20.0}]})


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        TrialLog.model_validate({"trials": [{"unknown": "x"}]})
