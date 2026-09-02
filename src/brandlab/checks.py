"""처방 사전점검(check).

제형을 실제로 만들기 전에, 처방서 숫자만으로 잡을 수 있는 실패·위반을 미리 거른다.

  1) HLB 균형 — O/W 유화 처방에서 '오일이 요구하는 HLB'와 '유화제가 공급하는 HLB'가
     맞는지 계산한다. 어긋나면 유화가 깨질(층분리) 가능성이 높다. 초보 실패 1순위를
     비커에 넣기 전에 잡는다.
  2) 배합한도 — 각 원료 함량이 원료 권장상한(max_percent)과 규제 배합한도(limits.yaml)를
     넘는지/근접했는지 스캔한다.

물성을 정량 예측하지는 않는다. HLB는 '유화가 될 만한 조합인가'의 정성 판정이다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .core.models import (
    Formula,
    Ingredient,
    IngredientMaster,
    LimitList,
)

# HLB 공급/요구 차이 허용치. |Δ| ≤ OK면 적합, ≤ CAUTION이면 주의, 초과면 위험.
HLB_OK_TOLERANCE = 1.0
HLB_CAUTION_TOLERANCE = 2.0
# 배합한도 대비 이 비율 이상이면 '도달'로 경고(초과 직전).
LIMIT_NEAR_RATIO = 0.95


@dataclass
class HlbResult:
    applicable: bool  # 유화 처방(유화제+요구HLB 오일 모두 존재)인가
    required_hlb: float | None
    supplied_hlb: float | None
    emulsifiers: list[str] = field(default_factory=list)
    oils: list[str] = field(default_factory=list)
    verdict: str = "해당없음"  # "적합" | "주의" | "위험" | "해당없음"
    message: str = ""

    @property
    def gap(self) -> float | None:
        if self.required_hlb is None or self.supplied_hlb is None:
            return None
        return round(self.supplied_hlb - self.required_hlb, 2)


@dataclass
class LimitFinding:
    id: str
    name: str
    percent: float
    limit: float
    source: str  # "권장상한" | "배합한도"
    status: str  # "초과" | "도달"
    reference: str | None = None


@dataclass
class CheckResult:
    slug: str
    version: int
    hlb: HlbResult
    limit_findings: list[LimitFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        no_over = not any(f.status == "초과" for f in self.limit_findings)
        return no_over and self.hlb.verdict != "위험"


def _ingredient_index(
    ingredients: IngredientMaster | Mapping[str, Ingredient],
) -> dict[str, Ingredient]:
    if isinstance(ingredients, IngredientMaster):
        return ingredients.index()
    return dict(ingredients)


def _aggregate(formula: Formula) -> dict[str, float]:
    agg: dict[str, float] = {}
    for fi in (i for p in formula.phases for i in p.ingredients):
        agg[fi.id] = agg.get(fi.id, 0.0) + fi.percent
    return agg


def _weighted(pairs: list[tuple[float, float]]) -> float | None:
    """[(가중치, 값)] → 가중평균. 가중치 합이 0이면 None."""
    w = sum(p[0] for p in pairs)
    if w <= 0:
        return None
    return sum(p[0] * p[1] for p in pairs) / w


def check_hlb(
    formula: Formula,
    idx: Mapping[str, Ingredient],
    agg: Mapping[str, float],
) -> HlbResult:
    """유화 처방의 required HLB(오일 가중평균) vs 공급 HLB(유화제 가중평균)."""
    emul: list[tuple[float, float]] = []  # (percent, hlb)
    emul_ids: list[str] = []
    oils: list[tuple[float, float]] = []  # (percent, required_hlb)
    oil_ids: list[str] = []
    for ing_id, percent in agg.items():
        ing = idx.get(ing_id)
        if ing is None:
            continue
        if ing.hlb is not None:
            emul.append((percent, ing.hlb))
            emul_ids.append(ing_id)
        if ing.required_hlb is not None:
            oils.append((percent, ing.required_hlb))
            oil_ids.append(ing_id)

    supplied = _weighted(emul)
    required = _weighted(oils)

    if supplied is None or required is None:
        # 유화 처방이 아니거나 HLB 데이터가 없어 판정 생략
        msg = "유화(O/W) 처방이 아니거나 HLB 데이터(유화제 hlb·오일 required_hlb)가 없어 건너뜀"
        return HlbResult(
            applicable=False,
            required_hlb=required,
            supplied_hlb=supplied,
            emulsifiers=emul_ids,
            oils=oil_ids,
            verdict="해당없음",
            message=msg,
        )

    gap = abs(supplied - required)
    if gap <= HLB_OK_TOLERANCE:
        verdict = "적합"
        msg = f"공급 HLB {supplied:.1f} ≈ 요구 HLB {required:.1f} (Δ{supplied - required:+.1f}) — 유화 안정 예상"
    elif gap <= HLB_CAUTION_TOLERANCE:
        verdict = "주의"
        msg = (
            f"공급 HLB {supplied:.1f} vs 요구 HLB {required:.1f} (Δ{supplied - required:+.1f}) "
            "— 경계. 파일럿 배치로 층분리 확인 권장"
        )
    else:
        verdict = "위험"
        msg = (
            f"공급 HLB {supplied:.1f} vs 요구 HLB {required:.1f} (Δ{supplied - required:+.1f}) "
            "— 불일치. 유화 깨짐(층분리) 위험. 유화제 종류/비율 재조정 필요"
        )
    return HlbResult(
        applicable=True,
        required_hlb=round(required, 2),
        supplied_hlb=round(supplied, 2),
        emulsifiers=emul_ids,
        oils=oil_ids,
        verdict=verdict,
        message=msg,
    )


def check_limits(
    formula: Formula,
    idx: Mapping[str, Ingredient],
    agg: Mapping[str, float],
    limits: LimitList | None,
) -> list[LimitFinding]:
    """각 원료 함량이 권장상한(max_percent)·규제 배합한도(limits.yaml)를 넘는지 스캔."""
    # limits.yaml에서 이 처방 형태에 적용되는 원료별 한도 수집
    reg_caps: dict[str, tuple[float, str | None]] = {}
    if limits is not None:
        for lim in limits.limits:
            if lim.product_type is not None and lim.product_type != formula.product_type:
                continue
            cur = reg_caps.get(lim.ingredient_id)
            if cur is None or lim.max_percent < cur[0]:
                reg_caps[lim.ingredient_id] = (lim.max_percent, lim.reference)

    findings: list[LimitFinding] = []
    for ing_id, percent in agg.items():
        ing = idx.get(ing_id)
        name = ing.name if ing else ing_id

        # 후보 한도: (값, 출처라벨, reference)
        candidates: list[tuple[float, str, str | None]] = []
        if ing is not None and ing.max_percent is not None:
            candidates.append((ing.max_percent, "권장상한", None))
        if ing_id in reg_caps:
            cap, ref = reg_caps[ing_id]
            candidates.append((cap, "배합한도", ref))

        for cap, source, ref in candidates:
            if percent > cap + 1e-9:
                status = "초과"
            elif percent >= cap * LIMIT_NEAR_RATIO:
                status = "도달"
            else:
                continue
            findings.append(
                LimitFinding(ing_id, name, percent, cap, source, status, ref)
            )

    # 초과 먼저, 그다음 도달
    findings.sort(key=lambda f: (f.status != "초과", f.id))
    return findings


def check_formula(
    formula: Formula,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    limits: LimitList | None = None,
) -> CheckResult:
    """처방 사전점검: HLB 균형 + 배합한도 스캔."""
    idx = _ingredient_index(ingredients)
    agg = _aggregate(formula)
    hlb = check_hlb(formula, idx, agg)
    findings = check_limits(formula, idx, agg, limits)
    return CheckResult(
        slug=formula.slug,
        version=formula.version,
        hlb=hlb,
        limit_findings=findings,
    )


__all__ = [
    "HlbResult",
    "LimitFinding",
    "CheckResult",
    "check_hlb",
    "check_limits",
    "check_formula",
]
