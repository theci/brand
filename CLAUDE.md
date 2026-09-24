# brand-lab — 코드베이스 오리엔테이션

화장품·생활화학·식품 **1인 브랜드 처방·마케팅 관리** 로컬 도구. 이 파일은 반복 탐색을 줄이기 위한 지도다.

## 실행·테스트 (중요)
- `.venv/bin/python`엔 **pip·pytest가 없다.** 반드시 **`uv run`** 을 쓴다.
  - 테스트: `uv run pytest -q` (또는 특정 파일 `uv run pytest tests/test_prompt_builder.py -q`)
  - 앱: `uv run streamlit run streamlit_app.py`
  - 마이그레이션: `uv run python -m brandlab.migrate [--dry-run]`
- venv 활성화 상태라면 `PYTHONPATH=src pytest`도 가능.

## 아키텍처 원칙 (불변)
- **로직 = `src/brandlab/`**, **UI = `pages/`(Streamlit, 표시만)**, **데이터 = YAML**.
- 모든 모델은 **pydantic v2 `extra="forbid"`** → YAML에 오타/미정의 키 있으면 로드 실패.
- 모델 정본 = **`src/brandlab/core/models.py`**. 최상위 `src/brandlab/models.py`는 P9 레짐 리팩터링 이후 **하위호환 shim**(새 코드는 `from brandlab.core.models import ...`).
- **분류 체계(통제 어휘, enum 강제)**: 원료는 `category`(대분류 `IngredientCategory`, 착색 포함) + `effects`(효능 태그 `IngredientEffect`, 활성 세부). 제품(Formula)은 `category`(종류 `ProductCategory`) + `line`(라인/시리즈, 자유 문자열). 자유 문자열로 늘리지 말 것 — 새 값은 enum에 추가. 일괄 재분류는 `uv run python -m brandlab.migrate_taxonomy [--dry]`. UI는 `ui.product_picker(lab, key)`로 종류→라인→제품 3단 선택(플랫 드롭다운 금지). `labeling.REACTIVE_CATEGORIES`·`checks._PRESERVATIVE_CATEGORIES` 등 category 값에 의존하는 코드가 있으니 어휘 변경 시 동반 수정.
- LLM은 프롬프트 생성 후 붙여넣기(자동 호출 아님). 규제·실촬영은 코드로 강제. **처방 % = 영업비밀.**
- **커머스 운영(주문·결제·배송·CS)은 스코프 밖** — 플랫폼 정체성 = "증거·서사·포지셔닝의 원천"(`docs/플랫폼/플랫폼_확장_사업화_설계.md` §6).

## 데이터 위치
- **처방(제품): `formulas/<slug>/vN.yaml`** — 600여종(대부분 herbnoori 임포트, 자체 개발 ~18종). `fill_volume_ml`/`net_weight_g`, `packaging:[{id,qty_per_unit}]`, `source_url`(허브누리 원본) 참조. 임포트 처방 슬러그 = `hn-<branduid>`.
- **브랜드 레벨(싱글턴): `data/brand/`** — `core.yaml`(BrandCore), `personas.yaml`·`problem.yaml`·`research.yaml`(Discovery 3종), `budget.yaml`, `reviews.yaml`, `progress.yaml`.
  - ⇒ **구조 = 멀티 처방 + 싱글 브랜드**(파운더 1명). 별도 브랜드 추가하려면 `data/brand/` 경로 하드코딩부터 리팩터 필요.
- **공용 마스터: `data/`** — `packaging.yaml`, `inventory.yaml`, `curriculum.yaml`, `regulatory/<레짐>/`.
- 파일 없으면 로더가 **빈 모델 반환**(대부분 선택 데이터). 로더 경로는 `src/brandlab/loader.py`.

## 핵심 모듈 (기능 → 파일)
- 로드: `loader.py` (`load_lab`은 `ui.py`) · 모델: `core/models.py`
- 규제·라벨: `labeling.py` (`screen()`) — 내용량으로 tier 판정: **>50mL=`full`(전성분 전체 필수)**, 10<x≤50=`reduced`, ≤10=`minimal`.
- 원가: `cost.py` (`unit_cost`, `moq_bottleneck`) — 원료비+부자재비, MOQ 병목 자본.
- 이미지 프롬프트: `prompt_builder.py` — `SCENES`(장면 레시피), `PRESETS`, `REF_BRANDS`, `HONEST_FINISH`(마감 지시어), `REALSHOT_GUARD`(제품 실촬영 강제).
- 디자인 브리프: `design_brief.py` (`build_brief` → 규제표기+톤+비주얼+§6 이미지 프롬프트 컴파일).
- 마케팅 자산: `narrative.py`(개발서사), `listing.py`(상품등록), `touchpoints.py`(고객접점), `adcopy.py`/`checks.py`(문구검사), `positioning.py`, `brand_core.py`.
- 기타: `discovery.py`, `advisor.py`(규제판정), `doe.py`/`doe_optimize.py`, `stability.py`, `panel.py`, `batchrecord.py`, `certification.py`, `shopping.py`, `dashboard.py`.
- 학습 트랙: `curriculum.py` — 데일리 루틴 + **제형 마스터리**(`load_mastery`/`weekly_focus`, 데이터 `data/curriculum_mastery.yaml`, 진행 `progress_mastery.yaml`, 페이지 `pages/33_제형마스터리.py`).
- 허브누리 크롤·임포트(`herbnoori_crawl.py`·`herbnoori_import.py`·`herbnoori_batch.py`): 레시피 크롤→처방 YAML. `extract_recipe_full`은 중첩표까지 특징/대체재료 추출. 대량 임포트에 사용.
- 페이지↔STEP 매핑: `streamlit_app.py`의 `SECTIONS`(STEP 0~11).

## 브랜드 컨셉 (현재)
- **"가공하지 않은 파운더"** — 완성도가 아니라 정직함이 무기. 화려·인공(가상모델/렌더/스톡) 배제, 파운더 실물·과정 실촬영. `data/brand/core.yaml`에 톤·비주얼·금지어로 인코딩됨.
- 이미지 프롬프트 기본값도 이 컨셉에 맞춰 **자연광·정직**으로 재정의(럭셔리는 옵션 강등). AI는 배경·무드만, 제품·인물은 실촬영.

## 히어로 제품 (2026-09 전환)
- **브랜드 = 다도기(Dadogi)** — '다독이다'에서 온 조어. `data/brand/core.yaml` brand_name.
- **히어로 = `sebum-calm-cream`("시크 진정 밸런스 크림", 50mL 무향, `jar-50ml`)**, 최신 = **v2**.
  - 파운더 본인이 **예민·지성(지루성 피부염 경향)** 으로 고생 → 자기 문제를 푸는 제품이 히어로(진정성=실화).
  - **전문 앵글 = 말라세지아-세이프**: 효모가 대사하는 **C11~24 지방산 오일 전면 배제**(올리브·코코넛·호호바·버터류 금지), 스쿠알란·MCT(C8/C10)·디메치콘 등 '먹이 아닌' 에몰리언트만. 무향.
  - ⚠️ **화장품이라 병명·치료·항염·살균 표방 금지** — "예민·지성용 무향 진정 보습"으로 사실 기반 포지셔닝(문구검사가 지킴).
- (구 히어로 `daily-lotion`은 참고 세그먼트로 강등. 브랜드 discovery(personas/problem/core)는 새 히어로 기준으로 재작성됨.)
- SKU 전략: 새 SKU 남발 금지, **처방 하나 → 옵션·세트·구독 5줄**(`docs/출시/SKU_전략_히어로_옵션구성.md`).
- **정본 = `docs/정본_히어로_파이프라인.md`** — "여기서 시작". STEP 0~11을 지휘하고 나머지 문서를 참고 서랍으로 규정.

## 문서 맵 (`docs/`)
- **`정본_히어로_파이프라인.md` — 시작점(정본).** 헷갈리면 이것부터. 나머지는 참고 서랍.
- `플랫폼/` — 확장 설계(사업화·마케팅·식품·규제레짐), 사용/데이터 가이드.
- `출시/` — SKU 전략, 운영 자동화 플레이북, 브랜딩·마케팅 가이드, 판매전 등록 체크리스트, OEM 발주.
- `사업/` — 팬베이스·피드백 루프 전략, 제품별 사업 시나리오(**히어로 = `사업_시나리오_지성진정크림.md`**, STEP 0~11 허브).
- `커리큘럼/` — 학습 자산(정본 STEP 3 참고 서랍): 제형 아키타입 지도(14제형)·원료 팔레트(60종)·실습 워크드예제 + 처방 전문성 로드맵.

## 컨벤션
- **규제·단가·MOQ 수치는 예시(검증 필요)** — 집행 전 식약처·환경부·공정위 원문 대조. `data/packaging.yaml` 단가/MOQ도 예시값.
- 커밋 메시지는 **한국어**.
