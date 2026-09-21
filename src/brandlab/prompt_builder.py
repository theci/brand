"""나노바나나 이미지 프롬프트 빌더.

두 갈래로 '프로 수준' 영어 프롬프트를 만든다.

1) **장면 레시피(scene recipe)** — 참고 프롬프트 모음처럼, 촬영 장면별로 이미 짜인
   멀티블록 템플릿(Subject/Composition/Lighting/Texture & Detail/Color Scheme/
   Camera & Perspective/Aesthetic)에 제품·브랜드 데이터를 자동으로 채운다.
   (탑뷰 히어로컷·원료 페트리·제형 스와치·자연물 연출·플로팅 물방울·상세 배경·모델컷)

2) **직접 조립(palette)** — 6블록 + 키워드 팔레트(prompt_keywords.yaml). `rich=True`면
   칩(en)이 아니라 팔레트의 hint 문장을 이어 붙이고, 카메라·컬러스킴·질감 디테일·
   레퍼런스 브랜드·품질 지시어 블록을 자동 확장한다.

★ 제품 실물(형태·색·제형)은 실촬영 필수 — real_product=True면 '제품 변경 금지' 가드를 강제 삽입한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .brand_core import suggest_container
from .core.models import BrandCore, Formula

# 제품 실물 보존 가드(실촬영 필수 규칙을 프롬프트에 기계적으로 삽입)
REALSHOT_GUARD = (
    "Use the uploaded REAL product photo as reference; keep its exact shape, color, and "
    "texture unchanged. Generate only the background and mood — never re-render the product."
)

# 품질·마감 지시어(공통 꼬리표) — 브랜드 컨셉 "가공하지 않은 파운더"에 맞춘 정직한 마감.
# 화려한 스튜디오 렌더가 아니라 자연광·실물 그대로. (구 이름 HONEST_FINISH → HONEST_FINISH)
HONEST_FINISH = (
    "natural-light photography, true-to-life color and real material texture, "
    "honest and unstyled — authentic, not glossy, not an artificial studio render"
)
# 기본 제외(네거티브) — 과장·오염 + '꾸며낸 화려함/가짜 감성'까지 차단
DEFAULT_EXCLUSIONS = (
    "no added text, no logos, no watermark, no extra props, no image noise, "
    "no glossy luxury sheen, no artificial studio gloss, no fake film-grain look, "
    "no virtual/CGI model"
)

# 레퍼런스 브랜드 톤(선택 옵션). 담백·자연을 앞에, 럭셔리는 뒤로 강등.
REF_BRANDS = {
    "담백·인디": "MUJI, Aesop, Frama — plain, honest, unbranded feel",
    "natural": "Innisfree, Melixir, Aesop",
    "clean": "Laneige, Sulwhasoo, Hera",
    "editorial": "NARS, Fenty Beauty, Hince",
    "luxury": "Dior, YSL Beauté, Tamburins",
}

# 6블록 + 프로 확장 블록 (key, 출력 라벨) — 참고 프롬프트 순서를 따른다.
_BLOCKS = [
    ("subject", "Subject"),
    ("concept", "Concept"),
    ("composition", "Composition"),
    ("styling", "Styling"),
    ("lighting", "Lighting & Background"),
    ("texture_detail", "Texture & Detail"),
    ("color_scheme", "Color Scheme"),
    ("camera", "Camera & Perspective"),
    ("aesthetic", "Aesthetic & Brand Context"),
]

# 앵글 → 렌즈·시점 문구(Camera & Perspective 블록 자동 생성용)
_CAMERA_HINTS: dict[str, str] = {
    "top-down": "90° overhead top-down view, 50mm lens, deep focus with uniform sharpness across the frame",
    "flat lay": "90° overhead flat-lay, 50mm lens, deep focus across the whole frame",
    "macro close-up": "85mm macro lens, shallow depth of field, tack-sharp on the texture with soft bokeh falloff",
    "45-degree": "45° diagonal side angle slightly above the midline, 70mm lens, balanced depth",
    "low-angle": "low-angle ~35° looking upward, 85mm lens, sculptural heroic perspective",
    "side profile": "straight side-profile, 85mm lens, edge-defining focus on the silhouette",
    "front-facing": "eye-level straight-on, 50mm lens, product-forward clarity",
    "eye-level": "eye-level neutral perspective, 50mm lens, moderate depth of field",
    "diagonal angle": "dynamic diagonal framing, 70mm lens, moderate depth of field",
    "product hero angle": "hero three-quarter angle slightly above, 85mm lens, product spotlight",
    "wide-angle": "wide 24-35mm view expanding the space, deep focus",
    "compressed angle": "compressed 100mm telephoto feel, shallow depth of field",
}
_DEFAULT_CAMERA = "eye-level three-quarter angle, 50mm lens, moderate depth of field"

# 조명·색온도 기본 꼬리표(참고 프롬프트가 늘 넣던 ~5500K·no harsh shadows)
_LIGHT_TAIL = "~5500K neutral daylight, soft even illumination, no harsh shadows, gentle grounding shadow for depth"


def product_hints(formula: Formula, lab, core: BrandCore | None = None) -> dict[str, str]:
    """제품 데이터·브랜드 코어에서 Subject/Concept/Styling/Aesthetic 초안을 만든다."""
    core = core or BrandCore()
    container = suggest_container(formula, lab) or formula.product
    subject = f"the product ({container})"
    concept = core.one_liner or f"{formula.product} — honest, natural-light product photo"
    styling = core.visual.texture or ""
    colors = [c for c in (core.visual.main_color, core.visual.sub_color) if c]
    aesthetic = (f"{', '.join(colors)} palette, " if colors else "") + "honest, unstyled, natural light"
    return {"subject": subject, "concept": concept, "styling": styling, "aesthetic": aesthetic}


def compose_blocks(
    *,
    subject: str = "",
    concept: str = "",
    angle: list[str] | None = None,
    lighting: list[str] | None = None,
    composition: list[str] | None = None,
    texture: list[str] | None = None,
    color: list[str] | None = None,
    aesthetic: list[str] | None = None,
    styling_extra: str = "",
) -> dict[str, str]:
    """카테고리 선택(키워드 en 목록)을 6블록 문자열로 매핑한다(칩 그대로 — 레거시)."""
    comp = ", ".join((angle or []) + (composition or []))
    styl = ", ".join(texture or [])
    if styling_extra.strip():
        styl = (styl + ", " if styl else "") + styling_extra.strip()
    light = ", ".join((lighting or []) + (color or []))
    aes = ", ".join(aesthetic or [])
    return {
        "subject": subject.strip(),
        "concept": concept.strip(),
        "composition": comp,
        "styling": styl,
        "lighting": light,
        "aesthetic": aes,
    }


def _join_sent(bits: list[str]) -> str:
    """문장 조각들을 중복 제거하며 '. '로 이어 붙인다."""
    seen: set[str] = set()
    out: list[str] = []
    for b in bits:
        s = (b or "").strip().rstrip(".")
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return ". ".join(out)


def _phrases(cat: str, ens: list[str] | None, lib) -> list[str]:
    """칩 en 목록 → 팔레트 hint 문장 목록(hint 없으면 en 그대로)."""
    if not ens:
        return []
    idx: dict[str, str] = {}
    if lib is not None:
        for k in lib.get(cat):
            idx[k.en] = (getattr(k, "hint", "") or k.en).strip()
    return [idx.get(e, e) for e in ens]


def compose_rich(
    *,
    subject: str = "",
    concept: str = "",
    lib=None,
    angle: list[str] | None = None,
    lighting: list[str] | None = None,
    composition: list[str] | None = None,
    texture: list[str] | None = None,
    color: list[str] | None = None,
    aesthetic: list[str] | None = None,
    styling_extra: str = "",
    brand_colors: list[str] | None = None,
    ref_brands: str = "",
) -> dict[str, str]:
    """칩 선택을 '프로 수준' 멀티블록 프롬프트로 확장한다.

    칩(en) 대신 팔레트 hint 문장을 이어 붙이고, Texture & Detail / Color Scheme /
    Camera & Perspective / 레퍼런스 브랜드 / 품질 지시어 블록을 자동으로 채운다.
    """
    angle = angle or []
    color = color or []

    comp_bits = _phrases("angle", angle, lib) + _phrases("composition", composition, lib)
    composition_s = _join_sent(comp_bits)

    styl_bits = _phrases("texture", texture, lib)
    if styling_extra.strip():
        styl_bits.append(styling_extra.strip())
    styling_s = _join_sent(styl_bits)

    light_bits = _phrases("lighting", lighting, lib) + _phrases("color", color, lib)
    light_bits.append(_LIGHT_TAIL)
    lighting_s = _join_sent(light_bits)

    texture_detail_s = ""
    if texture:
        texture_detail_s = _join_sent(
            _phrases("texture", texture, lib)
            + ["realistic material detail, crisp well-defined edges, no visible noise"]
        )

    cs_bits: list[str] = []
    if brand_colors:
        cs_bits.append("Brand palette " + " / ".join(brand_colors))
    if color:
        cs_bits.append("Tones: " + ", ".join(color))
    cs_bits.append("clean color grading, balanced highlights and shadows")
    color_scheme_s = _join_sent(cs_bits)

    camera_s = _CAMERA_HINTS.get(angle[0], _DEFAULT_CAMERA) if angle else _DEFAULT_CAMERA

    aes_bits = _phrases("aesthetic", aesthetic, lib)
    if ref_brands:
        aes_bits.append(f"inspired by {ref_brands}")
    aes_bits.append(HONEST_FINISH)
    aes_bits.append(DEFAULT_EXCLUSIONS)
    aesthetic_s = _join_sent(aes_bits)

    return {
        "subject": subject.strip(),
        "concept": concept.strip(),
        "composition": composition_s,
        "styling": styling_s,
        "lighting": lighting_s,
        "texture_detail": texture_detail_s,
        "color_scheme": color_scheme_s,
        "camera": camera_s,
        "aesthetic": aesthetic_s,
    }


def assemble(blocks: dict[str, str], *, real_product: bool = True) -> str:
    """블록 딕셔너리를 완성된 영어 프롬프트로 조립한다. 빈 블록은 생략."""
    lines: list[str] = []
    for key, label in _BLOCKS:
        val = (blocks.get(key) or "").strip()
        if key == "subject" and real_product:
            val = (val + ". " if val else "") + REALSHOT_GUARD
        if val:
            lines.append(f"[{label}] {val}")
    return "\n\n".join(lines) + "\n"


# txt 예시에서 뽑은 프리셋(카테고리 → 키워드 en 목록). 키워드는 팔레트에 존재해야 한다.
PRESETS: dict[str, dict[str, list[str]]] = {
    "제품 각도컷 (탑뷰)": {
        "angle": ["top-down"],
        "lighting": ["natural daylight", "soft diffused"],
        "composition": ["minimal centered", "negative space"],
        "color": ["neutral beige"],
        "texture": ["matte finish"],
        "aesthetic": ["modern clean", "minimal warm beige"],
    },
    "원료 시각화": {
        "angle": ["top-down"],
        "lighting": ["natural daylight"],
        "composition": ["side-by-side"],
        "texture": ["matte finish"],
        "color": ["neutral beige"],
        "aesthetic": ["modern clean", "natural organic"],
    },
    "제형 클로즈업": {
        "angle": ["macro close-up"],
        "lighting": ["natural daylight", "soft diffused"],
        "texture": ["matte finish"],
        "aesthetic": ["modern clean", "natural organic"],
    },
    "파운더·인물 연출컷": {
        "lighting": ["natural daylight", "side light"],
        "composition": ["rule of thirds"],
        "color": ["warm palette"],
        "aesthetic": ["lifestyle casual", "earth natural"],
    },
}


# ──────────────────────────────────────────────────────────────────────────
# 장면 레시피 — 촬영 장면별 멀티블록 템플릿(제품·브랜드 데이터를 자동 삽입)
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SceneRecipe:
    """촬영 장면 레시피. blocks의 값은 {placeholder}를 쓰는 템플릿 문자열."""

    label: str
    shot: str
    real_product: bool
    blocks: dict[str, str]
    needs_model: bool = False
    tags: list[str] = field(default_factory=list)


def _scene_context(
    formula: Formula | None, lab, core: BrandCore | None
) -> dict[str, str]:
    """장면 템플릿에 채워 넣을 컨텍스트(제품·브랜드·컬러·톤·레퍼런스)."""
    core = core or BrandCore()
    v = core.visual
    if formula is not None:
        container = suggest_container(formula, lab) or f"{formula.product} container"
        product = formula.product
    else:
        container = v.container or "the product container"
        product = core.brand_name or "the product"
    colors = [c for c in (v.main_color, v.sub_color, v.point_color) if c]
    palette = " / ".join(colors) if colors else "soft neutral tones"
    tone = ", ".join(core.tone_adjectives) if core.tone_adjectives else "honest, plain, unpretentious"
    mood = v.texture or "soft, light, fresh"
    concept = core.one_liner or core.promise or product
    return {
        "product": product,
        "container": container,
        "palette": palette,
        "main_color": v.main_color or "warm ivory",
        "sub_color": v.sub_color or "soft beige",
        "tone": tone,
        "mood": mood,
        "concept": concept,
        "ref_honest": REF_BRANDS["담백·인디"],
        "ref_clean": REF_BRANDS["clean"],
        "ref_natural": REF_BRANDS["natural"],
        "ref_luxury": REF_BRANDS["luxury"],
        "ref_editorial": REF_BRANDS["editorial"],
        "quality": HONEST_FINISH,
        "exclusions": DEFAULT_EXCLUSIONS,
    }


SCENES: dict[str, SceneRecipe] = {
    "제품 탑뷰 히어로컷": SceneRecipe(
        label="제품 탑뷰 히어로컷",
        shot="위에서 내려다본 미니멀 정물 — 상세페이지 대표컷",
        real_product=True,
        tags=["제품", "히어로"],
        blocks={
            "subject": "{product} in a {container}, viewed from directly above",
            "concept": "quiet, honest minimalism — {concept}",
            "composition": (
                "strong top-down angle centered on the product; symmetrical, product-focused "
                "layout with generous negative space; soft grounding shadow beneath for depth"
            ),
            "styling": "clean surfaces with subtle reflections; matte label with clear typography",
            "lighting": (
                "soft, even studio lighting from above emphasizing shape and material; "
                "smooth {main_color} background with gentle gradient; " + _LIGHT_TAIL
            ),
            "texture_detail": "realistic material detail, crisp well-defined edges, no visible noise",
            "color_scheme": "Brand palette {palette}. Clean color grading, balanced highlights",
            "camera": _CAMERA_HINTS["top-down"],
            "aesthetic": (
                "plain honest still-life — simple, minimal, unstyled; {tone}; "
                "inspired by {ref_honest}. " + HONEST_FINISH + ". " + DEFAULT_EXCLUSIONS
            ),
        },
    ),
    "제품 45도 히어로컷": SceneRecipe(
        label="제품 45도 히어로컷",
        shot="45도 사선 — 입체감과 라벨을 함께 보여주는 대표컷",
        real_product=True,
        tags=["제품", "히어로"],
        blocks={
            "subject": "{product} in a {container}, viewed from a 45-degree side angle",
            "concept": "honest simplicity, nothing to hide — {concept}",
            "composition": (
                "camera at a 45-degree diagonal, slightly above the midline, showing both the "
                "cap and the front face while preserving depth; refined proportion and symmetry"
            ),
            "styling": "smooth reflective surfaces catching soft highlights; matte label for contrast",
            "lighting": (
                "soft directional light from the front-left accentuating edges and contours; "
                "warm {main_color} background with delicate shadow gradation; " + _LIGHT_TAIL
            ),
            "texture_detail": "clean glass/plastic texture, well-defined edges, realistic reflections",
            "color_scheme": "Brand palette {palette}. Warm, editorial color grading",
            "camera": _CAMERA_HINTS["45-degree"],
            "aesthetic": (
                "minimalist and plain, honest and grounded; {tone}; inspired by {ref_honest}. "
                + HONEST_FINISH + ". " + DEFAULT_EXCLUSIONS
            ),
        },
    ),
    "원료 시각화 (페트리 3접시)": SceneRecipe(
        label="원료 시각화 (페트리 3접시)",
        shot="투명 페트리 3접시에 핵심 원료 3종 — 성분 소구 컷",
        real_product=False,
        tags=["원료", "성분"],
        blocks={
            "subject": (
                "three transparent shallow glass Petri dishes in a straight horizontal line "
                "on a pure white background; open circular dishes, no lids, thin rim visible; "
                "left: [ingredient_1], center: [ingredient_2], right: [ingredient_3]"
            ),
            "concept": "honest, clear ingredient story — {concept}",
            "composition": (
                "slightly elevated top view (~20°) showing the circular rims and soft shadow "
                "beneath each dish; identical spacing; seamless pure white, no gradient"
            ),
            "styling": "clear glossy glass with subtle reflection and light refraction; minimal, clinical",
            "lighting": (
                "soft diffused daylight from the top-right, gentle shadows and realistic rim "
                "highlights; bright, clean, minimal; " + _LIGHT_TAIL
            ),
            "texture_detail": "true-to-life ingredient texture; no text, labels, markings or measurement lines",
            "color_scheme": "pure white base; ingredient-driven accent colors; clean color grading",
            "camera": _CAMERA_HINTS["top-down"],
            "aesthetic": (
                "honest ingredient photography; {tone}; inspired by {ref_natural}. "
                + HONEST_FINISH + ". " + DEFAULT_EXCLUSIONS
            ),
        },
    ),
    "제형 스와치 (텍스처 발림컷)": SceneRecipe(
        label="제형 스와치 (텍스처 발림컷)",
        shot="크림/로션 제형을 넓게 펴 바른 텍스처 클로즈업 (발림·발색)",
        real_product=False,
        tags=["제형", "텍스처"],
        blocks={
            "subject": (
                "a wide organic smear of {product} formula, shaped like a soft brush stroke — "
                "thicker at one side, tapering off; the actual product used as color reference"
            ),
            "concept": "sensorial texture and finish — {concept}",
            "composition": (
                "top-down flat-lay centered on the smear with slightly irregular edges; "
                "clean, spacious negative space; soft drop shadow separating it from the surface"
            ),
            "styling": "creamy, moist, light finish (foamy cream, not dense clay); smooth even surface",
            "lighting": (
                "soft high-key light from the upper left, crisp yet diffused highlights across "
                "the top edge; subtle shadow to the lower right; pure {main_color} surface; " + _LIGHT_TAIL
            ),
            "texture_detail": (
                "smooth glossy body with realistic ridges and thickness variation; visible "
                "micro-detail; no reflections beyond natural sheen; no noise"
            ),
            "color_scheme": "Brand palette {palette}. Accurate formula color, even sheen",
            "camera": _CAMERA_HINTS["macro close-up"],
            "aesthetic": (
                "macro texture photography, honest minimalist tone; {tone}; "
                "inspired by {ref_natural}. " + HONEST_FINISH + ". " + DEFAULT_EXCLUSIONS
            ),
        },
    ),
    "자연물 연출컷 (성분 스토리)": SceneRecipe(
        label="자연물 연출컷 (성분 스토리)",
        shot="식물·자연 소품으로 성분 원산지·순함을 연출한 무드컷",
        real_product=True,
        tags=["제품", "자연", "무드"],
        blocks={
            "subject": (
                "{product} in a {container} placed at the center on a natural surface, "
                "surrounded by botanical props (leaves, dew drops, small wildflowers) that "
                "echo the key ingredients"
            ),
            "concept": "nature-origin purity and nourishment — {concept}",
            "composition": (
                "front-facing with a slight top-down perspective (~25-35°); product tilted "
                "gently toward the camera; props arranged diagonally for natural flow; "
                "background fades into soft green bokeh while the product stays sharp"
            ),
            "styling": "moist mossy/plant textures, tiny droplets; handcrafted organic feel",
            "lighting": (
                "warm natural daylight from the upper left, soft shadow to the lower right; "
                "cinematic, slightly dewy glow; " + _LIGHT_TAIL
            ),
            "texture_detail": "rich botanical detail, realistic dew and leaf texture, shallow bokeh behind",
            "color_scheme": "Brand palette {palette}; natural green + warm accents; organic tone",
            "camera": _CAMERA_HINTS["45-degree"],
            "aesthetic": (
                "honest natural still-life evoking real botanical origin; {tone}; "
                "inspired by {ref_natural}. " + HONEST_FINISH + ". " + DEFAULT_EXCLUSIONS
            ),
        },
    ),
    "플로팅 물방울컷 (수분·앰플)": SceneRecipe(
        label="플로팅 물방울컷 (수분·앰플)",
        shot="공중에 떠 물방울에 둘러싸인 제품 — 수분·청량 소구",
        real_product=True,
        tags=["제품", "수분", "무드"],
        blocks={
            "subject": (
                "{product} in a {container} appearing to float in midair, surrounded by 6-8 "
                "perfectly spherical water droplets of varying sizes suspended around it"
            ),
            "concept": "pure hydration and freshness — {concept}",
            "composition": (
                "product centered and vertical with a soft reflection glow beneath (floating, "
                "not resting); droplets layered in foreground/midground/background for depth; "
                "negative space ~1.5× the product height for an elegant editorial layout"
            ),
            "styling": "crystal-clear glass with refraction; glossy high-surface-tension droplets",
            "lighting": (
                "cool diffused daylight from the upper right, delicate specular highlights on "
                "the glass and droplets; luminous airy background; ~6200K cool white; no harsh shadows"
            ),
            "texture_detail": "sharp label and glass refraction with soft droplet bokeh; luminous, clean",
            "color_scheme": "Brand palette {palette}; cool luminous tone; airy color grading",
            "camera": _CAMERA_HINTS["low-angle"],
            "aesthetic": (
                "honest skincare shot emphasizing hydration and clarity; {tone}; "
                "inspired by {ref_natural}. " + HONEST_FINISH + ". " + DEFAULT_EXCLUSIONS
            ),
        },
    ),
    "상세페이지 배경 변주 (3×3)": SceneRecipe(
        label="상세페이지 배경 변주 (3×3)",
        shot="누끼컷에 배경만 바꿔 9종 변주 — 상세페이지 물량용",
        real_product=True,
        tags=["제품", "상세페이지"],
        blocks={
            "subject": (
                "the uploaded {product} arranged as 9 high-quality background/mood variations "
                "in a clean 3×3 grid on one sheet"
            ),
            "concept": "e-commerce detail-page variations — {concept}",
            "composition": (
                "even 3×3 grid, one product per cell, consistent framing and scale; each cell a "
                "different background/mood while the product stays identical in every cell"
            ),
            "styling": "consistent product placement; varied surfaces, props and backdrops per cell",
            "lighting": "consistent soft studio lighting across all cells; " + _LIGHT_TAIL,
            "texture_detail": "realistic, detail-page-ready rendering in every cell; no noise",
            "color_scheme": "Brand palette {palette} anchoring all nine cells; cohesive color grading",
            "camera": _CAMERA_HINTS["front-facing"],
            "aesthetic": (
                "realistic, suitable for e-commerce product detail pages; {tone}; "
                "inspired by {ref_natural}. " + HONEST_FINISH + ". " + DEFAULT_EXCLUSIONS
            ),
        },
    ),
    "파운더 연출컷 (제품 홀드)": SceneRecipe(
        label="파운더 연출컷 (제품 홀드)",
        shot="파운더 본인이 제품을 든 자연광 포트레이트 — 진짜 사진 참조(가상모델 금지)",
        real_product=True,
        needs_model=True,
        tags=["파운더", "제품", "진정성"],
        blocks={
            "subject": (
                "a candid, natural portrait of the REAL founder holding {product} in one hand "
                "so the label reads clearly; use the attached real founder photo as the subject "
                "reference and keep the real face, real skin and real proportions unchanged — "
                "do NOT beautify, do NOT generate a virtual/idealized model"
            ),
            "concept": "founder-led, honest and personal — this is the person who made it — {concept}",
            "composition": (
                "medium close-up, relaxed ¾ view; both the face and the product in focus; "
                "natural, slightly imperfect hand pose; a little breathing room in the frame"
            ),
            "styling": (
                "bare or minimal makeup, real skin texture kept; everyday clothing; "
                "plain real setting (home workspace / desk), not a studio backdrop"
            ),
            "lighting": (
                "soft natural window daylight from the side, gentle real shadows; "
                "no beauty-retouch glow; " + _LIGHT_TAIL
            ),
            "texture_detail": (
                "real skin with natural texture and small imperfections kept; crisp product label"
            ),
            "color_scheme": "Brand palette {palette}; plain, muted, true-to-life color grading",
            "camera": "medium close-up, 50mm lens, moderate depth of field, handheld feel",
            "aesthetic": (
                "honest founder portrait, lifestyle-documentary tone, unretouched; {tone}; "
                "inspired by {ref_honest}. Real photographic look, real person only. "
                + HONEST_FINISH + ". " + DEFAULT_EXCLUSIONS
            ),
        },
    ),
}


def scene_prompt(
    scene_key: str,
    *,
    formula: Formula | None = None,
    lab=None,
    core: BrandCore | None = None,
) -> str:
    """장면 레시피를 제품·브랜드 데이터로 채워 완성된 영어 프롬프트로 조립한다."""
    rec = SCENES[scene_key]
    ctx = _scene_context(formula, lab, core)
    blocks = {k: tmpl.format(**ctx) for k, tmpl in rec.blocks.items()}
    return assemble(blocks, real_product=rec.real_product)


# 브랜드 무드보드 — 제품 실물 없이 '브랜딩 느낌'만 빠르게 확인(비용 투입 전 탐색).
# 종류(한글 라벨 → 영어 컨셉 문구). 제품이 없으므로 REALSHOT_GUARD를 넣지 않는다.
MOODBOARD_KINDS: dict[str, str] = {
    "무드보드": "a curated brand mood board, a collage of textures, materials and color swatches",
    "컬러 스토리": "a brand color story, palette swatches paired with material and fabric texture samples",
    "패키지 무드": "packaging concept mood, blank unbranded container silhouettes in the brand palette",
    "키비주얼": "a brand key visual, a hero atmosphere scene expressing the brand feeling",
}


def moodboard_prompt(core: BrandCore, *, kind: str = "무드보드") -> str:
    """브랜드 코어의 컬러·톤만으로 브랜딩 느낌 확인용 무드보드 프롬프트를 만든다.

    제품 실물이 없는 기획 단계 탐색용이라 REALSHOT_GUARD 없이 자유 컨셉으로 생성한다
    (제품 촬영 프롬프트는 compose_blocks/assemble 경로를 쓴다).
    """
    v = core.visual
    base = MOODBOARD_KINDS.get(kind) or next(iter(MOODBOARD_KINDS.values()))
    concept = f"{base} for {core.brand_name or 'the brand'}"
    if core.one_liner:
        concept += f" — {core.one_liner}"
    colors = [c for c in (v.main_color, v.sub_color, v.point_color) if c]
    styling = ", ".join(x for x in (v.texture, v.photo_note) if x)
    aesthetic = ", ".join(
        [*core.tone_adjectives, "cohesive brand identity, editorial moodboard aesthetic"]
    )
    blocks = {
        "concept": concept,
        "composition": "balanced grid moodboard layout with generous negative space",
        "styling": styling,
        "lighting": f"palette {', '.join(colors)}" if colors else "soft natural daylight",
        "aesthetic": aesthetic,
    }
    return assemble(blocks, real_product=False)


__all__ = [
    "REALSHOT_GUARD",
    "HONEST_FINISH",
    "DEFAULT_EXCLUSIONS",
    "REF_BRANDS",
    "PRESETS",
    "MOODBOARD_KINDS",
    "SCENES",
    "SceneRecipe",
    "product_hints",
    "compose_blocks",
    "compose_rich",
    "assemble",
    "scene_prompt",
    "moodboard_prompt",
]
