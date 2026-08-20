"""화장품법 레짐.

기존 화장품 규제 로직(brandlab.labeling)을 이 레짐의 구현으로 사용한다.
진입비용·기간 등 규제 수치는 코드가 아니라 data/regulatory/cosmetics/regime.yaml에서 읽는다.
sku_expansion_cost=0, renewal_period_years=None 이 이 레짐의 핵심 특성이다.
"""

from __future__ import annotations

from pathlib import Path

from .. import labeling
from ..core.models import Formula
from ..loader import (
    PROJECT_ROOT,
    BrandLab,
    load_regime_info,
    load_regime_label_items,
)
from .base import CostBreakdown, Finding, LabelItem, LabelSpec

REGIME_CODE = "cosmetics"


class CosmeticsRegime:
    """화장품법 레짐. Regime 프로토콜 구현."""

    def __init__(self, root: Path | str = PROJECT_ROOT) -> None:
        self._root = Path(root)
        self._info = load_regime_info(REGIME_CODE, self._root / "data" / "regulatory")
        self.code = self._info.code
        self.law_name = self._info.law_name
        self.display_name = self._info.display_name
        self._lab: BrandLab | None = None
        self._label_items = None

    # --- 데이터 지연 로딩 ---
    def _get_lab(self) -> BrandLab:
        if self._lab is None:
            self._lab = BrandLab.load(self._root)
        return self._lab

    # --- Regime 인터페이스 ---
    def validate(self, product: Formula) -> list[Finding]:
        lab = self._get_lab()
        screening = labeling.screen(product, lab)
        findings: list[Finding] = []

        # 규제 데이터 최신성
        for w in screening.freshness.warnings:
            findings.append(Finding("warning", "cosmetics.freshness", w))

        # 배합한도
        if not screening.limits.has_data:
            findings.append(
                Finding("warning", "cosmetics.limits.no_data", screening.limits.warnings[0])
            )
        for v in screening.limits.violations:
            findings.append(
                Finding(
                    "error",
                    "cosmetics.limit.exceeded",
                    f"배합한도 초과: {v.name} {v.percent:g}% > {v.max_percent:g}%",
                    reference=v.reference,
                )
            )

        # 알러젠 표기 의무
        for a in screening.allergens.declared:
            findings.append(
                Finding(
                    "info",
                    "cosmetics.allergen.declare",
                    f"알러젠 표기 필요: {a.name} ({a.inci}) {a.concentration_percent:g}%",
                )
            )

        # 전성분 생성 경고(예: 비누화)
        for w in screening.inci.warnings:
            findings.append(Finding("warning", "cosmetics.inci", w))
        for w in screening.allergens.warnings:
            findings.append(Finding("warning", "cosmetics.allergen", w))

        return findings

    def label_spec(self, product: Formula) -> LabelSpec:
        if self._label_items is None:
            self._label_items = load_regime_label_items(
                REGIME_CODE, self._root / "data" / "regulatory"
            )
        items = [
            LabelItem(key=i.key, label=i.label, required=i.required, note=i.note)
            for i in self._label_items.items
        ]
        lab = self._get_lab()
        req = labeling.labeling_requirements(product, lab.labeling_rules)
        notes = list(req.notes)
        return LabelSpec(regime_code=self.code, items=items, notes=notes)

    def entry_cost(self, product: Formula) -> CostBreakdown:
        return CostBreakdown(
            regime_code=self.code,
            entry_cost=int(self._info.entry_cost or 0),
            lead_time_days=int(self._info.lead_time_days or 0),
            detail={"영업자_등록": int(self._info.entry_cost or 0)},
            notes=list(self._info.notes),
        )

    def lead_time_days(self, product: Formula) -> int:
        return int(self._info.lead_time_days or 0)

    def sku_expansion_cost(self, product: Formula) -> int:
        # 화장품법: 등록 후 SKU 추가 규제비용 0원
        return int(self._info.sku_expansion_cost or 0)

    def renewal_period_years(self, product: Formula) -> int | None:
        return self._info.renewal_period_years


__all__ = ["CosmeticsRegime", "REGIME_CODE"]
