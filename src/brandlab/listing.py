"""상품 등록(리스팅) 생성 — 상세페이지·커머스 텍스트 자료를 제품 데이터에서 조립한다.

LLM을 부르지 않는다. 제품 데이터(전성분·근거·용량·공정) + 브랜드 코어 시트를 조립해:
  - 상품명 후보 / 한 줄 소개 / 용량 / 전성분 고지 / 사용법 / 주의사항
  - 근거(증거) 카드
  - ★실촬영 컷 리스트 + 배경만 교체할 AI 프롬프트(제품 실물은 실촬영 필수)
  - 상세페이지 카피 '생성 프롬프트'(브랜드 자산 + 근거 + 규제 준수 → 외부 AI에 붙여넣기)

이미지 원칙: 제품 실물(형태·색·제형)은 AI 생성 금지, 실촬영. AI는 배경·무드만.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .brand_core import asset_text, evidence_cards
from .core.models import BrandCore, Formula
from .labeling import screen
from .loader import PROJECT_ROOT

# 화장품법상 금지·주의(카피 생성 프롬프트에 넣을 준수 지침)
_COMPLIANCE_RULES = [
    "의약품 오인 표현(치료·개선·완화·재생·항염) 금지",
    "기능성 표방(미백·주름개선·자외선차단) 금지 — 심사 미완료",
    "최상급·배타적 표현(최고·1위·유일·100%·완벽·부작용 없음) 금지",
    "근거 없는 효능 단정 금지 — 사실만 서술",
    "브랜드 어휘 사전 금지어 사용 금지",
]

# 반드시 확보할 실촬영 컷(제품 실물)
_SHOT_LIST = [
    "정면 제품컷(누끼)",
    "측면 제품컷",
    "45도 제품컷",
    "탑다운 제품컷",
    "제형 클로즈업 — ★실촬영 필수(질감·색은 AI 금지)",
    "제품 사용 장면컷",
]


@dataclass
class Listing:
    slug: str
    version: int
    product_names: list[str]
    one_liner: str | None
    volume: str | None
    inci_text: str
    usage: str
    caution: list[str]
    evidence: list[str]
    shot_list: list[str]
    background_prompts: list[str]
    copy_prompt: str
    warnings: list[str] = field(default_factory=list)


def _volume(formula: Formula) -> str | None:
    if formula.fill_volume_ml is not None:
        return f"{formula.fill_volume_ml:g} ml"
    if formula.net_weight_g is not None:
        return f"{formula.net_weight_g:g} g"
    return None


def _usage(formula: Formula) -> str:
    regime = formula.regime
    pt = formula.product_type.value
    if regime == "chemical_safety":
        return "리드스틱을 꽂아 공간에 두고 사용합니다. 화기에 주의하세요."
    if regime == "food":
        return "직사광선을 피해 서늘한 곳에 보관하고, 개봉 후 빨리 드세요."
    if pt == "rinse_off":
        return "적당량을 덜어 물과 함께 거품 내어 부드럽게 세정한 뒤 미온수로 헹굽니다."
    return "적당량을 덜어 피부에 부드럽게 펴 발라 흡수시킵니다. 아침·저녁 사용."


def _caution(formula: Formula) -> list[str]:
    if formula.regime == "chemical_safety":
        return [
            "화기 주의. 직사광선을 피해 보관.",
            "어린이·반려동물 손이 닿지 않는 곳에 보관.",
            "눈·피부에 직접 닿지 않게 주의. 삼키지 마세요.",
        ]
    if formula.regime == "food":
        return [
            "알레르기 유발 성분은 원재료명·함량을 확인하세요.",
            "직사광선을 피하고 개봉 후 냉장 보관.",
        ]
    return [
        "상처·습진 등 이상이 있는 부위에는 사용을 자제하세요.",
        "사용 중 붉은 반점·가려움·자극 등이 생기면 사용을 멈추고 전문의와 상담하세요.",
        "직사광선을 피해 보관하고, 어린이 손이 닿지 않는 곳에 두세요.",
    ]


def _background_prompts(formula: Formula, core: BrandCore) -> list[str]:
    """제품은 실촬영, 배경만 AI로 바꾸는 나노바나나식 프롬프트(영어)."""
    mood = "modern clean, editorial, premium"
    colors = []
    if core.visual.main_color:
        colors.append(core.visual.main_color)
    if core.visual.sub_color:
        colors.append(core.visual.sub_color)
    palette = f"brand palette {', '.join(colors)}" if colors else "warm beige minimal palette"
    guard = (
        "Use the uploaded REAL product photo as reference; keep its exact shape, color, "
        "and texture unchanged. Generate ONLY the background and mood — never alter or "
        "re-render the product itself."
    )
    return [
        f"[Subject] the uploaded real product. [Composition] minimal centered, negative space. "
        f"[Lighting & Background] soft diffused top-left studio light, {palette}, gentle shadow. "
        f"[Aesthetic] {mood}. {guard}",
        f"[Subject] the uploaded real product on a textured stone/wood base. "
        f"[Composition] 45-degree, rule of thirds. [Lighting & Background] warm natural daylight, "
        f"subtle props, {palette}. [Aesthetic] natural organic premium. {guard}",
    ]


def _copy_prompt(formula: Formula, core: BrandCore, evidence: list[str]) -> str:
    lines = [
        asset_text(core),
        "[이번 작업] 위 브랜드 자산과 아래 '검증된 근거'만 사용해, 커머스 상세페이지 텍스트를 만들어줘.",
        "",
        "[검증된 근거 — 이 사실만 쓸 것, 창작 금지]",
    ]
    lines += [f"- {e}" for e in evidence] or ["- (근거 미작성 — 브랜드 코어에서 추출하세요)"]
    lines += [
        "",
        "[출력]",
        "1. 상품명 후보 3개 (검색 키워드 자연스럽게)",
        "2. 상세페이지 상단 헤드라인 3안 (각 20자 이내)",
        "3. 상세페이지 본문 블록 5개 (블록별: 소제목 + 본문 3줄)",
        "4. 핵심 성분 소개 3개 (근거 기반, 효능 단정 금지)",
        "5. 사용법 3단계 / 주의사항",
        "",
        "[필수 준수]",
    ]
    lines += [f"- {r}" for r in _COMPLIANCE_RULES]
    return "\n".join(lines) + "\n"


def build_listing(
    formula: Formula,
    lab,
    core: BrandCore | None = None,
    *,
    stability=None,
    mask_percent: bool = True,
) -> Listing:
    """제품 데이터 + 브랜드 코어 → 리스팅 자료."""
    core = core or BrandCore()
    warnings: list[str] = []

    # 상품명 후보
    brand = (core.brand_name or "").strip()
    base = formula.product
    names: list[str] = []
    for cand in ([f"{brand} {base}"] if brand else []) + [base]:
        if cand and cand not in names:
            names.append(cand)

    # 전성분
    try:
        inci_text = screen(formula, lab).inci.text
    except Exception as exc:  # noqa: BLE001
        inci_text = ""
        warnings.append(f"전성분 생성 생략: {exc}")

    evidence = [
        c.text for c in evidence_cards(formula, lab, stability=stability, mask_percent=mask_percent)
    ]

    return Listing(
        slug=formula.slug,
        version=formula.version,
        product_names=names,
        one_liner=core.one_liner,
        volume=_volume(formula),
        inci_text=inci_text,
        usage=_usage(formula),
        caution=_caution(formula),
        evidence=evidence,
        shot_list=list(_SHOT_LIST),
        background_prompts=_background_prompts(formula, core),
        copy_prompt=_copy_prompt(formula, core, evidence),
        warnings=warnings,
    )


def listing_markdown(listing: Listing) -> str:
    """리스팅을 1개 markdown 문서로."""
    L = listing
    md = [
        f"# 상품 등록 자료 — {L.slug} v{L.version}",
        "",
        "## 기본 정보",
        f"- 상품명 후보: {', '.join(L.product_names)}",
        f"- 한 줄 소개: {L.one_liner or '(브랜드 코어에서 작성)'}",
        f"- 용량: {L.volume or '(미정)'}",
        "",
        "## 전성분 (표시 순서)",
        L.inci_text or "(전성분 생성 실패)",
        "",
        "## 사용법",
        L.usage,
        "",
        "## 주의사항",
        *[f"- {c}" for c in L.caution],
        "",
        "## 검증된 근거 (창작 금지)",
        *([f"- {e}" for e in L.evidence] or ["- (미작성)"]),
        "",
        "## 실촬영 컷 리스트 (제품 실물은 AI 금지)",
        *[f"- {s}" for s in L.shot_list],
        "",
        "## 배경 연출 AI 프롬프트 (제품은 실촬영, 배경만)",
        *[f"{i+1}. {p}" for i, p in enumerate(L.background_prompts)],
        "",
        "## 상세페이지 카피 생성 프롬프트 (외부 AI에 붙여넣기)",
        "```",
        L.copy_prompt.rstrip("\n"),
        "```",
        "",
        "> ⚠️ 규제·표현은 예시이며 1차 스크리닝입니다. 출고 전 규제 검수 게이트를 통과시키고 전문가 검토를 받으세요.",
    ]
    return "\n".join(md) + "\n"


def save_listing(listing: Listing, root: Path | str = PROJECT_ROOT) -> Path:
    """listings/<slug>_v<n>.md 로 저장."""
    out = Path(root) / "listings"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{listing.slug}_v{listing.version}.md"
    path.write_text(listing_markdown(listing), encoding="utf-8")
    return path


__all__ = ["Listing", "build_listing", "listing_markdown", "save_listing"]
