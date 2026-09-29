"""허브누리 상세 엑셀을 '제형 아키타입'(14종)별로 나눠 카드형 엑셀로 뽑는다.

단순 100개 분할 대신, 각 제품을 `docs/커리큘럼/제형_아키타입_지도.md`의 14개 제형
골격으로 분류해 아키타입별 파일로 나눈다 — 원료·제형 공부용.

분류 근거(신뢰 순):
  1) 제품명 키워드(미스트/앰플/크림/오일/밤/샴푸/디퓨저/바스…)
  2) 처방 원료 구성(`formulas/<slug>/vN.yaml`의 phase 원료를
     `data/ingredients.yaml`의 IngredientCategory로 집계한 비율)
  3) ProductCategory(formula.category) 폴백

엑셀↔처방 조인 키 = 허브누리 branduid(엑셀 '링크' 열 ↔ formula.source_url).

사용:
    uv run python scripts/archetype_cards.py \
        --xlsx 허브누리_레시피_목록_상세.xlsx --out-dir 카드_아키타입
    # 분류 분포만 미리보기(파일 생성 안 함):
    uv run python scripts/archetype_cards.py --xlsx ... --dry
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl
import yaml

from brandlab.herbnoori_detail import _BRANDUID, finalize_cards

# 14 아키타입(정렬용 번호 접두). 지도의 순서를 따른다.
ARCHETYPES = {
    "01_토너·미스트", "02_젤", "03_앰플·세럼", "04_팩·마스크·패드", "05_로션",
    "06_크림", "07_페이스·바디오일", "08_밤·살브·연고", "09_색조", "10_세정(클렌징)",
    "11_헤어세정", "12_완제베이스+활성", "13_입욕·스크럽", "14_생활화학",
}


def _ingredient_categories() -> dict[str, str]:
    """ingredients.yaml: id -> IngredientCategory(한글 값)."""
    ing = yaml.safe_load(Path("data/ingredients.yaml").read_text(encoding="utf-8"))
    return {it["id"]: it.get("category")
            for it in (ing.get("ingredients") or [])
            if isinstance(it, dict) and it.get("id")}


def _formula_index(id2cat: dict[str, str]) -> dict[str, dict]:
    """branduid -> {name, pcat, comp{IngredientCategory: 비율}} (formulas 전체)."""
    out: dict[str, dict] = {}
    for f in glob.glob("formulas/**/*.yaml", recursive=True):
        try:
            d = yaml.safe_load(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        m = re.search(r"branduid=(\d+)", str(d.get("source_url", "")))
        if not m:
            continue
        comp: dict[str, float] = defaultdict(float)
        tot = 0.0
        for ph in (d.get("phases") or []):
            for r in (ph.get("ingredients") or []):
                pct = r.get("percent") or 0
                cat = id2cat.get(r.get("id"))
                if cat:
                    comp[cat] += pct
                tot += pct
        if tot > 0:
            comp = {k: v / tot for k, v in comp.items()}
        out[m.group(1)] = {"name": d.get("product", ""),
                           "pcat": d.get("category", ""), "comp": dict(comp)}
    return out


def classify(name: str, pcat: str, comp: dict[str, float]) -> str:
    """제품명·원료구성·ProductCategory → 14 아키타입 중 하나(없으면 기타/식품)."""
    n = name or ""

    def has(*ks: str) -> bool:
        return any(k in n for k in ks)

    def g(k: str) -> float:
        return comp.get(k, 0.0)

    if pcat == "생활화학" or has("디퓨저", "방향제", "탈취", "페브리즈", "세제", "주방",
                              "섬유", "룸스프레이", "퍼퓸", "캔들", "석고", "방향",
                              "사쉐", "모기", "퇴치", "벌레", "좀약"):
        return "14_생활화학"
    if has("바스", "바쓰", "입욕", "족욕", "스크럽", "바스솔트", "바스붐", "발포", "배쓰"):
        return "13_입욕·스크럽"
    if has("립스틱", "립글로스", "립틴트", "립틴", "틴트", "파운데이션", "마스카라",
           "블러셔") or (g("착색") >= 0.03 and g("워터") < 0.10):
        return "09_색조"
    if has("샴푸", "린스", "두피", "헤어"):
        return "11_헤어세정"
    if pcat == "클렌징" or g("계면활성제") >= 0.05 or has("클렌징", "폼클", "워시",
                                                    "클렌저", "세안", "페이셜폼"):
        return "10_세정(클렌징)"
    if g("완제베이스") >= 0.30:
        return "12_완제베이스+활성"
    if g("워터") < 0.05 and (g("왁스") >= 0.08 or has("밤", "살브", "연고", "립밤",
                                                   "버터바", "스틱밤")):
        return "08_밤·살브·연고"
    if g("워터") < 0.05 and (g("에몰리언트") >= 0.50 or (has("오일") and g("유화제") < 0.02)):
        return "07_페이스·바디오일"
    if ("젤" in n) or (g("점증") >= 0.30 and g("유화제") < 0.02 and g("활성") < 0.15
                       and not has("크림", "로션", "세럼", "앰플", "에센스")):
        return "02_젤"
    if has("팩", "패드", "마스크", "시트"):
        return "04_팩·마스크·패드"
    if g("유화제") >= 0.02 and g("워터") >= 0.10:
        return "06_크림" if (g("에몰리언트") >= 0.18 or "크림" in n) else "05_로션"
    if g("활성") >= 0.30 or has("앰플", "세럼", "에센스"):
        return "03_앰플·세럼"
    if "크림" in n:
        return "06_크림"
    if "로션" in n:
        return "05_로션"
    if g("워터") >= 0.55 and g("유화제") < 0.02:
        return "01_토너·미스트"
    if has("스킨", "토너", "미스트", "워터"):
        return "01_토너·미스트"
    fb = {"토너·미스트": "01_토너·미스트", "에센스·세럼·앰플": "03_앰플·세럼",
          "팩·패드": "04_팩·마스크·패드", "로션·크림": "05_로션",
          "오일·밤": "07_페이스·바디오일", "클렌징": "10_세정(클렌징)",
          "니들": "03_앰플·세럼", "식품": "99_식품", "생활화학": "14_생활화학"}
    return fb.get(pcat, "00_기타(미분류)")


def _product_groups(ws, link_i: int) -> list[list[list]]:
    """마스터 행 → 제품 그룹(링크 있는 행에서 새 제품 시작)."""
    groups: list[list[list]] = []
    for row in ws.iter_rows(min_row=2):
        vals = [c.value for c in row]
        link = vals[link_i] if link_i < len(vals) else None
        if link and _BRANDUID.search(str(link)):
            groups.append([vals])
        elif groups:
            groups[-1].append(vals)
        else:
            groups.append([vals])
    return groups


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="상세 엑셀 → 아키타입별 카드 엑셀")
    ap.add_argument("--xlsx", default="허브누리_레시피_목록_상세.xlsx",
                    help="상세 마스터 엑셀(제품명·…·상세내용·만들기·이미지·링크)")
    ap.add_argument("--out-dir", default="카드_아키타입", help="결과 폴더")
    ap.add_argument("--dry", action="store_true", help="분류 분포만 출력(파일 생성 X)")
    args = ap.parse_args(argv)

    xlsx = Path(args.xlsx)
    id2cat = _ingredient_categories()
    formulas = _formula_index(id2cat)

    wb = openpyxl.load_workbook(xlsx)
    ws = wb.worksheets[0]
    header = [c.value for c in ws[1]]
    link_i = header.index("링크")
    name_i = header.index("제품명")

    groups = _product_groups(ws, link_i)
    buckets: dict[str, list[list[list]]] = defaultdict(list)
    for ggrp in groups:
        first = ggrp[0]
        link = first[link_i]
        m = _BRANDUID.search(str(link)) if link else None
        if not m:
            buckets["00_기타(미분류)"].append(ggrp)
            continue
        fo = formulas.get(m.group(1))
        nm = first[name_i]
        if not fo:
            buckets["00_기타(미분류)"].append(ggrp)
            continue
        arch = classify(fo["name"] or nm, fo["pcat"], fo["comp"])
        buckets[arch].append(ggrp)

    print(f"제품 {sum(len(v) for v in buckets.values())}개 → 아키타입 {len(buckets)}종",
          file=sys.stderr)
    for k in sorted(buckets):
        print(f"  {k:<18} {len(buckets[k]):>4}개", file=sys.stderr)
    if args.dry:
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for arch in sorted(buckets):
        grps = buckets[arch]
        tmp = out_dir / f"_tmp_{arch}.xlsx"
        twb = openpyxl.Workbook()
        tws = twb.active
        tws.title = "레시피"
        tws.append(header)
        for ggrp in grps:
            for row in ggrp:
                tws.append(row)
        twb.save(tmp)
        out = out_dir / f"{arch}.xlsx"
        finalize_cards(tmp, out=out)
        tmp.unlink(missing_ok=True)
        made.append(out)
    print(f"\n완료: {len(made)}개 파일 → {out_dir}/", file=sys.stderr)
    for o in made:
        print("   ", o.name, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
