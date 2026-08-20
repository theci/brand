"""화학제품안전법(안전확인대상생활화학제품) 레짐.

화장품과 정반대로, SKU(품목·배합)마다 시험비가 들고 3년마다 갱신한다.
  - entry_cost / sku_expansion_cost: 품목의 시험비(fees.yaml)를 반환
  - renewal_period_years: 3
규제 수치는 코드가 아니라 data/regulatory/chemical_safety/*.yaml에서 읽는다.
"""

from __future__ import annotations

from pathlib import Path

from ..core.models import (
    ChemicalSafetyFees,
    Config,
    IngredientMaster,
    ProhibitedList,
    RestrictedList,
)
from ..core.models import Formula
from ..loader import (
    PROJECT_ROOT,
    load_chemical_safety_fees,
    load_config,
    load_ingredients,
    load_prohibited,
    load_regime_info,
    load_regime_label_items,
    load_restricted,
)
from .base import CostBreakdown, Finding, LabelItem, LabelSpec

REGIME_CODE = "chemical_safety"


class ChemicalSafetyRegime:
    """안전확인대상생활화학제품 레짐. Regime 프로토콜 구현."""

    def __init__(self, root: Path | str = PROJECT_ROOT) -> None:
        self._root = Path(root)
        self._reg_dir = self._root / "data" / "regulatory"
        self._info = load_regime_info(REGIME_CODE, self._reg_dir)
        self.code = self._info.code
        self.law_name = self._info.law_name
        self.display_name = self._info.display_name
        self._fees: ChemicalSafetyFees | None = None
        self._config: Config | None = None
        self._prohibited: ProhibitedList | None = None
        self._restricted: RestrictedList | None = None
        self._ingredients: IngredientMaster | None = None
        self._label_items = None

    # --- 지연 로딩 ---
    def _get_fees(self) -> ChemicalSafetyFees:
        if self._fees is None:
            self._fees = load_chemical_safety_fees(self._reg_dir)
        return self._fees

    def _get_config(self) -> Config:
        if self._config is None:
            self._config = load_config(self._root / "data" / "config.yaml")
        return self._config

    def _get_ingredients(self) -> IngredientMaster:
        if self._ingredients is None:
            self._ingredients = load_ingredients(self._root / "data" / "ingredients.yaml")
        return self._ingredients

    def _category(self, product: Formula) -> str:
        cat = getattr(product, "product_category", None)
        if not cat:
            raise ValueError(
                f"'{product.slug} v{product.version}'에 product_category가 없습니다. "
                "화학제품안전법 레짐은 품목 코드가 필요합니다."
            )
        fees = self._get_fees()
        if cat not in fees.categories:
            raise ValueError(
                f"등록되지 않은 품목 코드: {cat!r}. 사용 가능: {sorted(fees.categories)}"
            )
        return cat

    # --- Regime 인터페이스 ---
    def entry_cost(self, product: Formula) -> CostBreakdown:
        cat = self._category(product)
        fee = self._get_fees().categories[cat]
        return CostBreakdown(
            regime_code=self.code,
            entry_cost=fee.fee,
            lead_time_days=fee.lead_time_days,
            detail={cat: fee.fee},
            notes=[f"품목 '{cat}' 신고 시험비. 품목·배합마다 발생."],
        )

    def lead_time_days(self, product: Formula) -> int:
        cat = self._category(product)
        return self._get_fees().categories[cat].lead_time_days

    def sku_expansion_cost(self, product: Formula) -> int:
        # ★ 화장품과 정반대: 새 SKU마다 그 품목의 시험비가 든다.
        cat = self._category(product)
        return self._get_fees().categories[cat].fee

    def renewal_period_years(self, product: Formula) -> int | None:
        return self._get_fees().renewal_period_years

    def validate(self, product: Formula) -> list[Finding]:
        findings: list[Finding] = []
        fees = self._get_fees()
        cfg = self._get_config()
        thresholds = cfg.regulatory_thresholds

        cat = getattr(product, "product_category", None)
        if not cat:
            findings.append(
                Finding(
                    "error",
                    "chem.category.missing",
                    "product_category가 없습니다. 화학제품안전법 레짐은 품목 코드가 필요합니다.",
                )
            )
        elif cat not in fees.categories:
            findings.append(
                Finding(
                    "error",
                    "chem.category.unknown",
                    f"등록되지 않은 품목 코드: {cat!r}. fees.yaml을 확인하세요.",
                )
            )
        else:
            fee = fees.categories[cat]
            # 경제성 경고 (임계값은 config.yaml에서 조정)
            if fee.fee > thresholds.high_entry_cost:
                findings.append(
                    Finding(
                        "warning",
                        "chem.cost.high",
                        f"이 품목은 1인 창업 규모에서 진입비용이 과도합니다"
                        f"({fee.fee:,}원 > {thresholds.high_entry_cost:,}원). "
                        "총 예산 대비 비율을 확인하십시오.",
                        reference=fees.source_url,
                    )
                )
            if fee.lead_time_days > thresholds.long_lead_time_days:
                findings.append(
                    Finding(
                        "warning",
                        "chem.leadtime.long",
                        f"시험 기간이 길어 출시 일정에 큰 영향을 줍니다"
                        f"({fee.lead_time_days}일 > {thresholds.long_lead_time_days}일).",
                        reference=fees.source_url,
                    )
                )

        findings.extend(self._check_substances(product))
        return findings

    def _check_substances(self, product: Formula) -> list[Finding]:
        """함유금지·제한물질 대조. 데이터가 비면 '미입력' 경고(통과 아님)."""
        findings: list[Finding] = []
        prohibited = self._prohibited or load_prohibited(REGIME_CODE, self._reg_dir)
        restricted = self._restricted or load_restricted(REGIME_CODE, self._reg_dir)
        self._prohibited, self._restricted = prohibited, restricted

        if not prohibited.substances and not restricted.substances:
            findings.append(
                Finding(
                    "warning",
                    "chem.substances.no_data",
                    "규제 데이터 미입력: 함유금지/제한물질 목록이 비어 있어 대조하지 못했습니다"
                    "(통과가 아님). 고시 별표로 채우세요.",
                )
            )
            return findings

        idx = self._get_ingredients().index()
        agg: dict[str, float] = {}
        for fi in (i for p in product.phases for i in p.ingredients):
            agg[fi.id] = agg.get(fi.id, 0.0) + fi.percent

        def _keys(ing_id: str) -> set[str]:
            ing = idx.get(ing_id)
            keys = {ing_id.lower()}
            if ing:
                keys |= {ing.name.lower(), ing.inci.lower()}
                if ing.cas:
                    keys.add(ing.cas.lower())
            return keys

        prohibited_keys = {
            k
            for s in prohibited.substances
            for k in ({s.name.lower()} | ({s.cas.lower()} if s.cas else set()))
        }
        for ing_id in agg:
            if _keys(ing_id) & prohibited_keys:
                findings.append(
                    Finding("error", "chem.prohibited", f"함유금지물질 사용: {ing_id}")
                )

        for r in restricted.substances:
            r_keys = {r.name.lower()} | ({r.cas.lower()} if r.cas else set())
            if r.product_category and r.product_category != getattr(
                product, "product_category", None
            ):
                continue
            for ing_id, pct in agg.items():
                if _keys(ing_id) & r_keys and pct > r.max_percent:
                    findings.append(
                        Finding(
                            "error",
                            "chem.restricted.exceeded",
                            f"함유제한물질 초과: {ing_id} {pct:g}% > {r.max_percent:g}%",
                            reference=r.reference,
                        )
                    )
        return findings

    def label_spec(self, product: Formula) -> LabelSpec:
        if self._label_items is None:
            self._label_items = load_regime_label_items(REGIME_CODE, self._reg_dir)
        items = [
            LabelItem(key=i.key, label=i.label, required=i.required, note=i.note)
            for i in self._label_items.items
        ]
        return LabelSpec(
            regime_code=self.code,
            items=items,
            notes=["화학제품안전법 표시기준은 화장품과 필수 항목이 다릅니다."],
        )


__all__ = ["ChemicalSafetyRegime", "REGIME_CODE"]
