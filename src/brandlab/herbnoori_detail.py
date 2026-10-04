"""허브누리 상세정보(page01) 크롤러 — 재료표 밖의 '작성자 꿀팁·제조과정·캡처'.

herbnoori_crawl.py는 재료+용량 '표'만 뽑는다. 이 모듈은 같은 상세페이지의
'상세정보' 구간(<div id="page01">)에서 표 바깥의 서술형 내용을 가져온다:
  - 요약(난이도·소요시간·준비물)
  - 작성자 꿀팁(사용법·경험담 등 서술 문단)
  - 제조과정 설명("만들기" 단계 텍스트)
  - 캡처 이미지(제조과정 사진 등) → 로컬 저장 + URL

엑셀 정리용. 각 제품(branduid) 1건으로 요약해 반환한다.

사용 예:
    # 엑셀(링크 열의 branduid)에 상세내용/이미지 열을 추가
    uv run python -m brandlab.herbnoori_detail --xlsx 허브누리_레시피_목록.xlsx \
        --img-dir cards/detail_img

    # 특정 제품만 콘솔로 확인(저장 안 함)
    uv run python -m brandlab.herbnoori_detail --branduids 1002 --dump

출처 표시: 허브누리는 레시피 공개·인쇄를 허용하되 출처 표시를 요구한다.
주의: 외부 사이트 반복 호출. 기본 지연 1.0초.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

BASE = "https://www.herbnoori.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 상세정보 구간 경계(상단 탭 네비·후기·문의를 배제).
_PAGE01 = re.compile(r"(?is)<!-- page01 상세정보 -->(.*?)<!--// page01 상세정보 -->")
# 판매자 자유 편집영역 시작(이 뒤부터가 실제 상세내용; 앞은 탭 네비).
_OPENEDITOR = re.compile(r"(?is)<!--\s*\[OPENEDITOR\]\s*-->")
# 상세내용 종료 신호(이 뒤 안내문·품질배너는 버린다).
_TEXT_TERMINATORS = ("허브누리에서 제공", "타사의 원료를 사용")
# 서술에서 지우는 상단 상용구.
_BOILERPLATE_LINES = {
    "레시피후기", "상세정보", "레시피관련상품", "레시피문의", "위로 올라가기",
    "[허브누리의 아주 쉬운 레시피]", ".",
}
# 내려받지 않을 이미지(품질경영 배너·여백/스페이서 등).
_IMG_SKIP = ("shop_img/company", "/blank", "spacer", "btn_", "icon_", "bg_")

_CELL = re.compile(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>")
_ROW = re.compile(r"(?is)<tr[^>]*>(.*?)</tr>")
_TABLE_OPEN = re.compile(r"(?i)<table\b")
_TABLE_CLOSE = re.compile(r"(?i)</table>")
_NESTED_TABLE = re.compile(r"(?is)<table\b.*?</table>")
_IMG_SRC = re.compile(r"""(?is)<img[^>]+src\s*=\s*["']?([^"'\s>]+)""")


# ── 학습용: 원료 역할(제형 phase) 분류 + 용량 % 환산 ──────────────────────
# 제형 골격을 눈에 보이게: 각 원료를 대분류 역할로 태깅한다. 키워드 규칙(위→아래
# 우선순위)으로 재료명+특징을 훑는다. 화장품 처방의 통상 phase 어휘 기준(예시,
# 검증 필요) — 셰프의 '기본 골격' 감각용이지 규제 분류가 아니다.
ROLE_ORDER = ["수상", "유상", "유화", "경화", "계면", "보습",
              "활성", "향", "색소", "방부", "점증/pH", "기타"]
ROLE_COLORS = {  # 옅은 배경색(역할 셀)
    "수상": "DCEBFF", "유상": "FFF0CC", "유화": "D8F5D8", "경화": "E8E0D0",
    "계면": "E6DAF5", "보습": "CFF3F0", "활성": "EAD9F7", "향": "FBD9E8",
    "색소": "F5D9C0", "방부": "E2E5E9", "점증/pH": "E9F0D6", "기타": "F0F0F0",
}

# 제형별 배합 기본원칙·주의(치트시트용). 화장품 제조의 통상 공정 지식(예시,
# 검증 필요) — 효능·치료 표방 아님. 키 = archetype_cards의 파일명에서 번호 뗀 값.
ARCHETYPE_TIPS = {
    "토너·미스트": [
        "에센셜오일은 가용화제(올리브리퀴드 등) 없이 넣으면 분리·자극 — 전체 0.5~1% 이내로.",
        "물이 대부분이라 방부 필수(무방부는 냉장·수일 내 소진).",
        "점증제(잔탄검 등)는 글리세린에 미리 분산 후 넣어야 안 뭉침.",
    ],
    "젤": [
        "카보머는 물에 완전 수화 후 중화(pH 조절)해야 젤이 잡힘.",
        "전해질(소금기)·고농도 알콜·산성 활성은 점도를 무너뜨릴 수 있음.",
        "기포 생기면 잠시 두어 빼거나 저속 교반.",
    ],
    "앰플·세럼": [
        "활성마다 안정 pH가 다름(비타민C 산성, 펩타이드 중성) — 섞기 전 확인.",
        "히알루론산은 물에 충분히 불려 사용(덩어리 방지).",
        "고농도라도 권장 사용량 초과 ≠ 효과 비례, 자극만 커질 수 있음.",
    ],
    "팩·마스크·패드": [
        "클레이는 금속 도구 피하고, 굳기 전 씻어냄(과건조 시 당김).",
        "시트·패드는 수분 많아 오염·변질 취약 → 위생·방부 철저.",
        "가루 클레이는 수상에 먼저 분산 후 나머지 배합.",
    ],
    "로션": [
        "유화 핵심: 수상·유상 같은 온도(65~75℃)에서 합쳐야 안 깨짐.",
        "유화제가 부족하면 분리 — 오일상 대비 적정 비율 확보.",
        "향·활성 첨가물은 40~50℃로 식은 뒤 투입(열 손상 방지).",
    ],
    "크림": [
        "왁스·버터 완전히 녹인 뒤 유화, 식으며 점도가 오름.",
        "로션과 같은 '동일 온도 유화' 원칙 + 유상 비율 높아 핸드블렌더로 미세화.",
        "수분 함유 → 방부·pH 관리 필수.",
    ],
    "페이스·바디오일": [
        "무수 처방 → 방부 불필요, 대신 물 유입 금지(들어가면 상함).",
        "산패 방지: 비타민E(토코페롤) 소량 + 서늘·차광 보관.",
        "에센셜오일은 캐리어오일에 희석(원액 도포는 자극).",
    ],
    "밤·살브·연고": [
        "왁스(밀랍·칸데릴라) 비율이 굳기를 결정 — 늘리면 단단, 줄이면 말랑.",
        "무수 처방 → 방부 불필요, 수분 유입 금지.",
        "다 녹인 뒤 40~50℃에서 향 투입, 굳으며 수축·기포 가능.",
    ],
    "색조": [
        "파우더(색소·마이카)는 뭉치면 색 얼룩 → 미리 갈거나 분산제로 분산.",
        "립·무수 색조는 방부 불필요, 수분 유입만 주의.",
        "눈가·입술용은 사용 허가된 색소인지 확인(안전성·규제).",
    ],
    "세정(클렌징)": [
        "계면활성제 과농도는 자극 — 아미노산·글루코사이드계로 순하게.",
        "약산성(pH 5~6)으로 맞추면 피부 부담↓.",
        "워셔블 오일은 가용화제(올리브리퀴드) 비율 확보해야 물에 헹궈짐.",
    ],
    "헤어세정": [
        "물비누베이스는 알칼리 → 산성 린스(구연산)로 마무리하면 모발 정돈.",
        "물 함량 높아 방부 필수.",
        "두피 민감 — 계면활성제·에센셜오일 농도 과하지 않게.",
    ],
    "완제베이스+활성": [
        "완제 베이스는 이미 유화·방부 완료 → 활성 '소량 추가'만(과투입 시 유화 깨짐).",
        "베이스 권장 첨가 한도를 지킬 것.",
        "활성 pH가 베이스와 안 맞으면 분리·변색.",
    ],
    "입욕·스크럽": [
        "바스밤: 베이킹소다+구연산은 습기에 미리 반응 → 건조·밀봉 보관.",
        "스크럽 입자가 거칠면 피부 손상 → 고운 입자 사용.",
        "오일 함유 제품은 욕조 미끄럼 주의.",
    ],
    "생활화학": [
        "화장품과 규제 레짐이 다름 — 생활화학제품은 안전확인·신고 대상.",
        "혼합 금지 조합 주의(예: 염소계+산성). 용도·주의 표기 확인.",
        "계면활성제·산/알칼리 농도와 보관 안전 기준 준수.",
    ],
    "기타(미분류)": [
        "먼저 제형(수상/유상/무수/유화 여부)을 파악하고 해당 골격을 참고.",
        "기본 점검: 방부(물 있으면 필수)·pH·유화 온도.",
    ],
}
# (역할, 키워드들) — 앞선 규칙이 이기므로 향/방부/활성을 오일·왁스보다 먼저.
_ROLE_RULES = [
    ("향", ("에센셜오일", "essential", "에센셜", "eo", "아로마오일", "앱솔루트", "향",
            "옵소루트", "프래그런스", "프레그런스", "향료", "플레이버", "플래이버", "부케")),
    ("방부", ("방부", "보존제", "보존", "페녹시", "페 녹 시", "1,2-헥산", "헥산다이올",
             "파라벤", "소르빈", "안식향", "벤조", "나파졸", "항균제", "그레이프후르츠종자")),
    ("계면", ("계면활성", "물비누베이스", "비누베이스", "코코베타인", "베타인",
             "글루코사이드", "les", "설페이트", "sls", "sci", "애플워시", "폼베이스",
             "물비누", "가용화제")),
    ("유화", ("유화왁스", "유화제", "이멀", "올리브리퀴드", "montanov", "몬타노브",
             "올리브유화", "gms", "세테아릴올리브", "글리세릴스테아", "폴리소르베이트",
             "세틸에틸", "이엘")),
    ("활성", ("추출물", "팅크", "인퓨즈", "egf", "fgf", "펩타이드", "콜라겐", "엘라스틴",
             "나이아신", "비타민", "아데노신", "알부틴", "코엔자임", "세라마이드",
             "플라센타", "태반", "진주", "점액", "히아루론", "판테놀", "알로에겔",
             "알로에모이스트", "알로에베라겔", "알로에원액", "천연알로에", "센텔라",
             "병풀", "아미노산", "레티놀", "발효", "카페인", "글루타치온", "알란토인",
             "보르피린", "낫또", "프로바이오", "리피듀어", "코직", "트라넥삼", "곡물",
             "로즈플라워겔", "리페어")),
    ("보습", ("글리세린", "솔비톨", "소르비톨", "프로판다이올", "베타인글리", "우레아",
             "히알루론", "부틸렌글라이콜", "다이올", "당류", "꿀", "허니", "자일리톨",
             "에코보습", "보습제")),
    ("유상", ("오일", " oil", "버터", "스쿠알", "스쿠알란", "트리글리", "에스터",
             "미네랄오일", "왁스에스터", "지방산", "세틸알콜", "세테아릴알콜",
             "스테아릴", "실리콘", "디메치콘", "사이클로")),
    ("경화", ("밀랍", "칸데릴라", "카나우바", "비즈왁스", "왁스", "경화제")),
    ("색소", ("색소", "마이카", "산화철", "이산화티탄", "티타늄", "옥사이드", "피그먼트",
             "펄", "클레이", "카올린", "시카고", "울트라마린")),
    ("점증/pH", ("구연산", "점증", "잔탄", "쟁탄", "카보머", "하이셀", "하이드록시에틸",
                "셀룰로", "검", "중조", "베이킹소다", "수산화", "트리에탄올", "ph")),
    ("수상", ("정제수", "증류수", "워터", "하이드로졸", "플로럴", "수(", "물", "우린물",
             "베라원액", "발효액")),
]


def tidy_feature(s: str) -> str:
    """원료 특징 텍스트를 학습용으로 정돈(규칙 기반, 무료).

    '/'·줄바꿈으로 흩어진 조각을 ' · '로 통일, 중복·군더더기 제거, 공백 정리.
    """
    if not s:
        return ""
    parts = re.split(r"\s*[/\n]\s*", str(s))
    out: list[str] = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip(" ,·-~")
        p = re.sub(r"^[-·]\s*", "", p)
        if p and p not in out:
            out.append(p)
    return " · ".join(out)


def classify_role(name: str, feature: str = "") -> str:
    """원료 역할 추정: 이름으로 먼저(정확), 못 잡으면 특징으로 보조. 미스는 '기타'.

    이름 우선이라 '호호바오일(특징:보습)'이 보습으로 새지 않고 유상으로 남는다.
    """
    nm = (name or "").lower()
    for role, kws in _ROLE_RULES:
        if any(k in nm for k in kws):
            return role
    ft = (feature or "").lower()
    for role, kws in _ROLE_RULES:
        if any(k in ft for k in kws):
            return role
    return "기타"


_AMT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:[~\-]\s*(\d+(?:\.\d+)?))?\s*"
                  r"(kg|g|ml|mL|㎖|방울|%)")


def amount_to_g(s: str) -> float | None:
    """용량 문자열 → 그램 근사(범위는 중앙값, 방울≈0.05g, ml≈g). %/미상은 None."""
    if not s:
        return None
    m = _AMT.search(str(s))
    if not m:
        return None
    lo = float(m.group(1))
    val = (lo + float(m.group(2))) / 2 if m.group(2) else lo
    unit = m.group(3)
    if unit == "%":
        return None                      # %는 별도 취급(합산 제외)
    if unit == "kg":
        return val * 1000
    if unit == "방울":
        return val * 0.05
    return val                            # g·ml·㎖ ≈ 그램


def _table_spans(h: str) -> list[tuple[int, int]]:
    """중첩 포함 모든 <table>의 (시작,끝) 위치를 balanced 매칭으로 반환(안쪽부터).

    허브누리는 레시피 표를 레이아웃 표 안에 중첩한다. 단순 `<table.*?</table>`
    는 span이 깨져 엉뚱한 표를 잡으므로, 여는/닫는 태그를 스택으로 맞춘다.
    """
    toks = sorted(
        [(m.start(), "o") for m in _TABLE_OPEN.finditer(h)]
        + [(m.end(), "c") for m in _TABLE_CLOSE.finditer(h)])
    stack: list[int] = []
    spans: list[tuple[int, int]] = []
    for pos, kind in toks:
        if kind == "o":
            stack.append(pos)
        elif stack:
            spans.append((stack.pop(), pos))
    return spans


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def fetch_html(url: str) -> str:
    return fetch_bytes(url).decode("cp949", errors="replace")  # 허브누리는 CP949


def _text(fragment: str) -> str:
    """HTML 조각 → 정돈된 여러 줄 텍스트(<br>/블록 = 줄바꿈)."""
    t = re.sub(r"(?is)<script.*?</script>", " ", fragment)
    t = re.sub(r"(?is)<style.*?</style>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", t)
    t = re.sub(r"(?i)</td>", " | ", t)  # 만들기 표: 단계들을 한 줄에 구분
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html.unescape(t)
    out = []
    for ln in t.splitlines():
        ln = re.sub(r"[ \t ]+", " ", ln).strip().strip("|").strip()
        if ln and ln not in _BOILERPLATE_LINES:
            out.append(ln)
    return "\n".join(out)


# 용량 셀 패턴(예: '10g', '15~20g', '72방울', '3.6ml'). 재료표 판별 보조.
_AMOUNT_CELL = re.compile(
    r"^\s*\d+(?:\.\d+)?(?:\s*[~\-]\s*\d+(?:\.\d+)?)?\s*(g|kg|ml|mL|㎖|방울)\b")


def _is_recipe_table(table_html: str) -> bool:
    """재료표인가? 중첩 표를 지운 뒤 '직계 셀 전체'로 판정한다.

    이 사이트는 헤더(원료명·용량·특징…)와 데이터를 셀 하나당 한 행으로 흩어
    놓기도 한다. 그래서 첫 몇 행만 봐선 놓친다. 직계 셀들을 모아:
      (재료/원료 헤더 존재) AND (용량/양 헤더 또는 용량형 셀 2개 이상) → 재료표.
    중첩 표를 먼저 제거해, 레시피표를 감싼 레이아웃 표가 오인돼 꿀팁까지
    지워지는 것을 막는다.
    """
    inner = table_html[table_html.find(">") + 1:]  # 바깥 <table ...> 태그 제거
    inner = _NESTED_TABLE.sub(" ", inner)  # 직계 셀만 남기기
    cells = [re.sub(r"(?s)<[^>]+>", " ", c).strip() for c in _CELL.findall(inner)]

    # 헤더는 '짧은 헤더 셀'일 때만 인정한다. 긴 산문 셀에 '원료'·'양'이 부분문자열로
    # 들어간 경우(예: "자연화장품원료", "많은 양을 사용")를 재료표로 오인하지 않도록.
    def _hdr(words: tuple[str, ...]) -> bool:
        return any(c == w or (len(c) <= 6 and w in c)
                   for c in cells for w in words)

    has_ing = _hdr(("재료", "원료", "재료종류", "재료명", "원료명"))
    has_amt_hdr = _hdr(("용량", "양", "총양", "총량"))
    amt_cells = sum(1 for c in cells if _AMOUNT_CELL.match(c))
    return has_ing and (has_amt_hdr or amt_cells >= 2)


def extract_detail(branduid: str) -> dict | None:
    """상세페이지 → {branduid, url, text, images:[url,...]} 또는 None.

    text = 요약+꿀팁+제조과정(재료표 제외). images = 캡처/설명 이미지 URL(절대경로).
    """
    url = f"{BASE}/shop/shopdetail.html?branduid={branduid}"
    h = fetch_html(url)
    m = _PAGE01.search(h)
    if not m:
        return None
    blk = m.group(1)

    # 1) 판매자 편집영역만: [OPENEDITOR] 뒤 → 상단 탭 네비 자동 제거.
    oe = _OPENEDITOR.search(blk)
    body = blk[oe.end():] if oe else blk

    # 2) 종료 신호 이후(안내문·품질배너) 잘라내기.
    cut = len(body)
    for term in _TEXT_TERMINATORS:
        i = body.find(term)
        if i != -1:
            cut = min(cut, i)
    body = body[:cut]

    # 3) 이미지 URL 수집(절대경로화, 보일러플레이트 제외).
    images: list[str] = []
    for src in _IMG_SRC.findall(body):
        absu = urljoin(url, src.strip())
        if any(s in absu.lower() for s in _IMG_SKIP):
            continue
        if absu not in images:
            images.append(absu)

    # 4) 재료표만 잘라내고 텍스트화(만들기 표·꿀팁은 남긴다).
    #    balanced span으로 각 <table>을 잡아, '직계 헤더가 재료표'인 것만 공백 처리.
    #    단, 재료표를 감싼 '바깥 레이아웃 표'도 직계 헤더가 재료표로 오인될 수 있다
    #    (그 안엔 만들기·꿀팁 표가 함께 중첩됨). 그래서 recipe로 판정된 span 중
    #    '다른 recipe span을 포함하는 wrapper'는 건너뛰고, 가장 안쪽 재료표만 지운다.
    recipe_spans = [(s, e) for s, e in _table_spans(body)
                    if _is_recipe_table(body[s:e])]
    innermost = [(s, e) for s, e in recipe_spans
                 if not any(s <= s2 and e2 <= e and (s, e) != (s2, e2)
                            for s2, e2 in recipe_spans)]
    chars = list(body)
    for s, e in innermost:
        for k in range(s, e):
            chars[k] = " "
    text = _text("".join(chars))

    if not text and not images:
        return None
    return {"branduid": branduid, "url": url, "text": text, "images": images}


def download_images(images: list[str], out_dir: Path, delay: float = 0.3) -> list[Path]:
    """이미지들을 out_dir에 저장하고 로컬 경로 목록 반환(실패분은 건너뜀)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for i, u in enumerate(images, 1):
        ext = Path(urlsplit(u).path).suffix or ".jpg"
        dst = out_dir / f"{i:02d}{ext}"
        if not dst.exists():
            try:
                dst.write_bytes(fetch_bytes(u))
            except Exception as e:  # 개별 이미지 실패는 무시
                print(f"    ⚠ 이미지 실패 {u}: {e}", file=sys.stderr)
                continue
            time.sleep(delay)
        saved.append(dst)
    return saved


# ── branduid 목록: 엑셀 '링크' 열에서 추출 ────────────────────────────────
_BRANDUID = re.compile(r"branduid=(\d+)")


def branduids_from_xlsx(xlsx: Path, link_col: str = "링크",
                        sheet: str | None = None) -> list[str]:
    """엑셀의 링크 열(제품 첫 행에만 존재)에서 branduid를 순서대로 뽑는다."""
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        sys.exit("openpyxl이 필요합니다:  uv add openpyxl  (또는 uv run --with openpyxl ...)")
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(c) if c is not None else "" for c in next(rows)]
    ci = header.index(link_col)
    ids: list[str] = []
    for row in rows:
        val = row[ci]
        if not val:
            continue
        mm = _BRANDUID.search(str(val))
        if mm and mm.group(1) not in ids:
            ids.append(mm.group(1))
    return ids


# '만들기 과정' 분리: 제목행(…만들기 / 만들기과정) 또는 첫 번호단계(1. / 1-4. / 1))부터.
_MAKING_HEAD = re.compile(r"(만들기\s*과정|만들기)\s*$")
_STEP_LINE = re.compile(r"^\s*\d+\s*([.)]|[-~]\s*\d)")


def split_making(text: str) -> tuple[str, str]:
    """상세내용 텍스트 → (설명·꿀팁, 만들기과정). 만들기 없으면 (원문, '').

    우선순위: '…만들기'/'만들기과정' 제목행 → 없으면 첫 번호단계(1./1-4./1)) 행.
    그 지점부터 끝까지를 만들기로 본다(하위 제목·색상 캡션 포함).
    """
    lines = text.split("\n")
    idx = None
    for i, l in enumerate(lines):
        if _MAKING_HEAD.search(l.strip()):
            idx = i
            break
    if idx is None:
        for i, l in enumerate(lines):
            if _STEP_LINE.match(l.strip()):
                idx = i
                break
    if idx is None:
        return text.strip(), ""
    return "\n".join(lines[:idx]).strip(), "\n".join(lines[idx:]).strip()


def build_glossary(xlsx: Path, out: Path | None = None, *,
                   link_col: str = "링크", sheet: str | None = None) -> Path:
    """마스터 → 원료 사전(중복 제거). 원료별 역할·대표특징·대표%·대체재·등장수.

    같은 원료가 여러 제품에 반복되므로 '원료 단위'로 접어 학습용 색인을 만든다.
    - 역할 = classify_role 최빈값, 대표특징 = tidy 후 최빈 문구
    - 대표% = 각 제품 내 비율(그램 환산)들의 중앙값, 대체재 = 합집합
    역할(ROLE_ORDER)→등장수 순 정렬, 역할 색상. 순수 데이터 기반(창작 없음).
    """
    import openpyxl
    from collections import Counter, defaultdict
    from statistics import median
    from openpyxl.styles import Alignment, Font, PatternFill, Side, Border
    from openpyxl.utils import get_column_letter

    wb = openpyxl.load_workbook(xlsx)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    header = [c.value for c in ws[1]]
    idx = {n: header.index(n) for n in header}
    rows = [[c.value for c in row] for row in ws.iter_rows(min_row=2)]

    def _norm(s):  # 중복키: 괄호/슬래시 뒤 제거 + 공백 무시(표기 변형 병합).
        return re.sub(r"\s+", "", re.sub(r"\s*[\(/].*$", "", str(s or "")))

    # 제품 그룹핑 → 그룹별 총 그램으로 각 원료 % 산출.
    groups, cur = [], None
    for row in rows:
        lk = row[idx[link_col]] if idx[link_col] < len(row) else None
        if lk and _BRANDUID.search(str(lk)):
            cur = [row]
            groups.append(cur)
        elif cur is not None:
            cur.append(row)

    cnt = Counter()
    roles = defaultdict(Counter)
    feats = defaultdict(Counter)
    alts = defaultdict(set)
    pcts = defaultdict(list)
    raw_names = {}
    for g in groups:
        parsed = []
        for row in g:
            nm = row[idx["재료"]] if idx["재료"] < len(row) else None
            if not nm:
                continue
            key = _norm(nm)
            if not key:
                continue
            raw_names.setdefault(key, str(nm))
            amt = row[idx["용량"]] if "용량" in idx else None
            feat = row[idx["특징"]] if "특징" in idx else None
            alt = row[idx["대체재료"]] if "대체재료" in idx else None
            grams = amount_to_g(amt)
            cnt[key] += 1
            roles[key][classify_role(str(nm), str(feat or ""))] += 1
            tf = tidy_feature(feat)
            if tf:
                feats[key][tf] += 1
            ta = tidy_feature(alt)
            if ta:
                alts[key].add(ta)
            parsed.append((key, grams))
        tot = sum(x[1] for x in parsed if x[1]) or 0
        if tot:
            for key, grams in parsed:
                if grams:
                    pcts[key].append(grams / tot * 100)

    order = {role: i for i, role in enumerate(ROLE_ORDER)}
    items = sorted(cnt, key=lambda k: (order.get(roles[k].most_common(1)[0][0], 99),
                                       -cnt[k]))

    gwb = openpyxl.Workbook()
    gs = gwb.active
    gs.title = "원료사전"
    cols = ["역할", "원료", "등장수", "대표 사용%", "대표 특징", "대체재(모음)"]
    widths = [8, 24, 7, 9, 46, 40]
    for i, (c, w) in enumerate(zip(cols, widths), 1):
        cell = gs.cell(1, i, c)
        cell.font = Font(bold=True, size=10)
        cell.fill = PatternFill("solid", fgColor="E8EEF7")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        gs.column_dimensions[get_column_letter(i)].width = w
    role_fill = {r: PatternFill("solid", fgColor=ROLE_COLORS[r]) for r in ROLE_ORDER}
    wrap = Alignment(wrap_text=True, vertical="top")
    thin = Side(style="thin", color="D8DCE3")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    r = 2
    for key in items:
        role = roles[key].most_common(1)[0][0]
        pv = f"{round(median(pcts[key]))}%" if pcts.get(key) else ""
        feat = feats[key].most_common(1)[0][0] if feats.get(key) else ""
        alt = " · ".join(sorted(a for a in alts[key] if a))[:300]
        vals = [role, raw_names.get(key, key), cnt[key], pv, feat, alt]
        for ci, v in enumerate(vals, 1):
            cc = gs.cell(r, ci, v)
            cc.alignment = wrap
            cc.border = border
        gs.cell(r, 1).fill = role_fill.get(role, role_fill["기타"])
        gs.cell(r, 1).alignment = Alignment(horizontal="center", vertical="top")
        gs.cell(r, 3).alignment = Alignment(horizontal="center", vertical="top")
        gs.cell(r, 4).alignment = Alignment(horizontal="center", vertical="top")
        n = 1
        for ci in (5, 6):
            v = vals[ci - 1]
            if v:
                n = max(n, -(-sum(2 if ord(c) > 0x2000 else 1
                                  for c in str(v)) // (widths[ci - 1] - 1)))
        gs.row_dimensions[r].height = min(160, max(15, n * 15))
        r += 1
    gs.freeze_panes = "A2"
    gs.auto_filter.ref = f"A1:F{r - 1}"
    out = out or xlsx.with_name("원료_사전.xlsx")
    gwb.save(out)
    print(f"원료 사전 → {out.name}: 고유 원료 {len(items)}종", file=sys.stderr)
    return out


def enrich_glossary(glossary: Path, master: Path, *,
                    cards_dir: Path = Path("카드_아키타입"),
                    link_col: str = "링크") -> Path:
    """원료 사전에 '사용% 범위'·'주 사용 제형' 열을 추가(기존 특징 편집은 보존).

    - 사용% 범위 = 각 제품 내 비율(그램 환산)들의 최소~중앙~최대 → '같은 원료가
      비율/제형 따라 다르게 발현'을 실데이터로 보여줌.
    - 주 사용 제형 = 카드 파일(아키타입)에서 그 원료가 등장하는 제형 집합.
    원료 매칭은 공백·괄호 무시 정규화 키. 기존 열(특징 등)은 손대지 않는다.
    """
    import openpyxl
    from collections import defaultdict
    from statistics import median

    def _norm(s):
        return re.sub(r"\s+", "", re.sub(r"\s*[\(/].*$", "", str(s or "")))

    # 1) 마스터에서 원료별 사용% 수집.
    mwb = openpyxl.load_workbook(master, read_only=True)
    mws = mwb.worksheets[0]
    mh = [c.value for c in next(mws.iter_rows(min_row=1, max_row=1))]
    mi = {n: mh.index(n) for n in mh}
    groups, cur = [], None
    for row in mws.iter_rows(min_row=2, values_only=True):
        lk = row[mi[link_col]] if mi[link_col] < len(row) else None
        if lk and _BRANDUID.search(str(lk)):
            cur = [row]
            groups.append(cur)
        elif cur is not None:
            cur.append(row)
    pcts = defaultdict(list)
    for g in groups:
        parsed = [(_norm(x[mi["재료"]]), amount_to_g(x[mi["용량"]]))
                  for x in g if x[mi["재료"]]]
        tot = sum(gr for _, gr in parsed if gr) or 0
        if tot:
            for k, gr in parsed:
                if gr:
                    pcts[k].append(gr / tot * 100)

    # 2) 카드 파일에서 원료→제형(아키타입) 집합. 역할 열(4열)이 ROLE이면 재료행.
    roleset = set(ROLE_ORDER)
    arche_of = defaultdict(set)
    for f in sorted(cards_dir.glob("*.xlsx")):
        if f.name.startswith("~$"):
            continue
        a = re.sub(r"^\d+_", "", f.stem)
        cw = openpyxl.load_workbook(f, read_only=True).worksheets[0]
        for row in cw.iter_rows(min_row=2, values_only=True):
            if len(row) >= 4 and row[3] in roleset and row[0]:
                arche_of[_norm(row[0])].add(a)

    # 3) 사전에 열 추가(기존 보존). 원료 = B열(2).
    gwb = openpyxl.load_workbook(glossary)
    gs = gwb.worksheets[0]
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    ncol = gs.max_column
    c1, c2 = ncol + 1, ncol + 2
    for col, title, w in ((c1, "사용% 범위(최소~중앙~최대)", 18), (c2, "주 사용 제형", 34)):
        hc = gs.cell(1, col, title)
        hc.font = Font(bold=True, size=10)
        hc.fill = PatternFill("solid", fgColor="E8EEF7")
        hc.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        gs.column_dimensions[get_column_letter(col)].width = w
    wrap = Alignment(wrap_text=True, vertical="top")
    for r in range(2, gs.max_row + 1):
        key = _norm(gs.cell(r, 2).value)
        v = pcts.get(key)
        if v:
            gs.cell(r, c1, f"{min(v):.0f} ~ {median(v):.0f} ~ {max(v):.0f}%")
        gs.cell(r, c1).alignment = Alignment(horizontal="center", vertical="top")
        arches = arche_of.get(key)
        if arches:
            gs.cell(r, c2, " · ".join(sorted(arches)))
        gs.cell(r, c2).alignment = wrap
    gwb.save(glossary)
    print(f"원료 사전 보강 → {glossary.name}: 사용%·제형 열 추가(특징 보존)",
          file=sys.stderr)
    return glossary


def restructure_master(xlsx: Path, out: Path | None = None, *,
                       sheet: str | None = None) -> Path:
    """마스터에 '만들기' 열을 추가(상세내용에서 분리)하고 '링크'를 맨 끝으로 옮긴다.

    새 열 순서: 제품명·분류·재료·용량·특징·대체재료·상세내용·만들기·이미지·링크.
    """
    import openpyxl
    wb = openpyxl.load_workbook(xlsx)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    header = [c.value for c in ws[1]]
    idx = {name: header.index(name) for name in header}
    # 목표 열 순서(존재하는 것만).
    order = ["제품명", "분류", "재료", "용량", "특징", "대체재료",
             "상세내용", "만들기", "이미지", "링크"]
    ti = idx["상세내용"]

    new_wb = openpyxl.Workbook()
    dst = new_wb.active
    dst.title = ws.title
    dst.append(order)
    for row in ws.iter_rows(min_row=2, values_only=True):
        detail, making = "", ""
        if row[ti]:
            detail, making = split_making(str(row[ti]))
        get = lambda name: (row[idx[name]] if name in idx else None)  # noqa: E731
        out_row = []
        for name in order:
            if name == "상세내용":
                out_row.append(detail if row[ti] else get("상세내용"))
            elif name == "만들기":
                out_row.append(making)
            else:
                out_row.append(get(name))
        dst.append(out_row)
    out = out or xlsx
    new_wb.save(out)
    print(f"마스터 재구성 → {out.name} (열: {' · '.join(order)})", file=sys.stderr)
    return out


def split_by_products(xlsx: Path, per_file: int = 100, *, link_col: str = "링크",
                      sheet: str | None = None,
                      out_stem: str | None = None) -> list[Path]:
    """상세 엑셀을 '제품 단위'로 per_file개씩 여러 파일로 나눈다(썸네일 삽입 전 데이터).

    제품 = 링크 있는 행 + 그 뒤 링크 없는 재료 행들. 제품을 절대 쪼개지 않는다.
    반환: 생성된 파일 경로 목록(각각 헤더 포함, 상세내용·이미지 열 포함).
    """
    import openpyxl
    src = openpyxl.load_workbook(xlsx)
    ws = src[sheet] if sheet else src.worksheets[0]
    header = [c.value for c in ws[1]]
    link_i = header.index(link_col)
    all_rows = [[c.value for c in row] for row in ws.iter_rows(min_row=2)]

    # 제품 그룹핑: 링크 있는 행에서 새 제품 시작.
    groups: list[list[list]] = []
    for row in all_rows:
        link = row[link_i] if link_i < len(row) else None
        if link and _BRANDUID.search(str(link)):
            groups.append([row])
        elif groups:
            groups[-1].append(row)
        else:
            groups.append([row])  # 첫 제품 앞 잔여 행(있으면) 보호

    stem = out_stem or (Path(xlsx).stem)
    parent = Path(xlsx).parent
    n_files = -(-len(groups) // per_file)  # ceil
    outs: list[Path] = []
    for fi in range(n_files):
        chunk = groups[fi * per_file:(fi + 1) * per_file]
        wb = openpyxl.Workbook()
        dst = wb.active
        dst.title = ws.title
        dst.append(header)
        for g in chunk:
            for row in g:
                dst.append(row)
        text_col = header.index("상세내용") + 1
        img_col = header.index("이미지") + 1
        _format_detail_columns(dst, text_col, img_col)
        out = parent / f"{stem}_p{fi + 1}of{n_files}.xlsx"
        wb.save(out)
        outs.append(out)
        print(f"  파일 {fi + 1}/{n_files}: 제품 {len(chunk)}개 → {out.name}",
              file=sys.stderr)
    return outs


def write_back_xlsx(xlsx: Path, details: dict[str, dict], out: Path,
                    link_col: str = "링크", sheet: str | None = None) -> None:
    """제품 첫 행(링크 있는 행)에 '상세내용'·'이미지' 열을 채워 새 파일로 저장."""
    import openpyxl
    wb = openpyxl.load_workbook(xlsx)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    """제품 첫 행(링크 있는 행)에 '상세내용'·'이미지' 열을 채워 새 파일로 저장."""
    import openpyxl
    wb = openpyxl.load_workbook(xlsx)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    header = [c.value for c in ws[1]]
    link_i = header.index(link_col) + 1
    # 새 열 추가(있으면 재사용).
    def ensure_col(name: str) -> int:
        if name in header:
            return header.index(name) + 1
        col = ws.max_column + 1
        ws.cell(row=1, column=col, value=name)
        header.append(name)
        return col
    text_col = ensure_col("상세내용")
    img_col = ensure_col("이미지")
    for r in range(2, ws.max_row + 1):
        link = ws.cell(row=r, column=link_i).value
        if not link:
            continue
        mm = _BRANDUID.search(str(link))
        if not mm:
            continue
        d = details.get(mm.group(1))
        if not d:
            continue
        ws.cell(row=r, column=text_col, value=d.get("text", ""))
        ws.cell(row=r, column=img_col, value="\n".join(str(p) for p in d.get("saved", [])))
    _format_detail_columns(ws, text_col, img_col)
    wb.save(out)


def _format_detail_columns(ws, text_col: int, img_col: int,
                           text_width: int = 42, img_width: int = 38) -> None:
    """상세내용·이미지 열을 '줄바꿈+위 정렬'로, 내용에 맞춰 행 높이를 늘린다.

    엑셀은 wrap만으론 행 높이를 자동으로 키우지 않아, 표시 줄 수를 어림해
    행 높이를 직접 지정한다(과도한 높이는 상한으로 제한).
    """
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Alignment
    wrap_top = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions[get_column_letter(text_col)].width = text_width
    ws.column_dimensions[get_column_letter(img_col)].width = img_width

    def visual_lines(val: str, width: int) -> int:
        if not val:
            return 1
        lines = 0
        for ln in str(val).split("\n"):
            # 한글은 폭이 넓어 대략 2칸으로 계산.
            w = sum(2 if ord(c) > 0x2000 else 1 for c in ln)
            lines += max(1, -(-w // width))  # ceil
        return lines

    for r in range(2, ws.max_row + 1):
        tc = ws.cell(row=r, column=text_col)
        ic = ws.cell(row=r, column=img_col)
        tc.alignment = wrap_top
        ic.alignment = wrap_top
        if tc.value or ic.value:
            n = max(visual_lines(tc.value, text_width),
                    visual_lines(ic.value, img_width))
            ws.row_dimensions[r].height = min(600, max(15, n * 15))


def embed_thumbnails(xlsx: Path, out: Path | None = None, *,
                     img_col_name: str = "이미지", sheet: str | None = None,
                     thumb_px: int = 110, per_row: int = 4, gap_px: int = 4,
                     thumb_dir: Path = Path("cards/detail_img/_thumbs")) -> Path:
    """이미지 열의 경로들을 작은 썸네일로 줄여 각 셀에 격자로 박아 넣는다.

    - 원본은 그대로 두고 <파일>_썸네일.xlsx(또는 out)로 저장.
    - 셀당 가로 per_row개씩 줄바꿈(격자). 파일 비대·속도는 감수(사용자 선택).
    - 썸네일은 thumb_dir에 캐시(재실행 시 재사용).
    """
    import openpyxl
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.drawing.spreadsheet_drawing import (
        AnchorMarker, OneCellAnchor)
    from openpyxl.drawing.xdr import XDRPositiveSize2D
    from openpyxl.utils import get_column_letter
    from openpyxl.utils.units import pixels_to_EMU
    from PIL import Image as PILImage

    wb = openpyxl.load_workbook(xlsx)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    header = [c.value for c in ws[1]]
    img_ci = header.index(img_col_name)  # 0-based
    thumb_dir.mkdir(parents=True, exist_ok=True)
    box = thumb_px + gap_px
    xbase = get_column_letter(img_ci + 1)
    total = 0

    for r in range(2, ws.max_row + 1):
        cell = ws.cell(row=r, column=img_ci + 1)
        val = cell.value
        if not val:
            continue
        paths = [p.strip() for p in str(val).splitlines() if p.strip()]
        if not paths:
            continue
        cell.value = None  # 경로 텍스트 제거(썸네일로 대체)
        placed = 0
        for k, p in enumerate(paths):
            src = Path(p)
            if not src.exists():
                continue
            # 썸네일 생성/캐시
            tpath = thumb_dir / (src.parent.name + "_" + src.name)
            if not tpath.exists():
                try:
                    im = PILImage.open(src)
                    im.thumbnail((thumb_px, thumb_px))
                    im.convert("RGB").save(tpath, "JPEG", quality=70)
                except Exception as e:
                    print(f"    ⚠ 썸네일 실패 {src}: {e}", file=sys.stderr)
                    continue
            xi = XLImage(str(tpath))
            col_off = (placed % per_row) * box
            row_off = (placed // per_row) * box
            marker = AnchorMarker(col=img_ci, colOff=pixels_to_EMU(col_off),
                                  row=r - 1, rowOff=pixels_to_EMU(row_off))
            size = XDRPositiveSize2D(pixels_to_EMU(xi.width),
                                     pixels_to_EMU(xi.height))
            xi.anchor = OneCellAnchor(_from=marker, ext=size)
            ws.add_image(xi)
            placed += 1
            total += 1
        # 행 높이·열 너비를 격자에 맞춤
        if placed:
            rows_of = -(-placed // per_row)  # ceil
            need_h_pt = rows_of * box * 0.75
            cur = ws.row_dimensions[r].height or 15
            ws.row_dimensions[r].height = max(cur, need_h_pt)
    # 이미지 열 너비를 격자 폭에 맞춤(px→엑셀문자폭 근사).
    ws.column_dimensions[xbase].width = max(
        ws.column_dimensions[xbase].width or 8, per_row * box / 7)

    out = out or xlsx.with_name(xlsx.stem + "_썸네일.xlsx")
    wb.save(out)
    print(f"썸네일 {total}장 삽입 → {out}", file=sys.stderr)
    return out


def finalize_merged(xlsx: Path, out: Path | None = None, *,
                    link_col: str = "링크", sheet: str | None = None,
                    thumb_px: int = 110, res_px: int = 900,
                    per_row: int = 4, gap_px: int = 4,
                    text_width: int = 42,
                    thumb_dir: Path = Path("cards/detail_img/_thumbs")) -> Path:
    """제품 단위로 상세내용·이미지를 '세로 병합'하고 썸네일을 격자로 박는다.

    - 상세내용·이미지 칸을 제품의 재료 행들에 걸쳐 병합 → 긴 텍스트/썸네일 높이가
      제품 전체 행에 분산돼, 첫 행만 비대해지는 여백 문제를 없앤다.
    - 제품별 배경 밴드(줄무늬)·제품명 굵게·상단 구분선으로 제품 경계를 뚜렷이.
    - 썸네일은 첫 행 기준 절대 오프셋으로 앵커링(행 높이와 무관하게 위치 정확).
    - 해상도(`res_px`)와 표시 크기(`thumb_px`)를 분리: 썸네일은 롱사이드 res_px로
      박되 격자엔 thumb_px로 작게 표시 → 엑셀에서 늘리면 res_px까지 선명(큰
      통이미지 가독성 확보). 원본이 작으면 확대하지 않는다.
    """
    import openpyxl
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
    from openpyxl.drawing.xdr import XDRPositiveSize2D
    from openpyxl.utils import get_column_letter
    from openpyxl.utils.units import pixels_to_EMU
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from PIL import Image as PILImage

    wb = openpyxl.load_workbook(xlsx)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    header = [c.value for c in ws[1]]
    link_i = header.index(link_col) + 1
    text_col = header.index("상세내용") + 1
    make_col = header.index("만들기") + 1 if "만들기" in header else None
    img_col = header.index("이미지") + 1
    ncol = ws.max_column
    box = thumb_px + gap_px
    thumb_dir.mkdir(parents=True, exist_ok=True)

    # 제품 그룹 경계(링크 있는 행에서 시작) → (start_row, end_row).
    starts = [r for r in range(2, ws.max_row + 1)
              if ws.cell(r, link_i).value
              and _BRANDUID.search(str(ws.cell(r, link_i).value))]
    if not starts or starts[0] != 2:
        starts = [2] + starts
    bounds = [(s, (starts[i + 1] - 1 if i + 1 < len(starts) else ws.max_row))
              for i, s in enumerate(starts)]

    wrap_top = Alignment(wrap_text=True, vertical="top", horizontal="left")
    band_fill = PatternFill("solid", fgColor="EFF4FB")  # 옅은 파랑(짝수 제품)
    top_side = Side(style="thin", color="B0B8C4")
    total = 0
    for gi, (s, e) in enumerate(bounds):
        n = e - s + 1
        # 1) 상세내용·만들기·이미지 세로 병합(제품 전체 행).
        merge_cols = [text_col, img_col] + ([make_col] if make_col else [])
        if n > 1:
            for mc in merge_cols:
                ws.merge_cells(start_row=s, start_column=mc,
                               end_row=e, end_column=mc)
        tcell = ws.cell(s, text_col)
        tcell.alignment = wrap_top
        ws.cell(s, img_col).alignment = wrap_top
        mcell = ws.cell(s, make_col) if make_col else None
        if mcell is not None:
            mcell.alignment = wrap_top

        # 2) 썸네일 삽입(첫 행 기준 절대 오프셋 격자).
        paths = [p.strip() for p in str(ws.cell(s, img_col).value or "").splitlines()
                 if p.strip()]
        ws.cell(s, img_col).value = None
        placed = 0
        for p in paths:
            src = Path(p)
            if not src.exists():
                continue
            # 캐시 파일명에 해상도 태그 → 옛 110px 캐시와 충돌 방지.
            tpath = thumb_dir / f"{src.parent.name}_{src.stem}_r{res_px}.jpg"
            if not tpath.exists():
                try:
                    im = PILImage.open(src)
                    im.thumbnail((res_px, res_px))  # 롱사이드 res_px로 박기
                    im.convert("RGB").save(tpath, "JPEG", quality=75)
                except Exception as ex:
                    print(f"    ⚠ 썸네일 실패 {src}: {ex}", file=sys.stderr)
                    continue
            xi = XLImage(str(tpath))
            # 표시 크기는 롱사이드 thumb_px로 축소(비율 유지). 내부 데이터는 res_px라
            # 엑셀에서 늘리면 선명. 원본이 thumb_px보다 작으면 그대로 표시.
            scale = min(1.0, thumb_px / max(xi.width, xi.height))
            disp_w = max(1, round(xi.width * scale))
            disp_h = max(1, round(xi.height * scale))
            marker = AnchorMarker(col=img_col - 1,
                                  colOff=pixels_to_EMU((placed % per_row) * box),
                                  row=s - 1,
                                  rowOff=pixels_to_EMU((placed // per_row) * box))
            xi.anchor = OneCellAnchor(_from=marker, ext=XDRPositiveSize2D(
                pixels_to_EMU(disp_w), pixels_to_EMU(disp_h)))
            ws.add_image(xi)
            placed += 1
            total += 1

        # 3) 필요한 총 높이 = max(상세내용/만들기 줄, 썸네일 격자, 최소행). N행에 분산.
        def _lines(txt: str) -> int:
            c = 0
            for ln in str(txt or "").split("\n"):
                w = sum(2 if ord(ch) > 0x2000 else 1 for ch in ln)
                c += max(1, -(-w // text_width))
            return c
        text_h = _lines(tcell.value) * 15
        make_h = _lines(mcell.value) * 15 if mcell is not None else 0
        thumb_h = -(-placed // per_row) * box * 0.75 if placed else 0
        need = max(text_h, make_h, thumb_h, n * 16)
        per = min(409, max(16, need / n))  # 엑셀 행 높이 상한 409pt
        for r in range(s, e + 1):
            ws.row_dimensions[r].height = per

        # 4) 제품 밴드·구분선·제품명 굵게.
        for r in range(s, e + 1):
            for c in range(1, ncol + 1):
                cell = ws.cell(r, c)
                if gi % 2 == 1:
                    cell.fill = band_fill
                if r == s:
                    cell.border = Border(top=top_side)
        name_cell = ws.cell(s, 1)
        name_cell.font = Font(bold=True)
        name_cell.alignment = Alignment(vertical="top", wrap_text=True)

    # 열 너비.
    ws.column_dimensions[get_column_letter(text_col)].width = text_width
    if make_col:
        ws.column_dimensions[get_column_letter(make_col)].width = text_width
    ws.column_dimensions[get_column_letter(img_col)].width = per_row * box / 7
    ws.freeze_panes = "A2"  # 헤더 고정(스크롤 편의)

    out = out or xlsx.with_name(xlsx.stem + "_썸네일.xlsx")
    wb.save(out)
    print(f"  {out.name}: 제품 {len(bounds)}개 · 썸네일 {total}장", file=sys.stderr)
    return out


def finalize_cards(xlsx: Path, out: Path | None = None, *,
                   link_col: str = "링크", sheet: str | None = None,
                   thumb_px: int = 110, res_px: int = 900,
                   per_row: int | None = None, gap_px: int = 4,
                   img_px: int = 190, img_per_row: int = 4,
                   img_big_px: int = 540, big_thresh: int = 600,
                   thumb_dir: Path = Path("cards/detail_img/_thumbs")) -> Path:
    """제품 = '카드'. 재료·용량은 좁은 미니표로 두고, 상세내용·만들기·이미지는
    제품 아래에 '전폭(A:D 병합) 1블록'으로 내려 넣는다(세로병합 대안).

    finalize_merged와 달리 상세내용/만들기를 좁은 옆 컬럼에 세로병합하지 않아,
    긴 산문이 표 전체 너비를 써서 줄바꿈·행높이 뻥튀기가 사라진다. 새 시트를
    처음부터 다시 쓰는 방식이라 정렬/자동필터는 없어진다(읽기용 리포트 지향).

    제품 블록 구조:
        [제품명  [분류]]                  ← 헤더(굵게, 상단 굵은선)
        재료 | 용량 | 특징 | 대체재료       ← 미니표 헤더
        (재료 행들…)
        — 상세내용 —                      ← 라벨
        (전폭 본문)
        — 만들기 —
        (전폭 본문)
        — 이미지 —
        (전폭 썸네일 격자)
    """
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.drawing.spreadsheet_drawing import AbsoluteAnchor
    from openpyxl.drawing.xdr import XDRPoint2D, XDRPositiveSize2D
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.utils.units import pixels_to_EMU
    from PIL import Image as PILImage

    COLS = ["재료", "용량", "%", "역할", "특징", "대체재료"]   # 미니표(공부용 6열)
    WIDTHS = {1: 18, 2: 9, 3: 6, 4: 9, 5: 30, 6: 18}        # 열 너비(문자폭)
    NC = len(COLS)
    full_chars = sum(WIDTHS.values())               # 전폭 밴드 줄바꿈 기준(≈90)

    src = openpyxl.load_workbook(xlsx)
    ws = src[sheet] if sheet else src.worksheets[0]
    header = [c.value for c in ws[1]]
    idx = {name: header.index(name) for name in header}
    link_i = idx[link_col]
    rows = [[c.value for c in row] for row in ws.iter_rows(min_row=2)]

    # 제품 그룹핑(링크 있는 행에서 새 제품 시작) — split_by_products와 동일 규칙.
    groups: list[list[list]] = []
    for row in rows:
        link = row[link_i] if link_i < len(row) else None
        if link and _BRANDUID.search(str(link)):
            groups.append([row])
        elif groups:
            groups[-1].append(row)
        else:
            groups.append([row])

    wb = Workbook()
    dst = wb.active
    dst.title = ws.title
    for ci, w in WIDTHS.items():
        dst.column_dimensions[get_column_letter(ci)].width = w

    box = thumb_px + gap_px
    total_px = int(full_chars * 7)                  # 전폭 픽셀 근사
    if per_row is None:
        per_row = max(1, total_px // box)
    # 이미지는 텍스트(A:D) 오른쪽 패널에 큼직하게. E열은 여백, 그 오른쪽부터 격자.
    #    Mac 엑셀은 OneCellAnchor의 큰 colOff/rowOff를 셀 크기로 클램프해 이미지가
    #    한 자리에 겹쳐버린다. 그래서 '절대좌표(AbsoluteAnchor)'로 박는다.
    IMG_BOX = img_px + gap_px
    GUTTER = 3                                       # E 여백열 너비(문자)
    dst.column_dimensions[get_column_letter(NC + 1)].width = GUTTER

    # 열 너비(문자)→픽셀은 폰트/OS(특히 Mac 엑셀)마다 달라 과소추정하면 이미지가
    # D열을 덮는다. 넉넉히 과대추정(8px/char + 여유)해서 D를 확실히 비켜가게 한다.
    def _col_px(w_chars: float) -> int:
        return round(w_chars * 8) + 8
    img_x0_px = (sum(_col_px(WIDTHS[c]) for c in range(1, NC + 1))
                 + _col_px(GUTTER) + 24)             # A~D + E여백 + 마진
    thumb_dir.mkdir(parents=True, exist_ok=True)

    wrap_top = Alignment(wrap_text=True, vertical="top", horizontal="left")
    thin = Side(style="thin", color="D0D5DD")
    grid = Border(left=thin, right=thin, top=thin, bottom=thin)
    thick = Side(style="medium", color="8A94A6")
    name_fill = PatternFill("solid", fgColor="E8EEF7")   # 제품 헤더
    label_fill = PatternFill("solid", fgColor="F2F4F7")  # 미니표헤더·밴드라벨
    band_fill = PatternFill("solid", fgColor="F7FAFF")   # 짝수 제품 줄무늬

    def _lines(val, width: int) -> int:
        if val is None or str(val) == "":
            return 1
        n = 0
        for ln in str(val).split("\n"):
            w = sum(2 if ord(c) > 0x2000 else 1 for c in ln)
            n += max(1, -(-w // width))  # ceil
        return n

    def _fill_row(r: int, fill) -> None:
        for c in range(1, NC + 1):
            dst.cell(r, c).fill = fill

    def _wrap_chunks(text: str, width: int, max_lines: int = 24):
        """긴 본문을 '표시 줄 수 ≤ max_lines' 조각들로 나눈다(줄 경계 유지).

        엑셀 행 높이 상한(409pt) 때문에 한 셀에 다 넣으면 잘리므로, 여러 본문
        행으로 흘려 전체가 보이게 한다. 반환: [(조각텍스트, 표시줄수), ...].
        """
        out, cur, cur_v = [], [], 0
        for ln in text.split("\n"):
            w = sum(2 if ord(c) > 0x2000 else 1 for c in ln)
            v = max(1, -(-w // width))  # ceil
            if cur and cur_v + v > max_lines:
                out.append(("\n".join(cur), cur_v))
                cur, cur_v = [], 0
            cur.append(ln)
            cur_v += v
        if cur:
            out.append(("\n".join(cur), cur_v))
        return out or [("", 1)]

    from collections import Counter, defaultdict
    role_fill = {role: PatternFill("solid", fgColor=ROLE_COLORS[role])
                 for role in ROLE_ORDER}

    def _analyze(g):
        """그룹 → (ing_rows, role_pct).

        ing_rows = [(재료, 용량, '%'문자, 역할, 특징, 대체재료), ...]
        role_pct = {역할: 합계%} (그램 환산 가능한 원료 기준).
        """
        raw = []
        for row in g:
            name = row[idx["재료"]] if "재료" in idx and idx["재료"] < len(row) else None
            amt = row[idx["용량"]] if "용량" in idx and idx["용량"] < len(row) else None
            feat = row[idx["특징"]] if "특징" in idx and idx["특징"] < len(row) else None
            alt = row[idx["대체재료"]] if "대체재료" in idx and idx["대체재료"] < len(row) else None
            if not (name or amt):
                continue
            grams = amount_to_g(amt)
            role = classify_role(str(name or ""), str(feat or ""))
            raw.append((name, amt, grams, role, tidy_feature(feat), tidy_feature(alt)))
        tot = sum(x[2] for x in raw if x[2]) or 0
        ing_rows, role_pct = [], {}
        for name, amt, grams, role, feat, alt in raw:
            if grams and tot:
                p = grams / tot * 100
                pct = "<1%" if p < 0.5 else f"{round(p)}%"
                role_pct[role] = role_pct.get(role, 0.0) + p
            else:
                pct = ""
            ing_rows.append((name, amt, pct, role, feat, alt))
        return ing_rows, role_pct

    analyzed = [_analyze(g) for g in groups]

    # 아키타입 골격 집계: 역할별 % 분포(제품마다 1값) + 대표원료 빈도.
    role_series = defaultdict(list)
    ing_freq = Counter()
    for ing_rows, role_pct in analyzed:
        for role, p in role_pct.items():
            role_series[role].append(p)
        for name, *_ in ing_rows:
            key = re.sub(r"\s*[\(/].*$", "", str(name or "")).strip()
            if len(key) >= 2:
                ing_freq[key] += 1

    def _band(vals):
        """정렬된 %들의 대표 범위(p25~p75, 반올림)."""
        s = sorted(vals)
        lo = s[max(0, round((len(s) - 1) * 0.25))]
        hi = s[min(len(s) - 1, round((len(s) - 1) * 0.75))]
        return round(lo), round(hi)

    arche = re.sub(r"^\d+_", "", re.sub(r"^_tmp_", "", Path(xlsx).stem))
    n_prod = sum(1 for g in groups if any(
        (r[idx["재료"]] if "재료" in idx and idx["재료"] < len(r) else None) for r in g))
    summary_fill = PatternFill("solid", fgColor="FFF6DC")   # 옅은 노랑(요약)
    summary_key = PatternFill("solid", fgColor="FCEFBE")

    r = 1
    total_thumbs = 0

    # ── 0) 아키타입 골격 요약(파일 맨 위, 전폭) ─────────────────────────────
    def _summary_row(text, height, *, bold=False, fill=summary_fill, size=10,
                     color="3A3A3A"):
        nonlocal r
        dst.merge_cells(start_row=r, start_column=1, end_row=r, end_column=NC)
        c = dst.cell(r, 1, text)
        c.font = Font(bold=bold, size=size, color=color)
        c.alignment = Alignment(vertical="center", horizontal="left", wrap_text=True)
        for cc in range(1, NC + 1):
            dst.cell(r, cc).fill = fill
        dst.row_dimensions[r].height = height
        r += 1

    _summary_row(f"━  {arche} 골격 치트시트  (이 파일 {n_prod}종 기준)  ━",
                 20, bold=True, fill=summary_key, size=12, color="6B5900")
    def _rolelabel(role):
        lo, hi = _band(role_series[role])
        return f"{role} 소량" if hi == 0 else f"{role} {lo}~{hi}%"
    skel = " · ".join(_rolelabel(role) for role in ROLE_ORDER
                      if role in role_series and len(role_series[role]) >= 2)
    _summary_row("전형 구성(%):  " + (skel or "데이터 부족"),
                 max(16, _lines("전형 구성(%):  " + skel, full_chars) * 15))
    tops = " · ".join(f"{nm}×{c}" for nm, c in ing_freq.most_common(8))
    _summary_row("자주 쓰는 원료:  " + tops,
                 max(16, _lines("자주 쓰는 원료:  " + tops, full_chars) * 15))
    tips = ARCHETYPE_TIPS.get(arche)
    if tips:
        body = "⚠ 이 제형 배합 주의·기본원칙\n" + "\n".join(f"· {t}" for t in tips)
        _summary_row(body, max(28, _lines(body, full_chars) * 15),
                     fill=PatternFill("solid", fgColor="FDECE0"), color="7A4A2A")
    dst.row_dimensions[r].height = 6
    r += 1

    for gi, g in enumerate(groups):
        first = g[0]
        striped = gi % 2 == 1
        r0 = r  # 제품 블록 시작행(오른쪽 이미지 패널을 여기에 앵커)
        ing_rows, role_pct = analyzed[gi]

        def get(name, row=first):
            return row[idx[name]] if name in idx and idx[name] < len(row) else None

        # 1) 제품 헤더(A:D 병합, 굵게, 상단 굵은선). 원본 링크는 제품명에 하이퍼링크로.
        dst.merge_cells(start_row=r, start_column=1, end_row=r, end_column=NC)
        nm, cat = get("제품명") or "", get("분류") or ""
        link = get(link_col)
        title = f"{nm}    [{cat}]" if cat else str(nm)
        hc = dst.cell(r, 1, (title + "    ↗ 원본") if link else title)
        if link:
            hc.hyperlink = str(link)
            hc.font = Font(bold=True, size=12, color="1155CC", underline="single")
        else:
            hc.font = Font(bold=True, size=12)
        hc.alignment = Alignment(vertical="center", horizontal="left", wrap_text=True)
        for c in range(1, NC + 1):
            dst.cell(r, c).fill = name_fill
            dst.cell(r, c).border = Border(top=thick)
        dst.row_dimensions[r].height = 22
        r += 1

        # 2) 미니표 헤더(재료·용량·특징·대체재료).
        for ci, label in enumerate(COLS, start=1):
            cc = dst.cell(r, ci, label)
            cc.font = Font(bold=True, size=9)
            cc.fill = label_fill
            cc.alignment = Alignment(vertical="center", horizontal="center")
            cc.border = grid
        dst.row_dimensions[r].height = 15
        r += 1

        # 3) 재료 행들: 재료 | 용량 | % | 역할(색상) | 특징 | 대체재료.
        for name, amt, pct, role, feat, alt in ing_rows:
            vals = [name, amt, pct, role, feat, alt]
            maxln = 1
            for ci, v in enumerate(vals, start=1):
                cc = dst.cell(r, ci, v)
                cc.alignment = wrap_top
                cc.border = grid
                if striped:
                    cc.fill = band_fill
                # 실제 엑셀 줄바꿈이 추정보다 촘촘할 수 있어 폭을 1 줄여 여유를 준다.
                maxln = max(maxln, _lines(v, WIDTHS[ci] - 1))
            # %는 가운데, 역할 셀은 역할색으로 칠해 제형 골격이 한눈에.
            dst.cell(r, 3).alignment = Alignment(vertical="top", horizontal="center")
            rc = dst.cell(r, 4)
            rc.fill = role_fill.get(role, role_fill["기타"])
            rc.alignment = Alignment(vertical="top", horizontal="center")
            dst.row_dimensions[r].height = min(409, max(15, maxln * 16))
            r += 1

        # 3b) phase 합계 줄(전폭): 역할별 % 합.
        if role_pct:
            parts = " · ".join(f"{role} {round(role_pct[role])}"
                               for role in ROLE_ORDER if role in role_pct)
            dst.merge_cells(start_row=r, start_column=1, end_row=r, end_column=NC)
            pc = dst.cell(r, 1, "▶ phase 합계(%):  " + parts)
            pc.font = Font(bold=True, size=9, color="2A4A6B")
            pc.alignment = Alignment(vertical="center", horizontal="left")
            for cc in range(1, NC + 1):
                dst.cell(r, cc).fill = PatternFill("solid", fgColor="EEF3F8")
            dst.row_dimensions[r].height = 14
            r += 1

        # 4) 상세내용·만들기 밴드(라벨행 + 전폭 본문행).
        for label in ("상세내용", "만들기"):
            txt = get(label)
            if not txt or not str(txt).strip():
                continue
            dst.merge_cells(start_row=r, start_column=1, end_row=r, end_column=NC)
            lc = dst.cell(r, 1, f"— {label} —")
            lc.font = Font(bold=True, size=9, color="55606E")
            lc.alignment = Alignment(vertical="center", horizontal="left")
            _fill_row(r, label_fill)
            dst.row_dimensions[r].height = 14
            r += 1
            # 본문: 409pt를 넘으면 잘리므로 여러 전폭 행으로 나눠 흘린다.
            for chunk, vlines in _wrap_chunks(str(txt).strip(), full_chars, 24):
                dst.merge_cells(start_row=r, start_column=1, end_row=r, end_column=NC)
                bc = dst.cell(r, 1, chunk)
                bc.alignment = wrap_top
                if striped:
                    _fill_row(r, band_fill)
                dst.row_dimensions[r].height = min(409, max(15, vlines * 16))
                r += 1

        # 5) 이미지: 텍스트(A:D) 오른쪽 패널(F열~)에 큼직하게, 블록 첫 행에 앵커.
        #    텍스트 밴드와 세로로 안 겹치고, 이미지가 커도 A:D 레이아웃과 무관.
        text_end = r  # A:D 텍스트가 채운 마지막 다음 행
        paths = [p.strip() for p in str(get("이미지") or "").splitlines() if p.strip()]
        existing = [Path(p) for p in paths if Path(p).exists()]
        panel_h_px = 0
        if existing:
            # 블록 세로 시작 y(px) = 앞선 모든 행 높이의 합(전 행이 명시적 높이).
            y0_px = sum((dst.row_dimensions[rr].height or 15)
                        for rr in range(1, r0)) / 0.75
            # 썸네일 로드 후 소/대 분류(내부해상도 기준). 큰 것 = 실험·제조 방법
            # 스크린샷(통이미지) → 읽을 수 있게 자기 행에 크게, 작은 것은 격자.
            small, big = [], []
            for sp in existing:
                tpath = thumb_dir / f"{sp.parent.name}_{sp.stem}_r{res_px}.jpg"
                if not tpath.exists():
                    try:
                        im = PILImage.open(sp)
                        im.thumbnail((res_px, res_px))  # 롱사이드 res_px로 박기
                        im.convert("RGB").save(tpath, "JPEG", quality=75)
                    except Exception as ex:
                        print(f"    ⚠ 썸네일 실패 {sp}: {ex}", file=sys.stderr)
                        continue
                xi = XLImage(str(tpath))
                (big if max(xi.width, xi.height) >= big_thresh else small).append(xi)

            def _place(xi, x_px, y_px, target):
                scale = min(1.0, target / max(xi.width, xi.height))
                dw = max(1, round(xi.width * scale))
                dh = max(1, round(xi.height * scale))
                xi.anchor = AbsoluteAnchor(
                    pos=XDRPoint2D(pixels_to_EMU(x_px), pixels_to_EMU(y_px)),
                    ext=XDRPositiveSize2D(pixels_to_EMU(dw), pixels_to_EMU(dh)))
                dst.add_image(xi)
                return dw, dh

            y = y0_px
            # (a) 작은 이미지: 4열 격자(img_px).
            for i, xi in enumerate(small):
                _place(xi, img_x0_px + (i % img_per_row) * IMG_BOX,
                       y + (i // img_per_row) * IMG_BOX, img_px)
                total_thumbs += 1
            if small:
                y += (-(-len(small) // img_per_row)) * IMG_BOX
            # (b) 큰 이미지: 각자 자기 행에 크게(img_big_px), 좌측정렬로 세로 적재.
            for xi in big:
                _, dh = _place(xi, img_x0_px, y, img_big_px)
                y += dh + gap_px
                total_thumbs += 1
            panel_h_px = y - y0_px

        # 6) 블록 높이 보정: 이미지 패널이 텍스트보다 길면 스페이서 행으로 채워
        #    다음 제품이 이미지 아래로 내려가게(제품 간 이미지 겹침 방지).
        text_h_px = sum((dst.row_dimensions[rr].height or 15) / 0.75
                        for rr in range(r0, text_end))
        deficit = panel_h_px - text_h_px
        while deficit > 1:
            add_pt = min(409.0, deficit * 0.75)
            if striped:
                _fill_row(r, band_fill)
            dst.row_dimensions[r].height = add_pt
            r += 1
            deficit -= add_pt / 0.75

        # 7) 제품 사이 여백 한 줄.
        dst.row_dimensions[r].height = 6
        r += 1

    out = out or xlsx.with_name(xlsx.stem + "_카드.xlsx")
    wb.save(out)
    print(f"  {out.name}: 제품 {len(groups)}개 · 썸네일 {total_thumbs}장 (카드형)",
          file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="허브누리 상세내용(꿀팁·제조과정·캡처) 크롤러")
    ap.add_argument("--xlsx", help="레시피 목록 엑셀(링크 열의 branduid 사용)")
    ap.add_argument("--sheet", help="시트명(기본: 첫 시트)")
    ap.add_argument("--out", help="결과 엑셀 경로(기본: <원본>_상세.xlsx)")
    ap.add_argument("--branduids", help="직접 지정(쉼표구분). 지정 시 xlsx 목록 무시")
    ap.add_argument("--img-dir", default="cards/detail_img", help="이미지 저장 루트")
    ap.add_argument("--no-images", action="store_true", help="이미지 저장 생략(URL만)")
    ap.add_argument("--delay", type=float, default=1.0, help="페이지 요청 간 지연(초)")
    ap.add_argument("--limit", type=int, default=0, help="최대 제품 수(0=무제한)")
    ap.add_argument("--dump", action="store_true", help="저장 없이 콘솔 출력(점검용)")
    args = ap.parse_args(argv)

    if args.branduids:
        ids = [b.strip() for b in args.branduids.split(",") if b.strip()]
    elif args.xlsx:
        ids = branduids_from_xlsx(Path(args.xlsx), sheet=args.sheet)
    else:
        ap.error("--xlsx 또는 --branduids 중 하나가 필요합니다.")
    if args.limit:
        ids = ids[: args.limit]
    print(f"대상 제품: {len(ids)}개", file=sys.stderr)

    img_root = Path(args.img_dir)
    details: dict[str, dict] = {}
    ok = miss = 0
    for n, b in enumerate(ids, 1):
        try:
            d = extract_detail(b)
        except Exception as e:
            print(f"  ⚠ {b}: {e}", file=sys.stderr)
            miss += 1
            time.sleep(args.delay)
            continue
        if not d:
            print(f"  ⚠ {b}: 상세내용 없음 — 건너뜀", file=sys.stderr)
            miss += 1
            time.sleep(args.delay)
            continue
        prod_dir = img_root / f"hn-{b}"
        if not args.no_images and not args.dump and d["images"]:
            d["saved"] = download_images(d["images"], prod_dir)
        elif args.no_images and prod_dir.is_dir():
            # 재다운로드 없이 이미 받아둔 이미지를 그대로 목록화(텍스트만 갱신 시).
            d["saved"] = sorted(p for p in prod_dir.iterdir() if p.is_file())
        else:
            d["saved"] = []
        details[b] = d
        ok += 1
        tlen = len(d["text"])
        print(f"  ✅ [{n}/{len(ids)}] {b}  텍스트 {tlen}자 · 이미지 {len(d['images'])}장")
        if args.dump:
            print("  " + "-" * 60)
            print(d["text"])
            for u in d["images"]:
                print("   IMG", u)
            print("  " + "-" * 60)
        time.sleep(args.delay)

    print(f"\n완료: {ok}개 수집, {miss}개 건너뜀", file=sys.stderr)

    if args.xlsx and not args.dump:
        out = Path(args.out) if args.out else Path(args.xlsx).with_name(
            Path(args.xlsx).stem + "_상세.xlsx")
        write_back_xlsx(Path(args.xlsx), details, out, sheet=args.sheet)
        print(f"엑셀 저장 → {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
