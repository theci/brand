"""개발 서사 / Build-in-Public — 흩어진 개발 기록을 타임라인·콘텐츠 소재로.

"제품은 베껴도 기술을 아는 창업자의 서사는 못 베낀다."
이미 쌓인 데이터(버전이력·배치기록·DOE·안정성)를 재사용해 새 저장은 최소.

  - timeline(slug): 개발 이벤트를 날짜순으로
  - content_seeds(slug): 마케팅 12포맷에 매핑한 콘텐츠 소재 카드(실패담·비하인드·성분해부…)
  - seed_to_prompt(seed, core): 브랜드 자산 + 규제 준수 + 실촬영 안내가 붙은 게시 프롬프트
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .brand_core import asset_text, evidence_cards
from .core.models import BrandCore

# 게시 프롬프트에 넣을 규제 준수(화장품법)
_RULES = [
    "의약품 오인 표현(치료·개선·완화·재생·항염) 금지",
    "기능성 표방(미백·주름개선·자외선차단) 금지 — 심사 미완료",
    "최상급·배타적 표현(최고·1위·유일·100%·완벽) 금지",
    "근거 없는 효능 단정 금지 — 겪은 사실만 서술",
    "제품 실물(형태·색·제형)은 실촬영, AI는 배경만",
]


@dataclass
class TimelineEvent:
    date: date | None
    kind: str  # 버전 | 배치 | 실험 | 안정성
    title: str
    detail: str = ""


@dataclass
class ContentSeed:
    format_no: int  # 마케팅 12포맷 번호
    format_name: str
    title: str
    angle: str


def _mine(slug: str, items, attr: str = "formula_ref"):
    out = []
    for it in items or []:
        ref = getattr(it, attr, None)
        if ref and slug in ref:
            out.append(it)
    return out


def timeline(slug: str, lab, *, batches=None, doe=None, stability=None) -> list[TimelineEvent]:
    """개발 이벤트를 날짜순으로(날짜 있는 것 먼저)."""
    ev: list[TimelineEvent] = []

    fs = sorted((f for f in lab.formulas if f.slug == slug), key=lambda f: f.version)
    for f in fs:
        if f.parent_version:
            ev.append(TimelineEvent(None, "버전", f"v{f.version} 개발", f"v{f.parent_version} 개선"))
        else:
            ev.append(TimelineEvent(None, "버전", f"v{f.version} 최초 개발", f.product))

    for b in _mine(slug, batches):
        yp = f" · 수율 {b.yield_percent:g}%" if b.yield_percent is not None else ""
        ev.append(TimelineEvent(b.date, "배치", f"배치 {b.batch_id}", (b.observations or "") + yp))

    for d in _mine(slug, doe):
        ev.append(TimelineEvent(None, "실험", f"DOE: {d.name}", f"{len(d.factors)}인자 {2 ** len(d.factors)}런"))

    for s in _mine(slug, stability):
        ev.append(TimelineEvent(s.start_date, "안정성", f"안정성 {s.sample_id}", f"{s.condition.value} 조건"))

    ev.sort(key=lambda e: (e.date is None, e.date or date.min))
    return ev


def content_seeds(slug: str, lab, *, batches=None, doe=None, stability=None) -> list[ContentSeed]:
    """개발 데이터에서 마케팅 12포맷 콘텐츠 소재를 뽑는다."""
    seeds: list[ContentSeed] = []
    fs = [f for f in lab.formulas if f.slug == slug]

    improved = [f for f in fs if f.parent_version]
    if improved:
        f = max(improved, key=lambda x: x.version)
        seeds.append(ContentSeed(
            11, "실패담", f"v{f.parent_version}의 문제를 v{f.version}에서 고친 이야기",
            "개발 중 엎은 과정 = 못 베끼는 신뢰",
        ))

    if fs:
        target = max(fs, key=lambda x: x.version)
        cards = evidence_cards(target, lab, mask_percent=False)
        star = next((c.text for c in cards if c.source == "전성분"), None)
        if star:
            seeds.append(ContentSeed(1, "성분 해부", star, "왜 이 성분을 이만큼 넣었나"))

    if _mine(slug, doe):
        seeds.append(ContentSeed(5, "미신 깨기", "무엇이 무엇을 지배하는지 실험으로 확인", "DOE 주효과 데이터"))

    if _mine(slug, batches):
        n = len(_mine(slug, batches))
        seeds.append(ContentSeed(4, "비하인드", f"직접 만든 배치 {n}회의 기록", "제조·수율·pH 과정"))

    if _mine(slug, stability):
        seeds.append(ContentSeed(4, "비하인드", "시간이 지나도 안 변하는지 증명", "45℃ 가속 안정성 시험"))

    seeds.append(ContentSeed(3, "만든 이유", "왜 이 제품을 만들었나", "창업 스토리 — 대기업이 못 하는 사람 이야기"))
    return seeds


def seed_to_prompt(seed: ContentSeed, core: BrandCore | None = None) -> str:
    """콘텐츠 소재 → 게시 프롬프트(브랜드 자산 + 규제 준수 + 실촬영 안내)."""
    core = core or BrandCore()
    lines = [
        asset_text(core),
        f"[콘텐츠 주제] {seed.format_no}. {seed.format_name} — {seed.title}",
        f"[각도] {seed.angle}",
        "",
        "[요청] 위 브랜드 자산과 아래 규칙으로 이 주제의 인스타 릴스 대본(20초, 0~2초 후킹)·"
        "피드 캡션(300자)·블로그 개요를 만들어줘. 내가 실제로 겪은 사실만, 창작 금지.",
        "",
        "[필수 준수]",
    ]
    lines += [f"- {r}" for r in _RULES]
    return "\n".join(lines) + "\n"


__all__ = ["TimelineEvent", "ContentSeed", "timeline", "content_seeds", "seed_to_prompt"]
