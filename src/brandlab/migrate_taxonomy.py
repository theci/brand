"""분류 체계 마이그레이션 (원료 category 2계층화 + 처방 category/line 부여).

원료: 자유문자열 category(~60종 드리프트) → 통제 category(enum) + effects(효능 태그).
      ingredients.yaml의 'category:' 줄만 정규식 수술 → 주석/서식 보존.
처방: 각 formulas/<slug>/vN.yaml에 category(제품 종류)·line(제품 라인) 부여.
      regime: 줄 뒤에 삽입(이미 있으면 건너뜀).

실행:
    uv run python -m brandlab.migrate_taxonomy --dry     # 미리보기(파일 안 씀)
    uv run python -m brandlab.migrate_taxonomy           # 적용
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
ING = _REPO / "data" / "ingredients.yaml"
FORMULAS = _REPO / "formulas"

# --- 원료: 옛 category → (새 category, effects) ---------------------------
# 통제 category(16종): 에몰리언트 버터 왁스 유화제 계면활성제 보습 활성 착향
#                      점증 산화방지 보존 용제 pH조절 워터 완제베이스 식품원료
CAT_MAP: dict[str, tuple[str, list[str]]] = {
    "에몰리언트": ("에몰리언트", []),
    "버터": ("버터", []),
    "왁스": ("왁스", []),
    "유화제": ("유화제", []),
    "유화보조": ("유화제", []),
    "계면활성제": ("계면활성제", []),
    "가용화제": ("계면활성제", []),
    "세정보조": ("계면활성제", []),
    "보습": ("보습", []),
    "보습제": ("보습", []),
    "활성": ("활성", []),
    "진정": ("활성", ["진정"]),
    "피지조절": ("활성", ["피지조절"]),
    "활성/점증": ("활성", []),
    "착향": ("착향", []),
    "착향제": ("착향", []),
    "에센셜오일": ("착향", []),
    "점증제": ("점증", []),
    "점증/워터": ("점증", []),
    "산화방지제": ("산화방지", []),
    "보존": ("보존", []),
    "보존제": ("보존", []),
    "소취제": ("활성", ["소취"]),
    "용제": ("용제", []),
    "용매": ("용제", []),
    "pH조절제": ("pH조절", []),
    "비누화제": ("비누화제", []),
    "워터": ("워터", []),
    "완제베이스": ("완제베이스", []),
}
# 효능 태그(옛 '활성(X)'의 X 정규화)
EFFECT_MAP = {
    "미백": "미백", "재생": "재생", "진정": "진정", "장벽": "장벽",
    "발효": "발효", "항산화": "항산화", "탄력": "탄력", "주름개선": "주름",
    "주름": "주름", "영양": "영양", "볼륨": "볼륨", "보습": "보습",
    "펩타이드": None,  # 타입이라 효능 태그 아님 → 드롭
}


def map_category(old: str) -> tuple[str, list[str]]:
    old = old.strip()
    if old.endswith("(식품)"):
        return "식품원료", []
    m = re.match(r"활성\((.+)\)$", old)
    if m:
        eff = EFFECT_MAP.get(m.group(1).strip(), m.group(1).strip())
        return "활성", [eff] if eff else []
    if old in CAT_MAP:
        return CAT_MAP[old]
    return old, []  # 미매핑 → 그대로(드라이런에서 잡힘)


def migrate_ingredients(text: str) -> tuple[str, list[str]]:
    """category 줄만 치환하고 바로 아래에 effects 줄 삽입. (새 텍스트, 미매핑목록)."""
    unmapped: list[str] = []
    out_lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^(\s*)category:\s*(.+?)\s*$", line)
        if not m or "effects" in line:
            out_lines.append(line)
            continue
        indent, old = m.group(1), m.group(2)
        if old in ("에몰리언트", "버터", "왁스", "유화제", "계면활성제", "보습",
                   "활성", "착향", "점증", "산화방지", "보존", "용제", "pH조절",
                   "워터", "완제베이스", "식품원료") and _next_is_effects(text, line):
            out_lines.append(line)  # 이미 마이그레이션됨
            continue
        new_cat, effects = map_category(old)
        if new_cat == old and old not in CAT_MAP and not old.endswith("(식품)") \
           and not old.startswith("활성"):
            unmapped.append(old)
        out_lines.append(f"{indent}category: {new_cat}")
        eff_str = "[" + ", ".join(effects) + "]"
        out_lines.append(f"{indent}effects: {eff_str}")
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else ""), unmapped


def _next_is_effects(text: str, cat_line: str) -> bool:
    lines = text.splitlines()
    try:
        i = lines.index(cat_line)
    except ValueError:
        return False
    return i + 1 < len(lines) and "effects:" in lines[i + 1]


# --- 처방: slug/제품명 → category(종류)·line(라인) ------------------------
def formula_category(product: str, slug: str, regime: str = "cosmetics") -> str:
    if regime.startswith("food"):
        return "식품"
    if regime.startswith("chemical"):
        return "생활화학"
    s = product + " " + slug
    rules = [
        ("니들", "니들"), ("needle", "니들"),
        ("클렌징", "클렌징"), ("cleansing", "클렌징"),
        ("미스트", "토너·미스트"), ("토너", "토너·미스트"), ("mist", "토너·미스트"),
        ("toner", "토너·미스트"), ("패드", "토너·미스트"), ("pad", "토너·미스트"),
        ("앰플", "에센스·세럼·앰플"), ("에센스", "에센스·세럼·앰플"), ("세럼", "에센스·세럼·앰플"),
        ("ampoule", "에센스·세럼·앰플"), ("essence", "에센스·세럼·앰플"), ("serum", "에센스·세럼·앰플"),
        ("젤", "에센스·세럼·앰플"), ("gel", "에센스·세럼·앰플"),
        ("립밤", "오일·밤"), ("밤", "오일·밤"), ("balm", "오일·밤"),
        ("오일", "오일·밤"), ("oil", "오일·밤"),
        ("팩", "팩·패드"), ("pack", "팩·패드"),
        ("크림", "로션·크림"), ("로션", "로션·크림"), ("cream", "로션·크림"), ("lotion", "로션·크림"),
    ]
    for kw, cat in rules:
        if kw in s.lower() or kw in s:
            return cat
    return "기타"


def formula_line(product: str, slug: str) -> str | None:
    for prefix, line in [
        ("squalane", "스쿠알란"), ("vitaminc", "비타민C"), ("jobstears", "율무미백"),
        ("matrixyl", "매트릭실"), ("tx-toning", "TX토닝"), ("ha11", "히아루론산"),
        ("ha-", "히아루론산"), ("black-snail", "뮤신·블랙스네일"), ("mucin", "뮤신·블랙스네일"),
        ("snail", "뮤신·블랙스네일"), ("pdrn", "PDRN·니들"), ("egf", "PDRN·니들"),
        ("cica-needle", "PDRN·니들"), ("collagen-needle", "PDRN·니들"),
        ("thread-collagen", "콜라겐"), ("collagen-moisture", "콜라겐"),
        ("camellia", "클렌징·오일"), ("green-tea", "클렌징·오일"),
        ("borfirin", "스쿠알란"), ("herbnoori-daily", "데일리"),
    ]:
        if slug.startswith(prefix) or prefix in slug:
            return line
    return None


def migrate_formula(text: str) -> str | None:
    if re.search(r"^category:\s*", text, re.M):
        return None  # 이미 있음
    prod = (re.search(r"^product:\s*(.+)$", text, re.M) or [None, ""])[1].strip()
    slug = (re.search(r"^slug:\s*(.+)$", text, re.M) or [None, ""])[1].strip()
    rm = re.search(r"^regime:\s*([^\s#]+)", text, re.M)
    regime = rm.group(1) if rm else "cosmetics"
    cat = formula_category(prod, slug, regime)
    line = formula_line(prod, slug) if regime == "cosmetics" else None
    ins = f"category: {cat}\n" + (f"line: {line}\n" if line else "")
    # regime: 줄 뒤에 삽입(없으면 slug 줄 뒤)
    if re.search(r"^regime:.*$", text, re.M):
        return re.sub(r"(^regime:.*$\n)", r"\1" + ins, text, count=1, flags=re.M)
    return re.sub(r"(^slug:.*$\n)", r"\1" + ins, text, count=1, flags=re.M)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args(argv)

    new_ing, unmapped = migrate_ingredients(ING.read_text(encoding="utf-8"))
    print(f"[원료] category 재매핑. 미매핑: {sorted(set(unmapped)) or '없음'}")
    cats = re.findall(r"^\s*category:\s*(.+)$", new_ing, re.M)
    from collections import Counter
    print("  새 category 분포:", dict(Counter(c.strip() for c in cats)))

    fmls = sorted(FORMULAS.glob("*/v*.yaml"))
    changed = 0
    preview = []
    for p in fmls:
        t = p.read_text(encoding="utf-8")
        nt = migrate_formula(t)
        if nt:
            changed += 1
            cat = re.search(r"^category:\s*(.+)$", nt, re.M).group(1)
            ln = (re.search(r"^line:\s*(.+)$", nt, re.M) or [None, "-"])[1]
            preview.append(f"    {p.parent.name}: {cat} / {ln}")
            if not args.dry:
                p.write_text(nt, encoding="utf-8")
    print(f"[처방] category/line 부여 대상 {changed}/{len(fmls)}")
    for l in preview:
        print(l)

    if args.dry:
        print("\n(드라이런 — 파일 미변경)")
        return 0
    ING.write_text(new_ing, encoding="utf-8")
    print("\n적용 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
