"""진행 트래커 — 커리큘럼 로드·퀘스트·스트릭·마일스톤·저장 테스트."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from brandlab.core.models import Act, Curriculum, DailyReport, Milestone, Progress, Quest
from brandlab.curriculum import (
    add_report,
    current_position,
    days_since_report,
    milestone_status,
    next_quests,
    prefill_next,
    save_progress,
    set_start_date,
    streak,
    toggle_quest,
)
from brandlab.loader import load_curriculum, load_progress


def _cur() -> Curriculum:
    ms = Milestone(badge="b", dod="d")
    return Curriculum(
        acts=[
            Act(id="a1", title="A1", milestone=ms),
            Act(id="a2", title="A2", milestone=ms),
        ],
        quests=[
            Quest(id="a1-d1", act="a1", kind="desk", text="데스크1", week=1),
            Quest(id="a1-l1", act="a1", kind="lab", text="랩1", week=1),
            Quest(id="a2-d1", act="a2", kind="desk", text="데스크2", week=2),
        ],
    )


# --- 실제 데이터 로드 ---
def test_real_curriculum_loads():
    c = load_curriculum()
    assert len(c.acts) == 5
    assert len(c.quests) >= 30
    assert {q.kind for q in c.quests} == {"desk", "lab"}


# --- next_quests ---
def test_next_quests_order_and_kind_filter():
    c, p = _cur(), Progress()
    assert [q.id for q in next_quests(c, p)] == ["a1-d1", "a1-l1", "a2-d1"]
    assert [q.id for q in next_quests(c, p, kind="lab")] == ["a1-l1"]
    assert [q.id for q in next_quests(c, p, n=1)] == ["a1-d1"]


def test_next_quests_skips_done():
    c = _cur()
    p = toggle_quest(Progress(), "a1-d1", True)
    assert [q.id for q in next_quests(c, p)] == ["a1-l1", "a2-d1"]


# --- position ---
def test_current_position_tracks_act_and_dplus():
    c = _cur()
    p = set_start_date(Progress(), date(2026, 1, 1))
    pos = current_position(c, p, today=date(2026, 1, 6))
    assert pos.day_index == 5 and pos.act.id == "a1" and pos.week == 1
    p2 = toggle_quest(toggle_quest(p, "a1-d1", True), "a1-l1", True)
    assert current_position(c, p2, today=date(2026, 1, 6)).act.id == "a2"


# --- streak / 결석 ---
def test_streak_consecutive_and_gap():
    today = date(2026, 3, 10)
    p = Progress(reports=[
        DailyReport(date=today),
        DailyReport(date=today - timedelta(days=1)),
        DailyReport(date=today - timedelta(days=2)),
    ])
    assert streak(p, today=today) == 3
    # 어제로 끝나도 인정
    p2 = Progress(reports=[DailyReport(date=today - timedelta(days=1))])
    assert streak(p2, today=today) == 1
    # 이틀 이상 공백이면 0
    p3 = Progress(reports=[DailyReport(date=today - timedelta(days=3))])
    assert streak(p3, today=today) == 0


def test_days_since_report_detects_absence():
    today = date(2026, 3, 10)
    assert days_since_report(Progress(), today=today) is None
    p = Progress(reports=[DailyReport(date=today - timedelta(days=2))])
    assert days_since_report(p, today=today) == 2


# --- milestone ---
def test_milestone_earned_when_act_complete():
    c = _cur()
    p = toggle_quest(toggle_quest(Progress(), "a1-d1", True), "a1-l1", True)
    stats = {m.act.id: m for m in milestone_status(c, p)}
    assert stats["a1"].done == 2 and stats["a1"].total == 2 and stats["a1"].earned is True
    assert stats["a2"].earned is False


# --- prefill ---
def test_prefill_next_returns_next_text():
    c = _cur()
    assert prefill_next(c, Progress(), kind="desk") == "데스크1"


# --- 편집·저장 ---
def test_add_report_replaces_same_date():
    d = date(2026, 3, 10)
    p = add_report(Progress(), DailyReport(date=d, did="v1"))
    p = add_report(p, DailyReport(date=d, did="v2"))
    assert len(p.reports) == 1 and p.reports[0].did == "v2"


def test_save_progress_roundtrip(tmp_path: Path):
    path = tmp_path / "progress.yaml"
    p = set_start_date(Progress(), date(2026, 1, 1))
    p = toggle_quest(p, "a1-d1", True)
    p = add_report(p, DailyReport(date=date(2026, 1, 2), did="첫 보고", next="다음"))
    save_progress(p, path)
    reloaded = load_progress(path)
    assert reloaded.start_date == date(2026, 1, 1)
    assert reloaded.done == ["a1-d1"]
    assert reloaded.reports[0].did == "첫 보고"
