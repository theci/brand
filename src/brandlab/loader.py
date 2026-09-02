"""YAML 로드 및 검증 loader.

각 로더는 파일을 읽어 pydantic 모델로 검증한다.
처방 로더는 원료·패키지 id가 마스터 데이터에 실제로 존재하는지까지 교차 검증한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import (
    AdTermList,
    AllergenList,
    AromaMaterialList,
    BatchRecord,
    BrandCore,
    Config,
    DoeDesign,
    Formula,
    FoodAllergenList,
    Fragrance,
    IngredientMaster,
    Inventory,
    ChemicalSafetyFees,
    ClassificationRules,
    LabelingRules,
    LimitList,
    PackagingMaster,
    ProhibitedList,
    PromptKeywordLibrary,
    RegimeInfo,
    RegimeLabelItems,
    RestrictedList,
    StabilitySample,
)

# 프로젝트 루트 및 주요 경로 (loader.py 기준: src/brandlab/loader.py → 루트는 3단계 위)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
FORMULAS_DIR = PROJECT_ROOT / "formulas"
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
REGULATORY_DIR = DATA_DIR / "regulatory"


class BrandLabError(Exception):
    """brand-lab 로드/검증 최상위 예외."""


class ReferenceIntegrityError(BrandLabError):
    """처방이 존재하지 않는 원료/패키지 id를 참조할 때 발생."""


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise BrandLabError(f"파일이 없습니다: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 마스터 / 설정 / 규제 데이터
# ---------------------------------------------------------------------------
def load_ingredients(path: Path | str = DATA_DIR / "ingredients.yaml") -> IngredientMaster:
    return IngredientMaster.model_validate(_read_yaml(Path(path)))


def load_packaging(path: Path | str = DATA_DIR / "packaging.yaml") -> PackagingMaster:
    return PackagingMaster.model_validate(_read_yaml(Path(path)))


def load_config(path: Path | str = DATA_DIR / "config.yaml") -> Config:
    return Config.model_validate(_read_yaml(Path(path)))


def load_inventory(path: Path | str = DATA_DIR / "inventory.yaml") -> Inventory:
    """재고를 로드한다. 파일이 없으면 빈 재고를 반환한다(선택 데이터)."""
    p = Path(path)
    if not p.exists():
        return Inventory()
    return Inventory.model_validate(_read_yaml(p))


def load_brand_core(path: Path | str = DATA_DIR / "brand" / "core.yaml") -> BrandCore:
    """브랜드 코어 시트를 로드한다. 파일이 없으면 빈 시트를 반환한다(선택 데이터)."""
    p = Path(path)
    if not p.exists():
        return BrandCore()
    return BrandCore.model_validate(_read_yaml(p))


def load_prompt_keywords(
    path: Path | str = DATA_DIR / "marketing" / "prompt_keywords.yaml",
) -> PromptKeywordLibrary:
    """나노바나나 프롬프트 키워드 팔레트를 로드한다. 없으면 빈 라이브러리."""
    p = Path(path)
    if not p.exists():
        return PromptKeywordLibrary()
    return PromptKeywordLibrary.model_validate(_read_yaml(p))


def load_allergens(
    path: Path | str = DATA_DIR / "regulatory" / "cosmetics" / "allergens.yaml",
) -> AllergenList:
    return AllergenList.model_validate(_read_yaml(Path(path)))


def load_limits(path: Path | str = DATA_DIR / "regulatory" / "cosmetics" / "limits.yaml") -> LimitList:
    return LimitList.model_validate(_read_yaml(Path(path)))


def load_labeling_rules(
    path: Path | str = DATA_DIR / "regulatory" / "cosmetics" / "labeling_rules.yaml",
) -> LabelingRules:
    return LabelingRules.model_validate(_read_yaml(Path(path)))


def load_ad_terms(
    path: Path | str = DATA_DIR / "regulatory" / "cosmetics" / "ad_terms.yaml",
) -> AdTermList:
    return AdTermList.model_validate(_read_yaml(Path(path)))


def load_regime_info(
    regime_code: str, regulatory_dir: Path | str = REGULATORY_DIR
) -> RegimeInfo:
    """data/regulatory/<regime_code>/regime.yaml 을 읽는다."""
    path = Path(regulatory_dir) / regime_code / "regime.yaml"
    return RegimeInfo.model_validate(_read_yaml(path))


def load_regime_label_items(
    regime_code: str, regulatory_dir: Path | str = REGULATORY_DIR
) -> RegimeLabelItems:
    """data/regulatory/<regime_code>/label_items.yaml 을 읽는다."""
    path = Path(regulatory_dir) / regime_code / "label_items.yaml"
    return RegimeLabelItems.model_validate(_read_yaml(path))


def load_chemical_safety_fees(
    regulatory_dir: Path | str = REGULATORY_DIR,
) -> ChemicalSafetyFees:
    """data/regulatory/chemical_safety/fees.yaml 을 읽는다."""
    path = Path(regulatory_dir) / "chemical_safety" / "fees.yaml"
    return ChemicalSafetyFees.model_validate(_read_yaml(path))


def load_classification_rules(
    regulatory_dir: Path | str = REGULATORY_DIR,
) -> ClassificationRules:
    """data/regulatory/classification_rules.yaml 을 읽는다."""
    path = Path(regulatory_dir) / "classification_rules.yaml"
    return ClassificationRules.model_validate(_read_yaml(path))


def load_prohibited(
    regime_code: str, regulatory_dir: Path | str = REGULATORY_DIR
) -> ProhibitedList:
    """data/regulatory/<regime_code>/prohibited.yaml 을 읽는다."""
    path = Path(regulatory_dir) / regime_code / "prohibited.yaml"
    return ProhibitedList.model_validate(_read_yaml(path))


def load_restricted(
    regime_code: str, regulatory_dir: Path | str = REGULATORY_DIR
) -> RestrictedList:
    """data/regulatory/<regime_code>/restricted.yaml 을 읽는다."""
    path = Path(regulatory_dir) / regime_code / "restricted.yaml"
    return RestrictedList.model_validate(_read_yaml(path))


def load_food_allergens(
    regulatory_dir: Path | str = REGULATORY_DIR,
) -> FoodAllergenList:
    """data/regulatory/food/allergens_food.yaml 을 읽는다."""
    path = Path(regulatory_dir) / "food" / "allergens_food.yaml"
    return FoodAllergenList.model_validate(_read_yaml(path))


# ---------------------------------------------------------------------------
# 처방
# ---------------------------------------------------------------------------
def load_formula(
    path: Path | str,
    *,
    ingredient_ids: set[str] | None = None,
    packaging_ids: set[str] | None = None,
) -> Formula:
    """처방 1개를 로드·검증한다.

    ingredient_ids / packaging_ids가 주어지면 참조 무결성까지 검증한다.
    None이면 pydantic 구조 검증(percent 합계 포함)만 수행한다.
    """
    formula = Formula.model_validate(_read_yaml(Path(path)))

    if ingredient_ids is not None:
        missing = [i for i in formula.ingredient_ids() if i not in ingredient_ids]
        if missing:
            raise ReferenceIntegrityError(
                f"처방 '{formula.slug} v{formula.version}'이(가) 참조하는 원료 id가 "
                f"ingredients.yaml에 없습니다: {sorted(set(missing))}"
            )

    if packaging_ids is not None:
        missing_pkg = [p.id for p in formula.packaging if p.id not in packaging_ids]
        if missing_pkg:
            raise ReferenceIntegrityError(
                f"처방 '{formula.slug} v{formula.version}'이(가) 참조하는 패키지 id가 "
                f"packaging.yaml에 없습니다: {sorted(set(missing_pkg))}"
            )

    return formula


def iter_formula_paths(formulas_dir: Path | str = FORMULAS_DIR) -> list[Path]:
    """formulas/<slug>/v<n>.yaml 파일 경로를 모두 반환한다."""
    root = Path(formulas_dir)
    return sorted(root.glob("*/v*.yaml"))


# ---------------------------------------------------------------------------
# 실험 (experiments/)
# ---------------------------------------------------------------------------
def load_doe(path: Path | str) -> DoeDesign:
    return DoeDesign.model_validate(_read_yaml(Path(path)))


def load_stability(path: Path | str) -> StabilitySample:
    return StabilitySample.model_validate(_read_yaml(Path(path)))


def load_batch(path: Path | str) -> BatchRecord:
    return BatchRecord.model_validate(_read_yaml(Path(path)))


def iter_batch_paths(experiments_dir: Path | str = EXPERIMENTS_DIR) -> list[Path]:
    return sorted(Path(experiments_dir).glob("batches/*.yaml"))


def load_all_batches(experiments_dir: Path | str = EXPERIMENTS_DIR) -> list[BatchRecord]:
    return [load_batch(p) for p in iter_batch_paths(experiments_dir)]


def iter_doe_paths(experiments_dir: Path | str = EXPERIMENTS_DIR) -> list[Path]:
    return sorted(Path(experiments_dir).glob("doe/*.yaml"))


def iter_stability_paths(experiments_dir: Path | str = EXPERIMENTS_DIR) -> list[Path]:
    return sorted(Path(experiments_dir).glob("stability/*.yaml"))


def load_all_stability(
    experiments_dir: Path | str = EXPERIMENTS_DIR,
) -> list[StabilitySample]:
    return [load_stability(p) for p in iter_stability_paths(experiments_dir)]


# ---------------------------------------------------------------------------
# 조향 (data/aroma_materials.yaml, formulas/fragrance/*.yaml)
# ---------------------------------------------------------------------------
def load_aroma_materials(
    path: Path | str = DATA_DIR / "aroma_materials.yaml",
) -> AromaMaterialList:
    return AromaMaterialList.model_validate(_read_yaml(Path(path)))


def load_fragrance(path: Path | str) -> Fragrance:
    return Fragrance.model_validate(_read_yaml(Path(path)))


def iter_fragrance_paths(formulas_dir: Path | str = FORMULAS_DIR) -> list[Path]:
    return sorted(Path(formulas_dir).glob("fragrance/*.yaml"))


def load_all_fragrances(formulas_dir: Path | str = FORMULAS_DIR) -> list[Fragrance]:
    return [load_fragrance(p) for p in iter_fragrance_paths(formulas_dir)]


class BrandLab:
    """모든 데이터를 한 번에 로드·검증하는 진입점."""

    def __init__(
        self,
        ingredients: IngredientMaster,
        packaging: PackagingMaster,
        config: Config,
        allergens: AllergenList,
        limits: LimitList,
        labeling_rules: LabelingRules,
        formulas: list[Formula],
    ) -> None:
        self.ingredients = ingredients
        self.packaging = packaging
        self.config = config
        self.allergens = allergens
        self.limits = limits
        self.labeling_rules = labeling_rules
        self.formulas = formulas

    @classmethod
    def load(cls, root: Path | str = PROJECT_ROOT) -> "BrandLab":
        root = Path(root)
        data = root / "data"
        ingredients = load_ingredients(data / "ingredients.yaml")
        packaging = load_packaging(data / "packaging.yaml")
        config = load_config(data / "config.yaml")
        allergens = load_allergens(data / "regulatory" / "cosmetics" / "allergens.yaml")
        limits = load_limits(data / "regulatory" / "cosmetics" / "limits.yaml")
        labeling_rules = load_labeling_rules(
            data / "regulatory" / "cosmetics" / "labeling_rules.yaml"
        )

        ingredient_ids = set(ingredients.index())
        packaging_ids = set(packaging.index())

        # 규제/한도 데이터도 존재하는 원료를 가리키는지 확인
        _validate_regulatory_refs(limits, allergens, ingredients)

        formulas = [
            load_formula(
                p, ingredient_ids=ingredient_ids, packaging_ids=packaging_ids
            )
            for p in iter_formula_paths(root / "formulas")
        ]
        return cls(
            ingredients,
            packaging,
            config,
            allergens,
            limits,
            labeling_rules,
            formulas,
        )


def _validate_regulatory_refs(
    limits: LimitList,
    allergens: AllergenList,
    ingredients: IngredientMaster,
) -> None:
    ingredient_ids = set(ingredients.index())
    allergen_ids = set(allergens.index())

    missing_limit = [
        lim.ingredient_id
        for lim in limits.limits
        if lim.ingredient_id not in ingredient_ids
    ]
    if missing_limit:
        raise ReferenceIntegrityError(
            f"limits.yaml이 참조하는 원료 id가 ingredients.yaml에 없습니다: "
            f"{sorted(set(missing_limit))}"
        )

    # 원료에 표기된 allergen id가 allergens.yaml에 존재하는지 확인
    missing_allergen: set[str] = set()
    for ing in ingredients.ingredients:
        for ac in ing.allergens:
            if ac.id not in allergen_ids:
                missing_allergen.add(ac.id)
    if missing_allergen:
        raise ReferenceIntegrityError(
            f"원료가 참조하는 알러젠 id가 allergens.yaml에 없습니다: "
            f"{sorted(missing_allergen)}"
        )


__all__ = [
    "BrandLab",
    "BrandLabError",
    "ReferenceIntegrityError",
    "load_ingredients",
    "load_packaging",
    "load_config",
    "load_inventory",
    "load_brand_core",
    "load_prompt_keywords",
    "load_allergens",
    "load_limits",
    "load_labeling_rules",
    "load_ad_terms",
    "load_regime_info",
    "load_regime_label_items",
    "load_chemical_safety_fees",
    "load_classification_rules",
    "load_prohibited",
    "load_restricted",
    "load_food_allergens",
    "load_formula",
    "iter_formula_paths",
    "load_doe",
    "load_stability",
    "load_all_stability",
    "load_batch",
    "load_all_batches",
    "iter_batch_paths",
    "iter_doe_paths",
    "iter_stability_paths",
    "load_aroma_materials",
    "load_fragrance",
    "load_all_fragrances",
    "iter_fragrance_paths",
    "PROJECT_ROOT",
    "DATA_DIR",
    "FORMULAS_DIR",
    "EXPERIMENTS_DIR",
]
