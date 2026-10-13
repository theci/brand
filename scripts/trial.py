# -*- coding: utf-8 -*-
"""빠른 시험 로그 한 줄 입력 — 벤치에서 섞고 바로 터미널에 한 줄.

experiments/trials.yaml 에 QuickTrial 1건을 '추가'한다. Streamlit 그리드를 열지
않고, 피곤한 날에도 가장 적은 타이핑으로 '접은 것도 데이터'를 남기는 입구.

사용:
  uv run python scripts/trial.py "데일리로션 v2 / 잔탄 0.4→0.5 / ph 5.2 / 유화 ok / 약간 무거움 / 접기 / 스클레로튬검 시도"
  uv run python scripts/trial.py            # 인자 없으면 최근 로그 + 템플릿만 보여줌

입력 규칙 (전부 선택, '/' 로 구분):
  기준처방 / 바꾼것 / 사용감 / 다음아이디어        ← 이 순서로 자리 채움
  어디에 써도 자동으로 빼가는 특수값:
    - 날짜   : 2026-10-13 형태가 있으면 그 날짜(없으면 오늘)
    - ph     : "ph 5.2" / "pH5.2"
    - 유화    : "유화 ok/성공" → true, "유화 실패/분리/깨짐/x" → false
    - 판정    : keeper / 튜닝 / 접기

검증·백업은 brandlab.save_trials 가 담당(스키마 위반 시 저장 안 함, 기존 파일은 .bak).
"""
from __future__ import annotations

import re
import sys
from datetime import date

# Windows 콘솔(cp949)에서도 한글·기호가 깨지지 않도록 출력 인코딩 고정
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from brandlab.experiment_edit import save_trials
from brandlab.loader import load_trials

# 판정 어휘 (QuickTrial.verdict: keeper / 튜닝 / 접기)
_VERDICTS = {"keeper", "튜닝", "접기"}
# 유화 성공/실패 판별 키워드
_EMULSION_BAD = ("실패", "분리", "깨짐", "안됨", "안 됨", "fail", "x")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PH_RE = re.compile(r"^ph\s*([0-9]+(?:\.[0-9]+)?)$", re.IGNORECASE)


def parse_line(line: str) -> dict:
    """'/' 로 나눈 자유 입력을 QuickTrial dict 로 해석한다.

    특수값(날짜·ph·유화·판정)은 어느 칸에 있든 먼저 빼가고, 남은 조각을
    기준처방 → 바꾼것 → 사용감 → 다음아이디어 순으로 채운다.
    """
    pieces = [p.strip() for p in line.split("/") if p.strip()]
    trial: dict = {}
    rest: list[str] = []

    for p in pieces:
        low = p.lower()
        if _DATE_RE.match(p):
            trial["date"] = p
            continue
        m = _PH_RE.match(p)
        if m:
            trial["ph"] = float(m.group(1))
            continue
        if "유화" in p:
            trial["emulsion_ok"] = not any(bad in low for bad in _EMULSION_BAD)
            continue
        if p in _VERDICTS:
            trial["verdict"] = p
            continue
        rest.append(p)

    # 남은 조각을 자연스러운 서술 순서대로 배치
    for field, value in zip(("base", "changed", "sensory", "next_idea"), rest):
        trial[field] = value
    # 조각이 4개보다 많으면 넘치는 건 사용감에 이어붙여 버리지 않는다
    if len(rest) > 4:
        extra = " / ".join(rest[3:])
        trial["sensory"] = extra

    trial.setdefault("date", date.today().isoformat())
    return trial


# 보기 좋게 출력할 때 쓰는 한글 라벨
_LABELS = [
    ("date", "날짜"),
    ("base", "기준"),
    ("changed", "바꾼것"),
    ("emulsion_ok", "유화"),
    ("ph", "pH"),
    ("sensory", "사용감"),
    ("issues", "이슈"),
    ("verdict", "판정"),
    ("next_idea", "다음"),
]


def _fmt(trial: dict) -> str:
    parts = []
    for key, label in _LABELS:
        if key in trial and trial[key] not in (None, ""):
            val = trial[key]
            if isinstance(val, bool):
                val = "ok" if val else "실패"
            parts.append(f"{label} {val}")
    return "  ·  ".join(parts)


def _show_recent(n: int = 5) -> None:
    trials = load_trials().trials
    if not trials:
        print("(아직 기록 없음)")
        return
    print(f"── 최근 시험 {min(n, len(trials))}건 (총 {len(trials)}건) ──")
    for t in trials[-n:]:
        print("  " + _fmt(t.model_dump(mode="json", exclude_none=True)))


_TEMPLATE = (
    '템플릿:  "기준처방 / 바꾼것 / ph 5.2 / 유화 ok / 사용감 / 접기 / 다음아이디어"\n'
    "         (전부 선택 · 날짜·ph·유화·판정은 아무 칸에 써도 자동 인식 · 날짜 없으면 오늘)"
)


def main(argv: list[str]) -> int:
    line = " ".join(argv).strip()
    if not line:
        _show_recent()
        print()
        print(_TEMPLATE)
        return 0

    trial = parse_line(line)

    # 기존 로그 뒤에 1건 추가 (save_trials 가 스키마 검증 + .bak 롤백)
    existing = [t.model_dump(mode="json", exclude_none=True) for t in load_trials().trials]
    existing.append(trial)
    path = save_trials(existing)

    print("✅ 기록함 →", path)
    print("  " + _fmt(trial))
    print()
    _show_recent(3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
