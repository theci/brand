"""기획(Discovery) 슬라이스 1 — 모델·로더·예시 데이터 테스트."""

from __future__ import annotations

from brandlab.core.models import (
    Competitor,
    PainPoint,
    Persona,
    ProblemStatement,
)
from brandlab.loader import load_discovery


def test_painpoint_score_is_severity_times_frequency():
    assert PainPoint(desc="x", severity=4, frequency=5).score == 20
    assert PainPoint(desc="y").score == 9  # 기본 3×3


def test_persona_partial_save_defaults():
    p = Persona(id="a", name="A")  # 나머지 전부 선택
    assert p.pains == []
    assert p.priority == 3
    assert p.jobs == []


def test_competitor_gaps_optional():
    c = Competitor(name="현상적 경쟁")
    assert c.gaps == [] and c.claims == []


def test_problem_statement_all_optional():
    assert ProblemStatement().statement is None


def test_load_discovery_missing_returns_empty(tmp_path):
    d = load_discovery(tmp_path)  # 빈 폴더 → 모두 빈 모델
    assert d.personas.personas == []
    assert d.research.competitors == []
    assert d.research.sources == []
    assert d.problem.statement is None


def test_shipped_example_loads_and_is_consistent():
    d = load_discovery()  # data/brand/
    # 예시 페르소나·경쟁·출처가 있어야
    assert d.personas.personas, "예시 페르소나가 있어야 한다"
    assert d.research.competitors, "예시 경쟁이 있어야 한다"

    # 출처 참조 무결성: pains/notes/competitors 의 source_ref 가 실제 출처를 가리킨다
    src_ids = set(d.research.source_index())
    for per in d.personas.personas:
        for pain in per.pains:
            if pain.source_ref:
                assert pain.source_ref in src_ids, f"미상 출처: {pain.source_ref}"
    for note in d.research.market_notes:
        if note.source_ref:
            assert note.source_ref in src_ids
    for comp in d.research.competitors:
        if comp.source_ref:
            assert comp.source_ref in src_ids

    # 문제 정의의 persona_ref 가 실제 페르소나를 가리킨다
    if d.problem.persona_ref:
        assert d.problem.persona_ref in d.personas.index()


def test_shipped_example_pain_ranking():
    d = load_discovery()
    pains = [p for per in d.personas.personas for p in per.pains]
    top = max(pains, key=lambda p: p.score)
    assert top.score >= 12  # 최우선 페인이 뚜렷해야
