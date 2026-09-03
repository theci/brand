"""prompt_builder: 나노바나나 프롬프트 빌더 + 키워드 팔레트 테스트."""

from __future__ import annotations

from brandlab.core.models import BrandCore, BrandVisual
from brandlab.loader import BrandLab, load_prompt_keywords
from brandlab.prompt_builder import (
    MOODBOARD_KINDS,
    PRESETS,
    REALSHOT_GUARD,
    assemble,
    compose_blocks,
    moodboard_prompt,
    product_hints,
)


def test_keyword_palette_loaded():
    lib = load_prompt_keywords()
    cats = lib.categories
    for c in ["angle", "lighting", "composition", "texture", "color", "aesthetic"]:
        assert c in cats and len(cats[c]) >= 10
    # 대표 키워드 존재
    assert any(k.en == "top-down" for k in lib.get("angle"))


def test_presets_reference_real_keywords():
    # 모든 프리셋 키워드는 팔레트에 실제로 존재해야 한다(오타·유령 키워드 방지).
    lib = load_prompt_keywords()
    for name, sel in PRESETS.items():
        for cat, ens in sel.items():
            palette = {k.en for k in lib.get(cat)}
            missing = set(ens) - palette
            assert not missing, f"{name}/{cat}: {missing}"


def test_assemble_inserts_guard_for_real_product():
    blocks = compose_blocks(subject="the product (jar)", angle=["top-down"], lighting=["soft diffused"])
    p = assemble(blocks, real_product=True)
    assert REALSHOT_GUARD in p
    assert "[Subject]" in p and "[Composition]" in p


def test_assemble_no_guard_when_not_real_product():
    blocks = compose_blocks(concept="mood only", aesthetic=["modern clean"])
    p = assemble(blocks, real_product=False)
    assert REALSHOT_GUARD not in p


def test_compose_blocks_maps_categories():
    b = compose_blocks(
        angle=["top-down"], composition=["negative space"],
        texture=["matte finish"], styling_extra="soft bangs",
        lighting=["backlight"], color=["icy blue"], aesthetic=["luxury glossy"],
    )
    assert b["composition"] == "top-down, negative space"
    assert "matte finish" in b["styling"] and "soft bangs" in b["styling"]
    assert b["lighting"] == "backlight, icy blue"


def test_product_hints_from_core():
    lab = BrandLab.load()
    f = next(x for x in lab.formulas if x.slug == "basic-lotion" and x.version == 2)
    core = BrandCore(one_liner="성분 중심 스킨케어", visual=BrandVisual(main_color="#2B2B2B", texture="dewy"))
    h = product_hints(f, lab, core)
    assert h["concept"] == "성분 중심 스킨케어"
    assert "the product" in h["subject"]
    assert "#2B2B2B" in h["aesthetic"]


def test_moodboard_prompt_no_product_no_guard():
    core = BrandCore(
        brand_name="오후",
        one_liner="산뜻하게, 오후까지",
        tone_adjectives=["담백한", "정직한"],
        visual=BrandVisual(main_color="#EAE0D5", sub_color="#6B705C", texture="matte"),
    )
    p = moodboard_prompt(core, kind="무드보드")
    assert REALSHOT_GUARD not in p          # 제품 실물 없음 → 가드 없음
    assert "[Subject]" not in p             # 제품 subject 없음
    assert "오후" in p and "#EAE0D5" in p and "#6B705C" in p  # 브랜드명·컬러 반영
    assert "담백한" in p                     # 톤 반영
    assert "[Concept]" in p and "[Aesthetic" in p


def test_moodboard_kinds_all_render():
    core = BrandCore(brand_name="B", visual=BrandVisual(main_color="#111111"))
    for kind in MOODBOARD_KINDS:
        p = moodboard_prompt(core, kind=kind)
        assert "#111111" in p and p.strip()


def test_moodboard_empty_core_is_safe():
    p = moodboard_prompt(BrandCore())
    assert "[Concept]" in p                 # 최소 컨셉은 나온다
    assert REALSHOT_GUARD not in p
    assert "the brand" in p
