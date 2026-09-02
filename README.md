# brand-lab

화장품 1인 브랜드를 위한 **처방(formula) 관리 도구**.
집에서 처방을 개발하고 Git으로 버전 관리한 뒤, OEM 공장 양산으로 이관하는 워크플로우를 위한 뼈대입니다.

- 데이터는 전부 **YAML 파일** (DB 없음 → Git으로 버전 관리)
- 검증은 **pydantic v2**
- 테스트는 **pytest**

> 구현 범위: **레짐 추상화(화장품법·화학제품안전법) + 규제 판정(RegimeAdvisor) + 배치 계산 + 전성분/규정 스크리너 + 원가/손익 + 실험 관리(DOE·안정성) + 조향(블렌드·IFRA·숙성) + 문구 검사 + R&D 개발 루프(HLB 사전점검·버전 diff·배치 기록) + 원료 자동채움(PubChem) + 재고·장바구니 + 제품표준서 + CLI + Streamlit UI**.
>
> ⚠️ **이 도구는 법적 판단을 대체하지 않습니다.** 전성분/규정/레짐 판정은 1차 스크리닝이며,
> 규제 수치는 코드에 넣지 않고 전부 `data/regulatory/**/*.yaml`에서 읽습니다.
> 출시 전 반드시 식약처·환경부(KTR) 고시 원문과 대조하고 필요시 전문가 검토를 받으십시오.
>
> 📘 **처음이라면 [`GUIDE.md`](GUIDE.md)를 보세요** — 설치·기능별 사용법·테스트·자주 하는 작업까지 단계별로 정리한 상세 가이드입니다.
> 🔰 **YAML·코딩이 처음이라면 [`데이터_작성_가이드.md`](데이터_작성_가이드.md)** — 데이터 파일을 왜 이렇게 쓰는지, 비전공 신입도 직접 고치고 테스트할 수 있게 설명합니다.
> 🧪 **전체 흐름을 한 제품으로 따라가려면 [`예시_시나리오.md`](예시_시나리오.md)** — 고체 샴푸바 하나를 기획→처방→라벨→원가→안정성→검증까지 실제 명령·출력으로 보여줍니다.
> 📌 **실제로 쓰기 전에 [`사용_참고사항.md`](사용_참고사항.md)도 읽으세요** — 교체해야 할 예시값, 계산 가정, 레짐별 비용 차이를 정리해 두었습니다.

## 설치 및 실행

uv 사용 (권장):

```bash
uv venv
uv pip install -e ".[dev]"
uv run pytest
```

uv가 없으면 pip 폴백:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src pytest
```

전체 데이터 로드·검증:

```python
from brandlab import BrandLab

lab = BrandLab.load()          # data/ + formulas/ 전체 로드 & 교차 검증
print(len(lab.ingredients.ingredients), "종 원료")
for f in lab.formulas:
    print(f.slug, f.version, f.total_percent)
```

## 규제 레짐 아키텍처

여러 제품 카테고리는 **서로 다른 법**의 적용을 받고, 그 차이가 제품 전략을 결정합니다(특히 SKU 확장 비용). 그래서 규제별 로직을 **레짐 플러그인**으로 분리했습니다.

```
src/brandlab/
├── core/          # 레짐 무관: models(데이터), scaling(배치), costing(원가)
└── regimes/
    ├── base.py            # Regime 프로토콜 + Finding/LabelSpec/CostBreakdown
    ├── cosmetics.py       # 화장품법 (SKU 확장 0원, 갱신 없음)
    ├── chemical_safety.py # 화학제품안전법 (품목별 시험비, 3년 갱신)
    ├── unsupported.py     # 살생물제·의약외품 → 명시적 거부
    └── registry.py        # 코드→레짐 조회
```

`brandlab.batch`·`brandlab.cost`·`brandlab.models`는 하위 호환 shim으로 유지되며, 실제 구현은 `brandlab.core.*`에 있습니다.

```python
from brandlab import get_regime, regime_for
from brandlab.loader import BrandLab

lab = BrandLab.load()
f = lab.formulas[0]
regime = regime_for(f)                       # f.regime("cosmetics")로 레짐 선택
print(regime.sku_expansion_cost(f))          # 화장품 = 0원 (핵심 특성)
print(regime.renewal_period_years(f))        # 화장품 = None
for finding in regime.validate(f):
    print(finding.level, finding.message)
```

- **`sku_expansion_cost`** 가 이 구조의 핵심입니다. **화장품은 0원, 생활화학제품(화학제품안전법)은 품목마다 수십만원**(예: 방향제_지속방출형 27만원 × SKU 3개 = 81만원, 3년마다 갱신) — 이 한 줄이 제품 전략을 결정합니다.
- **화학제품안전법 레짐**: `product_category`(예: `방향제_비분사형`)로 `data/regulatory/chemical_safety/fees.yaml`에서 시험비·기간을 조회합니다. `validate()`는 진입비용 100만원 초과·시험기간 30일 초과 시 경제성 경고(임계값은 `config.yaml`), 함유금지/제한물질 데이터가 비면 "규제 데이터 미입력" 경고를 냅니다.
- **미지원 레짐**: `get_regime("biocide")`/`"quasi_drug"`의 `validate()`는 error를 반환하고 사유("1인 창업 규모에 맞지 않음…")를 설명합니다. 비용 조회는 `UnsupportedRegimeError`를 던집니다. **조용히 통과시키지 않습니다.**
- **규제 수치는 코드에 없습니다.** `data/regulatory/<regime_code>/regime.yaml`(진입비용·기간·SKU비용·갱신주기)·`label_items.yaml`에서 읽으며, 각 파일에 `last_updated`와 `source_url`이 있습니다.

### 규제 판정 엔진 (RegimeAdvisor)

기획 단계에서 **제품을 뭐라고 부르느냐**가 총 규제비용을 수백만원 바꿉니다. `src/brandlab/advisor/`가 이 비교를 자동화합니다(매칭 규칙·수치는 `data/regulatory/classification_rules.yaml` + 각 레짐 데이터).

```python
from brandlab import classify, compare, feasibility
from brandlab.core.models import ProductIntent

intent = ProductIntent(use="space", claims=["fragrance"], form="sustained_release")
classify(intent).candidates      # 방향제(화학제품안전법) + 향수(화장품) 둘 다
compare(intent, sku_count=10, horizon_years=5).summary
#  → "…최저 비용 경로는 '향수(화장품)'… 품목별 시험비 2,700,000원 차이가 주요인"
feasibility(ProductIntent(use="space", claims=["sanitize"])).verdict   # "REJECT"(살생물제)
```

- **`classify(intent)`** — 용도/기능/제형 → 가능한 레짐·카테고리 후보. 애매하면 여러 후보를 모두 반환하고 "관할 기관 확인 필요" 경고. 규칙이 비었거나 매칭이 없으면 **조용히 빈 결과를 내지 않고 경고**합니다.
- **`compare(intent, sku_count, horizon_years)`** — 후보별 등록비 + SKU 확장비 + 갱신비 + 총 규제비용 + 소요기간을 나란히 비교하고, **최저 비용 경로**와 차액을 문장으로 설명합니다. (화장품은 SKU 확장 0원, 방향제는 27만원×SKU + 3년 갱신 → SKU 10종에서 270만원 차이.)
- **`feasibility(intent, budget=…)`** — 1인 창업 적합성: 살생물제·의약외품이면 **REJECT**(사유 설명), 규제비용이 예산의 임계 비율(기본 20%, config)을 넘으면 **CAUTION**, 그 외 OK.
- 모든 출력에 "이 판정은 사전 검토용… 관할 기관이 최종 결정" 면책 문구가 붙습니다.

```bash
brandlab advise --use space --claim fragrance --form sustained_release --skus 10
brandlab advise --interactive
```

### 레짐 추가 방법

1. `data/regulatory/<code>/regime.yaml`(+ 필요 시 `label_items.yaml`, `prohibited.yaml` 등)을 만든다.
2. `src/brandlab/regimes/<code>.py`에 `Regime` 프로토콜을 구현한 클래스를 만든다.
3. `regimes/registry.py`의 `_BUILTIN`에 **한 줄**(`"<code>": <Class>`) 추가.
4. 처방 YAML의 `regime:` 필드에 코드를 지정한다.

### 처방 마이그레이션

기존 처방에 `regime` 필드를 추가하려면(원본은 `.bak` 백업):

```bash
uv run python -m brandlab.migrate            # 실행
uv run python -m brandlab.migrate --dry-run  # 대상만 확인
```

## 배치 계산 엔진

`src/brandlab/batch.py` — 계산은 물성을 정량 예측하지 않고, 계량과 정성적 리스크 경고만 다룹니다.

```python
from brandlab import BrandLab, scale, batch_sheet, scale_report

lab = BrandLab.load()
f = next(x for x in lab.formulas if x.slug == "cleansing-balm" and x.version == 1)

# 1) 임의 배치 크기로 환산 (목표 g은 소수 2자리)
r = scale(f, 500, ingredients=lab.ingredients)
print(r.total_g, r.total_ok, r.warnings)

# 2) 배치 지시서(마크다운) — 상별 표 + 공정(process) + 실측 빈 칸 + 배치번호/날짜
print(batch_sheet(f, 500, ingredients=lab.ingredients, batch_no="B-001"))

# 3) 스케일업 리스크 (정성적)
print(scale_report(f, f.base_batch_g, 500, ingredients=lab.ingredients).warnings)
```

- **`scale`** — 원료별 목표 g(소수 2자리), 상별 소계, 전체 합계를 계산하고 합계가 `target_g`와 일치하는지(`total_ok`) 검증합니다. 저울 최소 분해능(0.001g) 기준 **`min_weighable_g`(기본 0.1g) 미만으로 떨어지는 원료**는 "이 배치 크기에서는 계량 불가" 경고를 냅니다. 임계값은 인자로 조정 가능합니다.
- **`batch_sheet`** — 배치 지시서를 마크다운으로 반환합니다. 상별 `원료 / 목표% / 목표g / 실측g(빈 칸)` 표, 처방 YAML의 `process` 필드(공정 순서), 배치번호·제조일자·제조자 자리를 포함합니다.
- **`scale_report`** — 정성적 스케일업 리스크: 왁스/버터(카테고리 `왁스`·`버터`) 합계가 **10% 초과**면 냉각 속도 리스크 경고(파일럿 배치 필수), 유화제(카테고리 `계면활성제`) 존재 시 별도 경고, 둘 다 없으면(단순 오일/알코올 용액) "리스크 낮음".

### CLI

```bash
brandlab batch cleansing-balm v1 --grams 500          # rich 표로 배치 환산 + 리스크
brandlab batch cleansing-balm v1 --grams 500 --sheet  # 마크다운 배치 지시서
```

## 전성분 표시 생성기 + 규정 체커

`src/brandlab/labeling.py` — **1차 스크리닝**입니다(법적 판단 아님). 모든 규제 수치는 `data/regulatory/*.yaml`에서 읽습니다.

```python
from brandlab import BrandLab, screen, inci_list, allergen_check

lab = BrandLab.load()
f = next(x for x in lab.formulas if x.slug == "soap" and x.version == 1)

s = screen(f, lab)                 # 전 항목 통합 스크리닝
print(s.inci.text)                 # 전성분 표시(안) 문자열
print([a.inci for a in s.allergens.declared])   # 표기 의무 알러젠
print(s.requirement.tier)          # full / reduced / minimal
print(s.limits.has_data, s.limits.warnings)     # 배합한도(미입력이면 경고)
print(s.freshness.warnings)        # 규제 데이터 최신성
print(s.disclaimer)                # 면책 문구
```

- **`inci_list`** — 전성분 표시 문자열. 함량 임계값(`ingredient_order_threshold_percent`, 기본 1%) **초과** 성분은 함량 많은 순으로 정렬, 그 이하 성분·착향제(`fragrance`)·착색제(`colorant`)는 순서 무관(안전하게 내림차순 배치). 표기 의무 알러젠 INCI를 뒤에 덧붙입니다. 비누화 등 반응 공정이 포함되면 "완제품 전성분은 반응 생성물로 표기해야 한다"고 경고합니다.
- **`allergen_check`** — 완제품 중 알러젠 농도 = Σ(처방 내 원료 함량% × 원료 중 알러젠 함량% ÷ 100). 임계값(씻어내는 제품 0.01% 초과 / 씻어내지 않는 제품 0.001% 초과)을 넘으면 성분명 표기 의무로 판정합니다. (예: 향료 0.3% 안에 리모넨 5% → 완제품 0.015% → rinse-off에서 표기 필요.)
- **`labeling_requirements`** — 내용량(`fill_volume_ml` 또는 `net_weight_g`)으로 판정: 50 초과 → 전성분 필수(full), 10 이하 → 5가지 항목만(minimal), 그 사이 → 전성분 생략 가능하나 특정 성분 표시(reduced). 내용량 미상이면 안전하게 전성분 표시를 권장합니다.
- **`limit_check`** — 처방 함량을 `limits.yaml`의 배합한도와 대조. **`limits.yaml`이 비어 있으면 "규제 데이터 미입력"을 명시**하며 조용히 통과시키지 않습니다.
- **`freshness_check`** — 각 규제 YAML의 `last_updated`가 없거나 `stale_after_days`(기본 180일)를 넘으면 경고합니다.

### CLI

```bash
brandlab label soap v1        # 전성분·알러젠·표시의무·배합한도 + 면책문구를 한 화면에
```

## 원가 · 손익 계산

`src/brandlab/cost.py` — 모든 가정값(수수료율 등)은 코드가 아니라 `config.yaml`에서 읽고, 결과의 `assumptions`에 출처를 남깁니다.

```python
from brandlab import BrandLab, unit_cost, price_simulator, breakeven, moq_bottleneck

lab = BrandLab.load()
f = next(x for x in lab.formulas if x.slug == "cleansing-balm" and x.version == 1)

uc = unit_cost(f, 1000, ingredients=lab.ingredients, packaging=lab.packaging)
print(uc.unit_cost, uc.dead_stock_capital)         # 개당 원가, 사장 재고 자본
sim = price_simulator(uc, 34000, economics=lab.config.economics)
print(sim.contribution, sim.margin_on_net)         # 개당 공헌이익, 마진율
mb = moq_bottleneck(f, 1000, ingredients=lab.ingredients, packaging=lab.packaging)
print(mb.bottleneck.name, mb.total_upfront_capital)
```

- **`unit_cost(formula, batch_units)`** — 원료비 = Σ(처방 함량% × 개당 내용량 × 밀도(부피 기준일 때 ml→g 환산) × 원료 단가), 부자재비 = Σ(개당 수량 × 단가). 항목별 내역과 합계를 반환합니다. **MOQ 미달 시** 발주는 MOQ 기준으로 잡고 남는 수량을 **사장 재고**(묶인 자본)로 별도 표시합니다. 단가 미입력 원료/부자재는 0 처리하되 **경고**합니다(조용히 통과 금지).
- **`price_simulator(unit_cost, price)`** — `config.yaml`의 채널 수수료율·배송비·반품률·부가세를 반영해 개당 공헌이익·마진율을 계산합니다. `min_price_for_margin(unit_cost, target_margin)`은 목표 마진(실매출 대비)을 만족하는 최소 판매가를 **닫힌형(순환 참조 없음)**으로 역산합니다.
- **`breakeven(fixed_cost, unit_contribution)`** — 손익분기 수량(올림). 공헌이익 ≤ 0이면 `None`.
- **`moq_bottleneck(formula, target_units)`** — 각 부자재의 MOQ 대비 필요 수량을 비교해 **초도 물량을 결정하는 병목**과 **총 선투입 자본**(원료 생산분 + 부자재 MOQ 발주비)을 계산합니다. 용기 MOQ(2,000~3,000개)가 실제 병목이 되는 지점을 드러냅니다.

### CLI

```bash
brandlab cost cleansing-balm v1 --units 1000 --price 34000   # 원가·손익·MOQ 병목 + 가정 출처
```

## 실험 관리 — DOE 분석

`src/brandlab/doe.py` — 2^k 완전요인 설계의 주효과·교호작용을 평가 항목별로 계산하고, 플롯(PNG)과 해석 리포트를 생성합니다.

```python
from brandlab import load_doe, doe_analysis, doe_report, main_effects_plot, interaction_plot

design = load_doe("experiments/doe/cleansing-balm-screening.yaml")
a = doe_analysis(design)
print(a.main_effects["emulsifier"]["헹굼"])   # +1.5
main_effects_plot(a, "main.png")
interaction_plot(a, "inter.png")
print(doe_report(design, analysis=a))          # 해석 문장 포함 마크다운
```

- **`doe_analysis`** — 주효과(고수준 평균 − 저수준 평균)와 2요인 교호작용을 항목별로 계산. `factor_values`는 `low`/`high`(또는 `+`/`-`, 실제 수준값)를 자동 인식. **결측 점수는 평균에서 제외**(available-case)하며, 어떤 그룹이 통째로 결측이면 효과는 `None`. **run이 8개 미만이면 "설계 불완전" 경고.**
- **`doe_report`** — 주효과·교호작용 표 + "유화제가 헹굼에 가장 큰 영향(+1.5)" 형태의 해석 문장을 붙인 마크다운.
- **플롯** — 응답별 주효과 플롯, factor 쌍별 교호작용 플롯을 PNG로 저장(matplotlib Agg).

## 실험 관리 — 안정성 시험 트래커

`src/brandlab/stability.py` — **관찰일을 놓치면 그 시점 데이터가 사라지므로, 지연 감지가 핵심입니다.**

```python
from brandlab import load_all_stability, stability_schedule, stability_due, stability_summary
from datetime import date

print(stability_schedule(date(2026, 1, 1)))     # 1/2/4/8주 예정일
samples = load_all_stability("experiments")
for d in stability_due(samples, today=date(2026, 8, 19)):
    print(d.sample_id, d.week, d.days_overdue)   # 밀린 관찰
```

- **`stability_schedule(start_date)`** — 1/2/4/8주 관찰 예정일.
- **`stability_due(samples, today)`** — 예정일이 지났는데 관찰이 없는(±3일 허용) 시료를 지연 큰 순으로 반환.
- **`stability_summary(samples)`** — 조건(45C/RT/freeze_thaw/light)별 시계열 요약(체크포인트 done/overdue/upcoming).

### CLI

```bash
brandlab doe analyze experiments/doe/cleansing-balm-screening.yaml  # 리포트 + PNG 생성
brandlab stability due        # 밀린 관찰 시료 목록
brandlab stability summary    # 조건별 시계열 요약
```

## 조향 관리

`src/brandlab/fragrance.py` — 향수 처방의 희석 계량, 노트 비율, IFRA 한도, 숙성 알림.

```python
from brandlab import (
    load_aroma_materials, load_fragrance,
    blend_sheet, note_pyramid, ifra_check, maceration_due,
)

mats = load_aroma_materials()
frag = load_fragrance("formulas/fragrance/citrus-cologne-v1.yaml")

sheet = blend_sheet(frag, mats)          # 희석 반영 계량표
print(sheet.ethanol_to_add_g)            # 추가 에탄올(희석액 용매 차감)
print(note_pyramid(frag, mats).ratios)   # {'top':60, 'middle':15, 'base':25}
print(ifra_check(frag, mats).violations) # IFRA 한도 초과 원료
```

- **`blend_sheet`** — `parts`(원액 기준 비율)와 `dilution`(희석 농도%)으로 실제 **계량할 희석액 양**을 계산합니다. 예: 10% 희석액 3g = 원액 0.3g. 희석액이 가져오는 용매를 목표 에탄올량에서 차감해 **추가 에탄올**을 산출하고, 질량수지가 맞습니다.
- **`note_pyramid`** — top/middle/base 원액 비율(합계 100%) + 막대 차트(`note_pyramid_plot`).
- **`ifra_check`** — 원료별 완제품 중 농도를 `ifra_한도_퍼센트`와 대조. 한도 미입력 원료는 "체크 불가"로 표시(조용히 통과 안 함).
- **`maceration_due`** — `maceration_start_date + maceration_weeks`가 지났는데 아직 시향(평가)하지 않은 처방을 알립니다.
- **시향 평가** — `evaluations[{date, timepoints:[{시점, 강도, 메모}]}]` (0분/30분/2시간/6시간/24시간), `evaluation_curve`로 시점별 강도.

### CLI

```bash
brandlab fragrance blend citrus-cologne v1   # 계량표 + 노트 피라미드 + IFRA 체크
brandlab fragrance macerate                  # 숙성 완료·미시향 처방 알림
```

## 상세페이지 문구 검사기

`src/brandlab/adcopy.py` — **1차 스크리닝**입니다(법적 판단 아님). 검사할 표현 목록은 코드가 아니라 `data/regulatory/ad_terms.yaml`에서 읽습니다.

```python
from brandlab import lint, load_ad_terms

result = lint("미백 효과와 주름개선, 하루만에 완벽한 피부.", load_ad_terms())
for f in result.findings:
    print(f.start, f.expression, f.risk, f.suggestion)
print(result.disclaimer)
```

- **`lint(text, terms)`** — 등록된 표현을 찾아 위치·카테고리·위험도·대체안을 반환. `terms` 생략 시 기본 경로에서 로드.
- **한국어 형태소 변형** — 단순 substring이 아니라 **정규식**으로 매칭합니다. "미백"이 "미백효과"·"미백에"를, "주름 개선"이 "주름개선"·"주름 개선"을 모두 잡습니다(공백은 `\s*`, 끝에 한글 접미 허용). 각 표현에 `pattern`으로 정규식을 직접 지정할 수도 있습니다.
- **카테고리** — `functional_claim`(기능성 심사 대상), `drug_claim`(의약품 오인), `absolute_claim`(절대·최상급 과장), `unverified_claim`(미검증 효과).
- **`highlight_html`** — 문제 표현을 위험도 색으로 감싼 HTML(겹침은 최고 위험도로 병합, 원문 HTML은 이스케이프). Streamlit 하이라이트에 사용.
- 표현 목록이 비었거나 정규식이 잘못되면 **조용히 통과하지 않고 경고**합니다. 모든 결과 하단에 "…통과했다고 합법이 아니며 전문가 검토 필요" 면책 문구가 붙습니다.

### CLI

```bash
brandlab lint detail_page.txt    # 텍스트 파일의 문제 표현을 표로 출력
```

## R&D 개발 루프 · 재고 · 문서 (신규 명령)

제형을 실제로 만들고 개선하는 전 과정을 돕는 명령들입니다. 전체 흐름 예시는 [`예시_시나리오_처방개선.md`](예시_시나리오_처방개선.md).

| 명령 | 하는 일 | 모듈 |
|---|---|---|
| `check <slug> <ver>` | 제조 전 **HLB 유화 균형**(요구 vs 공급) + 배합한도 사전점검 | `checks.py` |
| `diff <slug> <v1> <v2>` | 버전 간 원료 신규/증량/감량 + 개당 원가 델타 | `diff.py` |
| `batchlog new/summary` | 배치 실측(수율·pH) 기록·요약 | `batchrecord.py` |
| `ingredient enrich <id>` | PubChem(무인증)에서 **CAS·밀도 자동채움** | `pubchem.py` |
| `inventory` | 재고·유통기한(개봉후 사용기한 포함) 상태 | `inventory.py` |
| `shopping <slug> <ver>` | 필요량 − 재고 = 부족분을 팩/MOQ로 올림 + 비용 | `shopping.py` |
| `dossier <slug> <ver>` | 제품표준서(전성분·제조·규제·안정성·원가) 컴파일 | `dossier.py` |

```bash
brandlab check daily-lotion v1                          # 유화 균형 + 배합한도
brandlab diff daily-lotion v1 v2 --units 1000           # 처방 개선 비교
brandlab batchlog new daily-lotion v1 --grams 100       # 기록지 생성 → 실측 기입
brandlab batchlog summary
brandlab ingredient enrich phenoxyethanol --write       # CAS·밀도 자동채움
brandlab inventory                                      # 재고·유통기한
brandlab shopping daily-lotion v1 --units 1000          # 재고 차감 구매목록
brandlab dossier daily-lotion v2 --units 1000 --out 제품표준서.md
```

- `check`의 HLB 점검은 원료에 `hlb`(유화제)·`required_hlb`(오일) 값이 있을 때 동작합니다.
- 재고(`data/inventory.yaml`)는 **선택 데이터** — 없으면 `shopping`은 전량 구매 목록으로 동작합니다.
- 배치 기록(`experiments/batches/*.yaml`)은 버전관리 대상, 제품표준서 생성물(`제품표준서*.md`)은 `.gitignore` 처리됩니다.

## Streamlit UI (로컬 전용)

`streamlit_app.py` + `pages/` — 계산은 전부 `src/brandlab` 함수를 호출하고, UI는 표시만 합니다. 인증·배포 없음.

```bash
uv run streamlit run streamlit_app.py
```

- **처방** — 처방 목록, 배치 크기 슬라이더로 g 실시간 환산(`scale`), 배치 지시서 마크다운 다운로드(`batch_sheet`)
- **라벨** — 전성분 문자열(복사 버튼), 알러젠 판정, 표시 의무, 배합한도(`screen`)
- **원가** — 수량·판매가 입력 → 원가·손익·MOQ 병목(`unit_cost`/`price_simulator`/`moq_bottleneck`), 판매가별 마진 곡선
- **실험** — DOE 주효과·교호작용 플롯(`doe_analysis`+플롯), 안정성 현황·밀린 관찰 알림(`stability_due`)
- **원료** — `ingredients.yaml` 조회·검색. **CoA 없음/화장품용 아님 원료를 붉게 표시**(캔들용 향료를 화장품에 쓰는 실수 방지)
- **문구검사** — 상세페이지 문구 입력 → 금지·주의 표현을 위험도 색으로 하이라이트(`lint`)

구현 메모:
- **캐시 무효화** — `st.cache_data` + 파일 mtime 키(`brandlab.ui.data_signature`). YAML을 편집하고 새로고침하면 반영됩니다.
- **한글 폰트** — `setup_korean_font()`가 설치된 한글 폰트(AppleGothic/NanumGothic 등)를 matplotlib에 설정해 차트 깨짐을 방지합니다.

## 디렉터리 구조

```
brand-lab/
├── pyproject.toml            # uv/pip 의존성, pytest 설정
├── requirements.txt          # pip 폴백용
├── data/
│   ├── ingredients.yaml      # 원료 마스터 (25종)
│   ├── packaging.yaml        # 포장재 마스터
│   ├── config.yaml           # 브랜드 전역 설정
│   ├── aroma_materials.yaml     # 향료 원료 마스터(조향)
│   └── regulatory/
│       ├── classification_rules.yaml  # 의도→레짐 매칭 규칙 (RegimeAdvisor)
│       ├── cosmetics/           # 화장품법 레짐 데이터
│       │   ├── regime.yaml         # 진입비용·기간·SKU비용·갱신주기
│       │   ├── label_items.yaml    # 라벨 필수 기재 항목
│       │   ├── allergens.yaml      # 표시대상 향료 알러젠 목록
│       │   ├── limits.yaml         # 원료 사용 한도(배합한도)
│       │   ├── labeling_rules.yaml # 표시 규정 수치(임계값·용량기준 등)
│       │   └── ad_terms.yaml       # 광고 문구 금지·주의 표현
│       ├── chemical_safety/     # 화학제품안전법 레짐 데이터
│       │   ├── regime.yaml         # 법·갱신 정보
│       │   ├── fees.yaml           # 품목별 시험비·기간 (KTR 공시)
│       │   ├── label_items.yaml    # 라벨 필수 항목(신고번호·안전기준 등)
│       │   ├── prohibited.yaml     # 함유금지물질(빈 껍데기 → 직접 채움)
│       │   └── restricted.yaml     # 함유제한물질(빈 껍데기 → 직접 채움)
│       ├── biocide/regime.yaml     # 살생물제(미지원) 거부 사유
│       └── quasi_drug/regime.yaml  # 의약외품(미지원) 거부 사유
├── formulas/
│   ├── cleansing-balm/v1.yaml
│   ├── lip-balm/v1.yaml
│   ├── face-oil/v1.yaml
│   ├── soap/v1.yaml          # formulas/<product-slug>/v<n>.yaml
│   ├── room-spray/v1.yaml    # 방향제_비분사형 (화학제품안전법)
│   ├── fabric-deodorizer/v1.yaml  # 탈취제_비분사형_액상 (화학제품안전법)
│   └── fragrance/*.yaml      # 향 처방 (조향)
├── experiments/
│   ├── doe/*.yaml            # DOE 설계·결과 (분석 산출물 PNG/MD는 gitignore)
│   └── stability/*.yaml      # 안정성 시험 시료·관찰 기록
├── streamlit_app.py          # Streamlit 홈 (uv run streamlit run streamlit_app.py)
├── pages/                    # Streamlit 페이지 (처방/라벨/원가/실험/원료)
├── src/brandlab/
│   ├── core/                 # 레짐 무관: models / scaling / costing
│   ├── regimes/              # 규제 레짐 플러그인 (base / cosmetics / chemical_safety / unsupported / registry)
│   ├── advisor/              # RegimeAdvisor (classify / compare / feasibility)
│   ├── migrate.py            # 처방 regime 필드 마이그레이션
│   ├── models.py             # (shim → core.models)
│   ├── loader.py             # YAML 로드·검증
│   ├── batch.py              # (shim → core.scaling)
│   ├── labeling.py           # 전성분 표시 생성기 + 규정 체커
│   ├── cost.py               # (shim → core.costing)
│   ├── doe.py                # DOE 분석 (주효과·교호작용·플롯·리포트)
│   ├── stability.py          # 안정성 시험 트래커 (예정일·지연 감지·요약)
│   ├── fragrance.py          # 조향 (블렌드 계량·노트 피라미드·IFRA·숙성)
│   ├── adcopy.py             # 상세페이지 문구 검사기 (lint·하이라이트)
│   ├── ui.py                 # Streamlit 공통 헬퍼 (캐시 로더·폰트·원료 플래그)
│   └── cli.py                # typer + rich CLI (batch / label / cost / doe / stability / fragrance / lint)
└── tests/
```

처방 파일은 `formulas/<제품-슬러그>/v<버전번호>.yaml` 규칙을 따릅니다. 새 버전은 `v2.yaml`처럼 파일을 추가하고 `parent_version`으로 이전 버전을 가리킵니다.

## 검증 규칙

로더가 강제하는 검증:

1. **percent 합계** — 처방의 모든 phase·원료 percent 합계가 `100 ± 0.01`이 아니면 검증 에러 (`models.PERCENT_TOLERANCE`).
2. **원료 참조 무결성** — 처방이 참조하는 `id`가 `ingredients.yaml`에 없으면 `ReferenceIntegrityError`.
3. **패키지 참조 무결성** — 처방이 참조하는 패키지 `id`가 `packaging.yaml`에 없으면 `ReferenceIntegrityError`.
4. **id 유일성** — 원료·패키지 마스터의 `id` 중복 시 에러.
5. **enum 제약** — `product_type`은 `leave_on` / `rinse_off`, `status`는 `개발중` / `확정`만 허용.

> `load_formula(path)`를 `ingredient_ids` 없이 호출하면 구조 검증(합계 포함)만 수행하고 참조 검증은 건너뜁니다. `BrandLab.load()`는 항상 전체 교차 검증을 수행합니다.

## YAML 필드 설명

### `data/ingredients.yaml` — 원료 마스터

최상위 키 `ingredients:` 아래 원료 목록.

| 필드 | 필수 | 설명 |
|------|------|------|
| `id` | ✅ | 처방에서 참조하는 고유 슬러그 (예: `mct`) |
| `name` | ✅ | 한글 표시명 |
| `inci` | ✅ | INCI 표준명 (예: `Caprylic/Capric Triglyceride`) |
| `category` | ✅ | 기능/분류 (에몰리언트, 왁스, 계면활성제, 산화방지제 …) |
| `max_percent` | | 안전사용 권장 상한(%). 참고용 (강제 검증은 다음 단계) |
| `price_per_kg` | | 원료 단가(원/kg). 원가 계산에 사용 |
| `density` | | 밀도(g/ml). 부피 기준 내용량을 질량으로 환산할 때 사용(없으면 1.0 가정) |
| `has_coa` | | 성적서(CoA) 보유 여부(기본 false). UI 원료 페이지에서 없으면 붉게 표시 |
| `cosmetic_grade` | | 화장품용 등급 여부(기본 true). 캔들/식품/공업용이면 false → 붉게 표시 |
| `grade` | | 등급 표기(cosmetic/candle/food 등). 선택 |
| `cas` | | CAS 번호 |
| `allergens` | | 이 원료에 포함된 알러젠 `[{id, percent}]` — `id`는 `allergens.yaml` 참조, `percent`는 원료 중 알러젠 함량%(공급처 CoA/GC 기준) |
| `fragrance` | | 착향제 여부(기본 false). 전성분 표시에서 순서 무관 그룹으로 분류 |
| `colorant` | | 착색제 여부(기본 false). 전성분 표시에서 순서 무관 그룹으로 분류 |
| `supplier` | | 공급처 |
| `notes` | | 비고 |

### `data/packaging.yaml` — 포장재 마스터

최상위 키 `packaging:` 아래 포장재 목록.

| 필드 | 필수 | 설명 |
|------|------|------|
| `id` | ✅ | 처방에서 참조하는 고유 슬러그 |
| `name` | ✅ | 표시명 |
| `type` | ✅ | jar / tin / tube / bottle / box … |
| `volume_ml` | | 용량(ml) |
| `material` | | 재질 (유리, PP, 알루미늄, 종이 …) |
| `unit_price` | | 개당 단가(원). 원가 계산에 사용 |
| `moq` | | 최소 주문 수량. 초도 물량·사장 재고 판정에 사용 |
| `supplier` | | 공급처 |
| `notes` | | 비고 |

### `data/config.yaml` — 브랜드 전역 설정

| 필드 | 필수 | 설명 |
|------|------|------|
| `brand_name` | ✅ | 브랜드명 |
| `default_currency` | | 기본 통화 (기본값 `KRW`) |
| `default_batch_g` | | 기본 배치 용량(g) (기본값 100) |
| `economics` | ✅ | 손익 계산 가정값 → `{channel_fee_rate, shipping_cost, return_rate, vat_rate, target_margin?}` |
| `notes` | | 비고 |

### `data/regulatory/allergens.yaml` — 표시대상 알러젠

최상위 키 `allergens:` 아래 목록 + `last_updated`(선택, 최신성 검사용) + `source`(선택).
표시 기준은 `labeling_rules.yaml`에서 읽습니다: **씻어내는 제품 0.01% 초과 / 씻어내지 않는 제품 0.001% 초과** 시 성분명 표기.

| 필드 | 필수 | 설명 |
|------|------|------|
| `last_updated` | | 데이터 갱신일(YYYY-MM-DD). 없거나 오래되면 경고 |
| `source` | | 근거 출처 |
| `id` | ✅ | 알러젠 슬러그 (원료의 `allergens[].id`가 참조) |
| `name` | ✅ | 한글명 |
| `inci` | ✅ | INCI 표준명 (예: `Linalool`) |
| `notes` | | 비고 |

### `data/regulatory/labeling_rules.yaml` — 표시 규정 수치

**모든 규제 수치는 여기서 읽습니다(코드 하드코딩 금지).** `last_updated`(선택)가 없거나 `stale_after_days`를 넘으면 경고합니다.

| 필드 | 필수 | 설명 |
|------|------|------|
| `stale_after_days` | ✅ | 최신성 기준(일). 초과 시 경고 |
| `ingredient_order_threshold_percent` | ✅ | 이 함량% 이하는 표시 순서 무관 (예: 1.0) |
| `allergen_thresholds` | ✅ | `{leave_on, rinse_off}` 알러젠 표시 임계값(%) |
| `full_labeling_volume_ml` / `_weight_g` | ✅ | 이 값 초과 시 전성분 표시 필수 |
| `minimal_labeling_volume_ml` / `_weight_g` | ✅ | 이 값 이하 시 5가지 항목만 표시 |
| `minimal_items` | ✅ | 소용량 제품 필수 표시 항목 목록 |
| `min_font_size_pt` | ✅ | 최소 글자 크기(pt) |
| `last_updated` / `source` | | 갱신일 / 출처 |

### `data/regulatory/limits.yaml` — 원료 사용 한도

최상위 키 `limits:` 아래 목록 + `last_updated`(선택) + `source`(선택). `limit_check`가 처방 함량과 대조하며, 목록이 비어 있으면 "규제 데이터 미입력"으로 경고합니다.

| 필드 | 필수 | 설명 |
|------|------|------|
| `last_updated` | | 데이터 갱신일. 없거나 오래되면 경고 |
| `source` | | 근거 출처 |
| `ingredient_id` | ✅ | 대상 원료 `id` |
| `max_percent` | ✅ | 최대 허용 함량(%) |
| `product_type` | | `leave_on` / `rinse_off`. 생략 시 모든 형태에 적용 |
| `reference` | | 근거(고시/규정/사내 기준) 출처 |

### `formulas/<slug>/v<n>.yaml` — 처방

| 필드 | 필수 | 설명 |
|------|------|------|
| `product` | ✅ | 제품명 (예: 클렌징밤) |
| `slug` | ✅ | 폴더 슬러그 (예: `cleansing-balm`) |
| `version` | ✅ | 버전 번호(정수) |
| `product_type` | ✅ | `leave_on`(씻어내지 않음) / `rinse_off`(씻어냄). **알러젠 표시 기준에 사용** |
| `status` | ✅ | `개발중` / `확정` |
| `base_batch_g` | ✅ | 기준 배치 용량(g) |
| `phases` | ✅ | 제조 상(相) 목록 → `{name, ingredients: [{id, percent}], process?}` (`process`: 배치 지시서에 출력할 공정 순서, 선택) |
| `packaging` | | 사용 포장재 → `[{id, qty_per_unit}]` |
| `fill_volume_ml` | | 1개당 충전량(ml) — 표시 의무 판정에 사용 |
| `net_weight_g` | | 고형 제품(비누 등) 내용량(g) — 부피가 없을 때 표시 의무 판정에 사용 |
| `notes` | | 비고 |
| `parent_version` | | 파생 원본 버전 번호 |

### `data/regulatory/ad_terms.yaml` — 광고 문구 금지·주의 표현

최상위 키 `terms:` 아래 목록 + `last_updated`/`source`(선택). **표현 목록은 전부 여기서 관리합니다(코드 하드코딩 금지).**

| 필드 | 필수 | 설명 |
|------|------|------|
| `expression` | ✅ | 기본형 표현(예: `미백`, `주름 개선`). 여러 단어는 공백을 넣어 띄어쓰기 변형까지 매칭 |
| `category` | ✅ | `functional_claim` / `drug_claim` / `absolute_claim` / `unverified_claim` |
| `risk` | ✅ | `high` / `medium` / `low` |
| `suggestion` | | 대체 표현 제안 |
| `reference` | | 근거 메모 |
| `pattern` | | 정규식 직접 지정(선택). 없으면 `expression`에서 형태소 변형 패턴 자동 생성 |

### `data/aroma_materials.yaml` — 향료 원료 (조향)

최상위 키 `materials:` 아래 목록.

| 필드 | 필수 | 설명 |
|------|------|------|
| `id` | ✅ | 향 처방에서 참조하는 슬러그 |
| `이름` | ✅ | 원료명 |
| `노트` | ✅ | `top` / `middle` / `base` |
| `계열` | ✅ | citrus / floral / woody / musk … |
| `cas` | | CAS 번호 |
| `희석농도_보유` | | 보유 희석농도(%) 목록 (예: `[10, 1]`) |
| `단가_원_per_10ml` | | 10ml당 단가(원) |
| `구매처` | | 구매처 |
| `ifra_한도_퍼센트` | | 완제품 중 IFRA 한도(%). 없으면 IFRA 체크에서 "한도없음" |
| `알러젠_해당` | | 알레르기 유발성분 여부 |
| `화장품용_등급` | | 화장품용 등급 여부(캔들용 등이면 false) |
| `시향_메모` | | 시향 메모 |

### `formulas/fragrance/*.yaml` — 향 처방 (조향)

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | ✅ | 향 이름 |
| `version` | ✅ | 버전(정수) |
| `총량_g` | ✅ | 총 배치 중량(g) |
| `concentration_percent` | ✅ | 향 농도(%) — EDP 15~20 등 |
| `ethanol_percent` | ✅ | 에탄올 목표 비율(%) |
| `accords` | ✅ | `[{name, materials:[{id, parts, dilution}]}]` — `parts`는 원액 기준 비율, `dilution`은 희석 농도%(100=원액) |
| `maceration_weeks` | ✅ | 숙성 주수 |
| `maceration_start_date` | | 숙성 시작일(YYYY-MM-DD). `maceration_due` 판정에 사용 |
| `evaluations` | | `[{date, timepoints:[{시점, 강도(1~5), 메모}]}]` 시향 기록 |

## 예시 데이터

- **원료 25종** — MCT, 호호바오일, 시어버터, 비즈왁스, 칸데릴라왁스, 세틸알코올, 올리브리퀴드, 폴리소르베이트80, 토코페롤, 피마자오일 등 실제 INCI명 포함.
- **처방 4종** — 클렌징밤(rinse_off), 립밤(leave_on), 페이스오일(leave_on), 비누(rinse_off). 모두 percent 합계 정확히 100.
