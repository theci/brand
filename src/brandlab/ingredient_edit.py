"""ingredients.yaml의 특정 원료 블록에 필드를 안전하게 채워 넣는다.

pyyaml로 재덤프하면 파일의 주석·정렬이 모두 사라진다. 이 모듈은 원문 텍스트를
줄 단위로 다뤄, 대상 원료 블록의 지정 필드만 갱신/삽입하고 나머지는 그대로 둔다.

- 필드가 이미 있으면 값만 교체(인라인 주석 보존).
- 없으면 `- id:` 줄 바로 아래에 올바른 들여쓰기로 삽입.
- 반환: (새 텍스트, 실제로 반영한 {필드: 값}).
"""

from __future__ import annotations

import re

_ID_RE = re.compile(r"^(\s*)-\s*id:\s*(.+?)\s*$")


def _format_value(field: str, value: object) -> str:
    if field == "cas":
        return f'"{value}"'
    if isinstance(value, float):
        # 불필요한 소수 0 제거(0.90 → 0.9, 1.0 → 1.0 유지)
        return repr(value)
    return str(value)


def _find_block(lines: list[str], ingredient_id: str) -> tuple[int, int, int] | None:
    """대상 원료의 (id줄 인덱스, 블록끝 인덱스[배타], 항목 들여쓰기)를 반환."""
    start = None
    item_indent = 0
    for i, line in enumerate(lines):
        m = _ID_RE.match(line)
        if m and m.group(2).strip() == ingredient_id:
            start = i
            item_indent = len(m.group(1))
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if _ID_RE.match(lines[j]):
            end = j
            break
    return start, end, item_indent


def _field_indent(lines: list[str], start: int, end: int, item_indent: int) -> int:
    """블록 내 기존 필드 줄의 들여쓰기를 감지. 없으면 item_indent+2."""
    for k in range(start + 1, end):
        m = re.match(r"^(\s+)[\w-]+:", lines[k])
        if m:
            return len(m.group(1))
    return item_indent + 2


def set_ingredient_fields(
    text: str, ingredient_id: str, fields: dict[str, object]
) -> tuple[str, dict[str, object]]:
    """원료 블록에 fields를 반영한 새 텍스트와 반영 내역을 반환.

    fields의 값이 None인 항목은 무시한다.
    대상 원료를 못 찾으면 KeyError.
    """
    effective = {k: v for k, v in fields.items() if v is not None}
    if not effective:
        return text, {}

    trailing_nl = text.endswith("\n")
    lines = text.splitlines()

    loc = _find_block(lines, ingredient_id)
    if loc is None:
        raise KeyError(f"원료 id를 찾을 수 없습니다: {ingredient_id}")
    start, end, item_indent = loc
    indent = " " * _field_indent(lines, start, end, item_indent)

    applied: dict[str, object] = {}
    for field, value in effective.items():
        formatted = _format_value(field, value)
        field_re = re.compile(rf"^(\s*){re.escape(field)}:\s*(\S.*?)?(\s+#.*)?$")

        replaced = False
        for k in range(start + 1, end):
            m = field_re.match(lines[k])
            if m:
                comment = m.group(3) or ""
                lines[k] = f"{m.group(1)}{field}: {formatted}{comment}"
                replaced = True
                break
        if not replaced:
            lines.insert(start + 1, f"{indent}{field}: {formatted}")
            end += 1  # 삽입으로 블록이 한 줄 늘어남
        applied[field] = value

    out = "\n".join(lines)
    if trailing_nl:
        out += "\n"
    return out, applied


__all__ = ["set_ingredient_fields"]
