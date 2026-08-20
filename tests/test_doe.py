"""DOE 분석 테스트."""

from __future__ import annotations

import pytest

from brandlab.doe import (
    MIN_COMPLETE_RUNS,
    doe_analysis,
    doe_report,
    interaction_plot,
    interpretation_sentences,
    main_effects_plot,
)
from brandlab.loader import load_doe
from brandlab.models import DoeDesign


def _design_2x2x1_scores():
    """손계산이 쉬운 통제 설계 (factor A만 응답 y에 +2 효과)."""
    # 4 run: A와 B 2인자, y = A수준에 따라 결정
    runs = [
        {"run_id": 1, "factor_values": {"A": "low", "B": "low"}, "scores": {"y": 2}},
        {"run_id": 2, "factor_values": {"A": "high", "B": "low"}, "scores": {"y": 4}},
        {"run_id": 3, "factor_values": {"A": "low", "B": "high"}, "scores": {"y": 2}},
        {"run_id": 4, "factor_values": {"A": "high", "B": "high"}, "scores": {"y": 4}},
    ]
    return DoeDesign(
        name="mini",
        factors=["A", "B"],
        response_items=["y"],
        runs=runs,
    )


# ---------------------------------------------------------------------------
# 주효과 손계산 일치
# ---------------------------------------------------------------------------
def test_main_effect_hand_calc():
    design = _design_2x2x1_scores()
    a = doe_analysis(design)
    # A 고수준 평균(4,4)=4, 저수준 평균(2,2)=2 → 주효과 +2
    assert a.main_effects["A"]["y"] == pytest.approx(2.0)
    # B는 효과 없음 → 0
    assert a.main_effects["B"]["y"] == pytest.approx(0.0)


def test_real_design_emulsifier_rinse_effect(project_root):
    design = load_doe(
        project_root / "experiments" / "doe" / "cleansing-balm-screening.yaml"
    )
    a = doe_analysis(design)
    # 데이터 구성상 유화제(emulsifier)의 헹굼 주효과 = +1.5
    assert a.main_effects["emulsifier"]["헹굼"] == pytest.approx(1.5)
    # 왁스의 경도 주효과 = +1.0
    assert a.main_effects["wax"]["경도"] == pytest.approx(1.0)


def test_interaction_computed(project_root):
    design = load_doe(
        project_root / "experiments" / "doe" / "cleansing-balm-screening.yaml"
    )
    a = doe_analysis(design)
    # 3인자 → 3개의 2요인 교호작용
    assert set(a.interactions.keys()) == {
        ("wax", "emulsifier"),
        ("wax", "shea"),
        ("emulsifier", "shea"),
    }
    for effs in a.interactions.values():
        assert set(effs.keys()) == set(a.response_items)


def test_numeric_factor_values():
    # low/high 대신 실제 수준값(숫자)으로도 부호 판정
    runs = [
        {"run_id": 1, "factor_values": {"A": 10}, "scores": {"y": 1}},
        {"run_id": 2, "factor_values": {"A": 20}, "scores": {"y": 3}},
    ]
    design = DoeDesign(name="num", factors=["A"], response_items=["y"], runs=runs)
    a = doe_analysis(design)
    assert a.main_effects["A"]["y"] == pytest.approx(2.0)  # 3 − 1


# ---------------------------------------------------------------------------
# run 8개 미만 경고 / 결측 안전
# ---------------------------------------------------------------------------
def test_incomplete_design_warns():
    design = _design_2x2x1_scores()  # 4 run < 8
    a = doe_analysis(design)
    assert not a.complete
    assert any("불완전" in w for w in a.warnings)


def test_missing_scores_do_not_break_mean():
    runs = [
        {"run_id": 1, "factor_values": {"A": "low"}, "scores": {"y": 2}},
        {"run_id": 2, "factor_values": {"A": "high"}, "scores": {"y": 4}},
        # 결측: scores에 y 없음
        {"run_id": 3, "factor_values": {"A": "low"}, "scores": {}},
        {"run_id": 4, "factor_values": {"A": "high"}, "scores": {"y": None}},
    ]
    design = DoeDesign(name="miss", factors=["A"], response_items=["y"], runs=runs)
    a = doe_analysis(design)
    # available-case: 고수준 [4], 저수준 [2] → +2 (결측 무시)
    assert a.main_effects["A"]["y"] == pytest.approx(2.0)
    assert any("결측" in w for w in a.warnings)


def test_effect_none_when_group_all_missing():
    runs = [
        {"run_id": 1, "factor_values": {"A": "low"}, "scores": {"y": 2}},
        {"run_id": 2, "factor_values": {"A": "high"}, "scores": {}},  # 고수준 결측
    ]
    design = DoeDesign(name="miss2", factors=["A"], response_items=["y"], runs=runs)
    a = doe_analysis(design)
    assert a.main_effects["A"]["y"] is None


# ---------------------------------------------------------------------------
# 리포트 / 플롯
# ---------------------------------------------------------------------------
def test_report_has_interpretation(project_root):
    design = load_doe(
        project_root / "experiments" / "doe" / "cleansing-balm-screening.yaml"
    )
    report = doe_report(design)
    assert "주효과" in report
    assert "교호작용" in report
    assert "해석" in report
    # 해석 문장에 dominant factor가 등장
    sentences = interpretation_sentences(doe_analysis(design))
    assert any("헹굼" in s for s in sentences)


def test_plots_saved(project_root, tmp_path):
    design = load_doe(
        project_root / "experiments" / "doe" / "cleansing-balm-screening.yaml"
    )
    a = doe_analysis(design)
    main_png = tmp_path / "main.png"
    inter_png = tmp_path / "inter.png"
    main_effects_plot(a, main_png)
    interaction_plot(a, inter_png)
    assert main_png.exists() and main_png.stat().st_size > 0
    assert inter_png.exists() and inter_png.stat().st_size > 0
