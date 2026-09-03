"""brand-lab 데이터 모델 (pydantic v2).

이 모듈은 YAML 파일의 구조를 그대로 표현하는 pydantic 모델만 정의한다.
계산 로직(수율, 원가, 알러젠 표시 등)은 다음 단계에서 별도 모듈로 추가한다.

여기서 수행하는 검증:
  - 처방(Formula) percent 합계 = 100 ± PERCENT_TOLERANCE
  - percent > 0
  - product_type / status 등 enum 값 제약
원료·패키지 id 참조 검증(교차 검증)은 마스터 데이터가 필요하므로
loader.py에서 수행한다.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 처방 percent 합계 허용 오차. 요구사항: 100 ± 0.01
PERCENT_TOLERANCE: float = 0.01


class ProductType(str, Enum):
    """제품 사용 형태.

    알러젠 표시 기준(다음 단계)에서 사용:
      - rinse_off (씻어내는 제품): 알러젠 0.01% 초과 시 표시
      - leave_on  (씻어내지 않는 제품): 알러젠 0.001% 초과 시 표시
    """

    LEAVE_ON = "leave_on"
    RINSE_OFF = "rinse_off"


class FormulaStatus(str, Enum):
    """처방 개발 상태."""

    DEVELOPING = "개발중"
    CONFIRMED = "확정"


# ---------------------------------------------------------------------------
# 원료 마스터 (data/ingredients.yaml)
# ---------------------------------------------------------------------------
class AllergenContent(BaseModel):
    """원료에 포함된 표시대상 알러젠과 그 함량.

    id      : allergens.yaml 의 알러젠 id
    percent : 원료(원물) 중 해당 알러젠의 함량(%). 공급처 CoA/GC 성적서 기준.
              완제품 중 농도 = 처방 내 원료 함량(%) × (percent / 100)
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    percent: float = Field(gt=0, le=100)


class FoodNutrition(BaseModel):
    """식품 원료의 100g당 영양성분. 식품 레짐에서만 사용(화장품 원료는 None).

    완제품 영양 = Σ(처방 내 원료 함량% / 100 × 원료 100g당 값).
    food_allergen_ids: data/regulatory/food/allergens_food.yaml 의 알레르기 id 목록.
    ※ 초기값은 예시이며, 공급처 성적서/식품영양성분 DB 값으로 교체할 것.
    """

    model_config = ConfigDict(extra="forbid")

    kcal_per_100g: float = Field(ge=0)
    protein_g: float = Field(default=0.0, ge=0)
    fat_g: float = Field(default=0.0, ge=0)
    carb_g: float = Field(default=0.0, ge=0)
    sugar_g: float = Field(default=0.0, ge=0)
    sodium_mg: float = Field(default=0.0, ge=0)
    food_allergen_ids: list[str] = Field(default_factory=list)


class Ingredient(BaseModel):
    """원료 1종.

    id      : 처방에서 참조하는 고유 슬러그 (예: "mct")
    name    : 한글 표시명 (예: "카프릴릭/카프릭 트리글리세라이드")
    inci    : INCI 표준명 (예: "Caprylic/Capric Triglyceride")
    category: 기능/분류 (예: 에몰리언트, 왁스, 계면활성제, 산화방지제 ...)
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    inci: str = Field(min_length=1)
    category: str = Field(min_length=1)
    # 안전사용 권장 상한(%) — 있으면 참고용. 강제 검증은 하지 않는다(다음 단계).
    max_percent: float | None = Field(default=None, gt=0, le=100)
    # 원료 단가(원/kg). 원가 계산에 사용.
    price_per_kg: float | None = Field(default=None, ge=0)
    # 밀도(g/ml). 부피 기준 내용량을 질량으로 환산할 때 사용. 없으면 1.0 g/ml로 가정.
    density: float | None = Field(default=None, gt=0)
    # 유화제 자신의 HLB 값(0~20). 유화제(계면활성제)에만 입력. 유화 성공 예측(check)에 사용.
    hlb: float | None = Field(default=None, ge=0, le=20)
    # 이 오일/유상 원료를 O/W로 유화하는 데 필요한 required HLB(0~20). 유상 원료에만 입력.
    required_hlb: float | None = Field(default=None, ge=0, le=20)
    # 성적서(CoA) 보유 여부. 안전상 기본 False(미확인) — UI에서 붉게 표시.
    has_coa: bool = False
    # 화장품용 등급 여부. 캔들/식품/공업용이면 False — UI에서 붉게 표시.
    cosmetic_grade: bool = True
    # 등급 표기(예: cosmetic / candle / food). 선택.
    grade: str | None = None
    cas: str | None = None
    # 이 원료에 포함된 표시대상 알러젠과 함량 (regulatory/allergens.yaml 참조)
    allergens: list[AllergenContent] = Field(default_factory=list)
    # 착향제(향료) 여부 — 전성분 표시에서 순서 무관 그룹으로 분류
    fragrance: bool = False
    # 착색제(색소) 여부 — 전성분 표시에서 순서 무관 그룹으로 분류
    colorant: bool = False
    # 식품 원료의 100g당 영양성분(식품 레짐 전용). 화장품 원료는 None.
    nutrition: FoodNutrition | None = None
    # 식품용 등급 여부(화장품 cosmetic_grade와 대칭). 식품 처방은 True여야 한다.
    food_grade: bool = False
    supplier: str | None = None
    notes: str | None = None


class IngredientMaster(BaseModel):
    """ingredients.yaml 최상위 구조."""

    model_config = ConfigDict(extra="forbid")

    ingredients: list[Ingredient]

    @model_validator(mode="after")
    def _unique_ids(self) -> "IngredientMaster":
        seen: set[str] = set()
        dups: set[str] = set()
        for ing in self.ingredients:
            if ing.id in seen:
                dups.add(ing.id)
            seen.add(ing.id)
        if dups:
            raise ValueError(f"원료 id가 중복되었습니다: {sorted(dups)}")
        return self

    def index(self) -> dict[str, Ingredient]:
        return {ing.id: ing for ing in self.ingredients}


# ---------------------------------------------------------------------------
# 패키지 마스터 (data/packaging.yaml)
# ---------------------------------------------------------------------------
class Packaging(BaseModel):
    """포장재 1종."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)  # jar, tin, tube, bottle, box ...
    volume_ml: float | None = Field(default=None, gt=0)
    material: str | None = None  # 유리, PP, PE, 종이 ...
    # 개당 단가(원). 원가 계산에 사용.
    unit_price: float | None = Field(default=None, ge=0)
    # 최소 주문 수량(MOQ). 초도 물량·사장 재고 판정에 사용.
    moq: int | None = Field(default=None, gt=0)
    supplier: str | None = None
    notes: str | None = None


class PackagingMaster(BaseModel):
    """packaging.yaml 최상위 구조."""

    model_config = ConfigDict(extra="forbid")

    packaging: list[Packaging]

    @model_validator(mode="after")
    def _unique_ids(self) -> "PackagingMaster":
        seen: set[str] = set()
        dups: set[str] = set()
        for pkg in self.packaging:
            if pkg.id in seen:
                dups.add(pkg.id)
            seen.add(pkg.id)
        if dups:
            raise ValueError(f"패키지 id가 중복되었습니다: {sorted(dups)}")
        return self

    def index(self) -> dict[str, Packaging]:
        return {pkg.id: pkg for pkg in self.packaging}


# ---------------------------------------------------------------------------
# 브랜드 설정 (data/config.yaml)
# ---------------------------------------------------------------------------
class Economics(BaseModel):
    """손익 계산 가정값. 값의 출처를 명확히 하기 위해 config.yaml에서 읽는다."""

    model_config = ConfigDict(extra="forbid")

    channel_fee_rate: float = Field(ge=0, lt=1)  # 판매 채널 수수료율 (판매가 기준)
    shipping_cost: float = Field(ge=0)  # 개당 출고 배송비(원)
    return_rate: float = Field(ge=0, lt=1)  # 반품률
    vat_rate: float = Field(ge=0, lt=1)  # 부가가치세율
    target_margin: float | None = Field(default=None)  # 목표 마진율(선택)


class RegulatoryThresholds(BaseModel):
    """레짐 경제성 경고 임계값. config.yaml에서 조정 가능."""

    model_config = ConfigDict(extra="forbid")

    high_entry_cost: int = Field(default=1_000_000, ge=0)  # 진입비용 과다 경고 기준(원)
    long_lead_time_days: int = Field(default=30, ge=0)  # 시험 기간 장기 경고 기준(일)
    # 규제비용이 예산의 이 비율을 넘으면 CAUTION (예: 0.2 = 20%)
    budget_caution_ratio: float = Field(default=0.2, gt=0, le=1)


class Config(BaseModel):
    """브랜드 전역 설정."""

    model_config = ConfigDict(extra="forbid")

    brand_name: str
    default_currency: str = "KRW"
    default_batch_g: float = Field(default=100.0, gt=0)
    economics: Economics
    regulatory_thresholds: RegulatoryThresholds = Field(
        default_factory=RegulatoryThresholds
    )
    notes: str | None = None


# ---------------------------------------------------------------------------
# 규제 데이터 (data/regulatory/*.yaml)
# ---------------------------------------------------------------------------
class Allergen(BaseModel):
    """표시대상 알러젠 (예: EU 26종 향료 알러젠)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    inci: str = Field(min_length=1)
    notes: str | None = None


class AllergenList(BaseModel):
    """allergens.yaml 최상위 구조."""

    model_config = ConfigDict(extra="forbid")

    # 규제 데이터 최신성 추적용. 없거나 오래되면 신선도 검사에서 경고한다.
    last_updated: date | None = None
    source: str | None = None
    source_url: str | None = None  # 출처 URL (규제 데이터 필수 권장)
    allergens: list[Allergen]

    def index(self) -> dict[str, Allergen]:
        return {a.id: a for a in self.allergens}


class IngredientLimit(BaseModel):
    """원료 사용 한도.

    product_type이 None이면 모든 제품 형태에 적용,
    지정되면 해당 형태에만 적용.
    """

    model_config = ConfigDict(extra="forbid")

    ingredient_id: str = Field(min_length=1)
    max_percent: float = Field(gt=0, le=100)
    product_type: ProductType | None = None
    reference: str | None = None  # 근거(고시/규정) 출처


class LimitList(BaseModel):
    """limits.yaml 최상위 구조."""

    model_config = ConfigDict(extra="forbid")

    # 규제 데이터 최신성 추적용.
    last_updated: date | None = None
    source: str | None = None
    source_url: str | None = None  # 출처 URL (규제 데이터 필수 권장)
    limits: list[IngredientLimit]


class AllergenThresholds(BaseModel):
    """제품 형태별 알러젠 표시 임계값(%)."""

    model_config = ConfigDict(extra="forbid")

    leave_on: float = Field(gt=0)
    rinse_off: float = Field(gt=0)

    def for_type(self, product_type: "ProductType") -> float:
        return self.leave_on if product_type is ProductType.LEAVE_ON else self.rinse_off


class LabelingRules(BaseModel):
    """labeling_rules.yaml — 표시 규정 수치.

    규제 수치는 코드에 하드코딩하지 않고 전부 이 파일에서 읽는다.
    임계값 필드는 기본값 없이 필수로 두어, 값이 반드시 YAML에서 오도록 강제한다.
    """

    model_config = ConfigDict(extra="forbid")

    last_updated: date | None = None
    source: str | None = None
    source_url: str | None = None  # 출처 URL (규제 데이터 필수 권장)
    # 최신성 검사 기준(일). 이 일수를 넘기면 오래된 데이터로 경고.
    stale_after_days: int = Field(gt=0)
    # 이 함량(%) 이하 성분은 전성분 표시 순서를 지키지 않아도 된다.
    ingredient_order_threshold_percent: float = Field(gt=0)
    # 제품 형태별 알러젠 표시 임계값(%).
    allergen_thresholds: AllergenThresholds
    # 전성분 표시 필수 기준(이 부피/중량 초과 시 필수).
    full_labeling_volume_ml: float = Field(gt=0)
    full_labeling_weight_g: float = Field(gt=0)
    # 축약 표시 기준(이 부피/중량 이하 시 5가지 항목만).
    minimal_labeling_volume_ml: float = Field(gt=0)
    minimal_labeling_weight_g: float = Field(gt=0)
    # 소용량(축약) 제품에 반드시 표시할 항목.
    minimal_items: list[str] = Field(min_length=1)
    # 최소 글자 크기(포인트).
    min_font_size_pt: float = Field(gt=0)


# ---------------------------------------------------------------------------
# 처방 (formulas/<slug>/v<n>.yaml)
# ---------------------------------------------------------------------------
class FormulaIngredient(BaseModel):
    """처방 내 원료 1줄. id는 ingredients.yaml의 원료 id를 참조한다."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    percent: float = Field(gt=0, le=100)


class Phase(BaseModel):
    """처방 상(相). 제조 시 함께 가열/혼합하는 원료 묶음 (예: A, B, C)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    ingredients: list[FormulaIngredient] = Field(min_length=1)
    # 배치 지시서에 출력할 공정 순서/방법 (예: "70도로 가열해 완전히 용해")
    process: str | None = None


class PackagingRef(BaseModel):
    """처방이 사용하는 포장재 참조. id는 packaging.yaml의 패키지 id를 참조한다."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    qty_per_unit: int = Field(gt=0)


class Formula(BaseModel):
    """제품 1개 버전의 처방."""

    model_config = ConfigDict(extra="forbid")

    product: str = Field(min_length=1)  # 제품명 (예: "클렌징밤")
    slug: str = Field(min_length=1)  # 폴더 슬러그 (예: "cleansing-balm")
    version: int = Field(gt=0)
    # 규제 레짐 코드(brandlab.regimes.registry에 등록된 코드). 기본은 화장품법.
    # 실제 유효성은 레짐 레이어에서 확인한다(모델은 레짐 무관 유지).
    regime: str = "cosmetics"
    # 요구사항 4: 알러젠 표시 기준에 쓰이므로 반드시 필수 필드.
    product_type: ProductType
    status: FormulaStatus
    base_batch_g: float = Field(gt=0)
    phases: list[Phase] = Field(min_length=1)
    packaging: list[PackagingRef] = Field(default_factory=list)
    fill_volume_ml: float | None = Field(default=None, gt=0)
    # 고형 제품(비누 등) 표시 기준용 내용량(g). 부피가 없으면 이 값으로 판정.
    net_weight_g: float | None = Field(default=None, gt=0)
    # 레짐별 세부 품목 코드(예: 화학제품안전법의 "방향제_지속방출형"). 시험비 조회 키.
    product_category: str | None = None
    notes: str | None = None
    parent_version: int | None = Field(default=None, gt=0)

    @property
    def total_percent(self) -> float:
        return sum(i.percent for p in self.phases for i in p.ingredients)

    def ingredient_ids(self) -> list[str]:
        """처방이 참조하는 모든 원료 id (등장 순서, 중복 포함)."""
        return [i.id for p in self.phases for i in p.ingredients]

    @model_validator(mode="after")
    def _check_total_percent(self) -> "Formula":
        total = self.total_percent
        if abs(total - 100.0) > PERCENT_TOLERANCE:
            raise ValueError(
                f"처방 percent 합계가 100 ± {PERCENT_TOLERANCE}이 아닙니다: "
                f"합계 {total:.4f}%"
            )
        return self


# ---------------------------------------------------------------------------
# 실험: DOE (experiments/doe/*.yaml)
# ---------------------------------------------------------------------------
class DoeRun(BaseModel):
    """실험 1회(run). factor_values는 인자별 수준(값 또는 low/high), scores는 항목별 점수."""

    model_config = ConfigDict(extra="forbid")

    run_id: int | str
    factor_values: dict[str, str | int | float | bool]
    # 결측을 허용(키 누락 또는 None). 분석에서 결측은 평균에서 제외한다.
    scores: dict[str, float | None] = Field(default_factory=dict)


class DoeDesign(BaseModel):
    """완전요인 설계와 결과 (experiments/doe/*.yaml)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    formula_ref: str | None = None
    factors: list[str] = Field(min_length=1)
    # 인자별 실제 수준값 (예: {wax: {low: 10, high: 18}}). 표시용, 선택.
    levels: dict[str, dict[str, float]] | None = None
    response_items: list[str] = Field(min_length=1)
    runs: list[DoeRun] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 실험: 안정성 시험 (experiments/stability/*.yaml)
# ---------------------------------------------------------------------------
class StabilityCondition(str, Enum):
    C45 = "45C"
    RT = "RT"
    FREEZE_THAW = "freeze_thaw"
    LIGHT = "light"


class StabilityObservation(BaseModel):
    """관찰 1회 기록."""

    model_config = ConfigDict(extra="forbid")

    date: date
    외관: str | None = None
    분리: str | None = None
    색: str | None = None
    냄새: str | None = None
    경도: str | None = None
    판정: str | None = None
    비고: str | None = None


class StabilitySample(BaseModel):
    """안정성 시험 시료 1종 (experiments/stability/*.yaml)."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1)
    formula_ref: str | None = None
    condition: StabilityCondition
    start_date: date
    observations: list[StabilityObservation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 배치 기록 (experiments/batches/*.yaml)
# ---------------------------------------------------------------------------
class BatchLine(BaseModel):
    """배치 제조 시 원료 1줄의 목표 vs 실측 무게.

    target_g : 처방 환산으로 계산된 목표 투입량(g)
    actual_g : 저울로 실제 계량해 넣은 값(g). 비워두면 목표대로 넣은 것으로 간주하지 않고 '미기록'.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    target_g: float = Field(ge=0)
    actual_g: float | None = Field(default=None, ge=0)


class BatchRecord(BaseModel):
    """소량 제조 1회 기록 (experiments/batches/*.yaml).

    벤치에서 실제로 만든 배치의 '실측 결과'를 시스템에 남긴다.
      - 목표 배치량 대비 실제 회수량 → 수율(yield)
      - 측정 pH (피부 제품 4.5~6.0 목표)
      - 원료별 목표 vs 실측 무게(선택)
      - 자유 관찰 메모
    측정 도구(저울·pH미터)로 얻은 숫자를 처방 버전에 연결해 재현성을 확보한다.
    """

    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(min_length=1)  # 예: DT-20260902-01
    formula_ref: str = Field(min_length=1)  # 예: "daily-toner v1"
    slug: str | None = None
    version: int | None = Field(default=None, gt=0)
    date: date
    target_g: float = Field(gt=0)  # 목표 배치량
    yield_g: float | None = Field(default=None, ge=0)  # 실제 회수량(완성 후 무게)
    ph: float | None = Field(default=None, ge=0, le=14)  # 측정 pH
    lines: list[BatchLine] = Field(default_factory=list)  # 원료별 목표/실측
    observations: str | None = None  # 외관·향·사용감 등 자유 메모
    operator: str | None = None

    @property
    def yield_percent(self) -> float | None:
        """수율(%) = 회수량 / 목표량 × 100. 회수량 미기록이면 None."""
        if self.yield_g is None or self.target_g <= 0:
            return None
        return round(self.yield_g / self.target_g * 100.0, 1)


# ---------------------------------------------------------------------------
# 재고 (data/inventory.yaml)
# ---------------------------------------------------------------------------
class InventoryIngredient(BaseModel):
    """원료 재고 1종.

    on_hand_g   : 현재 보유량(g)
    pack_size_g : 공급사 판매 단위(g). 구매는 이 배수로만 가능(장바구니 올림에 사용).
    pack_price  : 1팩 가격(원). 없으면 ingredients.yaml의 price_per_kg로 환산.
    expiry      : 유통기한(미개봉).
    opened      : 개봉일. pao_months와 함께 '개봉 후 사용기한'을 계산.
    pao_months  : 개봉 후 사용 가능 개월(Period After Opening).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    on_hand_g: float = Field(default=0.0, ge=0)
    pack_size_g: float | None = Field(default=None, gt=0)
    pack_price: float | None = Field(default=None, ge=0)
    expiry: date | None = None
    opened: date | None = None
    pao_months: int | None = Field(default=None, gt=0)
    notes: str | None = None


class InventoryPackaging(BaseModel):
    """포장재 재고 1종. 구매 단위(MOQ)는 packaging.yaml을 따른다."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    on_hand: int = Field(default=0, ge=0)
    notes: str | None = None


class Inventory(BaseModel):
    """inventory.yaml 최상위 구조. 파일이 없으면 빈 재고로 취급한다(선택 데이터)."""

    model_config = ConfigDict(extra="forbid")

    last_updated: date | None = None
    ingredients: list[InventoryIngredient] = Field(default_factory=list)
    packaging: list[InventoryPackaging] = Field(default_factory=list)

    def ingredient_index(self) -> dict[str, InventoryIngredient]:
        return {i.id: i for i in self.ingredients}

    def packaging_index(self) -> dict[str, InventoryPackaging]:
        return {p.id: p for p in self.packaging}


# ---------------------------------------------------------------------------
# 조향: 향료 원료 (data/aroma_materials.yaml)
# ---------------------------------------------------------------------------
class AromaNote(str, Enum):
    TOP = "top"
    MIDDLE = "middle"
    BASE = "base"


class AromaMaterial(BaseModel):
    """향료 원료 1종."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    이름: str = Field(min_length=1)
    cas: str | None = None
    노트: AromaNote
    계열: str = Field(min_length=1)  # citrus/floral/woody/musk/...
    희석농도_보유: list[float] = Field(default_factory=list)  # 보유 희석농도(%) 예: [10, 1]
    단가_원_per_10ml: float | None = Field(default=None, ge=0)
    구매처: str | None = None
    ifra_한도_퍼센트: float | None = Field(default=None, ge=0)  # 완제품 중 IFRA 한도(%)
    알러젠_해당: bool = False
    화장품용_등급: bool = True
    시향_메모: str | None = None


class AromaMaterialList(BaseModel):
    """aroma_materials.yaml 최상위 구조."""

    model_config = ConfigDict(extra="forbid")

    materials: list[AromaMaterial]

    @model_validator(mode="after")
    def _unique_ids(self) -> "AromaMaterialList":
        seen: set[str] = set()
        dups: set[str] = set()
        for m in self.materials:
            if m.id in seen:
                dups.add(m.id)
            seen.add(m.id)
        if dups:
            raise ValueError(f"향료 원료 id가 중복되었습니다: {sorted(dups)}")
        return self

    def index(self) -> dict[str, AromaMaterial]:
        return {m.id: m for m in self.materials}


# ---------------------------------------------------------------------------
# 조향: 향 처방 (formulas/fragrance/*.yaml)
# ---------------------------------------------------------------------------
class FragranceMaterial(BaseModel):
    """향 처방 내 원료 1줄.

    parts    : 원액(neat) 기준 상대 비율(부수)
    dilution : 계량에 사용하는 희석액 농도(%). 100이면 원액.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    parts: float = Field(gt=0)
    dilution: float = Field(default=100.0, gt=0, le=100)


class Accord(BaseModel):
    """어코드(향 묶음)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    materials: list[FragranceMaterial] = Field(min_length=1)


class FragranceEvalPoint(BaseModel):
    """시향 평가 1시점."""

    model_config = ConfigDict(extra="forbid")

    시점: str = Field(min_length=1)  # 0분/30분/2시간/6시간/24시간
    강도: int = Field(ge=1, le=5)
    메모: str | None = None


class FragranceEvaluation(BaseModel):
    """1회 시향 세션(시점별 기록)."""

    model_config = ConfigDict(extra="forbid")

    date: date
    timepoints: list[FragranceEvalPoint] = Field(default_factory=list)


class Fragrance(BaseModel):
    """향 처방 (formulas/fragrance/*.yaml)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: int = Field(gt=0)
    총량_g: float = Field(gt=0)
    concentration_percent: float = Field(gt=0, le=100)  # 향 농도(EDP 15~20 등)
    accords: list[Accord] = Field(min_length=1)
    ethanol_percent: float = Field(ge=0, le=100)
    maceration_weeks: int = Field(ge=0)
    maceration_start_date: date | None = None
    evaluations: list[FragranceEvaluation] = Field(default_factory=list)

    def all_materials(self) -> list[FragranceMaterial]:
        return [m for a in self.accords for m in a.materials]


# ---------------------------------------------------------------------------
# 광고 문구 검사 (data/regulatory/ad_terms.yaml)
# ---------------------------------------------------------------------------
class AdTermCategory(str, Enum):
    FUNCTIONAL = "functional_claim"  # 기능성화장품 심사 대상 표현(미백/주름개선/탈모완화 등)
    DRUG = "drug_claim"  # 의약품 오인 표현(치료/재생/염증완화 등)
    ABSOLUTE = "absolute_claim"  # 절대적·최상급 과장 표현(완벽/최고/100% 등)
    UNVERIFIED = "unverified_claim"  # 미검증 효과 표현(즉각/하루만에 등)


class AdRisk(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AdTerm(BaseModel):
    """금지·주의 표현 1건."""

    model_config = ConfigDict(extra="forbid")

    expression: str = Field(min_length=1)  # 기본형(예: "미백", "주름 개선")
    category: AdTermCategory
    risk: AdRisk
    suggestion: str | None = None  # 대체 표현 제안
    reference: str | None = None  # 근거 메모
    # 정규식 직접 지정(선택). 없으면 expression에서 형태소 변형 패턴을 자동 생성.
    pattern: str | None = None


class AdTermList(BaseModel):
    """ad_terms.yaml 최상위 구조. 표현 목록은 전부 이 파일에서 읽는다(코드 하드코딩 금지)."""

    model_config = ConfigDict(extra="forbid")

    last_updated: date | None = None
    source: str | None = None
    source_url: str | None = None  # 출처 URL (규제 데이터 필수 권장)
    terms: list[AdTerm] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 규제 레짐 설정 (data/regulatory/<regime_code>/regime.yaml, label_items.yaml)
# ---------------------------------------------------------------------------
class RegimeInfo(BaseModel):
    """레짐의 법·비용·기간 등 설정. 규제 수치는 코드가 아니라 이 YAML에서 읽는다."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    law_name: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    supported: bool = True
    # 지원 레짐용 비용/기간
    entry_cost: int | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    sku_expansion_cost: int | None = Field(default=None, ge=0)
    renewal_period_years: int | None = Field(default=None, ge=0)
    # 미지원 레짐용 거부 사유
    reject_reason: str | None = None
    approx_lead_time_months: int | None = Field(default=None, ge=0)
    notes: list[str] = Field(default_factory=list)
    # 규제 데이터 필수 메타
    last_updated: date | None = None
    source_url: str = Field(min_length=1)


class RegimeLabelItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    required: bool = True
    note: str | None = None


class RegimeLabelItems(BaseModel):
    """label_items.yaml — 레짐별 라벨 필수 기재 항목."""

    model_config = ConfigDict(extra="forbid")

    last_updated: date | None = None
    source_url: str = Field(min_length=1)
    items: list[RegimeLabelItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 화학제품안전법 데이터 (data/regulatory/chemical_safety/*.yaml)
# ---------------------------------------------------------------------------
class ChemFeeCategory(BaseModel):
    """품목별 시험비·기간."""

    model_config = ConfigDict(extra="forbid")

    fee: int = Field(ge=0)  # 신고 시험비(원)
    lead_time_days: int = Field(ge=0)  # 시험 기간(영업일/일)


class ChemicalSafetyFees(BaseModel):
    """fees.yaml — 안전확인대상생활화학제품 품목별 시험비용·기간."""

    model_config = ConfigDict(extra="forbid")

    categories: dict[str, ChemFeeCategory]
    renewal_period_years: int = Field(gt=0)
    last_updated: date | None = None
    source_url: str = Field(min_length=1)


class ProhibitedSubstance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    cas: str | None = None
    reference: str | None = None


class ProhibitedList(BaseModel):
    """prohibited.yaml — 함유금지물질."""

    model_config = ConfigDict(extra="forbid")

    last_updated: date | None = None
    source_url: str = Field(min_length=1)
    substances: list[ProhibitedSubstance] = Field(default_factory=list)


class RestrictedSubstance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    cas: str | None = None
    max_percent: float = Field(gt=0, le=100)
    product_category: str | None = None  # 특정 품목에만 적용되면 지정
    reference: str | None = None


class RestrictedList(BaseModel):
    """restricted.yaml — 함유제한물질."""

    model_config = ConfigDict(extra="forbid")

    last_updated: date | None = None
    source_url: str = Field(min_length=1)
    substances: list[RestrictedSubstance] = Field(default_factory=list)


class FoodAllergen(BaseModel):
    """식품 알레르기 유발물질 1종.

    id      : 원료 FoodNutrition.food_allergen_ids 가 참조하는 id (예: "milk")
    name    : 한글 표시명 (예: "우유")
    keywords: 원재료명에서 탐지할 키워드(선택) — 유청·카제인 등
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)


class FoodAllergenList(BaseModel):
    """allergens_food.yaml — 식품 알레르기 표시대상."""

    model_config = ConfigDict(extra="forbid")

    last_updated: date | None = None
    source_url: str = Field(min_length=1)
    allergens: list[FoodAllergen] = Field(default_factory=list)

    def index(self) -> dict[str, FoodAllergen]:
        return {a.id: a for a in self.allergens}


# ---------------------------------------------------------------------------
# 규제 판정 (RegimeAdvisor) — 제품 의도 → 레짐 분류
# ---------------------------------------------------------------------------
class ProductIntent(BaseModel):
    """제품 기획 의도.

    use   : body / space / fabric / surface
    claims: fragrance / cleanse / deodorize / moisturize / sanitize / ...
    form  : liquid / solid / spray / sustained_release
    """

    model_config = ConfigDict(extra="forbid")

    use: str | None = None
    claims: list[str] = Field(default_factory=list)
    form: str | None = None


class ClassificationMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use: str | None = None
    claim: str | list[str] | None = None
    form: str | None = None


class ClassificationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regime: str = Field(min_length=1)
    category_code: str | None = None  # 화학제품안전법 fees.yaml 품목 코드 등
    category_label: str = Field(min_length=1)
    note: str | None = None


class ClassificationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: ClassificationMatch
    candidate: ClassificationCandidate


class ClassificationRules(BaseModel):
    """classification_rules.yaml — 의도→레짐 매칭 규칙(코드 하드코딩 금지)."""

    model_config = ConfigDict(extra="forbid")

    last_updated: date | None = None
    source_url: str = Field(min_length=1)
    rules: list[ClassificationRule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 브랜드 코어 시트 (data/brand/core.yaml) — 마케팅 자산의 뿌리
# ---------------------------------------------------------------------------
class BrandVisual(BaseModel):
    """브랜드 코어 시트 ⑦ 비주얼 코드."""

    model_config = ConfigDict(extra="forbid")

    main_color: str | None = None  # HEX
    sub_color: str | None = None
    point_color: str | None = None
    container: str | None = None  # 용기(포장재에서 자동 제안)
    texture: str | None = None  # 제형 무드
    font_title: str | None = None
    font_body: str | None = None
    photo_note: str | None = None  # 조명·색온도·배경 등


class BrandCore(BaseModel):
    """브랜드 코어 시트 9칸. 모든 마케팅 AI 프롬프트 앞에 붙일 '브랜드 자산'.

    모든 칸은 선택(부분 저장·점진 편집 허용). ⑤근거·⑦비주얼·⑧금지어는 플랫폼이 초안을 채운다.
    """

    model_config = ConfigDict(extra="forbid")

    brand_name: str | None = None
    product_ref: str | None = None  # "slug vN" — 근거 추출 기준 제품
    entry_points: list[str] = Field(default_factory=list)  # ① 카테고리 진입점
    persona: str | None = None  # ② 타깃(인물)
    enemy: str | None = None  # ③ 적
    promise: str | None = None  # ④ 약속
    evidence: list[str] = Field(default_factory=list)  # ⑤ 근거(자동 추출 → 선택/편집)
    tone_adjectives: list[str] = Field(default_factory=list)  # ⑥ 톤 형용사
    forbidden_words: list[str] = Field(default_factory=list)  # ⑧ 브랜드 금지어
    vocabulary: list[str] = Field(default_factory=list)  # ⑧ 애용어
    visual: BrandVisual = Field(default_factory=BrandVisual)  # ⑦
    one_liner: str | None = None  # ⑨ 한 줄 소개


# ---------------------------------------------------------------------------
# 나노바나나 프롬프트 키워드 팔레트 (data/marketing/prompt_keywords.yaml)
# ---------------------------------------------------------------------------
class PromptKeyword(BaseModel):
    """프롬프트 키워드 1개(영어 키워드 + 한글 설명 + 예시 힌트)."""

    model_config = ConfigDict(extra="forbid")

    en: str = Field(min_length=1)
    ko: str = ""
    hint: str | None = None


class PromptKeywordLibrary(BaseModel):
    """prompt_keywords.yaml — 카테고리(angle/lighting/…)별 키워드 목록."""

    model_config = ConfigDict(extra="forbid")

    categories: dict[str, list[PromptKeyword]] = Field(default_factory=dict)

    def get(self, category: str) -> list[PromptKeyword]:
        return self.categories.get(category, [])


# ---------------------------------------------------------------------------
# 기획(Discovery) — 고객·문제 발견 (data/brand/personas.yaml·research.yaml·problem.yaml)
#   포지셔닝(아래)의 상류. 리서치가 쌓여도 안 깨지게 파일·모델을 분리한다.
#   모든 칸 선택(부분 저장·점진 편집). 출처(ResearchSource)를 1급 객체로 둔다.
# ---------------------------------------------------------------------------
class PainPoint(BaseModel):
    """페르소나의 고통 1개. 우선순위 점수 = 심각도 × 빈도."""

    model_config = ConfigDict(extra="forbid")

    desc: str = Field(min_length=1)
    severity: int = Field(default=3, ge=1, le=5)  # 심각도(1~5)
    frequency: int = Field(default=3, ge=1, le=5)  # 빈도(1~5)
    source_ref: str | None = None  # research.yaml sources[].id 참조

    @property
    def score(self) -> int:
        return self.severity * self.frequency


class Persona(BaseModel):
    """타깃 고객 1인."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    one_line: str | None = None  # 한 줄 정의
    context: str | None = None  # 상황·맥락(인구·환경)
    jobs: list[str] = Field(default_factory=list)  # 해결하려는 일(JTBD)
    current_solution: str | None = None  # 지금 쓰는 대안
    dissatisfaction: str | None = None  # 그 대안의 불만
    priority: int = Field(default=3, ge=1, le=5)  # 타깃 우선순위
    pains: list[PainPoint] = Field(default_factory=list)


class PersonaBook(BaseModel):
    """personas.yaml 최상위."""

    model_config = ConfigDict(extra="forbid")

    personas: list[Persona] = Field(default_factory=list)

    def index(self) -> dict[str, Persona]:
        return {p.id: p for p in self.personas}


class ResearchSource(BaseModel):
    """자료 출처 1개 — 모든 수치·주장이 이걸 참조한다(확장성의 핵심)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str | None = None
    kind: str | None = None  # 기사/논문/리뷰/커뮤니티/규정/데이터 …
    # 필드명을 date로 두면 date 타입을 가려(기본값 None) 파이단틱 평가가 깨짐 → researched_on 사용.
    researched_on: date | None = None
    reliability: int = Field(default=3, ge=1, le=5)  # 신뢰도(1~5)


class MarketNote(BaseModel):
    """시장 조사 노트 1개."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1)
    summary: str | None = None
    metric: str | None = None  # 수치(예: "시장 3,200억, 연 8%")
    tags: list[str] = Field(default_factory=list)  # 트렌드/규모/가격/규제 …
    source_ref: str | None = None


class Competitor(BaseModel):
    """경쟁 제품/현상 1개. gaps(빈틈)가 포지셔닝 comparison으로 승격된다."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)  # 현상으로 기술(실명 지양)
    category: str | None = None
    price_band: str | None = None
    claims: list[str] = Field(default_factory=list)  # 소구점
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)  # 약점/빈틈
    source_ref: str | None = None


class Research(BaseModel):
    """research.yaml 최상위 — 출처·시장노트·경쟁."""

    model_config = ConfigDict(extra="forbid")

    sources: list[ResearchSource] = Field(default_factory=list)
    market_notes: list[MarketNote] = Field(default_factory=list)
    competitors: list[Competitor] = Field(default_factory=list)

    def source_index(self) -> dict[str, ResearchSource]:
        return {s.id: s for s in self.sources}


class ProblemStatement(BaseModel):
    """problem.yaml — 발견을 종합한 문제 정의."""

    model_config = ConfigDict(extra="forbid")

    persona_ref: str | None = None  # personas[].id
    core_pain: str | None = None
    statement: str | None = None  # 문제 문장
    hypothesis: str | None = None  # 이걸 풀면 ~일 것이다
    success_metric: str | None = None  # 성공 판단 지표


class Discovery(BaseModel):
    """기획 3파일을 묶은 것. load_discovery가 조립해 반환(하류 프리필의 입력원)."""

    model_config = ConfigDict(extra="forbid")

    personas: PersonaBook = Field(default_factory=PersonaBook)
    research: Research = Field(default_factory=Research)
    problem: ProblemStatement = Field(default_factory=ProblemStatement)


# ---------------------------------------------------------------------------
# 포지셔닝 (data/brand/positioning.yaml) — 뾰족함의 뿌리
# ---------------------------------------------------------------------------
class ComparisonRow(BaseModel):
    """경쟁 비교표 1행."""

    model_config = ConfigDict(extra="forbid")

    axis: str = Field(min_length=1)  # 비교 축(예: 유화제 종류, 스쿠알란 함량)
    ours: str = ""  # 우리 값
    theirs: str = ""  # 경쟁/기존 값
    ours_wins: bool = False  # 우리 우위인가


class Positioning(BaseModel):
    """포지셔닝 문장의 구성 요소. 모든 칸 선택(부분 저장·점진 편집).

    목표 문장: "우리는 [타겟]에게 [경쟁]이 해결 못한 [페인]을 [신물질/공정]으로
    [수치적 이익]으로 해결하는 유일한 [카테고리]다."
    """

    model_config = ConfigDict(extra="forbid")

    product_ref: str | None = None  # 근거 추출 기준 제품 "slug vN"
    target: str | None = None  # 타겟
    competitor: str | None = None  # 경쟁사/기존 물질(현상으로, 실명 지양)
    pain: str | None = None  # 고객 페인 포인트
    tech: str | None = None  # 우리만의 신물질/신공정
    metric_benefit: str | None = None  # 구체적 수치적 이익/성능
    category: str | None = None  # 카테고리(작은 시장)
    entry_situations: list[str] = Field(default_factory=list)  # 카테고리 진입점(상황)
    comparison: list[ComparisonRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 후기 (data/brand/reviews.yaml) — 고객 접점 Phase 9. 후기 = 새 증거.
# ---------------------------------------------------------------------------
class Review(BaseModel):
    """수집한 고객 후기 1건."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    product_ref: str | None = None  # "slug vN"
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=1)
    author: str | None = None
    reviewed_on: date | None = None  # 필드명 date는 타입을 가리므로 reviewed_on
    verified: bool = False  # 구매 확인 후기
    incentivized: bool = False  # 대가성(협찬·원고료) — 뒷광고 표기 대상


class ReviewBook(BaseModel):
    """reviews.yaml 최상위."""

    model_config = ConfigDict(extra="forbid")

    reviews: list[Review] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 인증·시험 관문 (data/regulatory/<regime>/checklist.yaml, data/brand/cert_status.yaml)
# ---------------------------------------------------------------------------
class CertStatus(str, Enum):
    WAITING = "대기"
    PROGRESS = "진행"
    DONE = "완료"


class CertGate(BaseModel):
    """레짐별 필수 관문 1개(등록·시험·표시·생산 …)."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = "기타"  # 등록 | 시험 | 표시 | 생산 | 기타
    note: str | None = None


class CertChecklist(BaseModel):
    """checklist.yaml — 레짐의 출시 관문 정의(예시, 확인 필요)."""

    model_config = ConfigDict(extra="forbid")

    regime: str = Field(min_length=1)
    last_updated: date | None = None
    source_url: str | None = None
    gates: list[CertGate] = Field(default_factory=list)


class CertStatusEntry(BaseModel):
    """제품별 관문 진행 상태."""

    model_config = ConfigDict(extra="forbid")

    product_ref: str = Field(min_length=1)  # "slug vN"
    gate_key: str = Field(min_length=1)
    status: CertStatus = CertStatus.WAITING
    due_date: date | None = None
    cost: int | None = Field(default=None, ge=0)
    owner: str | None = None
    note: str | None = None


class CertStatusList(BaseModel):
    """cert_status.yaml — 관문 진행 상태 목록."""

    model_config = ConfigDict(extra="forbid")

    entries: list[CertStatusEntry] = Field(default_factory=list)
