"""데일리 루틴 커리큘럼 진행 로직 — 오늘의 퀘스트·스트릭·마일스톤.

완료 기반 진행(날짜 강제 아님): '다음 미완료 퀘스트'를 짚어 흐지부지를 막는다.
D+n은 표시용일 뿐 진도를 강제하지 않는다(결석해도 안 밀림). 상태는
data/brand/progress.yaml에 저장하며 검증 실패 시 롤백한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

from .core.models import Act, Curriculum, DailyReport, Progress, Quest
from .loader import DATA_DIR, load_progress
from .master_edit import save_with_backup

PROGRESS_PATH = DATA_DIR / "brand" / "progress.yaml"


@dataclass
class Position:
    day_index: int | None  # D+n (start_date 있으면)
    act: Act | None  # 현재 진행 act(첫 미완료 퀘스트의 act)
    week: int | None


@dataclass
class MilestoneStat:
    act: Act
    done: int
    total: int
    earned: bool  # act 퀘스트 전부 완료 → 🏅 획득


def next_quests(
    cur: Curriculum, prog: Progress, *, kind: str | None = None, n: int = 3
) -> list[Quest]:
    """미완료 퀘스트를 커리큘럼 순서대로. kind='desk'/'lab'로 필터, n으로 개수 제한(0=전체)."""
    done = set(prog.done)
    out = [q for q in cur.quests if q.id not in done and (kind is None or q.kind == kind)]
    return out[:n] if n else out


def _first_incomplete(cur: Curriculum, prog: Progress) -> Quest | None:
    done = set(prog.done)
    return next((q for q in cur.quests if q.id not in done), None)


def current_position(cur: Curriculum, prog: Progress, today: date | None = None) -> Position:
    """D+n + 현재 진행 중인 막/주차(첫 미완료 퀘스트 기준). 전부 완료면 마지막 막."""
    today = today or date.today()
    day_index = (today - prog.start_date).days if prog.start_date else None
    q = _first_incomplete(cur, prog)
    if q is None:
        return Position(day_index, cur.acts[-1] if cur.acts else None, None)
    act = next((a for a in cur.acts if a.id == q.act), None)
    return Position(day_index, act, q.week)


def _report_dates(prog: Progress) -> list[date]:
    return sorted({r.date for r in prog.reports})


def streak(prog: Progress, today: date | None = None) -> int:
    """보고한 날짜의 연속 수. 오늘 또는 어제로 끝나는 연속만 인정(끊기면 0)."""
    today = today or date.today()
    days = set(_report_dates(prog))
    if not days:
        return 0
    if today in days:
        cur = today
    elif (today - timedelta(days=1)) in days:
        cur = today - timedelta(days=1)
    else:
        return 0
    count = 0
    while cur in days:
        count += 1
        cur -= timedelta(days=1)
    return count


def days_since_report(prog: Progress, today: date | None = None) -> int | None:
    """마지막 보고 이후 경과일. 없으면 None. >=2면 '연속 결석' 경고."""
    today = today or date.today()
    ds = _report_dates(prog)
    return (today - ds[-1]).days if ds else None


def milestone_status(cur: Curriculum, prog: Progress) -> list[MilestoneStat]:
    """막별 (완료수/총수/획득여부). act 퀘스트 전부 완료 시 🏅 획득."""
    done = set(prog.done)
    out: list[MilestoneStat] = []
    for a in cur.acts:
        qs = [q for q in cur.quests if q.act == a.id]
        d = sum(1 for q in qs if q.id in done)
        out.append(MilestoneStat(a, d, len(qs), bool(qs) and d == len(qs)))
    return out


def prefill_next(cur: Curriculum, prog: Progress, *, kind: str | None = None) -> str:
    """보고의 '내일 할 것'에 넣을 다음 퀘스트 텍스트(제가 정해줄게요의 구현)."""
    nx = next_quests(cur, prog, kind=kind, n=1)
    return nx[0].text if nx else "다음 퀘스트 없음 — 다음 막으로!"


# ---------------------------------------------------------------------------
# 편집 (순수 함수로 새 Progress를 만들고, save_progress로 저장)
# ---------------------------------------------------------------------------
def set_start_date(prog: Progress, d: date) -> Progress:
    return prog.model_copy(update={"start_date": d})


def toggle_quest(prog: Progress, quest_id: str, done: bool) -> Progress:
    kept = [x for x in prog.done if x != quest_id]
    if done:
        kept.append(quest_id)
    return prog.model_copy(update={"done": kept})


def add_report(prog: Progress, report: DailyReport) -> Progress:
    """같은 날짜 보고는 교체."""
    others = [r for r in prog.reports if r.date != report.date]
    return prog.model_copy(update={"reports": [*others, report]})


def save_progress(prog: Progress, path: Path | str = PROGRESS_PATH) -> Path:
    """progress.yaml에 저장. 기존 파일은 .bak 백업, 검증 실패 시 롤백."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = prog.model_dump(mode="json", exclude_none=True)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    if path.exists():
        save_with_backup(path, text, load_progress)
    else:
        path.write_text(text, encoding="utf-8")
        try:
            load_progress(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    return path


__all__ = [
    "Position",
    "MilestoneStat",
    "next_quests",
    "current_position",
    "streak",
    "days_since_report",
    "milestone_status",
    "prefill_next",
    "set_start_date",
    "toggle_quest",
    "add_report",
    "save_progress",
]
