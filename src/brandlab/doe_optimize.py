"""DOE 최적화 — 주효과(설명)를 넘어 '다음에 시도할 추천 조합'(처방)을 낸다.

두 가지를 제시한다:
  1) 관측 런 랭킹 — 실제 만든 8개(2^k) 런을 목표(최대화/최소화) 기준 desirability로 줄 세워
     '지금까지 만든 것 중 최고 조합'을 고른다.
  2) 주효과 기반 추천 최적 — 각 인자를 목표에 유리한 수준(low/high)으로 설정한 조합.
     관측 런에 없는 조합일 수 있어 '다음 실험 후보'가 된다.

goals: {평가항목: "max"|"min"}. 미지정 항목은 max로 본다.
weights: {평가항목: 가중치}. 미지정은 1.0.

desirability: 각 항목 점수를 런 범위로 0~1 정규화(최소화 항목은 뒤집음) 후 가중 평균.
※ 관능 점수는 주관적이라, 결과는 '다음 실험 우선순위' 참고용이다(확정 아님).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .core.models import DoeDesign
from .doe import doe_analysis

_EPS = 1e-9


@dataclass
class RunScore:
    run_id: object
    factor_values: dict[str, str]
    desirability: float | None
    per_item: dict[str, float]  # 항목별 정규화 점수(0~1)


@dataclass
class FactorChoice:
    factor: str
    level: str  # "low" | "high" | "무관"
    influence: float  # +면 high 유리, -면 low 유리 (0이면 무관)


@dataclass
class DoeRecommendation:
    goals: dict[str, str]
    weights: dict[str, float]
    used_items: list[str]
    ranked: list[RunScore]
    best_run: RunScore | None
    factor_choices: list[FactorChoice]
    predicted_optimum: dict[str, str]
    warnings: list[str] = field(default_factory=list)


def _minmax(design: DoeDesign, item: str) -> tuple[float, float] | None:
    vals = [
        r.scores[item]
        for r in design.runs
        if item in r.scores and r.scores[item] is not None
    ]
    if not vals:
        return None
    return min(vals), max(vals)


def recommend(
    design: DoeDesign,
    goals: dict[str, str] | None = None,
    weights: dict[str, float] | None = None,
) -> DoeRecommendation:
    goals = dict(goals or {})
    weights = dict(weights or {})
    warnings: list[str] = []

    # 사용 가능한 항목(점수가 하나라도 있는 것)만
    ranges: dict[str, tuple[float, float]] = {}
    used: list[str] = []
    for item in design.response_items:
        mm = _minmax(design, item)
        if mm is None:
            warnings.append(f"'{item}'은 점수가 없어 최적화에서 제외했습니다.")
            continue
        ranges[item] = mm
        used.append(item)

    def _goal(item: str) -> str:
        return goals.get(item, "max")

    def _w(item: str) -> float:
        return float(weights.get(item, 1.0))

    # 1) 관측 런 랭킹 (desirability)
    ranked: list[RunScore] = []
    for r in design.runs:
        per_item: dict[str, float] = {}
        num = 0.0
        den = 0.0
        for item in used:
            sc = r.scores.get(item)
            if sc is None:
                continue
            lo, hi = ranges[item]
            if hi - lo < _EPS:
                d = 1.0  # 변별 없음
            else:
                d = (sc - lo) / (hi - lo)
                if _goal(item) == "min":
                    d = 1.0 - d
            per_item[item] = round(d, 3)
            num += _w(item) * d
            den += _w(item)
        desir = round(num / den, 3) if den > 0 else None
        ranked.append(
            RunScore(
                run_id=r.run_id,
                factor_values={k: str(v) for k, v in r.factor_values.items()},
                desirability=desir,
                per_item=per_item,
            )
        )
    ranked.sort(key=lambda x: (x.desirability is not None, x.desirability or 0.0), reverse=True)
    best = ranked[0] if ranked and ranked[0].desirability is not None else None

    # 2) 주효과 기반 추천 최적
    analysis = doe_analysis(design)
    choices: list[FactorChoice] = []
    optimum: dict[str, str] = {}
    for factor in design.factors:
        influence = 0.0
        for item in used:
            eff = analysis.main_effects[factor].get(item)
            if eff is None:
                continue
            lo, hi = ranges[item]
            rng = hi - lo
            if rng < _EPS:
                continue
            direction = 1.0 if _goal(item) == "max" else -1.0
            # main_effect(=high-low)를 항목 범위로 정규화, 목표 방향 반영, 가중
            influence += _w(item) * direction * (eff / rng)
        if influence > _EPS:
            level = "high"
        elif influence < -_EPS:
            level = "low"
        else:
            level = "무관"
        choices.append(FactorChoice(factor=factor, level=level, influence=round(influence, 3)))
        optimum[factor] = "low" if level == "무관" else level

    return DoeRecommendation(
        goals={i: _goal(i) for i in used},
        weights={i: _w(i) for i in used},
        used_items=used,
        ranked=ranked,
        best_run=best,
        factor_choices=choices,
        predicted_optimum=optimum,
        warnings=warnings,
    )


__all__ = ["RunScore", "FactorChoice", "DoeRecommendation", "recommend"]
