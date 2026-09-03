"""기획(Discovery) 로직 — 랭킹·문제초안·하류 프리필·저장.

Phase 11. 포지셔닝(뾰족함)의 상류. 리서치를 구조화해 쌓고, 그 결과를
포지셔닝·브랜드코어로 **프리필**해 하류 품질을 자동으로 끌어올린다.

- rank_pains            : 페르소나의 페인을 심각도×빈도로 랭킹
- draft_problem_statement: 문제 문장 자동 초안
- to_positioning_inputs : 페르소나·페인·경쟁 빈틈 → 포지셔닝 필드 프리필
- to_brandcore_inputs   : 페르소나·경쟁 → 브랜드 코어 필드 프리필
- save_personas/research/problem, save_discovery : YAML 저장
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .core.models import (
    ComparisonRow,
    Discovery,
    Persona,
    PersonaBook,
    PainPoint,
    ProblemStatement,
    Research,
)
from .loader import DATA_DIR


# ---------------------------------------------------------------------------
# 랭킹
# ---------------------------------------------------------------------------
@dataclass
class RankedPain:
    """페르소나 맥락을 유지한 페인(랭킹용)."""

    persona_id: str
    persona_name: str
    pain: PainPoint

    @property
    def score(self) -> int:
        return self.pain.score


def _personas(personas: PersonaBook | list[Persona]) -> list[Persona]:
    return personas.personas if isinstance(personas, PersonaBook) else list(personas)


def rank_pains(personas: PersonaBook | list[Persona]) -> list[RankedPain]:
    """모든 페르소나의 페인을 점수(심각도×빈도) 내림차순으로 반환."""
    ranked = [
        RankedPain(p.id, p.name, pain)
        for p in _personas(personas)
        for pain in p.pains
    ]
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


def primary_persona(discovery: Discovery) -> Persona | None:
    """우선순위(priority)가 가장 높은 페르소나. 동점이면 먼저 등장한 쪽."""
    people = discovery.personas.personas
    if not people:
        return None
    return max(people, key=lambda p: p.priority)


def top_pain(persona: Persona) -> PainPoint | None:
    """페르소나의 최우선 페인(점수 최대)."""
    if not persona.pains:
        return None
    return max(persona.pains, key=lambda p: p.score)


# ---------------------------------------------------------------------------
# 문제 문장 초안
# ---------------------------------------------------------------------------
def draft_problem_statement(
    persona: Persona, pains: list[PainPoint] | None = None
) -> str:
    """페르소나 + 최우선 페인 + 현재 대안의 불만으로 문제 문장을 조립한다."""
    pool = pains if pains is not None else persona.pains
    core = max(pool, key=lambda p: p.score).desc if pool else "해결되지 않은 불편"
    who = persona.one_line or persona.name
    alt = persona.current_solution
    dissat = persona.dissatisfaction

    sentence = f"{who}은(는) '{core}' 문제를 겪는다."
    if alt and dissat:
        sentence += f" 지금은 {alt}을(를) 쓰지만 {dissat}."
    elif alt:
        sentence += f" 지금은 {alt}을(를) 쓴다."
    elif dissat:
        sentence += f" 기존 대안은 {dissat}."
    return sentence


# ---------------------------------------------------------------------------
# 하류 프리필
# ---------------------------------------------------------------------------
def to_positioning_inputs(discovery: Discovery) -> dict:
    """포지셔닝 필드(target·pain·competitor·comparison) 프리필값을 만든다.

    반환 dict는 Positioning 필드명 키를 쓴다(빈 값은 제외). 페이지에서
    비어 있는 칸만 채우는 용도. 경쟁의 gaps(빈틈)는 comparison 행으로 승격.
    """
    out: dict = {}
    persona = primary_persona(discovery)
    if persona is not None:
        out["target"] = persona.one_line or persona.name
        tp = top_pain(persona)
        if tp is not None:
            out["pain"] = tp.desc

    competitors = discovery.research.competitors
    if competitors:
        out["competitor"] = competitors[0].name
        rows: list[ComparisonRow] = []
        for comp in competitors:
            for gap in comp.gaps:
                # 경쟁의 약점 = 우리 기회 → 축=빈틈, 경쟁=있음(문제), 우리=목표(우위)
                rows.append(
                    ComparisonRow(axis=gap, ours="(개선 목표)", theirs=comp.name, ours_wins=True)
                )
        if rows:
            out["comparison"] = rows
    return out


def to_brandcore_inputs(discovery: Discovery) -> dict:
    """브랜드 코어 필드(persona·enemy·entry_points) 프리필값을 만든다."""
    out: dict = {}
    persona = primary_persona(discovery)
    if persona is not None:
        out["persona"] = persona.one_line or persona.name
        if persona.jobs:
            out["entry_points"] = list(persona.jobs)
    competitors = discovery.research.competitors
    if competitors:
        # 적 = 현상적 경쟁(실명 지양) 또는 그 첫 빈틈
        out["enemy"] = competitors[0].name
    return out


# ---------------------------------------------------------------------------
# 저장
# ---------------------------------------------------------------------------
def _dump(model, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(model.model_dump(exclude_none=True), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def save_personas(book: PersonaBook, path: Path | str = DATA_DIR / "brand" / "personas.yaml") -> Path:
    return _dump(book, Path(path))


def save_research(research: Research, path: Path | str = DATA_DIR / "brand" / "research.yaml") -> Path:
    return _dump(research, Path(path))


def save_problem(problem: ProblemStatement, path: Path | str = DATA_DIR / "brand" / "problem.yaml") -> Path:
    return _dump(problem, Path(path))


def save_discovery(discovery: Discovery, brand_dir: Path | str = DATA_DIR / "brand") -> list[Path]:
    """기획 3파일을 모두 저장한다."""
    base = Path(brand_dir)
    return [
        save_personas(discovery.personas, base / "personas.yaml"),
        save_research(discovery.research, base / "research.yaml"),
        save_problem(discovery.problem, base / "problem.yaml"),
    ]


__all__ = [
    "RankedPain",
    "rank_pains",
    "primary_persona",
    "top_pain",
    "draft_problem_statement",
    "to_positioning_inputs",
    "to_brandcore_inputs",
    "save_personas",
    "save_research",
    "save_problem",
    "save_discovery",
]
