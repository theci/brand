"""문서 변경 이력 — git 히스토리에서 docs/ 문서의 생성·수정 날짜를 읽어 캘린더로 보여준다.

플랫폼이 만들어내는 문서(가이드·시나리오·커리큘럼)가 많아, "그날 무엇이 새로 생기고
고쳐졌는지"를 날짜별로 되짚어 복습하기 위한 학습 보조. git이 이미 기록한 사실을
파싱만 하며 별도 저장은 없다. UI(pages)는 이 데이터를 표시만 한다.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# 프로젝트 루트 (src/brandlab/doc_history.py 기준 두 단계 위 = 레포 루트)
_ROOT = Path(__file__).resolve().parents[2]

# git log --pretty 커스텀 포맷의 구분자(파일명에 나올 리 없는 제어문자 사용)
_REC = "\x1e"  # 커밋 레코드 시작 표시
_SEP = "\x1f"  # 필드 구분자


@dataclass
class DayLog:
    """하루치 문서 변경 묶음(그날 커밋들을 합친 결과)."""

    day: date
    subjects: list[str] = field(default_factory=list)  # 그날 커밋 제목들(무엇을 했나)
    added: list[str] = field(default_factory=list)  # 새로 생긴 문서(docs/ 상대경로)
    modified: list[str] = field(default_factory=list)  # 수정된 문서
    renamed: list[str] = field(default_factory=list)  # 이동/개명된 문서(새 경로)
    deleted: list[str] = field(default_factory=list)  # 삭제된 문서

    @property
    def total(self) -> int:
        return len(self.added) + len(self.modified) + len(self.renamed) + len(self.deleted)


def title_of(doc_path: str) -> str:
    """docs/ 경로에서 사람이 읽을 제목(파일명, 확장자 제거)을 뽑는다."""
    return Path(doc_path).stem


def folder_of(doc_path: str) -> str:
    """docs/ 바로 아래 분류 폴더명(없으면 '')을 돌려준다. 예: docs/홈랩/x.md → '홈랩'."""
    parts = Path(doc_path).parts
    # ("docs", "<folder>", ...) 형태
    if len(parts) >= 3 and parts[0] == "docs":
        return parts[1]
    return ""


def _git_log_raw(path_prefix: str) -> str:
    """git log 원문을 반환한다. git이 없거나 실패하면 빈 문자열."""
    fmt = f"{_REC}%ad{_SEP}%H{_SEP}%s"
    cmd = [
        "git",
        "-c",
        "core.quotepath=false",  # 한글 파일명을 8진 이스케이프하지 않고 UTF-8로
        "log",
        "--date=short",
        "--name-status",
        f"--pretty=format:{fmt}",
        "--",
        path_prefix,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except (OSError, ValueError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout or ""


def parse_git_log(raw: str, *, only_md: bool = True) -> list[DayLog]:
    """git log(--name-status, 커스텀 pretty) 원문을 날짜별 DayLog 목록으로 파싱한다.

    최신 날짜가 앞에 오도록 정렬. 같은 날 여러 커밋은 하나로 합치고,
    같은 문서가 여러 번 나오면 우선순위(추가>이동>수정)로 한 번만 표시한다.
    only_md=True면 .md 문서만(이미지 등 제외).
    """
    # day -> DayLog, day -> {path: 우선순위}
    days: dict[date, DayLog] = {}
    seen: dict[date, dict[str, int]] = {}
    order: list[date] = []
    _PRIORITY = {"A": 3, "R": 2, "M": 1, "D": 0}

    for chunk in raw.split(_REC):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        header, _, body = chunk.partition("\n")
        fields = header.split(_SEP)
        if len(fields) < 3:
            continue
        day_str, _hash, subject = fields[0], fields[1], fields[2]
        try:
            day = date.fromisoformat(day_str)
        except ValueError:
            continue

        if day not in days:
            days[day] = DayLog(day=day)
            seen[day] = {}
            order.append(day)
        dl = days[day]
        if subject and subject not in dl.subjects:
            dl.subjects.append(subject)

        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            cols = line.split("\t")
            code = cols[0][:1]  # A/M/D/R/C…
            path = cols[-1]  # 이동이면 마지막이 새 경로
            if not path:
                continue
            if only_md and not path.endswith(".md"):
                continue
            prio = _PRIORITY.get(code, 1)
            prev = seen[day].get(path)
            if prev is not None and prev >= prio:
                continue  # 같은 날 더 강한 상태가 이미 있음
            seen[day][path] = prio

        # 상태별 목록은 seen 확정 후 한 번에 재구성(중복 방지)

    # seen 우선순위 → 상태별 목록으로 배치
    _BUCKET = {3: "added", 2: "renamed", 1: "modified", 0: "deleted"}
    for day in order:
        dl = days[day]
        for path, prio in seen[day].items():
            getattr(dl, _BUCKET[prio]).append(path)
        for name in ("added", "modified", "renamed", "deleted"):
            getattr(dl, name).sort()

    order.sort(reverse=True)  # 최신 우선
    return [days[d] for d in order]


def load_doc_history(path_prefix: str = "docs/", *, only_md: bool = True) -> list[DayLog]:
    """docs/ 문서의 날짜별 변경 이력을 최신순으로 반환한다(git 없으면 빈 목록)."""
    return parse_git_log(_git_log_raw(path_prefix), only_md=only_md)


__all__ = ["DayLog", "load_doc_history", "parse_git_log", "title_of", "folder_of"]
