"""doe_optimize: DOE 추천 조합(desirability + 주효과 기반) 테스트."""

from __future__ import annotations

from brandlab.doe_optimize import recommend
from brandlab.loader import load_doe

DESIGN = "experiments/doe/basic-lotion-screening.yaml"
# 주효과(기지): emulsifier→유화안정성 +2 / oil→보습감 +2·발림성 -2 / humectant→끈적임 +2
GOALS = {"유화안정성": "max", "보습감": "max", "발림성": "max", "끈적임": "min"}


def _choices(rec):
    return {c.factor: c.level for c in rec.factor_choices}


def test_predicted_optimum_directions():
    rec = recommend(load_doe(DESIGN), GOALS)
    ch = _choices(rec)
    # 유화제↑ = 유화안정성↑ → high
    assert ch["emulsifier"] == "high"
    # 글리세린↑ = 끈적임↑(최소화 목표) → low
    assert ch["humectant"] == "low"
    # 오일↑ = 보습↑ 이지만 발림↓ (동일 가중이면 상쇄) → 무관
    assert ch["oil"] == "무관"


def test_weight_breaks_tradeoff():
    # 보습감에 가중을 크게 주면 오일은 high로 기운다.
    rec = recommend(load_doe(DESIGN), GOALS, weights={"보습감": 3.0})
    assert _choices(rec)["oil"] == "high"


def test_best_run_is_top_desirability():
    rec = recommend(load_doe(DESIGN), GOALS)
    assert rec.best_run is not None
    ds = [r.desirability for r in rec.ranked if r.desirability is not None]
    assert rec.best_run.desirability == max(ds)
    # 랭킹은 내림차순
    assert ds == sorted(ds, reverse=True)


def test_default_goals_all_max():
    rec = recommend(load_doe(DESIGN))
    assert set(rec.goals.values()) == {"max"}
    assert len(rec.used_items) == 4


def test_missing_scores_excluded_with_warning():
    design = load_doe(DESIGN)
    for r in design.runs:  # 한 항목을 전부 결측 처리
        r.scores["보습감"] = None
    rec = recommend(design, GOALS)
    assert "보습감" not in rec.used_items
    assert any("보습감" in w for w in rec.warnings)
