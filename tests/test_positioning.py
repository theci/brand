"""positioning: 포지셔닝 엔진 테스트."""

from __future__ import annotations

from brandlab.core.models import ComparisonRow, Positioning
from brandlab.loader import BrandLab, load_positioning
from brandlab.positioning import (
    build_statement,
    comparison_summary,
    save_positioning,
    suggest_metrics,
    variants,
)


def _full():
    return Positioning(
        target="성분표 읽는 민감성 피부",
        competitor="이름만 앞세운 마케팅",
        pain="환절기 볼 붉어짐",
        tech="HLB 균형 유화 공정",
        metric_benefit="스쿠알란 9% 배합",
        category="성분 중심 로션",
        entry_situations=["환절기 볼이 붉어질 때"],
    )


def test_statement_full_has_all_and_no_placeholder():
    s = build_statement(_full())
    for v in ["성분표 읽는 민감성 피부", "환절기 볼 붉어짐", "스쿠알란 9% 배합", "성분 중심 로션"]:
        assert v in s
    assert "[타겟]" not in s and "[카테고리]" not in s


def test_statement_empty_shows_placeholders():
    s = build_statement(Positioning())
    assert "[타겟]" in s and "[페인 포인트]" in s and "[수치적 이익]" in s


def test_variants_three_angles():
    vs = variants(_full())
    assert len(vs) == 3
    assert all(v.strip() for v in vs)
    # 진입점형은 상황을 포함
    assert "환절기 볼이 붉어질 때" in vs[0]


def test_suggest_metrics_from_evidence():
    lab = BrandLab.load()
    f = next(x for x in lab.formulas if x.slug == "basic-lotion" and x.version == 2)
    metrics = suggest_metrics(f, lab)
    assert metrics  # 숫자 있는 근거가 하나 이상
    assert all(any(ch.isdigit() for ch in m) for m in metrics)


def test_comparison_summary_only_wins():
    pos = Positioning(comparison=[
        ComparisonRow(axis="스쿠알란 함량", ours="9%", theirs="1%", ours_wins=True),
        ComparisonRow(axis="가격", ours="2만원", theirs="1만원", ours_wins=False),
    ])
    s = comparison_summary(pos)
    assert "스쿠알란 함량" in s and "가격" not in s


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "brand" / "positioning.yaml"
    save_positioning(_full(), path)
    loaded = load_positioning(path)
    assert loaded.target == "성분표 읽는 민감성 피부"
    assert loaded.entry_situations == ["환절기 볼이 붉어질 때"]


def test_load_missing_returns_empty(tmp_path):
    pos = load_positioning(tmp_path / "nope.yaml")
    assert isinstance(pos, Positioning)
    assert pos.target is None
