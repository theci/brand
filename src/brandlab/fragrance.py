"""조향 관리 — 희석 환산 계량표, 노트 피라미드, IFRA 체크, 숙성 알림.

핵심 환산: 처방의 parts는 '원액(neat) 기준' 상대 비율이다.
  - 원액량 neat = parts/총parts × (총량 × 농도%)
  - 계량량(희석액) weigh = neat × 100/dilution   (예: 10% 희석액 3g = 원액 0.3g)
  - 희석액이 가져오는 용매 = weigh − neat → 추가 에탄올량에서 차감
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .models import AromaMaterial, AromaMaterialList, Fragrance

# 계량은 소수 3자리(mg)까지.
ROUND_G = 3

# 노트 표시 순서.
NOTE_ORDER = ("top", "middle", "base")

# 시향 평가 표준 시점 순서.
EVAL_TIMEPOINTS = ("0분", "30분", "2시간", "6시간", "24시간")


# ---------------------------------------------------------------------------
# 자료구조
# ---------------------------------------------------------------------------
@dataclass
class BlendRow:
    accord: str
    material_id: str
    name: str
    note: str | None
    dilution: float
    parts: float
    neat_g: float  # 원액 환산량
    weigh_g: float  # 실제 계량할 희석액 양


@dataclass
class BlendSheet:
    name: str
    version: int
    총량_g: float
    concentration_percent: float
    concentrate_g: float  # 향 원액 총량(= 총량 × 농도%)
    rows: list[BlendRow]
    total_weigh_g: float  # 계량할 희석액 총량
    solvent_in_dilutions_g: float  # 희석액이 가져오는 용매
    ethanol_to_add_g: float  # 추가로 넣을 에탄올
    other_g: float  # 나머지(물 등)
    warnings: list[str] = field(default_factory=list)


@dataclass
class NotePyramid:
    grams: dict[str, float]  # note -> 원액 g
    ratios: dict[str, float]  # note -> %
    total_g: float


@dataclass
class IfraFinding:
    material_id: str
    name: str
    usage_percent: float  # 완제품 중 원액 농도(%)
    limit_percent: float | None
    over: bool


@dataclass
class IfraResult:
    findings: list[IfraFinding]
    violations: list[IfraFinding]
    without_limit: list[str]  # 한도 미입력 원료명
    warnings: list[str] = field(default_factory=list)


@dataclass
class MacerationStatus:
    name: str
    version: int
    start_date: date | None
    ready_date: date | None
    weeks: int
    status: str  # "숙성중" | "시향 필요" | "완료" | "시작일 미상"
    days: int  # 숙성중이면 남은 일수, 시향 필요면 경과 일수


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
def _material_index(
    materials: AromaMaterialList | Mapping[str, AromaMaterial],
) -> dict[str, AromaMaterial]:
    if isinstance(materials, AromaMaterialList):
        return materials.index()
    return dict(materials)


# ---------------------------------------------------------------------------
# 1. blend_sheet
# ---------------------------------------------------------------------------
def blend_sheet(
    fragrance: Fragrance,
    materials: AromaMaterialList | Mapping[str, AromaMaterial],
) -> BlendSheet:
    """희석 배율을 반영한 실제 계량표를 만든다."""
    idx = _material_index(materials)
    total_parts = sum(m.parts for m in fragrance.all_materials())
    if total_parts <= 0:
        raise ValueError("parts 합계가 0입니다.")

    concentrate_g = fragrance.총량_g * fragrance.concentration_percent / 100.0
    warnings: list[str] = []
    rows: list[BlendRow] = []
    total_weigh = 0.0

    for accord in fragrance.accords:
        for fm in accord.materials:
            mat = idx.get(fm.id)
            if mat is None:
                warnings.append(
                    f"향료 원료 '{fm.id}'가 aroma_materials.yaml에 없습니다."
                )
            neat = fm.parts / total_parts * concentrate_g
            weigh = neat * 100.0 / fm.dilution
            total_weigh += weigh
            rows.append(
                BlendRow(
                    accord=accord.name,
                    material_id=fm.id,
                    name=mat.이름 if mat else fm.id,
                    note=mat.노트.value if mat else None,
                    dilution=fm.dilution,
                    parts=fm.parts,
                    neat_g=round(neat, ROUND_G),
                    weigh_g=round(weigh, ROUND_G),
                )
            )
            # 보유 희석농도와 다르면 안내(원액 100%는 예외)
            if (
                mat is not None
                and fm.dilution != 100
                and mat.희석농도_보유
                and fm.dilution not in mat.희석농도_보유
            ):
                warnings.append(
                    f"'{mat.이름}' {fm.dilution:g}% 희석액은 보유 목록({mat.희석농도_보유})에 "
                    "없습니다. 별도 제조 필요."
                )
            # 화장품용 아님 경고
            if mat is not None and not mat.화장품용_등급:
                warnings.append(f"'{mat.이름}'은 화장품용 등급이 아닙니다.")

    total_weigh = round(total_weigh, ROUND_G)
    solvent_in_dil = round(total_weigh - concentrate_g, ROUND_G)
    ethanol_target = fragrance.총량_g * fragrance.ethanol_percent / 100.0
    ethanol_to_add = round(ethanol_target - solvent_in_dil, ROUND_G)
    other = round(fragrance.총량_g - total_weigh - ethanol_to_add, ROUND_G)

    if ethanol_to_add < 0:
        warnings.append(
            f"희석액이 가져오는 용매({solvent_in_dil:g}g)가 목표 에탄올량"
            f"({ethanol_target:g}g)을 초과합니다. 농도/희석 배율을 조정하세요."
        )
    if other < 0:
        warnings.append(
            f"성분 합계가 총량({fragrance.총량_g:g}g)을 초과합니다(기타 {other:g}g). "
            "농도·에탄올·희석 배율을 재검토하세요."
        )

    return BlendSheet(
        name=fragrance.name,
        version=fragrance.version,
        총량_g=fragrance.총량_g,
        concentration_percent=fragrance.concentration_percent,
        concentrate_g=round(concentrate_g, ROUND_G),
        rows=rows,
        total_weigh_g=total_weigh,
        solvent_in_dilutions_g=solvent_in_dil,
        ethanol_to_add_g=ethanol_to_add,
        other_g=other,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 2. note_pyramid
# ---------------------------------------------------------------------------
def note_pyramid(
    fragrance: Fragrance,
    materials: AromaMaterialList | Mapping[str, AromaMaterial],
) -> NotePyramid:
    """top/middle/base 원액 비율을 계산한다."""
    sheet = blend_sheet(fragrance, materials)
    grams = {n: 0.0 for n in NOTE_ORDER}
    for row in sheet.rows:
        if row.note in grams:
            grams[row.note] += row.neat_g
    total = sum(grams.values())
    ratios = {
        n: (grams[n] / total * 100.0 if total else 0.0) for n in NOTE_ORDER
    }
    return NotePyramid(
        grams={n: round(grams[n], ROUND_G) for n in NOTE_ORDER},
        ratios={n: round(ratios[n], 2) for n in NOTE_ORDER},
        total_g=round(total, ROUND_G),
    )


def note_pyramid_plot(pyramid: NotePyramid, path: Path | str) -> Path:
    """노트 비율 막대 차트를 PNG로 저장."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _set_korean_font(matplotlib)

    notes = list(NOTE_ORDER)
    labels = {"top": "Top", "middle": "Middle", "base": "Base"}
    values = [pyramid.ratios[n] for n in notes]
    colors = {"top": "#ffd43b", "middle": "#f06595", "base": "#845ef7"}

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar([labels[n] for n in notes], values, color=[colors[n] for n in notes])
    for i, v in enumerate(values):
        ax.text(i, v, f"{v:g}%", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("비율 %")
    ax.set_ylim(0, max(values + [1]) * 1.15)
    ax.set_title("노트 피라미드")
    fig.tight_layout()
    out = Path(path)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def _set_korean_font(matplotlib) -> None:
    from matplotlib import font_manager

    for name in ["AppleGothic", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR"]:
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            matplotlib.rcParams["font.family"] = name
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


# ---------------------------------------------------------------------------
# 3. ifra_check
# ---------------------------------------------------------------------------
def ifra_check(
    fragrance: Fragrance,
    materials: AromaMaterialList | Mapping[str, AromaMaterial],
) -> IfraResult:
    """원료별 IFRA 한도(완제품 중 %) 대비 사용률을 체크한다."""
    idx = _material_index(materials)
    sheet = blend_sheet(fragrance, materials)

    # 같은 원료가 여러 어코드에 있으면 원액량 합산
    neat_by_id: dict[str, float] = {}
    for row in sheet.rows:
        neat_by_id[row.material_id] = neat_by_id.get(row.material_id, 0.0) + row.neat_g

    findings: list[IfraFinding] = []
    without_limit: list[str] = []
    for mid, neat in neat_by_id.items():
        mat = idx.get(mid)
        usage = neat / fragrance.총량_g * 100.0  # 완제품 중 원액 농도(%)
        limit = mat.ifra_한도_퍼센트 if mat else None
        name = mat.이름 if mat else mid
        if limit is None:
            without_limit.append(name)
            over = False
        else:
            over = usage > limit
        findings.append(
            IfraFinding(
                material_id=mid,
                name=name,
                usage_percent=round(usage, 4),
                limit_percent=limit,
                over=over,
            )
        )

    findings.sort(key=lambda f: f.usage_percent, reverse=True)
    violations = [f for f in findings if f.over]
    warnings = [
        f"IFRA 한도 초과: {v.name} 사용률 {v.usage_percent:g}% > 한도 {v.limit_percent:g}%"
        for v in violations
    ]
    if without_limit:
        warnings.append(
            "IFRA 한도 미입력 원료(체크 불가): " + ", ".join(sorted(set(without_limit)))
        )
    return IfraResult(
        findings=findings,
        violations=violations,
        without_limit=sorted(set(without_limit)),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 4. maceration_due
# ---------------------------------------------------------------------------
def maceration_status(
    fragrance: Fragrance, today: date | None = None
) -> MacerationStatus:
    today = today or date.today()
    start = fragrance.maceration_start_date
    if start is None:
        return MacerationStatus(
            name=fragrance.name,
            version=fragrance.version,
            start_date=None,
            ready_date=None,
            weeks=fragrance.maceration_weeks,
            status="시작일 미상",
            days=0,
        )
    ready = start + timedelta(weeks=fragrance.maceration_weeks)
    evaluated_after = any(ev.date >= ready for ev in fragrance.evaluations)
    if ready > today:
        status, days = "숙성중", (ready - today).days
    elif evaluated_after:
        status, days = "완료", 0
    else:
        status, days = "시향 필요", (today - ready).days
    return MacerationStatus(
        name=fragrance.name,
        version=fragrance.version,
        start_date=start,
        ready_date=ready,
        weeks=fragrance.maceration_weeks,
        status=status,
        days=days,
    )


def maceration_due(
    fragrances: Iterable[Fragrance], today: date | None = None
) -> list[MacerationStatus]:
    """숙성이 끝났는데 아직 시향하지 않은(시향 필요) 처방을 경과 큰 순으로 반환."""
    today = today or date.today()
    due = [
        s
        for s in (maceration_status(f, today) for f in fragrances)
        if s.status == "시향 필요"
    ]
    due.sort(key=lambda s: s.days, reverse=True)
    return due


# ---------------------------------------------------------------------------
# 5. 시향 평가 곡선
# ---------------------------------------------------------------------------
def evaluation_curve(fragrance: Fragrance) -> list[tuple[str, float]]:
    """시점별 평균 강도(여러 세션 평균)를 표준 시점 순서로 반환."""
    buckets: dict[str, list[int]] = {}
    for ev in fragrance.evaluations:
        for tp in ev.timepoints:
            buckets.setdefault(tp.시점, []).append(tp.강도)
    ordered = [t for t in EVAL_TIMEPOINTS if t in buckets]
    ordered += [t for t in buckets if t not in EVAL_TIMEPOINTS]
    return [(t, sum(buckets[t]) / len(buckets[t])) for t in ordered]


__all__ = [
    "ROUND_G",
    "NOTE_ORDER",
    "EVAL_TIMEPOINTS",
    "BlendRow",
    "BlendSheet",
    "NotePyramid",
    "IfraFinding",
    "IfraResult",
    "MacerationStatus",
    "blend_sheet",
    "note_pyramid",
    "note_pyramid_plot",
    "ifra_check",
    "maceration_status",
    "maceration_due",
    "evaluation_curve",
]
