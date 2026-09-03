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


# ---------------------------------------------------------------------------
# 슬라이스 2 — 랭킹·문제초안·프리필·저장
# ---------------------------------------------------------------------------
from brandlab.core.models import Discovery, PersonaBook, Research  # noqa: E402
from brandlab.discovery import (  # noqa: E402
    draft_problem_statement,
    primary_persona,
    rank_pains,
    save_discovery,
    to_brandcore_inputs,
    to_positioning_inputs,
    top_pain,
)


def _persona(pid, priority, pains):
    return Persona(
        id=pid, name=pid, one_line=f"{pid} 한줄",
        current_solution="대형 브랜드", dissatisfaction="끈적임",
        jobs=["빠른 흡수"], priority=priority,
        pains=[PainPoint(**p) for p in pains],
    )


def test_rank_pains_desc_across_personas():
    book = PersonaBook(personas=[
        _persona("a", 3, [{"desc": "약함", "severity": 2, "frequency": 2}]),
        _persona("b", 3, [{"desc": "강함", "severity": 5, "frequency": 5}]),
    ])
    ranked = rank_pains(book)
    assert [r.pain.desc for r in ranked] == ["강함", "약함"]
    assert ranked[0].score == 25 and ranked[0].persona_id == "b"


def test_primary_persona_by_priority():
    d = Discovery(personas=PersonaBook(personas=[
        _persona("low", 2, [{"desc": "x"}]),
        _persona("high", 5, [{"desc": "y"}]),
    ]))
    assert primary_persona(d).id == "high"


def test_draft_problem_statement_uses_top_pain_and_alt():
    p = _persona("a", 5, [
        {"desc": "약한 불편", "severity": 2, "frequency": 2},
        {"desc": "치명적 불편", "severity": 5, "frequency": 5},
    ])
    s = draft_problem_statement(p)
    assert "치명적 불편" in s
    assert "대형 브랜드" in s and "끈적임" in s


def test_to_positioning_inputs_prefill():
    from brandlab.core.models import Competitor
    d = Discovery(
        personas=PersonaBook(personas=[_persona("hero", 5, [{"desc": "오후 당김", "severity": 4, "frequency": 5}])]),
        research=Research(competitors=[Competitor(name="A사", gaps=["끈적임", "흡수 느림"])]),
    )
    out = to_positioning_inputs(d)
    assert out["target"] == "hero 한줄"
    assert out["pain"] == "오후 당김"
    assert out["competitor"] == "A사"
    axes = [r.axis for r in out["comparison"]]
    assert "끈적임" in axes and "흡수 느림" in axes
    assert all(r.ours_wins for r in out["comparison"])


def test_to_brandcore_inputs_prefill():
    from brandlab.core.models import Competitor
    d = Discovery(
        personas=PersonaBook(personas=[_persona("hero", 5, [{"desc": "x"}])]),
        research=Research(competitors=[Competitor(name="현상적 경쟁")]),
    )
    out = to_brandcore_inputs(d)
    assert out["persona"] == "hero 한줄"
    assert out["enemy"] == "현상적 경쟁"
    assert out["entry_points"] == ["빠른 흡수"]


def test_save_discovery_roundtrip(tmp_path):
    d = Discovery(personas=PersonaBook(personas=[_persona("a", 4, [{"desc": "p", "severity": 5, "frequency": 4}])]))
    save_discovery(d, tmp_path)
    d2 = load_discovery(tmp_path)
    assert d2.personas.personas[0].id == "a"
    assert d2.personas.personas[0].pains[0].score == 20


def test_empty_discovery_prefill_is_empty():
    assert to_positioning_inputs(Discovery()) == {}
    assert to_brandcore_inputs(Discovery()) == {}
    assert top_pain(Persona(id="a", name="A")) is None
