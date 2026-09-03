"""고객 접점·후기 키트 (Phase 9) — 배송→소비자→재구매, 후기=새 증거.

브랜드 톤(BrandCore)으로 접점 문구를 만들고, 내보내기 전 규제 게이트(compliance_check)를
통과시킨다. 대가성(협찬·원고료) 후기 요청에는 **뒷광고 표기를 자동으로 붙인다.**
수집한 후기는 근거 카드(EvidenceCard)로 되먹여 브랜드 코어 ⑤ 근거를 강화한다.

문구는 1차 스크리닝이며 법적 판단이 아니다. 채널 정책·표시광고법은 별도 확인.
"""

from __future__ import annotations

from dataclasses import dataclass

from .brand_core import EvidenceCard
from .compliance import ComplianceResult, compliance_check
from .core.models import BrandCore, Review
from .models import AdTermList

# 추천·보증 등에 관한 표시·광고 심사지침(뒷광고 표기) — 대가성 후기 요청에 자동 첨부.
INCENTIVE_DISCLOSURE = "※ 이 후기는 브랜드로부터 제품(또는 원고료)을 제공받아 작성되었음을 표시해 주세요. (예: '협찬', '소정의 원고료를 받았습니다')"


@dataclass
class RepurchaseStep:
    day: int  # 배송 후 경과일(D+n)
    title: str
    message: str


def _brand(core: BrandCore) -> str:
    return core.brand_name or "우리 브랜드"


def insert_card(core: BrandCore, product_name: str) -> str:
    """동봉 카드 문구 — 감사 + 브랜드 약속(톤) + 사용 안내 + 후기 요청."""
    lines = [f"[{_brand(core)}] {product_name}을(를) 선택해 주셔서 고맙습니다."]
    if core.promise:
        lines.append(core.promise)
    elif core.one_liner:
        lines.append(core.one_liner)
    lines.append("권장 사용법대로 사용해 보시고, 궁금한 점은 언제든 문의해 주세요.")
    lines.append("솔직한 후기 한 줄이 다음 제품을 더 좋게 만드는 데 큰 힘이 됩니다.")
    return "\n".join(lines)


def review_request(core: BrandCore, product_name: str, *, incentive: bool = False) -> str:
    """후기 요청 메시지. incentive(대가성)면 뒷광고 표기를 자동 첨부."""
    msg = (
        f"안녕하세요! {_brand(core)}입니다. {product_name} 잘 사용하고 계신가요? "
        "2주 정도 써보신 솔직한 사용 경험을 남겨주시면 큰 도움이 됩니다."
    )
    if incentive:
        msg += "\n" + INCENTIVE_DISCLOSURE
    return msg


def repurchase_sequence(core: BrandCore, product_name: str) -> list[RepurchaseStep]:
    """카톡 재구매 시나리오 — D+3 / 14 / 40 / 70."""
    b = _brand(core)
    return [
        RepurchaseStep(3, "사용 확인",
                       f"{product_name} 잘 받으셨나요? 사용 중 불편한 점이 있으면 편하게 알려주세요."),
        RepurchaseStep(14, "후기 요청",
                       f"2주 사용해 보셨다면, {product_name} 사용 경험을 한 줄 후기로 남겨주시겠어요?"),
        RepurchaseStep(40, "소진 리마인드",
                       f"{product_name}이(가) 슬슬 떨어질 시점이에요. 다 쓰기 전에 준비해 두세요."),
        RepurchaseStep(70, "재구매 안내",
                       f"{b} 재구매 고객께 드리는 안내입니다. 필요하시면 편하게 다시 찾아주세요."),
    ]


def reviews_to_evidence(reviews: list[Review], *, min_rating: int = 4) -> list[EvidenceCard]:
    """후기 → 근거 카드. 구매 확인(verified)된 고평점만. 대가성은 표기 필요로 마킹."""
    cards: list[EvidenceCard] = []
    for r in reviews:
        if r.rating < min_rating or not r.verified:
            continue
        txt = f'"{r.text}" (★{r.rating}, 실사용 후기)'
        if r.incentivized:
            txt += " ※대가성 표기 필요"
        cards.append(EvidenceCard(text=txt, source="후기"))
    return cards


def check_message(
    text: str, core: BrandCore | None = None, *, terms: AdTermList | None = None
) -> ComplianceResult:
    """접점 문구를 규제 게이트에 통과시킨다(브랜드 금지어 포함)."""
    forbidden = core.forbidden_words if core else None
    return compliance_check(text, terms=terms, forbidden_words=forbidden)


__all__ = [
    "INCENTIVE_DISCLOSURE",
    "RepurchaseStep",
    "insert_card",
    "review_request",
    "repurchase_sequence",
    "reviews_to_evidence",
    "check_message",
]
