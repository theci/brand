"""허브누리(및 유사) 공개 레시피 → brand-lab 처방 YAML 변환기.

목적: 페이지 전체를 AI가 읽어 토큰을 태우는 대신, 사람이 '제품 카드'(재료·용량만)를
붙여넣고 이 스크립트를 돌리면 formulas/<slug>/v1.yaml 이 생성된다.

사용법:
    uv run python -m brandlab.herbnoori_import cards/my-product.yaml
    uv run python -m brandlab.herbnoori_import cards/my-product.yaml --force   # 덮어쓰기
    uv run python -m brandlab.herbnoori_import --template                       # 빈 카드 출력

동작:
  1) 카드의 재료 한글명을 ingredients.yaml의 id로 해석(자동 색인 + 별칭 사전).
  2) 모르는 원료가 있으면 → 붙여넣기용 stub을 출력하고 중단(먼저 등록 후 재실행).
  3) 용량(g·ml·방울)을 질량 percent로 환산(합계 100 정규화)해 처방 YAML 생성.
  4) 로더로 검증(참조무결성·합계 100)까지 수행.

카드 형식(YAML)은 --template 참고. 재료 1줄 = "한글명 | 용량 | 특징 | 대체" (뒤 2개 선택).
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import yaml

from brandlab.core.models import Formula
from brandlab.loader import DATA_DIR, load_ingredients

# 방울→g 환산(허브누리 기준 대략치). ml→g는 원료 density 사용(없으면 1.0).
DROP_G = 0.05
_REPO = Path(__file__).resolve().parents[2]
FORMULAS_DIR = _REPO / "formulas"

# --- 별칭: 자동 색인(ingredients.yaml의 name)으로 안 잡히는 표기만 등록 ---
#   키는 normalize()를 거친 값과 비교되므로 여기 키도 normalize 대상이다.
SYNONYMS: dict[str, str] = {
    "덱스판테놀": "panthenol",
    "판테놀": "panthenol",
    "mct": "mct",
    "카프릴릭카프릭트리글리세라이드": "mct",
    "비타민e": "tocopherol",
    "세틸알콜": "cetyl-alcohol",
    "호호바오일": "jojoba-oil",
    "정제호호바오일": "jojoba-oil",
    "히아루론산": "sodium-hyaluronate",
    "히알루론산": "sodium-hyaluronate",
    "프리미엄비타민c": "ethyl-ascorbyl-ether",
    "에칠아스코빌에텔": "ethyl-ascorbyl-ether",
    "에칠아스코르빌에텔": "ethyl-ascorbyl-ether",
    "비타민c": "ethyl-ascorbyl-ether",
    "나이아신아미이드": "niacinamide",  # 사이트 오타 대응
    "12헥산디올": "hexanediol",  # '1,2-헥산디올' 정규화 결과
    "폴리소르베이트20": "polysorbate-20",
    "식물성글리세린": "glycerin",
    "히아루론산11": "hyaluronic-acid-11",  # '11 히아루론산'과 어순만 다름
    "세라마이드5": "ceramide-complex",
    "쟁탄검": "xanthan-gum",       # '잔탄검' 오타
    "나이아신아마아드": "niacinamide",  # 오타
    "허브누리의촉촉화이트닝수분크림베이스": "whitening-moisture-cream-base",
    "트라넥삼산펩타이드": "tranexamic-acid",
    "버가못": "bergamot-fcf-eo",
    "버가못에센셜오일": "bergamot-fcf-eo",
    "세라마이드수": "ceramide-water-soluble",
    "세라마이드컴플렉스": "ceramide-complex",
    "12헥산다이올": "hexanediol",  # '1,2 헥산다이올' 표기 변형
    "유마카다미아넛오일": "macadamia-oil",  # '(유)마카다미아넛오일'
    "촉촉화이트닝수분크림베이스": "whitening-moisture-cream-base",
    "네놀리에센셜오일": "neroli-eo",  # '네롤리' 오타
    "브라이트닝블랜딩오일": "brightening-blending-oil",  # '블랜딩' 오타
    "밀랍": "beeswax",  # 밀랍 = 비즈왁스
    "멀티오일베이스": "multibalm-oil-base",  # '멀티밤오일베이스' 표기 변형
    "베베보블랜딩오일": "bebe-bo-blending-oil",  # '블랜딩' 오타
    "브렌딩오일": "blending-oil",  # '블렌딩오일' 오타
    "라벤더에센셜오일": "lavender-eo",  # 기존 name은 '라벤더오일'
    "세라마이드": "ceramide-complex",  # 일반 '세라마이드' 표기
    "버가못fcf에센셜오일": "bergamot-fcf-eo",  # FCF 괄호 없는 표기
    "병풀추출물": "centella-extract",  # 병풀 = 센텔라아시아티카
    "오가닉7": "organic-7-solution",  # '오가닉7 솔루션' 축약
    "불가리안로즈워터": "rose-water",
    "아주진한녹차추출물": "green-tea-extract",
    "카렌듈라인퓨즈오일": "calendula-oil",  # 인퓨즈오일 = 침출오일
    "산화아연분말": "zinc-oxide",
    "징크옥사이드분산액": "zinc-oxide",
    "티타늄디옥사이드분산액": "titanium-dioxide",
    "라벤더eo": "lavender-eo",
    "헥산디올": "hexanediol",  # 단독 표기
    "엑스트라버진코코넛오일": "coconut-oil",
    # 페이지7~9 표기 변형
    "골든호호바오일": "jojoba-oil",
    "골든호호바": "jojoba-oil",
    "마카다미아넛": "macadamia-oil",
    "유칼립투스에센셜오일": "eucalyptus-eo",  # '투' 표기(등록은 '튜')
    "캐모마일워터": "roman-chamomile-water",
    "로즈플라워젤": "rose-flower-gel",  # '젤' 표기(등록은 '겔')
    "플라워겔": "rose-flower-gel",
    "12헥산디올": "hexanediol",  # 이미 있으나 유지
    "1.2헥산디올": "hexanediol",  # 마침표 표기
    "버가못fcf": "bergamot-fcf-eo",
    "발효여과물": "galactomyces-ferment",
    "프리미엄fgf": "fgf",
    "폼클렌징베이스": "gentle-foam-cleanser-base",
    "립밤베이스": "lip-balm-base",
    "블렌딩에센셜오일": "blending-oil",
    "브라이트닝블렌딩에센셜오일": "blending-oil",
    "단백질추출물": "grain-protein-extract",
    "수분크림베이스": "cream-base",
    "워셔블리퀴드": "cleansing-liquid",
    "레드27번": "lip-color-red-27",
    "레드21번": "lip-color-21",
    "상황버섯추출물": "phellinus-extract",  # 띄어쓰기 변형 흡수
    "노니추출물": "noni-extract",
    "레몬밤워터": "lemon-balm-water",
    "화이트촉촉수분크림베이스": "whitening-moisture-cream-base",
    "블렌딩된오일": "blending-oil",
    "산화아연분산액": "zinc-oxide",
    # 페이지10~12 표기 변형
    "알란토인분말": "allantoin",
    "오일베이스": "multibalm-oil-base",
    "아몬드오일": "sweet-almond-oil",
    "버진아르간오일": "argan-oil",  # normalize가 '유기농' 제거
    "버진코코넛오일": "coconut-oil",
    "올리브에스터": "olive-ester-oil",
    "호호바": "jojoba-oil",  # '정제호호바' normalize 결과
    "티트리에센셜오일": "tea-tree-eo",
    "페파민트eo": "peppermint-eo",
    "밀랍스틱": "beeswax",
    "밀랍연고": "beeswax",
    "비밀랍": "beeswax",  # '비정제밀랍' normalize 결과
    "버가못오일": "bergamot-fcf-eo",  # '버가못오일(FCF)' 괄호 제거
    "로즈우드eo": "rosewood-eo",
    "유칼립튜스eo": "eucalyptus-eo",
    "유칼립투스eo": "eucalyptus-eo",
    "레몬eo": "lemon-eo",
    "네롤리eo": "neroli-eo",
    "로즈제라늄eo": "rose-geranium-eo",
    "로즈앱솔루트eo": "rose-absolute-eo",
    "마카다이마넛오일": "macadamia-oil",
    "마카다이미아넛오일": "macadamia-oil",
    "쿠포아수버터": "cupuacu-butter",
    "자초오일": "jacho-oil",
    "자초인퓨즈오일": "jacho-oil",
    "자초근": "jacho-oil",
    "자운고인퓨즈오일": "jaunggo-oil",
    "립베이스레드27": "lip-color-red-27",
    "립컬러베이스7": "lip-color-base",
    "레몬쥬스오일": "lemon-juice-blending-oil",
    "에코바세린": "natural-vaseline",
    "알로에모이스트": "aloe-vera-gel",
    "원하는플레이버오일": "strawberry-flavor-oil",
    "진주가루": "pearl-powder",
    "수용성보존제": "water-soluble-preservative",
    "버가못오일fcf": "bergamot-fcf-eo",
    "버가못fcfeo": "bergamot-fcf-eo",
    "버가못eofcf": "bergamot-fcf-eo",
    "지용성": "coenzyme-q10",
    "캘러스배양액": "callus-culture",
    "피마자오일": "castor-oil",
    "피마자유": "castor-oil",
    # 페이지13~15 표기 변형
    "골덴호호바오일": "jojoba-oil",  # '골든' 오타
    "골덴호호바": "jojoba-oil",
    "비동백오일": "camellia-oil",  # '유기농/비정제 동백오일' normalize 결과
    "버진동백오일": "camellia-oil",
    "만다린에센셜오일": "mandarin-eo",
    "세라마이드리포좀": "ceramide-water-soluble",
    "워터코포아수버터": "cupuacu-butter",
    "진한녹차추출물": "green-tea-extract",
    "로먼캐모마일에센셜오일": "roman-chamomile-eo",
    "로즈제라늄에센셜오일": "rose-geranium-eo",
    "갈락토발효여과물": "galactomyces-ferment",
    "디판테놀": "panthenol",  # D-판테놀
    "블렌딩eo": "blending-oil",
    "자운고8종오일": "jaunggo-oil",
    "자운고8종": "jaunggo-oil",
    "버가못eo": "bergamot-fcf-eo",
    "수용성천연방부제": "water-soluble-preservative",
    "세포배양액": "stem-cell-culture",
    "줄기세포배양": "stem-cell-culture",
    "장미줄기세포배양추출물": "rose-stem-cell-culture",
    "로즈줄기세포배양액": "rose-stem-cell-culture",
    "장미줄기세포배양액": "rose-stem-cell-culture",
    "로즈앱솔루트": "rose-absolute-eo",
    "로즈3%in호호바오일": "rose-absolute-eo",
    "씨벅턴오일": "sea-buckthorn-oil",
    "카밍5솔루션": "calming-5-solution",
    "프레쉬5솔루션": "fresh-5-solution",
    "인퓨즈오일": "chamomile-infused-oil",  # 캐모마일 아토 제품군 문맥
    "원하는에센셜오일": "essential-oil",
    "프리미엄로즈워터": "rose-water",
    "로즈워터등": "rose-water",
    "8종약재인퓨즈": "jaunggo-oil",
    # sample.txt skip 보강
    "에코바세린": "natural-vaseline",
    "페파민트오일": "peppermint-eo",
    "스쿠알렌": "squalane",
    "프랑킨센스": "frankincense-eo",
    "로즈에센셜오일": "rose-absolute-eo",
    "라놀린오일": "lanolin",
    "율무": "jobs-tears-extract",
    "레몬에센셜오일": "lemon-eo",
    "천연비타민e": "tocopherol",
    # 페이지16~18 표기 변형
    "세라마이드리퀴드": "ceramide-water-soluble",
    "제라늄에센셜오일": "rose-geranium-eo",
    "보톡스펩타이드": "peptide-complex",
    "뱀독펩타이드": "peptide-complex",
    "식물성스쿠알렌": "squalane",
    "호호바라이트": "jojoba-oil",
    "코엔자임텐수용성": "coenzyme-q10",
    "코엔자임텐": "coenzyme-q10",
    "코엔자임큐텐": "coenzyme-q10",
    "식물성플라센터": "plant-placenta",
    "브라이트닝오일": "brightening-blending-oil",
    "꿀추출물": "honey-extract",
    "비피다100발효여과물": "bifida-ferment",
    "스윗아몬드오일": "sweet-almond-oil",
    "알부틴": "alpha-arbutin",
    "달팽이점액추출물": "snail-mucin",
    "진한어성초추출물": "houttuynia-extract",
    "진한녹차추출물": "green-tea-extract",
    "금설": "gold-24k",
    # sample.txt skip 보강 2차
    "감초추출물": "licorice-root",
    "한방보존제": "herbal-preservative",
    "스윗오렌지에센셜오일": "orange-eo",
    "달맞이오일": "evening-primrose-oil",
    "로즈제라늄": "rose-geranium-eo",
    "아보카도": "avocado-oil",
    "오렌지": "orange-eo",
    "라벤더": "lavender-eo",
    "네롤리": "neroli-eo",
    "만다린": "mandarin-eo",
    "알로에모이스처": "aloe-vera-gel",
    # 페이지19~22 표기 변형
    "진한~어성초추출물": "houttuynia-extract",
    "불가리아로즈워터": "rose-water",
    "레몬쥬스에센셜오일": "lemon-juice-blending-oil",
    "살구씨오일베이스": "apricot-kernel-oil",
    "비베놈봉독": "bee-venom",
    "어성초분말": "houttuynia-extract",
    "스크럽베이스멀티": "scrub-base",
    "제주화산송이": "volcanic-ash-powder",
    "그린프레쉬아로마수": "aroma-water",
    "로즈플라워아로마수": "aroma-water",
    "러블리레몬아로마수": "aroma-water",
    "포도씨오일베이스": "grapeseed-oil",
    "오렌지eo": "orange-eo",
    "프리미엄페파민트워터": "peppermint-water",
    "해바라기오일": "sunflower-oil",
    "곱게간것": "coffee-scrub-powder",  # 커피스크럽 문맥
    # sample.txt skip 보강 3차
    "달맞이종자유": "evening-primrose-oil",
    "수용성한방보존제": "water-soluble-preservative",
    "로먼카모마일": "roman-chamomile-eo",
    "캐모마일오일": "chamomile-infused-oil",
    "엑스트라버진올리브오일": "olive-oil",
    "오렌지에센셜오일": "orange-eo",
    "인삼팅크처": "ginseng-extract",
    "인삼추출물인삼팅크처": "ginseng-extract",
    "증류수": "purified-water",
    "제라늄": "rose-geranium-eo",
    "알로에겔": "aloe-vera-gel",
    "자스민": "jasmine-eo",
    "쟁단검": "xanthan-gum",
    "천연비타민": "tocopherol",
    "비타민": "tocopherol",  # '천연비타민' normalize 결과
    "식물성발효주정": "ethanol",
    "코코베타인": "capb",
    "팔마로사": "palmarosa-eo",
    "위치헤이즐": "witch-hazel-water",
    "녹차씨유": "green-tea-seed-oil",
    "감초분말": "licorice-root",
    "어성초건초": "houttuynia-extract",
    "저먼캐모마일": "german-chamomile-eo",
    "티트리": "tea-tree-eo",
    "로즈앱솔루트에센셜오일": "rose-absolute-eo",
    "로즈앱솔루트": "rose-absolute-eo",
    "카렌듈라인퓨즈오일": "calendula-oil",
    # sample.txt skip 보강 4차
    "페파민트에센셜오일": "peppermint-eo",
    "로먼카모마일에센셜오일": "roman-chamomile-eo",
    "로만카모마일": "roman-chamomile-eo",
    "로즈마리에센셜오일": "rosemary-eo",
    "컬러믹스파운데이션": "foundation-color-base",
    "카모마일인퓨즈오일": "chamomile-infused-oil",
    "프랑킨센스에센셜오일": "frankincense-eo",
    "스위마조람eo": "marjoram-eo",
    "달맞이꽃종자유": "evening-primrose-oil",
    "저먼카모마일eo": "german-chamomile-eo",
    "저먼카모마일": "german-chamomile-eo",
    # 015/004(아토·베이비·여드름)
    "오가닉7추출물": "organic-7-solution",
    "식물성에탄올": "ethanol",
    "시트로넬라컴플렉스블렌딩오일": "citronella-eo",
    "베이비샴푸베이스": "baby-shampoo-base",
    "허브누리의아주순한베이비샴푸베이스": "baby-shampoo-base",
    "아주순한베이비샴푸베이스": "baby-shampoo-base",
    # 015/005(헤어·두피·바디)
    "샴푸베이스": "gentle-shampoo-base",
    "허브누리의아주순한샴푸베이스": "gentle-shampoo-base",
    "아주순한샴푸베이스": "gentle-shampoo-base",
    "맥주효모추출물": "yeast-extract",
    "페퍼민트에센셜오일": "peppermint-eo",
    "페퍼민트eo": "peppermint-eo",
    "로즈마리에센셜오일버베논": "rosemary-eo",
    "버베논로즈마리에센셜오일": "rosemary-eo",
    "로즈마리베버논eo": "rosemary-eo",
    "쥬니퍼베리eo": "juniper-eo",
    "l멘톨": "menthol",
    "구연산": "citric-acid-food",
    "구연산용액10%": "citric-acid-food",
    "천연알로에원액": "aloe-vera-gel",
    "워터코포아수": "cupuacu-butter",
    "천연한방존제": "herbal-preservative",
    "식물성에탄올70%": "ethanol",
    "베이킹소다": "sodium-bicarbonate",
    "핑크소금": "himalayan-pink-salt",
    "사해소금가는것": "dead-sea-salt",
    "카카오분말": "cacao-scrub-powder",
    "인스턴트커피": "coffee-scrub-powder",
    "초코향": "fragrance-generic",
    "히아신스향": "fragrance-generic",
    "아로마오일": "fragrance-generic",
    "히아신스향": "fragrance-generic",
    "라임캔디블렌딩오일": "blending-oil",
    "민트쿨컴플렉스블렌딩오일": "blending-oil",
    "컴플렉스블랜딩에센셜오일": "blending-oil",
    "블랜딩오일": "blending-oil",
    "블랜딩오일샴푸용": "blending-oil",
    "7가지한방추출물": "herbal-7-complex",
    "컨디셔닝유화제": "btms",
    "컨디셔닝유화제btms": "btms",
    "실크엘라스틴": "silk-elastin",
    "윤모생기추출물": "yunmo-extract",
    "msm유기유황": "msm",
    "msm식이유황": "msm",
    "덱스판테놀비타민b5": "panthenol",
    "알로에원액": "aloe-vera-gel",  # '천연알로에원액' normalize 결과
    "진~한녹차추출물": "green-tea-extract",
    "진~한하수오추출물": "fo-ti-extract",
    "한방존제": "herbal-preservative",  # '천연한방존제' normalize 결과
    "어성초두피건강샴푸": "gentle-shampoo-base",
    "시어버터스크럽베이스": "scrub-base",
    "페파민트에센셜오일eo": "peppermint-eo",
    "카프릴릭카프릭트리글리세라이드mct": "mct",
    "페퍼민트워터": "peppermint-water",
    "프리미엄네롤리워터": "neroli-water",
    "세틸알코올": "cetyl-alcohol",
    "그레이프프룻": "grapefruit-eo",
    "달인물": "herbal-7-complex",
    "베베보블렌딩eo": "bebe-bo-blending-oil",
    "물": "purified-water",
    "워터": "purified-water",
    # 015 skip 보강(sample.txt)
    "프리미엄로즈마리워터": "rosemary-water",
    "em발효액": "em-active",
    "레몬글라스에센셜오일": "lemongrass-eo",
    "일랑일랑에센셜오일": "ylang-ylang-eo",
    "올리브왁스": "olive-emulsifying-wax",
    "페파민트": "peppermint-eo",
    "페퍼민트": "peppermint-eo",
    "히말라얀루비쏠트": "himalayan-pink-salt",
    "크리스탈소금": "himalayan-pink-salt",
    "쥬니퍼베리에센셜오일": "juniper-eo",
    "탄산수소나트륨": "sodium-bicarbonate",
    "스피아민트에센셜오일": "spearmint-eo",
    "마카데미아넛오일": "macadamia-oil",
    "일랑일랑": "ylang-ylang-eo",
    "쥬니퍼베리": "juniper-eo",
    # 015/006002(향수·디퓨저) — 향 이름은 조합향료로, 베이스 변형은 각 베이스로
    "카네이션향": "fragrance-oil",
    "카네이션": "fragrance-oil",
    "무화과향": "fragrance-oil",
    "끌로에우먼": "fragrance-oil",
    "그린티시트러스": "fragrance-oil",
    "바닐라": "fragrance-oil",
    "핑크샌드": "fragrance-oil",
    "클린코튼": "fragrance-oil",
    "웨딩데이": "fragrance-oil",
    "로즈듀에": "fragrance-oil",
    "레드로지스": "fragrance-oil",
    "플라워바디겐조": "fragrance-oil",
    "에이프릴프레쉬": "fragrance-oil",
    "프러그런스오일": "fragrance-oil",
    "프러그런스": "fragrance-oil",
    "디퓨저전용베이스": "diffuser-base",
    "젬마석고": "eco-gypsum",
    "로즈우드에센셜오일오일": "rosewood-eo",
    "로즈우드에센셜오일": "rosewood-eo",
    "베이비파우더": "corn-starch",
    "라벤더건초": "dried-botanical",
    "캐모마일꽃건초": "dried-botanical",
    "장미꽃봉우리": "dried-botanical",
    "크리스탈방향볼": "crystal-ball",
    "비누용색소": "soap-colorant",
    "시트로넬라블랜딩오일": "blending-oil",
    "레몬쥬스블랜딩오일": "lemon-juice-blending-oil",
    "레몬쥬스": "lemon-juice-blending-oil",
    "휘기에": "fragrance-oil",
    "체리블라썸향": "cherry-blossom-fragrance",
    "에탄올": "ethanol",
    # 015/007(생활용품)
    "아로마베이스70": "aroma-base-70",
    "친환경석고분말": "eco-gypsum",
    "구연산수10%": "citric-acid-food",
    "편백수": "hinoki-water",
    "레몬글라스오일": "lemongrass-eo",
    "레몬글라스eo": "lemongrass-eo",
    "싸이프러스eo": "cypress-eo",
    "레몬쥬스eo": "lemon-juice-blending-oil",
    "유황msm": "msm",
    "식이유황": "msm",
    "약산성비누베이스": "weak-acid-soap-base",
    "맑은em": "em-active",
    "원하는향료": "fragrance-oil",
    "계피": "cinnamon-eo",
    "시나몬오일": "cinnamon-eo",
    "덴탈실리카연마용": "dental-silica",
    "덴탈연마실리카": "dental-silica",
    "덴탈점도실리카": "dental-silica",
    "애플워시": "apple-surfactant",
}

# 이름 매칭 시 떼어내는 수식 괄호(원료 동일성에 영향 없는 것들).
_STRIP_PARENS = ("유기농", "정제", "액상", "골든", "수", "수용성", "fcf", "소독용")
# 괄호 없이 앞에 붙는 수식어 단어(원료 동일성에 무관) — 제거 후 매칭.
_QUALIFIER_WORDS = ("유기농", "정제", "초임계", "천연")


def normalize(name: str) -> str:
    """매칭용 정규화: 공백/구두점 제거, 특정 수식 괄호 제거, 소문자화."""
    s = unicodedata.normalize("NFC", name).strip().lower()
    # 괄호 내용이 수식어면 제거, 아니면 괄호만 벗김
    def _paren(m: re.Match) -> str:
        inner = m.group(1)
        return "" if any(k in inner for k in _STRIP_PARENS) else inner
    s = re.sub(r"[\(\（]([^\)\）]*)[\)\）]", _paren, s)
    for w in _QUALIFIER_WORDS:
        s = s.replace(w, "")
    s = re.sub(r"[\s,·\-_/]+", "", s)  # 공백·쉼표·중점·하이픈·언더바·슬래시 제거
    return s


def build_name_index() -> dict[str, str]:
    """ingredients.yaml의 name → id 자동 색인 + 별칭."""
    idx: dict[str, str] = {}
    master = load_ingredients()
    for ing in master.ingredients:
        idx[normalize(ing.name)] = ing.id
        idx[normalize(ing.id)] = ing.id  # id를 그대로 적어도 인식
    idx.update(SYNONYMS)  # 별칭이 자동색인을 덮어씀
    return idx


_AMOUNT_RE = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*[~\-]\s*(\d+(?:\.\d+)?))?\s*(방울|kg|g|ml|㎖|mL)?",
    re.IGNORECASE)


def parse_amount(text: str, density: float | None) -> float:
    """'83g' '40방울' '100ml' '0~5g'(범위는 최댓값) → 질량(g). density 없으면 ml=1.0."""
    m = _AMOUNT_RE.search(text.strip())
    if not m:
        raise ValueError(f"용량을 해석할 수 없습니다: {text!r}")
    # 범위(a~b)는 최댓값을 취함 → 0으로 시작하는 범위에서 0이 되는 것 방지
    val = float(m.group(1))
    if m.group(2):
        val = max(val, float(m.group(2)))
    unit = (m.group(3) or "g").lower()
    if unit == "방울":
        return val * DROP_G
    if unit == "kg":
        return val * 1000.0
    if unit in ("ml", "㎖"):
        return val * (density if density else 1.0)
    return val  # g


def split_item(line: str) -> tuple[str, str, str, str]:
    """'한글명 | 용량 | 특징 | 대체' 파싱(뒤 2개 선택)."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 2:
        raise ValueError(f"재료 줄은 '이름 | 용량' 형식이어야 합니다: {line!r}")
    name, amount = parts[0], parts[1]
    feature = parts[2] if len(parts) > 2 else ""
    subst = parts[3] if len(parts) > 3 else ""
    return name, amount, feature, subst


def resolve_phases(card: dict, idx: dict[str, str], densities: dict[str, float | None]):
    """카드 → (phases 원자료, 미해결 원료 목록). phases 원자료는 g 기준."""
    raw_phases = card.get("phases")
    if not raw_phases:
        raw_phases = [{"name": card.get("process_name", "A"),
                       "process": card.get("process"),
                       "items": card["ingredients"]}]
    unknown: list[tuple[str, str, str]] = []  # (원본명, 특징, 대체)
    out = []
    for ph in raw_phases:
        items = ph.get("items") or ph.get("ingredients") or []
        resolved = []
        for line in items:
            name, amount, feature, subst = split_item(str(line))
            key = normalize(name)
            ing_id = idx.get(key)
            if ing_id is None:
                unknown.append((name, feature, subst))
                resolved.append((None, name, amount))
            else:
                g = parse_amount(amount, densities.get(ing_id))
                resolved.append((ing_id, name, g))
        out.append({"name": ph.get("name", "A"), "process": ph.get("process"),
                    "items": resolved})
    return out, unknown


def slugify_ascii(product: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", product.lower()).strip("-")
    return s or "product"


def stub_for(name: str, feature: str, subst: str) -> str:
    """미등록 원료를 ingredients.yaml에 붙여넣을 stub."""
    note_bits = [b for b in (feature, f"대체: {subst}" if subst else "") if b]
    note = " / ".join(note_bits) or "허브누리 레시피 기반—검증 필요"
    return (
        f"  - id: TODO-{slugify_ascii(name)}   # ← 적절한 영문 슬러그로 수정\n"
        f"    name: {name}\n"
        f"    inci: TODO (INCI 확인 필요)\n"
        f"    category: TODO\n"
        f"    density: 1.0\n"
        f"    has_coa: false\n"
        f"    grade: cosmetic\n"
        f"    notes: {note}"
    )


# --- 원본 붙여넣기(raw) 파서 ----------------------------------------------
# 허브누리 상세페이지에서 복사한 표를 그대로 먹는다. 가정:
#   · 제품 경계 = 어떤 줄 다음 줄이 '재료 … 용량 …' 헤더면, 앞 줄이 제품명.
#   · 재료 줄 = 금액 토큰(83g / 99~97g / 40방울 / 100ml)을 포함. 금액 앞이 이름.
#   · 금액 없는 줄(특징 이어짐 · '.' · 빈 줄)은 무시.
#   · 범위(99~97)는 첫 값을 취함.
_RAW_AMOUNT = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*[~\-]\s*(\d+(?:\.\d+)?))?\s*(방울|kg|g|ml|㎖|mL)")


def _is_header(line: str) -> bool:
    return "재료" in line and "용량" in line


def _find_amount(line: str):
    m = _RAW_AMOUNT.search(line)
    if not m:
        return None
    name = line[: m.start()].strip()
    if not name:
        return None
    val = m.group(1)
    if m.group(2):  # 범위(a~b)는 최댓값 — '0~5' 같은 0-시작 방지
        val = m.group(1) if float(m.group(1)) >= float(m.group(2)) else m.group(2)
    return name, f"{val}{m.group(3)}"


def parse_raw(text: str) -> list[dict]:
    """붙여넣기 텍스트 → 제품 카드(dict) 리스트. 각 카드는 ingredients=['이름 | 용량', ...]."""
    products: list[dict] = []
    cur: dict | None = None
    cut = False  # 한 표에 '완제 베이스 활용' 2번째 변형이 이어질 때 그 앞에서 끊음
    prev_nonblank: str | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if _is_header(s):
            if cur and cur["ingredients"]:
                products.append(cur)
            cur = {"product": prev_nonblank or "제품", "ingredients": []}
            cut = False
            prev_nonblank = s
            continue
        hit = _find_amount(s)
        if hit and cur is not None and not cut:
            name, amount = hit
            nn = normalize(name)
            # 스피큘·샷 등 무게 아닌 행(미세니들 키트) 무시
            if any(j in name for j in ("스피큘", "샷", "미세", "또는")):
                prev_nonblank = s
                continue
            # 재료 3개 이상 쌓인 뒤 '…베이스/솔루션앰플'이 나오면 = 2번째 변형 시작 → 절단
            if len(cur["ingredients"]) >= 3 and ("베이스" in nn or "솔루션앰플" in nn):
                cut = True
            else:
                cur["ingredients"].append(f"{name} | {amount}")
        prev_nonblank = s
    if cur and cur["ingredients"]:
        products.append(cur)
    return products


def guess_type(product: str) -> str:
    """제품명으로 rinse_off/leave_on 추정(확인 필요)."""
    return "rinse_off" if any(k in product for k in ("클렌징", "샴푸", "워시", "비누")) else "leave_on"


def build_formula_dict(card: dict, phases) -> dict:
    total_g = sum(g for ph in phases for (_id, _n, g) in ph["items"])
    if total_g <= 0:
        raise ValueError("총 용량이 0입니다.")
    # percent 환산 후, 반올림 오차를 가장 큰 성분에서 보정해 합계 100 보장.
    rows = []
    for ph in phases:
        prs = []
        for (ing_id, _name, g) in ph["items"]:
            prs.append([ing_id, round(g / total_g * 100, 2)])
        rows.append(prs)
    flat = [p for prs in rows for p in prs]
    drift = round(100.0 - sum(p[1] for p in flat), 2)
    if flat and drift:
        biggest = max(flat, key=lambda p: p[1])
        biggest[1] = round(biggest[1] + drift, 2)

    phase_dicts = []
    for ph, prs in zip(phases, rows):
        pd: dict = {"name": ph["name"],
                    "ingredients": [{"id": i, "percent": p} for i, p in prs]}
        if ph.get("process"):
            pd["process"] = ph["process"]
        phase_dicts.append(pd)

    slug = card.get("slug") or slugify_ascii(card["product"])
    regime = card.get("regime", "cosmetics")
    from brandlab.migrate_taxonomy import formula_category, formula_line
    cat = card.get("category") or formula_category(card["product"], slug, regime)
    line = card.get("line") or (formula_line(card["product"], slug) if regime == "cosmetics" else None)
    f: dict = {
        "product": card["product"],
        "slug": slug,
        "version": int(card.get("version", 1)),
        "regime": regime,
        "category": cat,
        **({"line": line} if line else {}),
        "product_type": card["type"],
        "status": card.get("status", "개발중"),
        "base_batch_g": round(total_g, 2),
        "phases": phase_dicts,
        "packaging": [],
    }
    if card.get("volume_ml"):
        f["fill_volume_ml"] = float(card["volume_ml"])
    if card.get("net_g"):
        f["net_weight_g"] = float(card["net_g"])
    if card.get("product_category"):  # 화학제품안전법 품목코드 등
        f["product_category"] = card["product_category"]
    src = card.get("source")
    if src:
        f["source_url"] = src
    note = card.get("notes") or ""
    if note:
        f["notes"] = note
    return f


TEMPLATE = """\
# 제품 카드 — 재료만 채워서 저장하면 스크립트가 처방 YAML을 만든다.
# 재료 1줄 = "한글명 | 용량 | 특징 | 대체"   (특징·대체는 선택, 없으면 생략)
# 용량 단위: g(기본) · ml(density로 g 환산) · 방울(≈0.05g)
product: 제품명
slug: my-product          # 선택. 없으면 product에서 자동 생성(영문일 때만 유효)
type: leave_on            # leave_on(씻지않음) | rinse_off(헹굼)
status: 개발중
volume_ml: 100            # 또는 net_g: 100
source: https://www.herbnoori.com/shop/shopdetail.html?branduid=XXXXX
# --- 단일상이면 ingredients, 여러 상이면 phases 사용 ---
ingredients:
  - 비타민나무워터 | 83g | 비타민나무 열매 증류수 | 티트리, 로즈워터
  - 글리세린 | 3g | 보습 | 히아루론산
  - 덱스판테놀 | 1g
# phases 예시(주석 해제해서 사용):
# phases:
#   - name: "A (유상)"
#     process: 70~80도 가열해 유화
#     items:
#       - 스쿠알란 | 13g
#       - 올리브유화왁스 | 5g
#   - name: B (수상)
#     items:
#       - 네롤리워터 | 50g
"""


def _print_stubs(unknown) -> None:
    print("⛔ ingredients.yaml에 없는 원료가 있습니다. 아래 stub을 채워 등록 후 다시 실행하세요:\n",
          file=sys.stderr)
    seen = set()
    for name, feature, subst in unknown:
        if name in seen:
            continue
        seen.add(name)
        print(stub_for(name, feature, subst) + "\n", file=sys.stderr)


def _run_raw(args) -> int:
    text = Path(args.card).read_text(encoding="utf-8")
    products = parse_raw(text)
    if not products:
        print("제품을 찾지 못했습니다. '재료 … 용량 …' 헤더 줄이 있는지 확인하세요.", file=sys.stderr)
        return 2

    idx = build_name_index()
    master = load_ingredients()
    densities = {ing.id: ing.density for ing in master.ingredients}
    ids = {ing.id for ing in master.ingredients}

    resolved_all, all_unknown = [], []
    for p in products:
        card = {"product": p["product"], "type": guess_type(p["product"]),
                "ingredients": p["ingredients"]}
        phases, unknown = resolve_phases(card, idx, densities)
        resolved_all.append((card, phases))
        all_unknown.extend(unknown)
    if all_unknown:
        _print_stubs(all_unknown)
        return 2

    slugs = [s.strip() for s in args.slugs.split(",")] if args.slugs else None
    if slugs and len(slugs) != len(products):
        print(f"⛔ 제품 {len(products)}개인데 slug는 {len(slugs)}개입니다.", file=sys.stderr)
        return 2

    print(f"{len(products)}개 제품 감지"
          + ("" if slugs else " — 미리보기(쓰려면 --slugs 지정):"))
    rc = 0
    for i, (card, phases) in enumerate(resolved_all):
        total = sum(g for ph in phases for (_id, _n, g) in ph["items"])
        card["volume_ml"] = round(total, 1)  # 내용량 미상 → 총량(≈1g/ml)으로 근사
        if slugs:
            card["slug"] = slugs[i]
        fdict = build_formula_dict(card, phases)
        formula = Formula.model_validate(fdict)
        missing = [x for x in formula.ingredient_ids() if x not in ids]
        if missing:
            print(f"⛔ [{card['product']}] 참조 id 누락: {sorted(set(missing))}", file=sys.stderr)
            rc = 2
            continue
        names = ", ".join(f"{i2['id']}={i2['percent']}%"
                          for ph in fdict["phases"] for i2 in ph["ingredients"])
        tag = f"[type={card['type']}·추정, 내용량≈{card['volume_ml']}g·추정]"
        if not slugs:
            print(f"  • {card['product']}  {tag}\n      {names}")
            continue
        out = FORMULAS_DIR / formula.slug / f"v{formula.version}.yaml"
        if out.exists() and not args.force:
            print(f"⛔ 이미 존재: {out} (덮어쓰려면 --force)", file=sys.stderr)
            rc = 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml.safe_dump(fdict, allow_unicode=True, sort_keys=False, width=100),
                       encoding="utf-8")
        print(f"  ✅ {card['product']} → {out}  (합계 {formula.total_percent:.2f}%) {tag}")
    if not slugs:
        print("\n※ type·내용량은 추정값 — 처방 파일 생성 후 확인/수정하세요.")
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="허브누리 레시피 카드 → 처방 YAML")
    ap.add_argument("card", nargs="?", help="제품 카드 YAML 경로")
    ap.add_argument("--template", action="store_true", help="빈 카드 템플릿 출력")
    ap.add_argument("--force", action="store_true", help="기존 처방 파일 덮어쓰기")
    ap.add_argument("--stdout", action="store_true", help="파일 대신 stdout으로 출력")
    ap.add_argument("--raw", action="store_true",
                    help="card를 허브누리 붙여넣기 원본으로 처리(여러 제품 가능)")
    ap.add_argument("--slugs",
                    help="--raw 전용. 제품별 slug를 순서대로 쉼표로. 생략 시 미리보기만.")
    args = ap.parse_args(argv)

    if args.template:
        print(TEMPLATE)
        return 0
    if not args.card:
        ap.error("card 경로가 필요합니다(또는 --template).")

    if args.raw:
        return _run_raw(args)

    card = yaml.safe_load(Path(args.card).read_text(encoding="utf-8"))
    idx = build_name_index()
    densities = {ing.id: ing.density for ing in load_ingredients().ingredients}

    phases, unknown = resolve_phases(card, idx, densities)
    if unknown:
        print("⛔ ingredients.yaml에 없는 원료가 있습니다. 아래 stub을 채워 등록 후 다시 실행하세요:\n",
              file=sys.stderr)
        seen = set()
        for name, feature, subst in unknown:
            if name in seen:
                continue
            seen.add(name)
            print(stub_for(name, feature, subst) + "\n", file=sys.stderr)
        print(f"(별칭으로 해결 가능하면 herbnoori_import.py의 SYNONYMS에 추가해도 됩니다.)",
              file=sys.stderr)
        return 2

    fdict = build_formula_dict(card, phases)
    # 로더 모델로 검증(합계 100·참조무결성).
    ids = {ing.id for ing in load_ingredients().ingredients}
    formula = Formula.model_validate(fdict)
    missing = [i for i in formula.ingredient_ids() if i not in ids]
    if missing:
        print(f"⛔ 참조 원료 id 누락: {sorted(set(missing))}", file=sys.stderr)
        return 2

    text = yaml.safe_dump(fdict, allow_unicode=True, sort_keys=False, width=100)
    if args.stdout:
        print(text)
        return 0

    out = FORMULAS_DIR / formula.slug / f"v{formula.version}.yaml"
    if out.exists() and not args.force:
        print(f"⛔ 이미 존재: {out} (덮어쓰려면 --force)", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"✅ 생성: {out}  (합계 {formula.total_percent:.2f}%, {len(formula.phases)}상, "
          f"{formula.product_type.value})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
