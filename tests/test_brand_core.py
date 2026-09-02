"""brand_core: 브랜드 코어 시트 근거 추출·자산 텍스트·저장 테스트."""

from __future__ import annotations

from brandlab.brand_core import asset_text, evidence_cards, save_brand_core
from brandlab.core.models import BrandCore, BrandVisual
from brandlab.loader import BrandLab, load_all_stability, load_brand_core


def _lab_and_lotion():
    lab = BrandLab.load()
    f = next(x for x in lab.formulas if x.slug == "basic-lotion" and x.version == 2)
    return lab, f


def test_evidence_cards_sources():
    lab, f = _lab_and_lotion()
    cards = evidence_cards(f, lab, stability=load_all_stability())
    sources = {c.source for c in cards}
    assert "전성분" in sources
    assert "처방" in sources
    assert "사전점검" in sources  # 유화 제품 → HLB 카드
    # 버전이력: basic-lotion은 v1·v2 존재
    assert any(c.source == "버전이력" for c in cards)


def test_hero_percent_masking():
    lab, f = _lab_and_lotion()
    unmasked = evidence_cards(f, lab, mask_percent=False)
    masked = evidence_cards(f, lab, mask_percent=True)
    hero_u = next(c.text for c in unmasked if c.source == "처방")
    hero_m = next(c.text for c in masked if c.source == "처방")
    assert any(ch.isdigit() for ch in hero_u)  # % 노출
    assert not any(ch.isdigit() for ch in hero_m)  # 마스킹 시 숫자 없음


def test_evidence_no_full_recipe_leak():
    # 근거는 전체 처방을 나열하지 않는다(성분 수보다 훨씬 적은 카드).
    lab, f = _lab_and_lotion()
    cards = evidence_cards(f, lab)
    assert len(cards) <= 8


def test_asset_text_sections():
    core = BrandCore(
        brand_name="오브제",
        entry_points=["환절기 볼 붉어짐"],
        evidence=["스쿠알란 9% 배합"],
        tone_adjectives=["담백한", "근거있는"],
        forbidden_words=["최고", "인생템"],
        visual=BrandVisual(main_color="#2B2B2B", container="50ml 유리자"),
        one_liner="성분 중심 스킨케어",
    )
    txt = asset_text(core, regulatory_forbidden=["미백", "주름개선"])
    assert "브랜드 자산" in txt
    assert "환절기 볼 붉어짐" in txt
    assert "스쿠알란 9% 배합" in txt
    assert "최고" in txt  # 금지어
    assert "미백" in txt  # 규제 금지어


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "brand" / "core.yaml"
    core = BrandCore(brand_name="테스트", persona="성분표 읽는 사람", evidence=["a", "b"])
    save_brand_core(core, path)
    loaded = load_brand_core(path)
    assert loaded.brand_name == "테스트"
    assert loaded.evidence == ["a", "b"]


def test_load_missing_returns_empty(tmp_path):
    core = load_brand_core(tmp_path / "nope.yaml")
    assert isinstance(core, BrandCore)
    assert core.brand_name is None
    assert core.evidence == []
