"""inventory.yaml 의 보유량(on_hand_g)과 last_updated 를 주석·정렬 보존하며 갱신.

pyyaml 재덤프는 주석·순서를 날린다. ingredient_edit 과 같은 방식으로 원문을
줄 단위로 다뤄, 대상 원료 블록의 on_hand_g 만 바꾸고 나머지는 그대로 둔다.
"""

from __future__ import annotations

import re
from datetime import date

from .ingredient_edit import set_ingredient_fields

_LAST_UPDATED_RE = re.compile(r"^last_updated:.*$", re.MULTILINE)


def _set_last_updated(text: str, on_date: date) -> str:
    line = f"last_updated: {on_date.isoformat()}"
    if _LAST_UPDATED_RE.search(text):
        return _LAST_UPDATED_RE.sub(line, text, count=1)
    # 없으면 맨 앞(주석 블록 뒤)에 삽입: 첫 비주석·비공백 줄 앞에.
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() and not ln.lstrip().startswith("#"):
            lines.insert(i, line)
            break
    else:
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def apply_consumption(text: str, updates: dict[str, float], last_updated: date) -> str:
    """원료별 새 보유량(updates)을 on_hand_g 에 반영하고 last_updated 를 갱신한다.

    updates 의 id 는 inventory.yaml 에 실제로 존재하는 원료여야 한다.
    없는 id 는 조용히 건너뛴다(호출부가 이미 재고 등록분만 넘기는 계약).
    """
    out = text
    for ing_id, on_hand in updates.items():
        try:
            out, _ = set_ingredient_fields(out, ing_id, {"on_hand_g": float(on_hand)})
        except KeyError:
            continue
    out = _set_last_updated(out, last_updated)
    return out


__all__ = ["apply_consumption"]
