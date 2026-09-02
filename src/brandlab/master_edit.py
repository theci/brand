"""마스터 데이터(ingredients.yaml / packaging.yaml)에 항목을 안전하게 추가·삭제한다.

pyyaml로 파일 전체를 재덤프하면 주석·정렬·필드 순서가 모두 사라진다.
이 모듈은 **원문 텍스트를 라인 단위로** 다뤄:
  - 추가: 검증된 항목 1개를 YAML 리스트 블록으로 렌더링해 파일 끝에 덧붙인다.
  - 삭제: 대상 id 블록만 잘라내고 나머지(주석 포함)는 그대로 둔다.

두 파일 모두 최상위가 단일 키(`ingredients:` / `packaging:`)의 시퀀스라
파일 끝에 덧붙이면 그 시퀀스의 새 항목이 된다.

안전 저장(save_with_backup)은 .bak 백업 후 쓰고, 검증 콜백이 실패하면 원문으로 롤백한다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import yaml

_ID_RE = re.compile(r"^(\s*)-\s*id:\s*(.+?)\s*$")

# ---------------------------------------------------------------------------
# 렌더링: 검증된 dict → YAML 리스트 블록 (2칸 들여쓰기)
# ---------------------------------------------------------------------------
# ingredients.yaml 필드 표기 순서 (파일 관례와 일치)
_INGREDIENT_ORDER = [
    "id", "name", "inci", "category",
    "max_percent", "price_per_kg", "density", "hlb", "required_hlb",
    "has_coa", "cosmetic_grade", "grade", "cas",
    "fragrance", "colorant", "food_grade", "supplier", "notes",
]
_PACKAGING_ORDER = [
    "id", "name", "type", "volume_ml", "material",
    "unit_price", "moq", "supplier", "notes",
]


def _ordered(fields: dict, order: list[str]) -> dict:
    """order를 따르되 None/빈 값은 제외한 정렬된 dict를 만든다."""
    out: dict = {}
    for key in order:
        if key not in fields:
            continue
        val = fields[key]
        if val is None:
            continue
        if isinstance(val, str) and val.strip() == "":
            continue
        if isinstance(val, (list, dict)) and len(val) == 0:
            continue  # 빈 allergens/nutrition 등은 렌더링에서 제외
        out[key] = val
    # order에 없는 키가 있으면 뒤에 붙인다(안전). 알러젠·영양성분 등 고급 필드 보존.
    for key, val in fields.items():
        if key in out or key in order or val is None:
            continue
        if isinstance(val, str) and val.strip() == "":
            continue
        if isinstance(val, (list, dict)) and len(val) == 0:
            continue
        out[key] = val
    return out


def render_block(fields: dict, order: list[str], *, indent: int = 2) -> str:
    """dict 1개를 `- key: value` 형태의 들여쓴 YAML 리스트 블록 문자열로 만든다."""
    d = _ordered(fields, order)
    dumped = yaml.safe_dump(
        [d], allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    pad = " " * indent
    lines = dumped.splitlines()
    return "\n".join(pad + ln if ln.strip() else ln for ln in lines)


def render_ingredient_block(fields: dict, *, indent: int = 2) -> str:
    return render_block(fields, _INGREDIENT_ORDER, indent=indent)


def render_packaging_block(fields: dict, *, indent: int = 2) -> str:
    return render_block(fields, _PACKAGING_ORDER, indent=indent)


# ---------------------------------------------------------------------------
# 추가 / 삭제 (텍스트 조작)
# ---------------------------------------------------------------------------
def append_item(text: str, block: str) -> str:
    """리스트 블록을 파일 끝에 한 줄 띄우고 덧붙인다."""
    body = text.rstrip("\n")
    return f"{body}\n\n{block.rstrip(chr(10))}\n"


def _find_item(lines: list[str], id_value: str) -> tuple[int, int] | None:
    """대상 id 항목의 (시작 인덱스, 끝 인덱스[배타])를 반환. 없으면 None.

    끝 = 같은 들여쓰기의 다음 리스트 항목(`- `) 또는 더 얕은 들여쓰기 줄, 아니면 EOF.
    항목 사이의 빈 줄은 블록에 포함해 함께 지운다(간격 유지).
    """
    target = id_value.strip().strip('"').strip("'")
    start = None
    indent = 0
    for i, line in enumerate(lines):
        m = _ID_RE.match(line)
        if m and m.group(2).strip().strip('"').strip("'") == target:
            start = i
            indent = len(m.group(1))
            break
    if start is None:
        return None

    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if not line.strip():
            continue  # 빈 줄은 통과(뒤따르는 항목까지 포함)
        cur = len(line) - len(line.lstrip())
        if cur < indent:
            end = j
            break
        if cur == indent and line.lstrip().startswith("-"):
            end = j
            break
    return start, end


def delete_item(text: str, id_value: str) -> str:
    """대상 id 항목 블록을 잘라낸 새 텍스트를 반환. 못 찾으면 KeyError."""
    trailing_nl = text.endswith("\n")
    lines = text.splitlines()
    loc = _find_item(lines, id_value)
    if loc is None:
        raise KeyError(f"id를 찾을 수 없습니다: {id_value}")
    start, end = loc
    del lines[start:end]
    out = "\n".join(lines).rstrip("\n")
    return out + "\n" if trailing_nl else out


def replace_item(text: str, id_value: str, new_block: str) -> str:
    """대상 id 항목 블록을 new_block으로 제자리 교체한 새 텍스트를 반환.

    위치(정렬 순서)는 유지된다. 못 찾으면 KeyError.
    해당 항목 내부의 인라인 주석은 교체로 사라진다(폼 편집의 한계).
    """
    trailing_nl = text.endswith("\n")
    lines = text.splitlines()
    loc = _find_item(lines, id_value)
    if loc is None:
        raise KeyError(f"id를 찾을 수 없습니다: {id_value}")
    start, end = loc
    block_lines = new_block.rstrip("\n").split("\n")
    if end < len(lines):
        block_lines = block_lines + [""]  # 다음 항목과의 빈 줄 간격 유지
    lines[start:end] = block_lines
    out = "\n".join(lines).rstrip("\n")
    return out + "\n" if trailing_nl else out


# ---------------------------------------------------------------------------
# 안전 저장 (백업 + 검증 + 롤백)
# ---------------------------------------------------------------------------
def save_with_backup(
    path: Path | str, new_text: str, validate: Callable[[Path], object]
) -> None:
    """new_text를 path에 쓰되, 먼저 .bak로 백업하고 validate가 실패하면 원문으로 롤백한다.

    validate는 path를 인자로 받아 로드·검증하는 콜백(예: load_ingredients).
    검증 실패 시 원문 복구 후 예외를 다시 던진다.
    """
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    backup = path.with_suffix(path.suffix + ".bak")
    backup.write_text(original, encoding="utf-8")
    path.write_text(new_text, encoding="utf-8")
    try:
        validate(path)
    except Exception:
        path.write_text(original, encoding="utf-8")  # 롤백
        raise


__all__ = [
    "render_block",
    "render_ingredient_block",
    "render_packaging_block",
    "append_item",
    "delete_item",
    "replace_item",
    "save_with_backup",
]
