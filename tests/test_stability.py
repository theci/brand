"""안정성 시험 트래커 테스트."""

from __future__ import annotations

from datetime import date

import pytest

from brandlab.loader import load_all_stability
from brandlab.models import StabilitySample
from brandlab.stability import (
    sample_status,
    stability_due,
    stability_schedule,
    stability_summary,
)


# ---------------------------------------------------------------------------
# 예정일 생성
# ---------------------------------------------------------------------------
def test_schedule_generates_1_2_4_8_weeks():
    sched = stability_schedule(date(2026, 1, 1))
    weeks = [c.week for c in sched]
    dates = [c.due_date for c in sched]
    assert weeks == [1, 2, 4, 8]
    assert dates == [
        date(2026, 1, 8),
        date(2026, 1, 15),
        date(2026, 1, 29),
        date(2026, 2, 26),
    ]


def _sample(observations, start=date(2026, 1, 1), condition="45C", sid="S1"):
    return StabilitySample.model_validate(
        {
            "sample_id": sid,
            "condition": condition,
            "start_date": start,
            "observations": observations,
        }
    )


# ---------------------------------------------------------------------------
# 지연 판정
# ---------------------------------------------------------------------------
def test_overdue_when_no_observation_past_due():
    # 시작 1/1, 오늘 2/1 → 1주(1/8)·2주(1/15)·4주(1/29) 예정일 지남, 관찰 없음 → 3건 지연
    sample = _sample([])
    due = stability_due([sample], today=date(2026, 2, 1))
    weeks = sorted(d.week for d in due)
    assert weeks == [1, 2, 4]  # 8주(2/26)는 아직 미래
    # 지연 큰 순 정렬(1주가 가장 오래 지남)
    assert due[0].week == 1
    assert due[0].days_overdue == (date(2026, 2, 1) - date(2026, 1, 8)).days


def test_observation_within_tolerance_marks_done():
    # 1주 예정 1/8, 관찰 1/9(오차 1일) → 완료 처리 → 지연 아님
    sample = _sample([{"date": date(2026, 1, 9), "판정": "적합"}])
    due = stability_due([sample], today=date(2026, 2, 1))
    assert 1 not in [d.week for d in due]


def test_upcoming_not_overdue():
    # 오늘이 1/10이면 1주(1/8)만 지남, 나머지는 upcoming
    sample = _sample([])
    statuses = {c.week: c.status for c in sample_status(sample, today=date(2026, 1, 10))}
    assert statuses[1] == "overdue"
    assert statuses[2] == "upcoming"
    assert statuses[4] == "upcoming"
    assert statuses[8] == "upcoming"


# ---------------------------------------------------------------------------
# 조건별 요약
# ---------------------------------------------------------------------------
def test_summary_groups_by_condition():
    s1 = _sample([], condition="45C", sid="A")
    s2 = _sample([], condition="RT", sid="B")
    s3 = _sample([], condition="45C", sid="C")
    summary = stability_summary([s1, s2, s3])
    assert set(summary.keys()) == {"45C", "RT"}
    assert len(summary["45C"]) == 2
    assert len(summary["RT"]) == 1


# ---------------------------------------------------------------------------
# 실데이터 로드
# ---------------------------------------------------------------------------
def test_real_data_due_detects_cb001(project_root):
    samples = load_all_stability(project_root / "experiments")
    # CB-001은 6/1 시작, 4주(6/29)·8주(7/27) 관찰 누락 → 과거 기준으로 지연 감지
    due = stability_due(samples, today=date(2026, 8, 19))
    cb001 = [d for d in due if d.sample_id == "CB-001"]
    assert {d.week for d in cb001} == {4, 8}
