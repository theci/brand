"""건강기능식품(건강기능식품법) 레짐.

일반식품(food)과 갈라지는 지점: '기능성'을 표방하면 이 레짐이다.
지원 레짐이지만 1인 창업 규모에서는 대부분 부담이 크다(제조업 허가·시설요건,
개별인정형 원료는 수억·수년). advise가 '일반식품 vs 건기식' 비용차를 보여주는 게 핵심.

validate가 하는 것:
  - 식품용 등급(food_grade)이 아닌 원료면 error
  - 진입비용이 임계(config.high_entry_cost)를 넘으면 경제성 warning (통과 아님)
  - 건기식 특유의 규제 부담(제조업 허가·개별인정형)을 info로 안내

규제 수치는 코드가 아니라 data/regulatory/health_functional_food/*.yaml에서 읽는다.
"""

from __future__ import annotations

from pathlib import Path

from ..core.models import Config, Formula, IngredientMaster
from ..loader import (
    PROJECT_ROOT,
    load_config,
    load_ingredients,
    load_regime_info,
    load_regime_label_items,
)
from .base import CostBreakdown, Finding, LabelItem, LabelSpec

REGIME_CODE = "health_functional_food"


class HealthFunctionalFoodRegime:
    """건강기능식품법 레짐. Regime 프로토콜 구현(지원하되 대부분 CAUTION)."""

    def __init__(self, root: Path | str = PROJECT_ROOT) -> None:
        self._root = Path(root)
        self._reg_dir = self._root / "data" / "regulatory"
        self._info = load_regime_info(REGIME_CODE, self._reg_dir)
        self.code = self._info.code
        self.law_name = self._info.law_name
        self.display_name = self._info.display_name
        self._ingredients: IngredientMaster | None = None
        self._config: Config | None = None
        self._label_items = None

    # --- 지연 로딩 ---
    def _get_ingredients(self) -> IngredientMaster:
        if self._ingredients is None:
            self._ingredients = load_ingredients(self._root / "data" / "ingredients.yaml")
        return self._ingredients

    def _get_config(self) -> Config:
        if self._config is None:
            self._config = load_config(self._root / "data" / "config.yaml")
        return self._config

    # --- Regime 인터페이스 ---
    def validate(self, product: Formula) -> list[Finding]:
        findings: list[Finding] = []
        idx = self._get_ingredients().index()

        # ① 식품용 등급 체크
        seen: set[str] = set()
        for fi in (i for p in product.phases for i in p.ingredients):
            if fi.id in seen:
                continue
            seen.add(fi.id)
            ing = idx.get(fi.id)
            if ing is not None and not ing.food_grade:
                findings.append(
                    Finding(
                        "error",
                        "hff.grade.not_food",
                        f"식품용 등급이 아닌 원료가 사용됨: {ing.name}({fi.id}).",
                    )
                )

        # ② 경제성 경고 (진입비용 과다)
        thresholds = self._get_config().regulatory_thresholds
        entry = int(self._info.entry_cost or 0)
        if entry > thresholds.high_entry_cost:
            findings.append(
                Finding(
                    "warning",
                    "hff.cost.high",
                    f"건강기능식품 진입비용이 1인 창업 규모에서 과도합니다"
                    f"(제조업 허가·시설요건 근사 {entry:,}원 > {thresholds.high_entry_cost:,}원).",
                    reference=self._info.source_url,
                )
            )

        # ③ 건기식 규제 부담 안내
        findings.append(
            Finding(
                "info",
                "hff.burden",
                "기능성을 표방하면 건강기능식품 영역입니다. 제조업 허가·시설요건이 있고, "
                "개별인정형 기능성 원료는 인정에 수억 원·수년이 듭니다. "
                "일반식품(기능성 미표방)으로 낼 수 있는지 먼저 검토하세요.",
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
            notes=[
                "건강기능식품은 '건강기능식품' 문구·도안, 기능성 정보, "
                "'질병 치료 의약품이 아님' 문구 등이 필수입니다.",
            ],
        )

    def entry_cost(self, product: Formula) -> CostBreakdown:
        return CostBreakdown(
            regime_code=self.code,
            entry_cost=int(self._info.entry_cost or 0),
            lead_time_days=int(self._info.lead_time_days or 0),
            detail={"제조업_허가_시설요건(근사)": int(self._info.entry_cost or 0)},
            notes=list(self._info.notes),
        )

    def lead_time_days(self, product: Formula) -> int:
        return int(self._info.lead_time_days or 0)

    def sku_expansion_cost(self, product: Formula) -> int:
        # 고시형 품목제조신고 비용은 별도. 비교에서는 진입비용(제조업 허가)이 지배적.
        return int(self._info.sku_expansion_cost or 0)

    def renewal_period_years(self, product: Formula) -> int | None:
        return self._info.renewal_period_years


__all__ = ["HealthFunctionalFoodRegime", "REGIME_CODE"]
