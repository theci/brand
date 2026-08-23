"""RegimeAdvisor — 제품 의도의 규제 레짐 분류·비용 비교·적합성 판정.

핵심 문제: 같은 향을 "향수(화장품)"로 내면 등록 1회로 SKU 무제한,
"디퓨저(방향제)"로 내면 향마다 시험비 + 3년 갱신. 이름이 총비용을 수백만원 바꾼다.
매칭 규칙과 규제 수치는 코드가 아니라 data/regulatory/ YAML에서 읽는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..core.models import ClassificationRules, ProductIntent
from ..loader import (
    PROJECT_ROOT,
    load_classification_rules,
    load_config,
)
from ..regimes import get_regime
from ..regimes.base import UnsupportedRegimeError

DISCLAIMER = (
    "※ 이 판정은 사전 검토용입니다. 제품 분류는 최종적으로 관할 기관이 결정합니다. "
    "출시 전 환경부·한국환경산업기술원 또는 지방식약청에 서면 질의로 확인하십시오."
)


# ---------------------------------------------------------------------------
# 자료구조
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    regime_code: str
    category_code: str | None
    label: str
    note: str | None = None


@dataclass
class ClassifyResult:
    intent: ProductIntent
    candidates: list[Candidate]
    warnings: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


@dataclass
class CompareRow:
    candidate: Candidate
    supported: bool
    registration_cost: int  # 일회성 등록비
    per_sku_cost: int  # SKU 1개당 규제비
    sku_expansion_total: int  # per_sku × sku_count
    renewals: int  # horizon 내 갱신 횟수
    renewal_cost: int
    total_regulatory_cost: int
    lead_time_days: int
    renewal_period_years: int | None
    note: str | None = None


@dataclass
class CompareResult:
    intent: ProductIntent
    sku_count: int
    horizon_years: int
    rows: list[CompareRow]
    cheapest: CompareRow | None
    summary: str  # 최저 비용 경로 설명 문장
    warnings: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


@dataclass
class FeasibilityResult:
    intent: ProductIntent
    verdict: str  # "OK" | "CAUTION" | "REJECT"
    reasons: list[str]
    candidates: list[Candidate] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# 의도 → 레짐용 pseudo product (레짐 비용 메서드는 .product_category만 참조)
# ---------------------------------------------------------------------------
@dataclass
class _IntentProduct:
    regime: str
    product_category: str | None
    slug: str = "(intent)"
    version: int = 0


# ---------------------------------------------------------------------------
# 1. classify
# ---------------------------------------------------------------------------
def _rule_matches(match, intent: ProductIntent) -> bool:
    if match.use is not None and match.use != intent.use:
        return False
    if match.form is not None and match.form != intent.form:
        return False
    if match.claim is not None:
        allowed = [match.claim] if isinstance(match.claim, str) else list(match.claim)
        if not (set(allowed) & set(intent.claims)):
            return False
    return True


def classify(
    intent: ProductIntent,
    rules: ClassificationRules | None = None,
    root: Path | str = PROJECT_ROOT,
) -> ClassifyResult:
    """제품 의도에 맞는 레짐/카테고리 후보를 반환한다."""
    if rules is None:
        rules = load_classification_rules(Path(root) / "data" / "regulatory")

    warnings: list[str] = []
    if not rules.rules:
        warnings.append(
            "분류 규칙 미입력: classification_rules.yaml이 비어 있어 분류하지 못했습니다"
            "(통과가 아님)."
        )

    candidates: list[Candidate] = []
    seen: set[tuple[str, str | None]] = set()
    for rule in rules.rules:
        if _rule_matches(rule.match, intent):
            key = (rule.candidate.regime, rule.candidate.category_code)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                Candidate(
                    regime_code=rule.candidate.regime,
                    category_code=rule.candidate.category_code,
                    label=rule.candidate.category_label,
                    note=rule.candidate.note,
                )
            )

    if rules.rules and not candidates:
        warnings.append(
            "일치하는 분류 규칙이 없습니다. 제품 의도를 구체화하거나 관할 기관에 확인하세요."
        )
    if len({c.regime_code for c in candidates}) > 1:
        warnings.append(
            "복수 레짐 후보가 있습니다 — 제품 분류는 최종적으로 관할 기관이 결정합니다."
        )
    return ClassifyResult(intent=intent, candidates=candidates, warnings=warnings)


# ---------------------------------------------------------------------------
# 2. compare
# ---------------------------------------------------------------------------
def _renewals_in_horizon(horizon_years: int, renewal_years: int | None) -> int:
    if not renewal_years:
        return 0
    return max(0, (horizon_years - 1) // renewal_years)


def compare(
    intent: ProductIntent,
    sku_count: int,
    horizon_years: int,
    rules: ClassificationRules | None = None,
    root: Path | str = PROJECT_ROOT,
) -> CompareResult:
    """후보 레짐별 총 규제비용을 비교한다."""
    classified = classify(intent, rules, root)
    rows: list[CompareRow] = []

    for cand in classified.candidates:
        regime = get_regime(cand.regime_code, root)
        pseudo = _IntentProduct(cand.regime_code, cand.category_code)
        try:
            per_sku = regime.sku_expansion_cost(pseudo)
            entry = regime.entry_cost(pseudo).entry_cost
            lead = regime.lead_time_days(pseudo)
            renewal_years = regime.renewal_period_years(pseudo)
        except UnsupportedRegimeError:
            rows.append(
                CompareRow(
                    candidate=cand,
                    supported=False,
                    registration_cost=0,
                    per_sku_cost=0,
                    sku_expansion_total=0,
                    renewals=0,
                    renewal_cost=0,
                    total_regulatory_cost=0,
                    lead_time_days=0,
                    renewal_period_years=None,
                    note="미지원 레짐(신고/승인 불가) — 적합성 판정 참조",
                )
            )
            continue

        # per_sku>0(품목별 신고)이면 entry_cost는 품목 시험비와 동일하므로
        # 일회성 등록비로 중복 계산하지 않는다. per_sku==0(화장품)이면 entry가 일회성 등록비.
        registration = 0 if per_sku > 0 else entry
        sku_total = per_sku * sku_count
        renewals = _renewals_in_horizon(horizon_years, renewal_years)
        renewal_cost = renewals * sku_total
        total = registration + sku_total + renewal_cost
        rows.append(
            CompareRow(
                candidate=cand,
                supported=True,
                registration_cost=registration,
                per_sku_cost=per_sku,
                sku_expansion_total=sku_total,
                renewals=renewals,
                renewal_cost=renewal_cost,
                total_regulatory_cost=total,
                lead_time_days=lead,
                renewal_period_years=renewal_years,
            )
        )

    supported = [r for r in rows if r.supported]
    cheapest = min(supported, key=lambda r: r.total_regulatory_cost) if supported else None

    summary = _summary_sentence(cheapest, supported, sku_count, horizon_years)
    return CompareResult(
        intent=intent,
        sku_count=sku_count,
        horizon_years=horizon_years,
        rows=rows,
        cheapest=cheapest,
        summary=summary,
        warnings=list(classified.warnings),
    )


def _summary_sentence(
    cheapest: CompareRow | None,
    supported: list[CompareRow],
    sku_count: int,
    horizon_years: int,
) -> str:
    if cheapest is None:
        return "비교 가능한(지원되는) 레짐 후보가 없습니다."
    if len(supported) < 2:
        return (
            f"단일 경로: {cheapest.candidate.label} "
            f"(총 규제비용 {cheapest.total_regulatory_cost:,}원 / {horizon_years}년)."
        )
    dearest = max(supported, key=lambda r: r.total_regulatory_cost)
    total_diff = dearest.total_regulatory_cost - cheapest.total_regulatory_cost
    sku_diff = dearest.sku_expansion_total - cheapest.sku_expansion_total
    return (
        f"SKU {sku_count}종·{horizon_years}년 기준 최저 비용 경로는 "
        f"'{cheapest.candidate.label}'입니다. '{dearest.candidate.label}'보다 "
        f"총 {total_diff:,}원 저렴"
        + (
            f" (품목별 시험비 {sku_diff:,}원 차이가 주요인)"
            if sku_diff
            else ""
        )
        + "."
    )


# ---------------------------------------------------------------------------
# 3. feasibility
# ---------------------------------------------------------------------------
def feasibility(
    intent: ProductIntent,
    *,
    budget: int | None = None,
    sku_count: int = 1,
    horizon_years: int = 5,
    rules: ClassificationRules | None = None,
    root: Path | str = PROJECT_ROOT,
) -> FeasibilityResult:
    """1인 창업 적합성 판정 (REJECT / CAUTION / OK)."""
    classified = classify(intent, rules, root)
    reasons: list[str] = []

    # 1) 미지원 레짐(살생물제·의약외품) → REJECT
    # 미지원 레짐은 비용 조회에서 UnsupportedRegimeError를 던진다. 이걸로 판별하고,
    # 사유는 미지원 레짐의 validate(pseudo)에서 얻는다(미지원 validate는 product를 참조하지 않음).
    reject_reasons: list[str] = []
    for cand in classified.candidates:
        regime = get_regime(cand.regime_code, root)
        pseudo = _IntentProduct(cand.regime_code, cand.category_code)
        try:
            regime.entry_cost(pseudo)
        except UnsupportedRegimeError:
            findings = regime.validate(pseudo)
            msg = next(
                (f.message for f in findings if f.code == "regime.unsupported"),
                "이 카테고리는 1인 창업 규모에 맞지 않습니다.",
            )
            reject_reasons.append(f"[{cand.label}] {msg}")
    if reject_reasons:
        return FeasibilityResult(
            intent=intent,
            verdict="REJECT",
            reasons=reject_reasons,
            candidates=classified.candidates,
        )

    if not classified.candidates:
        return FeasibilityResult(
            intent=intent,
            verdict="CAUTION",
            reasons=[
                "일치하는 분류 규칙이 없어 레짐을 특정하지 못했습니다. 관할 기관 확인이 필요합니다."
            ],
            candidates=classified.candidates,
        )

    # 2) 예산 대비 규제비용 → CAUTION
    cmp = compare(intent, sku_count, horizon_years, rules, root)
    cheapest = cmp.cheapest
    verdict = "OK"
    if cheapest is not None:
        reasons.append(
            f"최저 비용 경로 '{cheapest.candidate.label}' 총 규제비용 "
            f"{cheapest.total_regulatory_cost:,}원 (SKU {sku_count}종·{horizon_years}년)."
        )
        cfg = load_config(Path(root) / "data" / "config.yaml")
        thresholds = cfg.regulatory_thresholds
        if budget:
            ratio = thresholds.budget_caution_ratio
            share = cheapest.total_regulatory_cost / budget
            if share > ratio:
                verdict = "CAUTION"
                reasons.append(
                    f"규제비용이 예산의 {share:.0%}로 임계({ratio:.0%})를 초과합니다. "
                    "총 예산 대비 비중을 재검토하세요."
                )
        # 예산을 안 줘도, 최저 경로 규제비용이 1인 창업 임계를 넘으면 CAUTION.
        # (건강기능식품 등 진입 부담이 큰 레짐을 자동으로 잡는다.)
        if verdict == "OK" and cheapest.total_regulatory_cost > thresholds.high_entry_cost:
            verdict = "CAUTION"
            reasons.append(
                f"규제비용 {cheapest.total_regulatory_cost:,}원이 1인 창업 임계"
                f"({thresholds.high_entry_cost:,}원)를 초과합니다. 사업성을 재검토하세요."
            )
    return FeasibilityResult(
        intent=intent,
        verdict=verdict,
        reasons=reasons,
        candidates=classified.candidates,
    )


__all__ = [
    "DISCLAIMER",
    "Candidate",
    "ClassifyResult",
    "CompareResult",
    "CompareRow",
    "FeasibilityResult",
    "classify",
    "compare",
    "feasibility",
]
