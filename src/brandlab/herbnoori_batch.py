"""허브누리 배치 파이프라인 — 페이지 범위를 한 번에 크롤·해석·리포트한다.

페이지를 하나씩 돌며 수동 개입하던 흐름을, 다음 한 번의 리포트로 압축한다:

    uv run python -m brandlab.herbnoori_batch --xcode 007 --mcode 002 --pages 6-11

리포트는 제품별 상태를 4가지로 분류한다:
  ✅ ok        — 모든 원료가 마스터에 있고 % 합계도 정상 → 바로 처방화 가능
  🧪 ingred    — 미등록 원료가 있음(전체 유니크 stub을 한 번에 출력)
  👀 review    — 이중 변형/단일 원료 등 사람 확인 필요
  ⏭ skip      — 상세에 레시피 표가 없음(완제품·이미지 레시피)

원료 stub을 한 번 채워 넣고 다시 --write 로 실행하면, ok 상태 전부를
`formulas/hn-<branduid>/v1.yaml` 로 일괄 생성한다(슬러그는 나중에 rename 가능).

이 모듈은 크롤/임포트의 기존 함수를 재사용만 한다(로직 중복 없음).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .herbnoori_crawl import extract_recipe, list_branduids, parse_pages_arg, write_raw
from .herbnoori_import import (
    build_formula_dict,
    build_name_index,
    guess_type,
    parse_raw,
    resolve_phases,
)
from .core.models import Formula
from .loader import load_ingredients

FORMULAS_DIR = Path("formulas")


def _rows_to_raw(name: str, rows: list[str]) -> str:
    """extract_recipe의 (제품명, ['재료\\t용량', ...]) → parse_raw가 먹는 텍스트."""
    return "\n".join([name, *rows]) + "\n"


class Result:
    __slots__ = ("branduid", "name", "status", "detail", "cards", "rows")

    def __init__(self, branduid, name, status, detail="", cards=None, rows=None):
        self.branduid = branduid
        self.name = name
        self.status = status  # ok | ingred | review | skip | error
        self.detail = detail
        self.cards = cards or []  # [(card_dict, phases)] — ok/review일 때
        self.rows = rows  # extract_recipe의 rows(raw 저장용) — 표 있을 때


def classify(branduid: str, idx, densities, regime: str = "cosmetics") -> tuple[Result, list]:
    """한 상세페이지를 분류(1회 fetch). (Result, unknown_list) 반환."""
    try:
        res = extract_recipe(branduid)
    except Exception as e:  # 네트워크/파싱 오류
        return Result(branduid, f"branduid-{branduid}", "error", str(e)), []
    if res is None:
        return Result(branduid, f"branduid-{branduid}", "skip", "레시피 표 없음"), []

    name, rows = res
    products = parse_raw(_rows_to_raw(name, rows))
    if not products:
        return Result(branduid, name, "skip", "표는 있으나 재료 파싱 실패"), []

    unknown_all: list = []
    cards, flags = [], []
    if len(products) > 1:
        flags.append(f"이중변형({len(products)}개)")
    for p in products:
        card = {"product": p["product"], "type": guess_type(p["product"]),
                "ingredients": p["ingredients"], "regime": regime}
        phases, unknown = resolve_phases(card, idx, densities)
        unknown_all.extend(unknown)
        cards.append((card, phases))
        n_ing = sum(len(ph["items"]) for ph in phases)
        if n_ing <= 1:
            flags.append("단일원료")

    if unknown_all:
        names = ", ".join(sorted({u[0] for u in unknown_all}))
        return Result(branduid, name, "ingred", names, rows=rows), unknown_all
    if flags:
        return Result(branduid, name, "review", " · ".join(sorted(set(flags))),
                      cards, rows=rows), []
    return Result(branduid, name, "ok", f"{len(products)}제품", cards, rows=rows), []


def write_formula(card, phases, branduid, force=False) -> str:
    """ok 카드를 formulas/hn-<branduid>/v1.yaml 로 쓴다. 상태 문자열 반환."""
    import yaml

    total = sum(g for ph in phases for (_id, _n, g) in ph["items"])
    card["volume_ml"] = round(total, 1)
    card["slug"] = f"hn-{branduid}"
    fdict = build_formula_dict(card, phases)
    formula = Formula.model_validate(fdict)  # 검증(합계 100±0.01 등)
    out = FORMULAS_DIR / formula.slug / f"v{formula.version}.yaml"
    if out.exists() and not force:
        return f"skip(존재): {out}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        yaml.safe_dump(fdict, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8")
    return f"✅ {out}  (합계 {formula.total_percent:.2f}%)"


_ICON = {"ok": "✅", "ingred": "🧪", "review": "👀", "skip": "⏭", "error": "⚠"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="허브누리 배치 크롤·해석·리포트")
    ap.add_argument("--xcode", required=True)
    ap.add_argument("--mcode", required=True)
    ap.add_argument("--scode", default=None, help="하위분류 코드(예: 002). mcode에 하위분류가 있을 때")
    ap.add_argument("--regime", default="cosmetics",
                    help="레짐(cosmetics/chemical_safety/food …). 생활화학·방향제는 chemical_safety")
    ap.add_argument("--pages", default="1", help="예: 6-11 또는 6,7,9")
    ap.add_argument("--out", default="cards/raw", help="raw txt 저장 위치")
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--write", action="store_true",
                    help="ok 상태를 formulas/hn-<branduid>/v1.yaml 로 생성")
    ap.add_argument("--force", action="store_true", help="기존 처방 덮어쓰기")
    args = ap.parse_args(argv)

    # 1) branduid 수집(밴드 노이즈는 list_branduids가 이미 제거)
    ids: list[str] = []
    for pg in parse_pages_arg(args.pages):
        got = list_branduids(args.xcode, args.mcode, pg, scode=args.scode)
        print(f"페이지 {pg}: {len(got)}개", file=sys.stderr)
        ids.extend(got)
        time.sleep(args.delay)
    ids = list(dict.fromkeys(ids))

    idx = build_name_index()
    master = load_ingredients()
    densities = {ing.id: ing.density for ing in master.ingredients}

    # 2) 분류 + raw 저장
    out_dir = Path(args.out)
    results: list[Result] = []
    unknowns: list = []
    for b in ids:
        r, unk = classify(b, idx, densities, regime=args.regime)
        results.append(r)
        unknowns.extend(unk)
        # raw는 표가 있었던 경우만 저장(재현·수동보정용) — classify가 받아둔 rows 재사용
        if r.rows:
            write_raw(out_dir, b, r.name, r.rows)
        time.sleep(args.delay)

    # 3) 리포트
    order = {"ok": 0, "review": 1, "ingred": 2, "skip": 3, "error": 4}
    results.sort(key=lambda r: (order.get(r.status, 9), r.branduid))
    print("\n===== 배치 리포트 =====")
    for r in results:
        print(f"  {_ICON.get(r.status,'?')} {r.status:7} {r.branduid}  {r.name}"
              + (f"  — {r.detail}" if r.detail else ""))

    counts = {k: sum(1 for r in results if r.status == k) for k in _ICON}
    print("\n요약: " + " · ".join(f"{_ICON[k]}{k} {counts[k]}" for k in _ICON))

    # 4) 미등록 원료 유니크 stub(한 번에 채우기)
    if unknowns:
        from .herbnoori_import import stub_for
        seen, blocks = set(), []
        for name, feat, subst in unknowns:
            if name in seen:
                continue
            seen.add(name)
            blocks.append(stub_for(name, feat, subst))
        print(f"\n===== 미등록 원료 {len(blocks)}종(ingredients.yaml에 채우기) =====")
        print("\n".join(blocks))

    # 5) --write: ok 전부 생성
    if args.write:
        print("\n===== 처방 생성(ok) =====")
        for r in results:
            if r.status != "ok":
                continue
            for card, phases in r.cards:
                try:
                    print(f"  {r.branduid} {card['product']}: "
                          + write_formula(card, phases, r.branduid, force=args.force))
                except Exception as e:
                    print(f"  ⚠ {r.branduid} {card['product']}: {e}")
    else:
        print("\n(처방을 실제로 만들려면 --write. 그 전에 위 원료 stub을 채우세요.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
