"""시제품 관능·패널 평가 분석 — 항목별 집계·버전 비교·개선 힌트·근거 승격.

DOE(요인 최적화)·안정성(변질)과 달리, 확정 후보 시제품의 '선호·수용도'를 다수(타깃)에게
정량으로 받아 **본생산 직전 게이트**로 쓴다. 점수는 주관적·소표본 → 내부 의사결정·참고용이며
효능·효과 표방이 아니다. 근거로 승격할 때는 표본·방법 표기가 필요하다.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from .brand_core import EvidenceCard
from .core.models import PanelTest


@dataclass
class AttrStat:
    """평가 항목 1개의 집계."""

    attribute: str
    n: int  # 결측 제외 응답 수
    mean: float | None
    top_box: float | None  # 상위박스 비율(0..1): 점수 >= top_box_min
    target: float | None
    meets: bool | None  # mean >= target (target 없으면 None)


@dataclass
class PanelSummary:
    test_id: str
    formula_ref: str | None
    n_panelists: int  # 세그먼트 필터 후 응답 수
    scale_max: int
    stats: list[AttrStat]
    overall_mean: float | None  # 항목 평균들의 평균(항목 동일 가중)
    weak: list[str]  # 목표 미달 항목(개선 우선순위)


def _in_segment(response, segment: str | None) -> bool:
    return segment is None or response.segment == segment


def summarize(
    test: PanelTest, *, segment: str | None = None, top_box_min: float | None = None
) -> PanelSummary:
    """항목별 평균·top-box·목표 대비를 집계한다. 결측은 제외, segment 지정 시 해당만.

    top_box_min 기본값은 scale_max-1 (5점 척도의 상위 2박스=4·5). 결측/무응답은 안전 처리.
    """
    tb_min = top_box_min if top_box_min is not None else float(test.scale_max - 1)
    responses = [r for r in test.responses if _in_segment(r, segment)]
    targets = test.targets or {}
    stats: list[AttrStat] = []
    for attr in test.attributes:
        vals = [float(r.scores[attr]) for r in responses if r.scores.get(attr) is not None]
        n = len(vals)
        m = mean(vals) if n else None
        tb = (sum(1 for v in vals if v >= tb_min) / n) if n else None
        tgt = targets.get(attr)
        meets = (m >= tgt) if (m is not None and tgt is not None) else None
        stats.append(AttrStat(attr, n, m, tb, tgt, meets))
    means = [s.mean for s in stats if s.mean is not None]
    overall = mean(means) if means else None
    weak = [s.attribute for s in stats if s.meets is False]
    return PanelSummary(
        test.test_id, test.formula_ref, len(responses), test.scale_max, stats, overall, weak
    )


# ---------------------------------------------------------------------------
# 버전 비교 (v1 vs v2 …) — 항목별 승자 + 종합 승자
# ---------------------------------------------------------------------------
@dataclass
class CompareRow:
    attribute: str
    means: dict[str, float | None]  # 라벨 → 평균
    winner: str | None  # 최고 평균 라벨(동점·결측이면 None)


@dataclass
class PanelComparison:
    labels: list[str]
    rows: list[CompareRow]
    overall: dict[str, float | None]
    overall_winner: str | None


def _label(test: PanelTest) -> str:
    return test.formula_ref or test.test_id


def _argmax(d: dict[str, float | None]) -> str | None:
    vals = [(k, v) for k, v in d.items() if v is not None]
    if not vals:
        return None
    mx = max(v for _, v in vals)
    top = [k for k, v in vals if v == mx]
    return top[0] if len(top) == 1 else None  # 유일한 최고만 승자


def compare(tests: list[PanelTest], *, segment: str | None = None) -> PanelComparison:
    """여러 시제품(버전)을 항목별 평균으로 비교한다. 라벨은 formula_ref(없으면 test_id)."""
    summaries: list[tuple[str, PanelSummary]] = []
    seen: dict[str, int] = {}
    for t in tests:
        lbl = _label(t)
        seen[lbl] = seen.get(lbl, 0) + 1
        if seen[lbl] > 1:  # 라벨 충돌 시 고유화
            lbl = f"{lbl} ({t.test_id})"
        summaries.append((lbl, summarize(t, segment=segment)))
    labels = [lbl for lbl, _ in summaries]
    attrs: list[str] = []
    for _, s in summaries:
        for st in s.stats:
            if st.attribute not in attrs:
                attrs.append(st.attribute)
    rows: list[CompareRow] = []
    for attr in attrs:
        means: dict[str, float | None] = {}
        for lbl, s in summaries:
            st = next((x for x in s.stats if x.attribute == attr), None)
            means[lbl] = st.mean if st else None
        rows.append(CompareRow(attr, means, _argmax(means)))
    overall = {lbl: s.overall_mean for lbl, s in summaries}
    return PanelComparison(labels, rows, overall, _argmax(overall))


def improvement_hints(summary: PanelSummary) -> list[str]:
    """목표 미달 항목 → 다음 버전 개선 액션 문장(되먹임)."""
    return [
        f"{s.attribute} {s.mean:.1f} < 목표 {s.target:.1f} → 다음 버전에서 개선 검토"
        for s in summary.stats
        if s.meets is False and s.mean is not None and s.target is not None
    ]


def panel_to_evidence(
    test: PanelTest,
    *,
    min_mean: float = 4.0,
    min_n: int = 3,
    segment: str | None = "타깃",
    incentivized: bool = False,
    max_quotes: int = 2,
) -> list[EvidenceCard]:
    """강한 항목·대표 코멘트를 근거 카드로 승격한다(reviews_to_evidence와 동일 패턴).

    - 평균 min_mean 이상·표본 n>=min_n 항목만. source="관능평가".
    - 관능은 소표본·주관적이므로 '표본·방법 표기 필요'를 마킹. 대가성이면 뒷광고 표기도.
    """
    summary = summarize(test, segment=segment)
    seg_note = f"{segment} " if segment else ""
    mark = " ※표본·방법 표기 필요"
    if incentivized:
        mark += " ·대가성 표기 필요"
    cards: list[EvidenceCard] = []
    for s in summary.stats:
        if s.mean is not None and s.n >= min_n and s.mean >= min_mean:
            cards.append(
                EvidenceCard(
                    text=f"{s.attribute} 평균 {s.mean:.1f}/{test.scale_max} "
                    f"({seg_note}{s.n}명 관능){mark}",
                    source="관능평가",
                )
            )
    # 대표 코멘트 인용(세그먼트 내, 코멘트 있는 응답 중 개인 평균 상위)
    quoted = [
        r
        for r in test.responses
        if _in_segment(r, segment) and (r.comment or "").strip()
    ]

    def _rowmean(r) -> float:
        vs = [float(v) for v in r.scores.values() if v is not None]
        return mean(vs) if vs else 0.0

    quoted.sort(key=_rowmean, reverse=True)
    for r in quoted[:max_quotes]:
        cards.append(
            EvidenceCard(text=f'"{r.comment.strip()}" (관능 참여자){mark}', source="관능평가")
        )
    return cards


__all__ = [
    "AttrStat",
    "PanelSummary",
    "CompareRow",
    "PanelComparison",
    "summarize",
    "compare",
    "improvement_hints",
    "panel_to_evidence",
]
