"""처방 파일(formulas/<slug>/v<n>.yaml) 생성·삭제.

처방은 '파일 1개 = 항목 1개'라 공유 리스트를 다루는 master_edit와 달리 파일 단위로 처리한다.
새 파일이라 보존할 주석이 없어 yaml.safe_dump로 정렬 덤프한다.

검증(3중):
  1) Formula 구조 — percent 합계 100 ± 0.01, enum, 필수 필드 (pydantic)
  2) 참조 무결성 — 원료/포장재 id가 마스터에 실제 존재하는지(사전 차단)
  3) 파일로 쓴 뒤 load_formula로 재검증, 실패하면 파일 삭제(롤백)
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .core.models import Formula
from .loader import FORMULAS_DIR, load_formula


def formula_yaml(data: dict) -> str:
    """처방 dict를 YAML 텍스트로 덤프(키 순서 유지, 한글 그대로)."""
    return yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False
    )


def formula_path(slug: str, version: int, formulas_dir: Path | str = FORMULAS_DIR) -> Path:
    return Path(formulas_dir) / slug / f"v{version}.yaml"


def _cleanup_empty_dir(d: Path) -> None:
    """디렉토리가 비었으면 제거(처방 슬러그 폴더 정리)."""
    try:
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
    except OSError:
        pass


def create_formula(
    data: dict,
    *,
    ingredient_ids: set[str],
    packaging_ids: set[str],
    formulas_dir: Path | str = FORMULAS_DIR,
) -> Path:
    """검증된 처방 파일을 새로 만든다. 반환: 생성된 파일 경로.

    실패 시 예외를 던지며, 파일을 남기지 않는다.
    """
    # 1) 구조 검증 (percent 합계·enum·필수)
    Formula.model_validate(data)

    slug = data["slug"]
    version = int(data["version"])
    path = formula_path(slug, version, formulas_dir)
    if path.exists():
        raise FileExistsError(f"이미 존재하는 처방 파일입니다: {slug} v{version}")

    # 2) 참조 무결성 (사전 차단 — 친절한 메시지)
    used_ing = {i["id"] for ph in data["phases"] for i in ph["ingredients"]}
    missing_i = sorted(used_ing - set(ingredient_ids))
    if missing_i:
        raise ValueError(f"존재하지 않는 원료 id: {missing_i}")
    used_pkg = {p["id"] for p in data.get("packaging", [])}
    missing_p = sorted(used_pkg - set(packaging_ids))
    if missing_p:
        raise ValueError(f"존재하지 않는 포장재 id: {missing_p}")

    # 3) 쓰기 + 재검증 + 실패 시 롤백(파일 삭제)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(formula_yaml(data), encoding="utf-8")
    try:
        load_formula(path, ingredient_ids=set(ingredient_ids), packaging_ids=set(packaging_ids))
    except Exception:
        path.unlink(missing_ok=True)
        _cleanup_empty_dir(path.parent)
        raise
    return path


def delete_formula(path: Path | str) -> None:
    """처방 파일을 삭제한다. 슬러그 폴더가 비면 폴더도 제거."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"처방 파일이 없습니다: {path}")
    parent = path.parent
    path.unlink()
    _cleanup_empty_dir(parent)


__all__ = [
    "formula_yaml",
    "formula_path",
    "create_formula",
    "delete_formula",
]
