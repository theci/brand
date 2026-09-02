"""포지셔닝 엔진 — '뾰족함'을 강제해 포지셔닝 문장을 조립한다.

목표 문장:
  "우리는 [타겟]에게 [경쟁]이 해결 못한 [페인]을 [신물질/공정]으로 [수치적 이익]으로
   해결하는 유일한 [카테고리]다."

수치적 차별점(metric_benefit)은 제품 데이터의 근거(evidence_cards) 중 '숫자가 있는 사실'을
후보로 제안한다 — 마케팅의 뿌리는 검증 가능한 수치다.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .brand_core import evidence_cards
from .core.models import Positioning
from .loader import DATA_DIR


def _g(v: str | None, placeholder: str) -> str:
    return (v or "").strip() or placeholder


def build_statement(pos: Positioning) -> str:
    """핵심 포지셔닝 문장(빈 칸은 대괄호 플레이스홀더)."""
    return (
        f"우리는 {_g(pos.target, '[타겟]')}에게 "
        f"{_g(pos.competitor, '[기존/경쟁]')}이 해결하지 못한 "
        f"{_g(pos.pain, '[페인 포인트]')}를, "
        f"{_g(pos.tech, '[신물질/신공정]')}으로 "
        f"{_g(pos.metric_benefit, '[수치적 이익]')}으로 해결하는 "
        f"유일한 {_g(pos.category, '[카테고리]')}다."
    )


def variants(pos: Positioning) -> list[str]:
    """각도가 다른 포지셔닝 3안(진입점형·적 대비형·엘리베이터 피치형)."""
    situation = pos.entry_situations[0] if pos.entry_situations else "[상황]"
    out = [
        # 진입점형 — 상황과 제품을 연결
        f"{_g(situation, '[상황]')}일 때 떠오르는 {_g(pos.category, '[카테고리]')}. "
        f"{_g(pos.metric_benefit, '[수치적 이익]')}로 {_g(pos.pain, '[페인]')}을 해결합니다.",
        # 적 대비형 — 무엇에 반대하는가
        f"{_g(pos.competitor, '[기존 방식]')}에 반대합니다. "
        f"{_g(pos.target, '[타겟]')}을 위해 {_g(pos.tech, '[신공정]')}으로 "
        f"{_g(pos.metric_benefit, '[수치]')}을 만듭니다.",
        # 엘리베이터 피치형 — 30자 지향
        f"{_g(pos.target, '[타겟]')}를 위한 {_g(pos.category, '[카테고리]')}. "
        f"{_g(pos.tech, '[신물질]')}로 {_g(pos.metric_benefit, '[수치]')}.",
    ]
    return out


def suggest_metrics(formula, lab) -> list[str]:
    """제품 데이터 근거 중 '숫자가 있는 사실'을 수치적 차별점 후보로 제안."""
    cards = evidence_cards(formula, lab, mask_percent=False)
    return [c.text for c in cards if any(ch.isdigit() for ch in c.text)]


def comparison_summary(pos: Positioning) -> str:
    """우리 우위 행만 모아 한 줄 요약(수치적 이익 작성에 활용)."""
    wins = [
        f"{r.axis} {r.ours}(vs {r.theirs})"
        for r in pos.comparison
        if r.ours_wins and r.axis.strip()
    ]
    return " · ".join(wins)


def save_positioning(
    pos: Positioning, path: Path | str = DATA_DIR / "brand" / "positioning.yaml"
) -> Path:
    """포지셔닝을 YAML로 저장한다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(pos.model_dump(exclude_none=True), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


__all__ = [
    "build_statement",
    "variants",
    "suggest_metrics",
    "comparison_summary",
    "save_positioning",
]
