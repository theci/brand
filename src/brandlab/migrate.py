"""처방 YAML 마이그레이션 — regime 필드 추가 (P9).

기존 처방 YAML에 `regime: cosmetics`를 추가한다. 원본은 .bak으로 백업한다.
주석·서식을 보존하기 위해 파서 라운드트립 대신 텍스트 삽입 방식을 쓴다.

실행:
    python -m brandlab.migrate            # formulas/ 전체 마이그레이션
    python -m brandlab.migrate --dry-run  # 변경 없이 대상만 표시
"""

from __future__ import annotations

import sys
from pathlib import Path

from .loader import FORMULAS_DIR, iter_formula_paths

DEFAULT_REGIME = "cosmetics"


def _has_regime(text: str) -> bool:
    return any(line.startswith("regime:") for line in text.splitlines())


def _insert_regime(text: str, regime: str) -> str:
    """version: 줄 다음에 regime: 줄을 삽입한다(없으면 맨 앞)."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("version:"):
            newline = "\n" if not line.endswith("\n") else ""
            lines.insert(i + 1, f"{newline}regime: {regime}\n")
            return "".join(lines)
    return f"regime: {regime}\n" + text


def migrate_formulas(
    formulas_dir: Path | str = FORMULAS_DIR,
    *,
    regime: str = DEFAULT_REGIME,
    dry_run: bool = False,
) -> list[Path]:
    """formulas/<slug>/v<n>.yaml 에 regime 필드를 추가. 변경한 파일 경로 목록 반환."""
    changed: list[Path] = []
    for path in iter_formula_paths(formulas_dir):
        text = path.read_text(encoding="utf-8")
        if _has_regime(text):
            continue
        changed.append(path)
        if dry_run:
            continue
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(text, encoding="utf-8")
        path.write_text(_insert_regime(text, regime), encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    dry = "--dry-run" in argv
    changed = migrate_formulas(dry_run=dry)
    if not changed:
        print("마이그레이션 대상 없음 (모든 처방에 regime 필드가 이미 있음).")
        return
    verb = "대상" if dry else "마이그레이션 완료 (.bak 백업 생성)"
    print(f"{verb}: {len(changed)}개")
    for p in changed:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
