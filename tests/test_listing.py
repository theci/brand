"""listing: 상품 등록 자료 생성 테스트."""

from __future__ import annotations

from brandlab.core.models import BrandCore
from brandlab.listing import build_listing, listing_markdown, save_listing
from brandlab.loader import BrandLab


def _lab_lotion():
    lab = BrandLab.load()
    return lab, next(f for f in lab.formulas if f.slug == "basic-lotion" and f.version == 2)


def test_build_listing_core_fields():
    lab, f = _lab_lotion()
    core = BrandCore(brand_name="오브제", one_liner="성분 중심 스킨케어")
    L = build_listing(f, lab, core)
    assert L.inci_text  # 전성분 생성
    assert L.product_names[0].startswith("오브제")  # 브랜드+제품명
    assert L.evidence  # 근거 카드
    assert L.volume  # 50 ml
    assert any("Aqua" in L.inci_text for _ in [0])  # 물 포함


def test_background_prompt_forces_real_photo():
    lab, f = _lab_lotion()
    L = build_listing(f, lab)
    joined = " ".join(L.background_prompts)
    assert "never alter" in joined  # 제품 실물 변경 금지 가드
    assert any("실촬영" in s for s in L.shot_list)


def test_copy_prompt_has_compliance_rules():
    lab, f = _lab_lotion()
    L = build_listing(f, lab, BrandCore(brand_name="오브제"))
    assert "필수 준수" in L.copy_prompt
    assert "미백" in L.copy_prompt  # 기능성 표방 금지 규칙


def test_caution_regime_specific():
    lab = BrandLab.load()
    diffuser = next((f for f in lab.formulas if f.regime == "chemical_safety"), None)
    if diffuser is not None:
        L = build_listing(diffuser, lab)
        assert any("화기" in c for c in L.caution)


def test_markdown_and_save(tmp_path):
    lab, f = _lab_lotion()
    L = build_listing(f, lab, BrandCore(brand_name="오브제"))
    md = listing_markdown(L)
    assert "상품 등록 자료" in md
    assert "전성분" in md
    path = save_listing(L, root=tmp_path)
    assert path.exists()
    assert path.name == "basic-lotion_v2.md"
