"""허브누리(herbnoori.com) 레시피 크롤러.

목적: 카테고리의 제품들을 자동으로 돌며 레시피 표를 뽑아, herbnoori_import의
--raw 가 그대로 먹는 텍스트 파일로 저장한다. (사람이 페이지를 열거나 복붙할 필요 없음)

사용 예:
    # 천연화장품(xcode=007,mcode=002) 1~3페이지 → cards/raw/ 에 제품별 txt 저장
    uv run python -m brandlab.herbnoori_crawl --xcode 007 --mcode 002 --pages 1-3 --out cards/raw

    # 특정 제품만
    uv run python -m brandlab.herbnoori_crawl --branduids 288778,288757 --out cards/raw

    # 목록의 branduid만 출력(수집 규모 확인)
    uv run python -m brandlab.herbnoori_crawl --xcode 007 --mcode 002 --pages 1-3 --list

이후:  uv run python -m brandlab.herbnoori_import cards/raw/hn-288778.txt --raw

주의: 외부 사이트를 반복 호출한다. 기본 지연 1.0초. 대량 크롤 전 사이트 부하를 고려할 것.
허브누리는 레시피를 공개·인쇄 허용하나 '출처 표시'를 요구한다(각 파일에 출처 URL 기록).
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://www.herbnoori.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 레시피 표 종료 신호(이 뒤의 가격·후기·관련상품을 재료로 오인하지 않게).
TERMINATORS = ("만들기", "레시피후기", "상세정보", "선택상품", "레시피관련",
               "레시피문의", "위로 올라", "허브누리에서 제공", "타사의 원료")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    return raw.decode("cp949", errors="replace")  # 허브누리는 EUC-KR/CP949


def html_to_lines(h: str) -> list[str]:
    """HTML → 표 구조를 살린 텍스트 라인들(셀=탭, 행=줄바꿈)."""
    h = re.sub(r"(?is)<script.*?</script>", " ", h)
    h = re.sub(r"(?is)<style.*?</style>", " ", h)
    h = re.sub(r"(?i)</t[dh]>", "\t", h)
    h = re.sub(r"(?i)</tr>", "\n", h)
    h = re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = re.sub(r"(?i)</(p|div|li|h[1-6])>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = html.unescape(h)
    out = []
    for ln in h.splitlines():
        ln = re.sub(r"[  ]+", " ", ln).strip().strip("\t").strip()
        if ln:
            out.append(ln)
    return out


def page_title(h: str) -> str | None:
    m = re.search(r"(?is)<title>\s*\[?(.*?)\]?\s*</title>", h)
    return m.group(1).strip() if m else None


def list_branduids(xcode: str, mcode: str, page: int, scode: str | None = None) -> list[str]:
    scode_q = f"&scode={scode}" if scode else ""
    url = (f"{BASE}/shop/shopbrand.html?type=Y&xcode={xcode}&mcode={mcode}"
           f"{scode_q}&page={page}")
    h = fetch(url)
    # 본목록 그리드 링크만 취한다. 상·하단 슬라이드배너(sliderkit-panel)는
    # `branduid=NNNN`만 있고 카테고리 파라미터가 없어, xcode·mcode(·scode)를 요구해 거른다.
    seen, ids = set(), []
    pat = re.compile(
        rf"shopdetail\.html\?branduid=(\d+)&xcode={xcode}&mcode={mcode}{scode_q}")
    for m in pat.finditer(h):
        b = m.group(1)
        if b not in seen:
            seen.add(b)
            ids.append(b)
    return ids


# 용량 셀 판별(줄 시작이 숫자+단위, 범위 99~97 허용). 특징 텍스트의 숫자와 구분.
_AMOUNT_LINE = re.compile(
    r"^\s*\d+(?:\.\d+)?(?:\s*[~\-]\s*\d+(?:\.\d+)?)?\s*(방울|kg|g|㎖|ml|mL)")
_HEADER_CELLS = {"재료", "재료종류", "재료 종류", "원료명", "용량", "양", "총양", "총 양",
                 "특징", "특징및역할", "특징 및 역할", "특징및효능", "특징 및 효능",
                 "대체재료", "대체 재료", "분류", "구분", "분류 및 순서", "순서"}
# 용량 컬럼 헤더로 인정하는 셀(사이트마다 '용량'·'양(量)'·'총양'을 쓴다).
_AMOUNT_HEADERS = {"용량", "양", "총양", "총 양"}
# 재료 컬럼 헤더로 인정하는 토큰(재료/재료종류/원료명 등).
_INGREDIENT_HEADER_TOKENS = ("재료", "원료")
# 단위 없는 용량 셀(예: '10', '84', '9.5') — 일부 표는 단위를 생략한다(=g).
_BARE_NUM = re.compile(r"^\d+(?:\.\d+)?$")


def extract_recipe(branduid: str) -> tuple[str, list[str]] | None:
    """상세페이지 → (제품명, ['재료\\t용량', '이름\\t용량', ...]). 못 찾으면 None.

    이 사이트 표는 셀이 한 줄씩(이름→용량→특징→대체) 나오므로,
    '용량처럼 생긴 줄의 바로 앞 줄'을 재료명으로 짝짓는다(특징 다줄에도 안전).
    """
    url = f"{BASE}/shop/shopdetail.html?branduid={branduid}"
    h = fetch(url)
    name = page_title(h) or f"branduid-{branduid}"
    lines = html_to_lines(h)
    # 헤더는 '재료','용량/양',... 셀이 각각 한 줄. 용량 헤더 줄을 구간 시작으로.
    # 판매옵션의 '용량'과 구분하려고 앞 3줄 안에 '재료'가 있어야 한다.
    start = next((i for i, ln in enumerate(lines)
                  if ln.strip() in _AMOUNT_HEADERS
                  and any(any(t in lines[j] for t in _INGREDIENT_HEADER_TOKENS)
                          for j in range(max(0, i - 3), i))), None)
    if start is None:  # 한 줄에 같이 있는 경우(대비)
        start = next((i for i, ln in enumerate(lines)
                      if any(t in ln for t in _INGREDIENT_HEADER_TOKENS)
                      and ("용량" in ln or "\t양\t" in ln or "총양" in ln)), None)
    if start is None:
        return None

    rows = ["재료\t용량\t특징\t대체재료"]
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        # 종료어는 '줄 시작'일 때만(특징 설명에 '만들기' 등이 섞여 잘리는 것 방지)
        if any(ln.startswith(t) for t in TERMINATORS):
            break
        cells = [c.strip() for c in ln.split("\t")]
        # (1) 인라인 행: '이름 \t 용량 \t …' — 한 줄에 이름·용량이 함께.
        if (len(cells) >= 2 and _AMOUNT_LINE.match(cells[1])
                and cells[0] and cells[0] not in _HEADER_CELLS
                and not _AMOUNT_LINE.match(cells[0])):
            rows.append(f"{cells[0]}\t{cells[1]}")
            continue
        # (2) 셀-한줄 행: 용량만 있는 줄 → 바로 앞 줄(첫 셀)이 재료명.
        #     단위 있는 용량(_AMOUNT_LINE) 또는 단위 없는 숫자(_BARE_NUM, =g) 모두 허용.
        bare = _BARE_NUM.match(cells[0])
        if _AMOUNT_LINE.match(cells[0]) or bare:
            prev = lines[i - 1].split("\t")[0].strip() if i > 0 else ""
            if (not prev or prev in _HEADER_CELLS or prev == "."
                    or _AMOUNT_LINE.match(prev) or _BARE_NUM.match(prev)):
                continue
            amt = cells[0] + "g" if bare else cells[0]
            rows.append(f"{prev}\t{amt}")
    if len(rows) <= 1:
        return None
    return name, rows


def write_raw(out_dir: Path, branduid: str, name: str, block: list[str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    url = f"{BASE}/shop/shopdetail.html?branduid={branduid}"
    body = "\n".join([f"# 출처: {url}", name, *block]) + "\n"
    p = out_dir / f"hn-{branduid}.txt"
    p.write_text(body, encoding="utf-8")
    return p


def parse_pages_arg(s: str) -> list[int]:
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="허브누리 레시피 크롤러")
    ap.add_argument("--xcode", help="대분류 코드(예: 007)")
    ap.add_argument("--mcode", help="중분류 코드(예: 002)")
    ap.add_argument("--pages", default="1", help="페이지 범위(예: 1-3 또는 1,2,5)")
    ap.add_argument("--branduids", help="직접 지정(쉼표구분). 지정 시 xcode/pages 무시")
    ap.add_argument("--out", default="cards/raw", help="저장 디렉터리")
    ap.add_argument("--delay", type=float, default=1.0, help="요청 간 지연(초)")
    ap.add_argument("--limit", type=int, default=0, help="최대 제품 수(0=무제한)")
    ap.add_argument("--list", action="store_true", help="branduid만 나열(수집 안 함)")
    args = ap.parse_args(argv)

    # 1) 대상 branduid 수집
    if args.branduids:
        ids = [b.strip() for b in args.branduids.split(",") if b.strip()]
    else:
        if not (args.xcode and args.mcode):
            ap.error("--branduids 또는 (--xcode 와 --mcode)가 필요합니다.")
        ids = []
        for pg in parse_pages_arg(args.pages):
            got = list_branduids(args.xcode, args.mcode, pg)
            print(f"페이지 {pg}: {len(got)}개", file=sys.stderr)
            ids.extend(got)
            time.sleep(args.delay)
        # 목록 중복 제거(페이지 경계)
        ids = list(dict.fromkeys(ids))
    if args.limit:
        ids = ids[: args.limit]

    if args.list:
        print("\n".join(ids))
        print(f"\n총 {len(ids)}개", file=sys.stderr)
        return 0

    # 2) 상세 수집 → raw txt 저장
    out_dir = Path(args.out)
    ok = miss = 0
    for b in ids:
        try:
            res = extract_recipe(b)
        except Exception as e:  # 네트워크/파싱 오류는 건너뜀
            print(f"  ⚠ {b}: {e}", file=sys.stderr)
            miss += 1
            time.sleep(args.delay)
            continue
        if res is None:
            print(f"  ⚠ {b}: 레시피 표(재료/용량) 없음 — 건너뜀", file=sys.stderr)
            miss += 1
        else:
            name, block = res
            p = write_raw(out_dir, b, name, block)
            print(f"  ✅ {b}  {name}  ({len(block)-1}행) → {p}")
            ok += 1
        time.sleep(args.delay)

    print(f"\n완료: {ok}개 저장, {miss}개 건너뜀 → {out_dir}", file=sys.stderr)
    print("다음: uv run python -m brandlab.herbnoori_import <파일> --raw", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
