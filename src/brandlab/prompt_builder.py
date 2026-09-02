"""나노바나나 이미지 프롬프트 빌더.

txt의 6블록 구조([Subject]/[Concept]/[Composition]/[Styling]/[Lighting & Background]/
[Aesthetic & Brand Context])에, xlsx 키워드 팔레트(prompt_keywords.yaml)를 드롭다운 재료로 채워
완성된 영어 프롬프트를 조립한다. Subject/Concept는 제품 데이터·브랜드 코어에서 자동 초안.

★ 제품 실물(형태·색·제형)은 실촬영 필수 — real_product=True면 '제품 변경 금지' 가드를 강제 삽입한다.
"""

from __future__ import annotations

from .brand_core import suggest_container
from .core.models import BrandCore, Formula

# 제품 실물 보존 가드(실촬영 필수 규칙을 프롬프트에 기계적으로 삽입)
REALSHOT_GUARD = (
    "Use the uploaded REAL product photo as reference; keep its exact shape, color, and "
    "texture unchanged. Generate only the background and mood — never re-render the product."
)

# 6블록 (key, 출력 라벨)
_BLOCKS = [
    ("subject", "Subject"),
    ("concept", "Concept"),
    ("composition", "Composition"),
    ("styling", "Styling"),
    ("lighting", "Lighting & Background"),
    ("aesthetic", "Aesthetic & Brand Context"),
]

# txt 예시에서 뽑은 프리셋(카테고리 → 키워드 en 목록). 키워드는 팔레트에 존재해야 한다.
PRESETS: dict[str, dict[str, list[str]]] = {
    "제품 각도컷 (탑뷰)": {
        "angle": ["top-down"],
        "lighting": ["soft diffused", "top light"],
        "composition": ["minimal centered", "negative space"],
        "color": ["neutral beige"],
        "aesthetic": ["luxury glossy", "minimal warm beige"],
    },
    "원료 시각화": {
        "angle": ["top-down"],
        "lighting": ["natural daylight"],
        "composition": ["side-by-side"],
        "texture": ["glossy shine"],
        "color": ["pure white"],
        "aesthetic": ["modern clean", "editorial high-end"],
    },
    "제형 클로즈업": {
        "angle": ["macro close-up"],
        "lighting": ["soft diffused"],
        "texture": ["glossy shine"],
        "aesthetic": ["luxury glossy", "editorial high-end"],
    },
    "모델 연출컷": {
        "lighting": ["soft diffused", "studio key light"],
        "composition": ["rule of thirds"],
        "color": ["rosy pink"],
        "aesthetic": ["soft feminine", "romantic soft glow"],
    },
}


def product_hints(formula: Formula, lab, core: BrandCore | None = None) -> dict[str, str]:
    """제품 데이터·브랜드 코어에서 Subject/Concept/Styling/Aesthetic 초안을 만든다."""
    core = core or BrandCore()
    container = suggest_container(formula, lab) or formula.product
    subject = f"the product ({container})"
    concept = core.one_liner or f"{formula.product} — clean premium product photography"
    styling = core.visual.texture or ""
    colors = [c for c in (core.visual.main_color, core.visual.sub_color) if c]
    aesthetic = (f"{', '.join(colors)} palette, " if colors else "") + "modern clean editorial"
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
    """카테고리 선택(키워드 en 목록)을 6블록 문자열로 매핑한다."""
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


def assemble(blocks: dict[str, str], *, real_product: bool = True) -> str:
    """6블록 딕셔너리를 완성된 영어 프롬프트로 조립한다. 빈 블록은 생략."""
    lines: list[str] = []
    for key, label in _BLOCKS:
        val = (blocks.get(key) or "").strip()
        if key == "subject" and real_product:
            val = (val + ". " if val else "") + REALSHOT_GUARD
        if val:
            lines.append(f"[{label}] {val}")
    return "\n\n".join(lines) + "\n"


__all__ = [
    "REALSHOT_GUARD",
    "PRESETS",
    "product_hints",
    "compose_blocks",
    "assemble",
]
