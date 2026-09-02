"""compliance: 규제 검수 게이트 테스트."""

from __future__ import annotations

from brandlab.compliance import compliance_check


def test_clean_text_passes():
    res = compliance_check("정제수와 스쿠알란을 담은 순한 로션입니다.")
    assert res.ok
    assert res.findings == []


def test_brand_forbidden_word_fails():
    res = compliance_check("이건 최고예요", forbidden_words=["최고"])
    assert not res.ok
    assert any(f.category == "브랜드금지어" and f.matched_text == "최고" for f in res.findings)


def test_regulatory_term_detected():
    # ad_terms.yaml에 등록된 표현(미백 등)이 잡혀야 한다.
    res = compliance_check("미백 효과가 뛰어난 크림")
    assert len(res.findings) >= 1


def test_empty_forbidden_list_ok():
    res = compliance_check("순한 데일리 로션", forbidden_words=[])
    assert res.ok
