"""안정성 시험 트래커.

관찰 예정일(1/2/4/8주)을 생성하고, 오늘 기준으로 밀린 관찰을 찾아낸다.
관찰일을 놓치면 그 시점 데이터가 통째로 사라지므로, 지연 감지가 이 기능의 핵심이다.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import StabilitySample

# 표준 관찰 주차(주) → 일수로 환산해 예정일을 만든다.
CHECKPOINT_WEEKS = (1, 2, 4, 8)

# 예정일과 실제 관찰일의 허용 오차(일). 이 안에 관찰이 있으면 그 체크포인트는 완료로 본다.
MATCH_TOLERANCE_DAYS = 3


@dataclass
class Checkpoint:
    week: int
    due_date: date


@dataclass
class CheckpointStatus:
    week: int
    due_date: date
    status: str  # "done" | "overdue" | "upcoming"
    observed_date: date | None
    days_overdue: int  # overdue일 때 경과 일수(그 외 0)


@dataclass
class DueItem:
    sample_id: str
    condition: str
    formula_ref: str | None
    week: int
    due_date: date
    days_overdue: int


@dataclass
class SampleTimeline:
    sample_id: str
    condition: str
    checkpoints: list[CheckpointStatus]


# ---------------------------------------------------------------------------
# 1. 관찰 예정일 생성
# ---------------------------------------------------------------------------
def stability_schedule(start_date: date) -> list[Checkpoint]:
    """시작일 기준 1/2/4/8주 관찰 예정일을 생성한다."""
    return [
        Checkpoint(week=w, due_date=start_date + timedelta(weeks=w))
        for w in CHECKPOINT_WEEKS
    ]


# ---------------------------------------------------------------------------
# 체크포인트별 상태
# ---------------------------------------------------------------------------
def _match_observation(sample: StabilitySample, due: date) -> date | None:
    """예정일 ±허용오차 안에 관찰이 있으면 그 관찰일을 반환."""
    best: date | None = None
    for obs in sample.observations:
        if abs((obs.date - due).days) <= MATCH_TOLERANCE_DAYS:
            if best is None or abs((obs.date - due).days) < abs((best - due).days):
                best = obs.date
    return best


def sample_status(
    sample: StabilitySample, today: date | None = None
) -> list[CheckpointStatus]:
    """시료의 각 체크포인트 상태(done/overdue/upcoming)를 계산한다."""
    today = today or date.today()
    result: list[CheckpointStatus] = []
    for cp in stability_schedule(sample.start_date):
        observed = _match_observation(sample, cp.due_date)
        if observed is not None:
            status, overdue = "done", 0
        elif cp.due_date < today:
            status, overdue = "overdue", (today - cp.due_date).days
        else:
            status, overdue = "upcoming", 0
        result.append(
            CheckpointStatus(
                week=cp.week,
                due_date=cp.due_date,
                status=status,
                observed_date=observed,
                days_overdue=overdue,
            )
        )
    return result


# ---------------------------------------------------------------------------
# 2. 지연(밀린) 관찰 목록
# ---------------------------------------------------------------------------
def stability_due(
    samples: Iterable[StabilitySample], today: date | None = None
) -> list[DueItem]:
    """오늘 기준으로 관찰이 밀린(예정일 경과 + 미관찰) 항목을 반환한다.

    지연이 큰 순으로 정렬한다.
    """
    today = today or date.today()
    due: list[DueItem] = []
    for sample in samples:
        for cs in sample_status(sample, today):
            if cs.status == "overdue":
                due.append(
                    DueItem(
                        sample_id=sample.sample_id,
                        condition=sample.condition.value,
                        formula_ref=sample.formula_ref,
                        week=cs.week,
                        due_date=cs.due_date,
                        days_overdue=cs.days_overdue,
                    )
                )
    due.sort(key=lambda d: d.days_overdue, reverse=True)
    return due


# ---------------------------------------------------------------------------
# 3. 조건별 시계열 요약
# ---------------------------------------------------------------------------
def stability_summary(
    samples: Iterable[StabilitySample],
) -> dict[str, list[SampleTimeline]]:
    """조건별로 시료 시계열(체크포인트 판정)을 묶어 반환한다."""
    by_condition: dict[str, list[SampleTimeline]] = {}
    for sample in samples:
        timeline = SampleTimeline(
            sample_id=sample.sample_id,
            condition=sample.condition.value,
            checkpoints=sample_status(sample),
        )
        by_condition.setdefault(sample.condition.value, []).append(timeline)
    return by_condition


def observed_verdict(sample: StabilitySample, on: date) -> str | None:
    """특정 관찰일의 판정값을 반환(없으면 None)."""
    for obs in sample.observations:
        if obs.date == on:
            return obs.판정
    return None


__all__ = [
    "CHECKPOINT_WEEKS",
    "MATCH_TOLERANCE_DAYS",
    "Checkpoint",
    "CheckpointStatus",
    "DueItem",
    "SampleTimeline",
    "stability_schedule",
    "sample_status",
    "stability_due",
    "stability_summary",
    "observed_verdict",
]
