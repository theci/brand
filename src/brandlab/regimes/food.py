"""일반식품(식품위생법) 레짐.

화장품과 달리 '전성분'이 아니라 영양성분표·알레르기·소비기한 등을 표시한다.
규제 수치는 코드가 아니라 data/regulatory/food/*.yaml에서 읽는다.
sku_expansion_cost=0 (품목제조보고는 저비용) — 화장품과 비슷한 저부담 구조.

검증(validate)이 하는 것:
  - 식품용 등급(food_grade)이 아닌 원료가 쓰였으면 error (화장품용 원료 오용 방지)
  - 영양성분(nutrition) 결측 원료가 있으면 warning (영양성분표 계산 불가)
  - 알레르기 유발물질 포함 원료를 info로 안내
  - 식품첨가물 사용금지/제한물질 대조. 데이터가 비면 '미입력' warning(통과 아님)

※ 미생물·이물 등 식품 안전(HACCP)은 시설·공정 영역으로, 이 레짐이 대체하지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from ..core.models import Formula, IngredientMaster
from ..loader import (
    PROJECT_ROOT,
    load_food_allergens,
    load_ingredients,
    load_prohibited,
    load_regime_info,
    load_regime_label_items,
    load_restricted,
)
from .base import CostBreakdown, Finding, LabelItem, LabelSpec

REGIME_CODE = "food"


class FoodRegime:
    """일반식품(식품위생법) 레짐. Regime 프로토콜 구현."""

    def __init__(self, root: Path | str = PROJECT_ROOT) -> None:
        self._root = Path(root)
        self._reg_dir = self._root / "data" / "regulatory"
        self._info = load_regime_info(REGIME_CODE, self._reg_dir)
        self.code = self._info.code
        self.law_name = self._info.law_name
        self.display_name = self._info.display_name
        self._ingredients: IngredientMaster | None = None
        self._label_items = None

    # --- 지연 로딩 ---
    def _get_ingredients(self) -> IngredientMaster:
        if self._ingredients is None:
            self._ingredients = load_ingredients(self._root / "data" / "ingredients.yaml")
        return self._ingredients

    def _formula_ids(self, product: Formula) -> list[str]:
        # 등장 순서 유지, 중복 제거
        seen: dict[str, None] = {}
        for fi in (i for p in product.phases for i in p.ingredients):
            seen.setdefault(fi.id, None)
        return list(seen)

    # --- Regime 인터페이스 ---
    def validate(self, product: Formula) -> list[Finding]:
        findings: list[Finding] = []
        idx = self._get_ingredients().index()

        # ① 식품용 등급 체크
        for ing_id in self._formula_ids(product):
            ing = idx.get(ing_id)
            if ing is None:
                continue  # 참조 무결성은 로더가 잡는다
            if not ing.food_grade:
                findings.append(
                    Finding(
                        "error",
                        "food.grade.not_food",
                        f"식품용 등급이 아닌 원료가 식품 처방에 사용됨: "
                        f"{ing.name}({ing_id}). food_grade: true 원료만 사용하세요.",
                    )
                )

        # ② 영양성분 결측 → 영양성분표 계산 불가
        missing_nutrition = [
            ing_id
            for ing_id in self._formula_ids(product)
            if (ing := idx.get(ing_id)) is not None and ing.nutrition is None
        ]
        if missing_nutrition:
            findings.append(
                Finding(
                    "warning",
                    "food.nutrition.missing",
                    "영양성분표를 계산할 수 없습니다(원료 nutrition 결측): "
                    f"{missing_nutrition}. 해당 원료에 nutrition을 입력하세요.",
                )
            )

        # ③ 알레르기 유발물질 안내 (id → 한글명 매핑, 미등록 id는 경고)
        allergen_idx = load_food_allergens(self._reg_dir).index()
        for ing_id in self._formula_ids(product):
            ing = idx.get(ing_id)
            if ing is None or ing.nutrition is None or not ing.nutrition.food_allergen_ids:
                continue
            parts: list[str] = []
            unknown: list[str] = []
            for aid in ing.nutrition.food_allergen_ids:
                a = allergen_idx.get(aid)
                if a is None:
                    unknown.append(aid)
                    parts.append(aid)
                else:
                    parts.append(f"{a.name}({aid})")
            findings.append(
                Finding(
                    "info",
                    "food.allergen.declare",
                    f"알레르기 유발물질 포함 원료: {ing.name}({ing_id}) → {', '.join(parts)}. "
                    "라벨에 알레르기 표시가 필요합니다.",
                )
            )
            if unknown:
                findings.append(
                    Finding(
                        "warning",
                        "food.allergen.unknown",
                        f"allergens_food.yaml에 없는 알레르기 id: {unknown}. 목록을 보강하세요.",
                    )
                )

        # ④ 식품첨가물 사용금지/제한물질 대조
        findings.extend(self._check_substances(product, idx))
        return findings

    def _check_substances(self, product: Formula, idx) -> list[Finding]:
        findings: list[Finding] = []
        prohibited = load_prohibited(REGIME_CODE, self._reg_dir)
        restricted = load_restricted(REGIME_CODE, self._reg_dir)

        if not prohibited.substances and not restricted.substances:
            findings.append(
                Finding(
                    "warning",
                    "food.substances.no_data",
                    "규제 데이터 미입력: 식품 사용금지/제한물질 목록이 비어 있어 "
                    "대조하지 못했습니다(통과가 아님). 식품첨가물 기준·규격으로 채우세요.",
                )
            )
            return findings

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
                    Finding("error", "food.prohibited", f"사용금지물질 사용: {ing_id}")
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
                            "food.restricted.exceeded",
                            f"사용제한물질 초과: {ing_id} {pct:g}% > {r.max_percent:g}%",
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
            notes=[
                "식품 표시기준은 화장품 전성분과 다릅니다"
                "(영양성분표·알레르기·소비기한이 핵심).",
            ],
        )

    def entry_cost(self, product: Formula) -> CostBreakdown:
        return CostBreakdown(
            regime_code=self.code,
            entry_cost=int(self._info.entry_cost or 0),
            lead_time_days=int(self._info.lead_time_days or 0),
            detail={"영업등록": int(self._info.entry_cost or 0)},
            notes=list(self._info.notes),
        )

    def lead_time_days(self, product: Formula) -> int:
        return int(self._info.lead_time_days or 0)

    def sku_expansion_cost(self, product: Formula) -> int:
        # 일반식품: 품목제조보고는 저비용 → SKU 확장 규제비용 0(근사).
        return int(self._info.sku_expansion_cost or 0)

    def renewal_period_years(self, product: Formula) -> int | None:
        return self._info.renewal_period_years


__all__ = ["FoodRegime", "REGIME_CODE"]
