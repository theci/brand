"""시제품 관능·패널 평가 — 모델·로더·집계·비교·근거 승격·파일 편집 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from brandlab.core.models import PanelResponse, PanelTest
from brandlab.experiment_edit import (
    create_panel,
    delete_experiment,
    panel_path,
    set_panel_responses,
)
from brandlab.loader import iter_panel_paths, load_all_panel, load_panel
from brandlab.panel import (
    compare,
    improvement_hints,
    panel_to_evidence,
    summarize,
)


def _sample() -> PanelTest:
    return PanelTest(
        test_id="t1",
        formula_ref="daily-lotion v2",
        scale_max=5,
        attributes=["촉촉함", "산뜻함", "재구매의사"],
        targets={"촉촉함": 4.0, "재구매의사": 4.0},
        responses=[
            PanelResponse(panelist="P1", segment="타깃", scores={"촉촉함": 4, "산뜻함": 5, "재구매의사": 5}, comment="안 밀려요"),
            PanelResponse(panelist="P2", segment="타깃", scores={"촉촉함": 3, "산뜻함": 4, "재구매의사": 4}),
            PanelResponse(panelist="P3", segment="비타깃", scores={"촉촉함": 5, "산뜻함": 3, "재구매의사": 3}, comment="무거워요"),
        ],
    )


# --- 모델·로더 (Step 1) ---
def test_example_panel_loads():
    tests = load_all_panel()
    assert any(t.test_id == "daily-lotion-v2-panel1" for t in tests)
    t = load_panel(iter_panel_paths()[0])
    assert t.responses and t.attributes


# --- 집계 (Step 2) ---
def test_summarize_mean_and_target():
    s = summarize(_sample())
    m = {a.attribute: a for a in s.stats}
    assert m["촉촉함"].mean == pytest.approx(4.0)  # (4+3+5)/3
    assert m["촉촉함"].meets is True  # 4.0 >= 4.0
    assert m["재구매의사"].mean == pytest.approx(4.0)  # (5+4+3)/3
    assert m["산뜻함"].meets is None  # 목표 없음


def test_summarize_segment_filter_and_weak():
    s = summarize(_sample(), segment="타깃")
    assert s.n_panelists == 2
    m = {a.attribute: a for a in s.stats}
    assert m["재구매의사"].mean == pytest.approx(4.5)  # (5+4)/2, 비타깃 3 제외
    # 타깃만: 촉촉함 (4+3)/2 = 3.5 < 4.0 → 약점
    assert "촉촉함" in s.weak


def test_summarize_top_box():
    # 기본 top_box_min = scale_max-1 = 4 → 촉촉함(4,3,5) 중 4 이상은 2/3
    s = summarize(_sample())
    m = {a.attribute: a for a in s.stats}
    assert m["촉촉함"].top_box == pytest.approx(2 / 3)


def test_summarize_missing_scores_safe():
    t = PanelTest(
        test_id="m", attributes=["a", "b"],
        responses=[
            PanelResponse(panelist="P1", scores={"a": 5}),  # b 결측
            PanelResponse(panelist="P2", scores={}),  # 전체 결측
        ],
    )
    s = summarize(t)
    m = {a.attribute: a for a in s.stats}
    assert m["a"].n == 1 and m["a"].mean == pytest.approx(5.0)
    assert m["b"].n == 0 and m["b"].mean is None


# --- 비교 (Step 2) ---
def test_compare_winner_per_attribute():
    v1 = PanelTest(test_id="v1", formula_ref="lotion v1", attributes=["촉촉함"],
                   responses=[PanelResponse(panelist="A", scores={"촉촉함": 3})])
    v2 = PanelTest(test_id="v2", formula_ref="lotion v2", attributes=["촉촉함"],
                   responses=[PanelResponse(panelist="B", scores={"촉촉함": 5})])
    c = compare([v1, v2])
    row = c.rows[0]
    assert row.winner == "lotion v2"
    assert c.overall_winner == "lotion v2"


def test_compare_tie_has_no_winner():
    v1 = PanelTest(test_id="v1", formula_ref="a", attributes=["x"],
                   responses=[PanelResponse(panelist="A", scores={"x": 4})])
    v2 = PanelTest(test_id="v2", formula_ref="b", attributes=["x"],
                   responses=[PanelResponse(panelist="B", scores={"x": 4})])
    assert compare([v1, v2]).rows[0].winner is None


# --- 개선 힌트 (Step 2) ---
def test_improvement_hints_only_for_weak():
    hints = improvement_hints(summarize(_sample(), segment="타깃"))
    assert any("촉촉함" in h and "목표" in h for h in hints)


# --- 근거 승격 (Step 4) ---
def test_panel_to_evidence_promotes_strong_attrs():
    t = _sample()
    cards = panel_to_evidence(t, min_mean=4.0, min_n=2, segment="타깃")
    texts = [c.text for c in cards]
    assert all(c.source == "관능평가" for c in cards)
    # 타깃 재구매의사 평균 4.5 → 승격, 표본·방법 표기 마킹
    assert any("재구매의사" in x and "표본·방법 표기 필요" in x for x in texts)
    # 대표 코멘트 인용 카드 포함
    assert any("안 밀려요" in x for x in texts)


def test_panel_to_evidence_incentivized_marks_disclosure():
    cards = panel_to_evidence(_sample(), min_mean=1.0, min_n=1, incentivized=True)
    assert any("대가성 표기 필요" in c.text for c in cards)


# --- 파일 생성·응답 입력·삭제 (Step 3) ---
def test_create_and_set_responses_roundtrip(tmp_path: Path):
    p = panel_path("unit-test", experiments_dir=tmp_path)
    create_panel(
        {"test_id": "unit-test", "formula_ref": "x v1", "scale_max": 5,
         "attributes": ["촉촉함", "향"]},
        path=p,
    )
    assert p.exists() and load_panel(p).responses == []
    set_panel_responses(p, [
        {"panelist": "P1", "segment": "타깃", "scores": {"촉촉함": 4, "향": None}, "comment": "좋음"},
        {"panelist": "", "scores": {"촉촉함": 5}},  # 이름 없음 → 무시
    ])
    t = load_panel(p)
    assert len(t.responses) == 1
    r = t.responses[0]
    assert r.panelist == "P1" and "향" not in r.scores  # None 결측 제외
    delete_experiment(p)
    assert not p.exists()


# --- 대시보드 알림 (Step 6) ---
def test_dashboard_panel_alerts():
    from brandlab.dashboard import build_dashboard
    from brandlab.loader import BrandLab

    lab = BrandLab.load()
    weak = PanelTest(
        test_id="w", formula_ref="x v1", attributes=["a"], targets={"a": 5.0},
        responses=[PanelResponse(panelist="P", scores={"a": 2})],
    )
    pending = PanelTest(test_id="p", attributes=["a"])  # 응답 없음
    keys = {al.key for al in build_dashboard(lab, panel_tests=[weak, pending])}
    assert "panel_weak" in keys
    assert "panel_pending" in keys
