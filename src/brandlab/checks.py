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
    IncompatibilityRules,
    IncompatMatch,
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


# ---------------------------------------------------------------------------
# 제형·유수분 밸런스 분석 (로션/크림 개발 특화)
# ---------------------------------------------------------------------------
# 유상(oil phase)으로 보는 보습 역할
_OIL_ROLES = {"emollient", "occlusive", "emulsifier", "fragrance", "antioxidant"}


def _texture(oil_pct: float) -> str:
    """유상 % → 텍스처 분류(휴리스틱)."""
    if oil_pct < 8:
        return "라이트(에센스·젤 로션)"
    if oil_pct < 18:
        return "로션(가벼움)"
    if oil_pct < 30:
        return "크림"
    if oil_pct < 50:
        return "리치 크림"
    return "밤/무수 근접"


def moisture_role(ing: Ingredient | None) -> str:
    """원료의 보습 역할 추론. ing.moisture_role 우선, 없으면 category/HLB로."""
    if ing is None:
        return "other"
    if ing.moisture_role:
        return ing.moisture_role
    cat = ing.category
    if cat in {"왁스", "버터"}:
        return "occlusive"
    if cat == "에몰리언트":
        return "emollient"
    if cat == "보습제":
        return "humectant"
    if cat in {"계면활성제", "유화제"}:
        return "emulsifier"
    if cat in {"에센셜오일", "향료"} or ing.fragrance:
        return "fragrance"
    if cat == "산화방지제":
        return "antioxidant"
    if cat in {"용제", "용매"}:
        return "solvent"
    if cat == "점증제":  # 지방알코올(required_hlb 보유)=유상, 잔탄검 등=수상
        return "emollient" if ing.required_hlb is not None else "thickener_water"
    return "other"


@dataclass
class FormulationBalance:
    oil_pct: float  # 유상 합계 %
    water_pct: float  # 수상(=100-유상) %
    texture: str  # 텍스처 분류
    humectant_pct: float
    emollient_pct: float
    occlusive_pct: float
    emulsifier_pct: float
    role_pct: dict[str, float] = field(default_factory=dict)
    comments: list[str] = field(default_factory=list)


def formulation_balance(
    formula: Formula,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
) -> FormulationBalance:
    """유상/수상 비율·텍스처·휴멕턴트/에몰리언트/옥클루시브 3축을 계산한다."""
    idx = _ingredient_index(ingredients)
    agg = _aggregate(formula)

    role_pct: dict[str, float] = {}
    oil = 0.0
    for ing_id, pct in agg.items():
        ing = idx.get(ing_id)
        r = moisture_role(ing)
        role_pct[r] = role_pct.get(r, 0.0) + pct
        is_oil = r in _OIL_ROLES or (
            ing is not None and (ing.required_hlb is not None or ing.hlb is not None)
        )
        if is_oil:
            oil += pct

    oil = round(oil, 2)
    water = round(100.0 - oil, 2)

    def g(r: str) -> float:
        return round(role_pct.get(r, 0.0), 2)

    hum, emol, occl, emul = g("humectant"), g("emollient"), g("occlusive"), g("emulsifier")

    comments: list[str] = []
    if occl >= 15:
        comments.append(f"옥클루시브(왁스·버터·실리콘) {occl:g}% — 무겁고 번들거릴 수 있음(지성·여름 주의).")
    if hum >= 5 and occl < 3:
        comments.append(
            f"휴멕턴트 {hum:g}% 대비 잠금(옥클루시브) {occl:g}% — 건조 환경에선 오히려 당길 수 있음(잠금 보강 고려)."
        )
    if emol == 0 and occl == 0 and oil > 0:
        comments.append("유상이 유화제 위주 — 에몰리언트/옥클루시브가 적어 사용감이 빈약할 수 있음.")
    if oil == 0:
        comments.append("유상 0%(무수 또는 수상 전용) — 유수분 밸런스 개념이 크게 적용되지 않습니다.")
    if not comments:
        comments.append("유수분·보습 3축이 무난한 범위입니다.")

    return FormulationBalance(
        oil_pct=oil,
        water_pct=water,
        texture=_texture(oil),
        humectant_pct=hum,
        emollient_pct=emol,
        occlusive_pct=occl,
        emulsifier_pct=emul,
        role_pct={k: round(v, 2) for k, v in role_pct.items()},
        comments=comments,
    )


# ---------------------------------------------------------------------------
# 보존 시스템 점검 (물 든 제형의 미생물 방어)
# ---------------------------------------------------------------------------
_PRESERVATIVE_CATEGORIES = {"보존제"}
# 다기능 항균보조 — 단독으로는 광범위 보존제가 아님(보존 부담을 낮추는 보조).
_BOOSTER_IDS = {"pentylene-glycol", "hexanediol", "caprylyl-glycol", "ethylhexylglycerin"}
_WATER_INCI = {"water", "aqua"}
_WATER_IDS = {"water", "purified-water"}


@dataclass
class PreservationResult:
    is_water_based: bool
    preservatives: list[str]
    boosters: list[str]
    verdict: str  # "양호" | "주의" | "위험" | "해당없음"(무수)
    comments: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict in {"양호", "해당없음"}


def preservation_check(
    formula: Formula,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
) -> PreservationResult:
    """물이 든 처방에 보존제가 있는지·광범위한지 점검한다.

    - 무수(물 없음): 보존제 필수 아님 → '해당없음'
    - 물 있는데 보존제 없음 → '위험'
    - 보존제 있으나 단일·보조 없음 → '주의'(광범위 커버 권장)
    - 그 외 → '양호'
    """
    idx = _ingredient_index(ingredients)
    agg = _aggregate(formula)

    water = False
    pres: list[str] = []
    boost: list[str] = []
    for ing_id in agg:
        ing = idx.get(ing_id)
        if ing is None:
            continue
        if ing.inci.strip().lower() in _WATER_INCI or ing_id in _WATER_IDS:
            water = True
        if ing.category in _PRESERVATIVE_CATEGORIES:
            pres.append(ing.name)
        if ing_id in _BOOSTER_IDS:
            boost.append(ing.name)

    comments: list[str] = []
    if not water:
        verdict = "해당없음"
        comments.append("무수(물 없음) — 미생물 위험이 낮아 보존제가 필수는 아닙니다. 대신 산패(산화방지제)를 관리하세요.")
    elif not pres:
        verdict = "위험"
        comments.append("물이 들어가는데 보존제(카테고리 '보존제')가 없습니다. 미생물 오염 위험 — 보존제 필수.")
        if boost:
            comments.append(f"다기능 항균보조({', '.join(boost)})만으로는 광범위 보존이 부족할 수 있습니다.")
    else:
        verdict = "양호"
        comments.append(f"보존제 {len(pres)}종 포함: {', '.join(pres)}.")
        if len(pres) == 1 and not boost:
            verdict = "주의"
            comments.append("단일 보존제 — 세균·곰팡이·효모 광범위 커버를 위해 다기능 보조(펜틸렌글라이콜·1,2-헥산다이올 등) 병용을 권장.")
        comments.append("최종 방부력은 반드시 챌린지(방부력) 시험으로 검증하세요.")

    return PreservationResult(
        is_water_based=water,
        preservatives=pres,
        boosters=boost,
        verdict=verdict,
        comments=comments,
    )


# ---------------------------------------------------------------------------
# 원료 상용성(충돌) 점검
# ---------------------------------------------------------------------------
@dataclass
class CompatFinding:
    rule_id: str
    severity: str  # high | medium | low
    a_names: list[str]
    b_names: list[str]
    reason: str
    advice: str | None = None


_SEV_RANK = {"high": 0, "medium": 1, "low": 2}


def _match(ing: Ingredient, m: IncompatMatch) -> bool:
    if ing.id in m.ids:
        return True
    if ing.category in m.categories:
        return True
    inci = ing.inci.lower()
    return any(sub.lower() in inci for sub in m.inci_contains)


def compatibility_check(
    formula: Formula,
    *,
    ingredients: IngredientMaster | Mapping[str, Ingredient],
    rules: IncompatibilityRules,
) -> list[CompatFinding]:
    """처방 원료 조합을 규칙과 대조해 충돌을 찾는다. 규칙 없으면 빈 목록."""
    idx = _ingredient_index(ingredients)
    agg = _aggregate(formula)
    present = [idx[i] for i in agg if i in idx]

    findings: list[CompatFinding] = []
    for rule in rules.rules:
        a_hits = [ing.name for ing in present if _match(ing, rule.a)]
        b_hits = [ing.name for ing in present if _match(ing, rule.b)]
        # 서로 '다른' 원료가 a·b에 각각 있어야 실제 충돌(같은 원료 1개가 양쪽 매칭은 제외)
        if a_hits and b_hits and any(x != y for x in a_hits for y in b_hits):
            findings.append(
                CompatFinding(
                    rule_id=rule.id,
                    severity=rule.severity,
                    a_names=sorted(set(a_hits)),
                    b_names=sorted(set(b_hits)),
                    reason=rule.reason,
                    advice=rule.advice,
                )
            )
    findings.sort(key=lambda f: _SEV_RANK.get(f.severity, 3))
    return findings


__all__ = [
    "HlbResult",
    "LimitFinding",
    "CheckResult",
    "check_hlb",
    "check_limits",
    "check_formula",
    "FormulationBalance",
    "formulation_balance",
    "moisture_role",
    "PreservationResult",
    "preservation_check",
    "CompatFinding",
    "compatibility_check",
]
