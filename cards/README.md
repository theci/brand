# 제품 카드 → 처방 임포트

허브누리(등) 공개 레시피를 붙여넣어 `formulas/<slug>/v1.yaml`을 자동 생성한다.
AI가 페이지 전체를 읽지 않아도 되므로 토큰·시간을 아낀다.

## 워크플로

1. 빈 템플릿 뽑기
   ```
   uv run python -m brandlab.herbnoori_import --template > cards/새제품.yaml
   ```
2. `cards/새제품.yaml`에 **재료·용량만** 채운다. 재료 1줄 = `한글명 | 용량 | 특징 | 대체`
   (특징·대체는 선택). 용량 단위: `g`(기본) · `ml`(밀도로 g 환산) · `방울`(≈0.05g).
3. 변환
   ```
   uv run python -m brandlab.herbnoori_import cards/새제품.yaml
   ```
   - 기존 원료는 이름으로 자동 매칭(별칭 포함).
   - **모르는 원료가 있으면** 붙여넣기용 stub을 출력하고 멈춘다 → `data/ingredients.yaml`에
     등록(또는 스크립트의 `SYNONYMS`에 별칭 추가) 후 다시 실행.
   - 성공하면 percent 합계 100으로 정규화해 처방 파일을 쓰고 로더로 검증한다.

## 크롤러: 복붙조차 필요 없이 자동 수집

`herbnoori_crawl` 이 목록→상세 페이지를 자동으로 돌며 레시피 표를 뽑아
`--raw` 가 먹는 `.txt`(제품당 1개, `hn-<branduid>.txt`)로 저장한다. 페이지를 열 필요 없다.

```bash
# 카테고리(대분류 xcode / 중분류 mcode)의 1~3페이지 → cards/raw/ 에 저장
uv run python -m brandlab.herbnoori_crawl --xcode 007 --mcode 002 --pages 1-3 --out cards/raw

# 특정 제품만
uv run python -m brandlab.herbnoori_crawl --branduids 288778,288757 --out cards/raw

# 수집 규모만 먼저 확인(저장 안 함)
uv run python -m brandlab.herbnoori_crawl --xcode 007 --mcode 002 --pages 1-3 --list
```

그다음 뽑힌 파일을 `--raw` 로 처방화:
```bash
uv run python -m brandlab.herbnoori_import cards/raw/hn-288778.txt --raw                 # 미리보기
uv run python -m brandlab.herbnoori_import cards/raw/hn-288778.txt --raw --slugs vitamin-cleansing-water
```

동작·주의:
- 사이트가 **EUC-KR/CP949**라 디코딩 처리(그래서 브라우저 밖 fetch가 깨졌던 것).
- 표 셀이 한 줄씩 나오므로 **'용량 셀 바로 앞 줄 = 재료명'** 규칙으로 재구성(특징 다줄에도 안전).
  다상(유상/수상/첨가물) 제품도 분류 셀에 안 걸리고 재료만 뽑는다.
- 후기·가격·관련상품이 재료로 오인되지 않게 `만들기`/`레시피후기` 등에서 **구간을 끊는다**.
- **외부 사이트 반복 호출**: 기본 `--delay 1.0`초. 대량 크롤은 부하를 고려하고, 허브누리의
  '출처 표시' 요구에 따라 각 파일 첫 줄에 출처 URL을 남긴다.
- `--list` 는 페이지의 shopdetail 링크를 모두 긁으므로 **'함께 본 상품' 추천이 섞일 수 있다**.
  정확히 원하는 것만 받으려면 `--branduids` 사용 또는 결과 파일을 검토할 것.
- `--raw` 는 `type`·내용량을 **추정**하고, 모르는 원료는 stub을 내고 멈춘다(카드 모드와 동일).

## 원본 붙여넣기(--raw): 카드 만들 필요 없이 바로

허브누리 상세페이지의 표를 그대로 복사해 `.txt`로 저장하면 파싱까지 해준다.
여러 제품을 한 파일에 이어붙여도 된다(제품명 다음 줄이 `재료 … 용량 …` 헤더면 경계로 인식).

```
# 미리보기(무엇으로 해석되는지 확인만)
uv run python -m brandlab.herbnoori_import sample.txt --raw

# 실제 생성(제품 순서대로 slug 지정)
uv run python -m brandlab.herbnoori_import sample.txt --raw --slugs 제품1-slug,제품2-slug
```

- 특징이 여러 줄이거나 `.`·빈 줄이 섞여도 무시하고 재료·용량만 뽑는다.
- 범위(`99~97g`, `1~3g`)는 **첫 값**을 취한다.
- `type`(leave_on/rinse_off)과 내용량은 **추정값** — 이름에 '클렌징' 등이 있으면 rinse_off로,
  아니면 leave_on으로 찍고, 내용량은 총 g(≈1g/ml)으로 근사한다. **생성 후 확인·수정 필수.**
- 모르는 원료가 있으면 카드 모드와 동일하게 stub을 출력하고 멈춘다.

## 팁
- `--stdout` : 파일 대신 화면 출력(미리보기). `--force` : 기존 파일 덮어쓰기.
- 여러 상(유상/수상/첨가물)은 템플릿의 `phases:` 블록 사용.
- 부피(ml) 레시피는 원료 `density`로 질량 환산 — 밀도 미입력 원료는 1.0 가정(근사).
- 생성 후 규제·단가·INCI는 여전히 **검증 필요**(집행 전 식약처·공급처 대조).

예시: `_예시_비타민클렌징워터.yaml` 참고.
