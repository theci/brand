"""문서 캘린더 로직(brandlab.doc_history) 테스트 — git 원문 파싱을 검증한다."""

from __future__ import annotations

from datetime import date

from brandlab.doc_history import folder_of, load_doc_history, parse_git_log, title_of

REC = "\x1e"
SEP = "\x1f"


def _commit(day: str, sha: str, subject: str, lines: list[str]) -> str:
    header = f"{REC}{day}{SEP}{sha}{SEP}{subject}"
    return header + "\n" + "\n".join(lines) + "\n"


def test_parse_groups_by_day_and_status() -> None:
    raw = (
        _commit(
            "2026-09-13",
            "aaa",
            "docs: 학습 로드맵 신설",
            ["A\tdocs/커리큘럼/화장품_처방_전문성_학습로드맵.md", "M\tdocs/README.md"],
        )
        + _commit(
            "2026-09-13",
            "bbb",
            "docs: 원료 리스트 수정",
            ["M\tdocs/홈랩/원료_구매리스트_보관.md"],
        )
        + _commit(
            "2026-09-08",
            "ccc",
            "docs: 장비 가이드 수정",
            ["M\tdocs/홈랩/홈랩_장비구축_가이드.md"],
        )
    )
    hist = parse_git_log(raw)

    assert [d.day for d in hist] == [date(2026, 9, 13), date(2026, 9, 8)]  # 최신 우선
    d0 = hist[0]
    assert "docs/커리큘럼/화장품_처방_전문성_학습로드맵.md" in d0.added
    assert "docs/README.md" in d0.modified
    assert "docs/홈랩/원료_구매리스트_보관.md" in d0.modified
    assert len(d0.subjects) == 2  # 같은 날 두 커밋 제목이 합쳐짐
    assert d0.total == 3


def test_added_wins_over_modified_same_day() -> None:
    raw = (
        _commit("2026-09-13", "a", "생성", ["A\tdocs/x.md"])
        + _commit("2026-09-13", "b", "수정", ["M\tdocs/x.md"])
    )
    hist = parse_git_log(raw)
    assert hist[0].added == ["docs/x.md"]
    assert hist[0].modified == []  # 같은 날엔 '추가'로만 표시


def test_rename_uses_new_path() -> None:
    raw = _commit("2026-09-13", "a", "재편", ["R100\tdocs/old.md\tdocs/사업/new.md"])
    hist = parse_git_log(raw)
    assert hist[0].renamed == ["docs/사업/new.md"]


def test_only_md_filters_images() -> None:
    raw = _commit("2026-09-13", "a", "이미지", ["A\tdocs/img/a.png", "A\tdocs/b.md"])
    hist = parse_git_log(raw)
    assert hist[0].added == ["docs/b.md"]


def test_empty_raw_returns_empty() -> None:
    assert parse_git_log("") == []


def test_helpers() -> None:
    assert title_of("docs/홈랩/원료_구매리스트_보관.md") == "원료_구매리스트_보관"
    assert folder_of("docs/홈랩/원료_구매리스트_보관.md") == "홈랩"
    assert folder_of("docs/README.md") == ""


def test_load_doc_history_runs() -> None:
    # 실제 저장소에서 실행돼도 예외 없이 리스트를 반환해야 한다.
    hist = load_doc_history()
    assert isinstance(hist, list)
