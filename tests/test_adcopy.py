"""광고 문구 검사기 테스트."""

from __future__ import annotations

import pytest

from brandlab.adcopy import DISCLAIMER, highlight_html, lint
from brandlab.loader import load_ad_terms
from brandlab.models import AdTerm, AdTermList


@pytest.fixture
def terms() -> AdTermList:
    return AdTermList(
        terms=[
            AdTerm(
                expression="미백",
                category="functional_claim",
                risk="high",
                suggestion="피부 톤 케어",
                reference="기능성 심사 대상",
            ),
            AdTerm(
                expression="주름 개선",
                category="functional_claim",
                risk="high",
                suggestion="탄력 표현",
            ),
            AdTerm(
                expression="완벽",
                category="absolute_claim",
                risk="medium",
                suggestion="매끄러운",
            ),
        ]
    )


# ---------------------------------------------------------------------------
# 기본 탐지 + 위치
# ---------------------------------------------------------------------------
def test_finds_expression_with_position(terms):
    text = "이 제품은 미백 기능이 있습니다."
    result = lint(text, terms)
    m = next(f for f in result.findings if f.expression == "미백")
    assert m.risk == "high"
    assert m.category == "functional_claim"
    assert m.suggestion == "피부 톤 케어"
    assert text[m.start : m.end].startswith("미백")


def test_clean_text_no_findings(terms):
    result = lint("순한 사용감의 데일리 크림입니다.", terms)
    assert result.findings == []
    assert result.disclaimer == DISCLAIMER  # 통과해도 면책 문구는 항상


# ---------------------------------------------------------------------------
# 형태소 변형 (substring이 아니라 패턴)
# ---------------------------------------------------------------------------
def test_morphological_variants(terms):
    for variant in ["미백", "미백효과", "미백에", "미백을 원한다면"]:
        result = lint(variant, terms)
        assert any(f.expression == "미백" for f in result.findings), variant


def test_multiword_spacing_variants(terms):
    # "주름 개선" 등록 → "주름개선"(붙임)과 "주름 개선"(띄움) 모두 탐지
    for variant in ["주름개선 크림", "주름 개선 에센스", "주름개선효과"]:
        result = lint(variant, terms)
        assert any(f.expression == "주름 개선" for f in result.findings), variant


def test_matched_text_captures_variant(terms):
    result = lint("미백효과", terms)
    m = next(f for f in result.findings if f.expression == "미백")
    assert m.matched_text == "미백효과"


# ---------------------------------------------------------------------------
# 정렬 / 다중 탐지 / 위험도 집계
# ---------------------------------------------------------------------------
def test_multiple_findings_sorted_by_position(terms):
    text = "완벽한 미백과 주름개선"
    result = lint(text, terms)
    starts = [f.start for f in result.findings]
    assert starts == sorted(starts)
    assert len(result.findings) >= 3


def test_counts_by_risk(terms):
    result = lint("완벽한 미백", terms)
    counts = result.counts_by_risk()
    assert counts["high"] >= 1  # 미백
    assert counts["medium"] >= 1  # 완벽


# ---------------------------------------------------------------------------
# 빈 목록 / 패턴 오류 → 조용히 통과하지 않음
# ---------------------------------------------------------------------------
def test_empty_terms_warns():
    result = lint("미백 크림", AdTermList(terms=[]))
    assert result.findings == []
    assert any("표현이 없습니다" in w for w in result.warnings)


def test_bad_regex_pattern_warns_not_crash():
    bad = AdTermList(
        terms=[
            AdTerm(
                expression="x", category="drug_claim", risk="high", pattern="([",
            )
        ]
    )
    result = lint("치료 크림", bad)  # 예외 없이
    assert any("패턴 오류" in w for w in result.warnings)


def test_explicit_pattern_override():
    terms = AdTermList(
        terms=[
            AdTerm(
                expression="즉효",
                category="unverified_claim",
                risk="low",
                pattern=r"즉[효효]",
            )
        ]
    )
    assert lint("즉효 케어", terms).findings


# ---------------------------------------------------------------------------
# 하이라이트 HTML
# ---------------------------------------------------------------------------
def test_highlight_html_marks_and_escapes(terms):
    text = "미백 <b>강조</b>"
    result = lint(text, terms)
    html = highlight_html(text, result.findings)
    assert "<mark" in html
    assert "&lt;b&gt;" in html  # 원문 HTML은 이스케이프됨
    assert "background-color" in html


def test_highlight_empty_text(terms):
    assert highlight_html("", []) == ""


# ---------------------------------------------------------------------------
# 실데이터
# ---------------------------------------------------------------------------
def test_real_ad_terms_load_and_lint(project_root):
    terms = load_ad_terms(project_root / "data" / "regulatory" / "cosmetics" / "ad_terms.yaml")
    assert terms.terms
    text = "미백과 주름개선, 염증 완화에 좋고 하루만에 완벽한 피부."
    result = lint(text, terms)
    exprs = {f.expression for f in result.findings}
    assert "미백" in exprs
    assert "주름 개선" in exprs
    assert "염증 완화" in exprs
    assert "하루 만에" in exprs  # "하루만에"(붙임)도 탐지
    assert result.disclaimer == DISCLAIMER
