"""고객 접점·후기 키트(Phase 9) 테스트."""

from __future__ import annotations

from brandlab.core.models import BrandCore, Review
from brandlab.loader import load_reviews
from brandlab.touchpoints import (
    INCENTIVE_DISCLOSURE,
    check_message,
    insert_card,
    repurchase_sequence,
    review_request,
    reviews_to_evidence,
)

CORE = BrandCore(brand_name="테스트랩", promise="산뜻한 지속 보습", forbidden_words=["완벽"])


def test_insert_card_has_product_and_promise():
    card = insert_card(CORE, "수분 로션")
    assert "수분 로션" in card
    assert "산뜻한 지속 보습" in card
    assert "테스트랩" in card


def test_review_request_incentive_adds_disclosure():
    plain = review_request(CORE, "수분 로션", incentive=False)
    inc = review_request(CORE, "수분 로션", incentive=True)
    assert INCENTIVE_DISCLOSURE not in plain
    assert INCENTIVE_DISCLOSURE in inc


def test_repurchase_sequence_days():
    seq = repurchase_sequence(CORE, "수분 로션")
    assert [s.day for s in seq] == [3, 14, 40, 70]
    assert all("수분 로션" in s.message or s.title for s in seq)


def test_reviews_to_evidence_filters_verified_high_rating():
    reviews = [
        Review(id="a", rating=5, text="좋아요", verified=True),
        Review(id="b", rating=5, text="미검증", verified=False),  # 제외(미검증)
        Review(id="c", rating=3, text="낮은평점", verified=True),  # 제외(평점)
        Review(id="d", rating=4, text="협찬후기", verified=True, incentivized=True),
    ]
    cards = reviews_to_evidence(reviews)
    texts = [c.text for c in cards]
    assert any("좋아요" in t for t in texts)
    assert all(c.source == "후기" for c in cards)
    assert not any("미검증" in t for t in texts)
    assert not any("낮은평점" in t for t in texts)
    # 대가성 후기는 표기 필요 마킹
    assert any("대가성 표기 필요" in t for t in texts)


def test_generated_messages_pass_gate():
    # 기본 템플릿은 규제 위험 표현이 없어 게이트를 통과해야 한다
    assert check_message(insert_card(CORE, "수분 로션"), CORE).ok
    assert check_message(review_request(CORE, "수분 로션"), CORE).ok


def test_gate_flags_forbidden_word():
    res = check_message("이 제품은 완벽합니다", CORE)
    assert not res.ok  # 브랜드 금지어 '완벽' + 최상급 표현


def test_shipped_reviews_load():
    book = load_reviews()
    assert book.reviews  # 예시 후기 존재
    cards = reviews_to_evidence(book.reviews)
    assert cards  # 근거로 승격되는 후기 최소 1건
