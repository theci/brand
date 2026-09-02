"""실험 파일 생성·삭제 — DOE 설계(experiments/doe/) · 안정성 시료(experiments/stability/).

DOE: 인자·수준·평가항목을 받아 2^k 완전요인 런 골격을 자동 생성한다(점수는 빈칸=null).
     벤치에서 실험 후 scores를 채운다.
안정성: 시료ID·조건·시작일만 있으면 관찰 예정일(1/2/4/8주)은 stability 모듈이 계산한다.
        관찰(observations)은 이후 벤치에서 채운다.

검증: 파일로 쓴 뒤 load_doe / load_stability로 재검증, 실패하면 파일 삭제(롤백).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .core.models import DoeDesign, StabilitySample
from .loader import EXPERIMENTS_DIR, load_doe, load_stability


def _dump(data: dict) -> str:
    # default_flow_style=None: 중첩 소형 컬렉션은 flow({a: 1})로, 손으로 쓴 기존 파일과 유사.
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=None)


def full_factorial_runs(factors: list[str], response_items: list[str]) -> list[dict]:
    """2^k 완전요인 런 목록. 첫 인자가 가장 빨리 바뀌는 표준 순서(기존 파일과 동일).

    scores는 평가항목별 None(빈칸)으로 채워 넣는다.
    """
    runs: list[dict] = []
    k = len(factors)
    for i in range(2 ** k):
        fv = {f: ("high" if (i >> j) & 1 else "low") for j, f in enumerate(factors)}
        scores = {item: None for item in response_items}
        runs.append({"run_id": i + 1, "factor_values": fv, "scores": scores})
    return runs


def doe_path(filename: str, experiments_dir: Path | str = EXPERIMENTS_DIR) -> Path:
    return Path(experiments_dir) / "doe" / f"{filename}.yaml"


def stability_path(filename: str, experiments_dir: Path | str = EXPERIMENTS_DIR) -> Path:
    return Path(experiments_dir) / "stability" / f"{filename}.yaml"


def _create(data: dict, path: Path, model, loader) -> Path:
    model.model_validate(data)  # 1) 구조 검증
    if path.exists():
        raise FileExistsError(f"이미 존재하는 파일입니다: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump(data), encoding="utf-8")
    try:
        loader(path)  # 2) 파일 재검증
    except Exception:
        path.unlink(missing_ok=True)  # 롤백
        raise
    return path


def create_doe(data: dict, *, path: Path) -> Path:
    """DOE 설계 파일을 생성. 실패 시 파일을 남기지 않는다."""
    return _create(data, path, DoeDesign, load_doe)


def create_stability(data: dict, *, path: Path) -> Path:
    """안정성 시료 파일을 생성. 실패 시 파일을 남기지 않는다."""
    return _create(data, path, StabilitySample, load_stability)


def delete_experiment(path: Path | str) -> None:
    """실험 파일(DOE/안정성)을 삭제한다."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"파일이 없습니다: {path}")
    path.unlink()


__all__ = [
    "full_factorial_runs",
    "doe_path",
    "stability_path",
    "create_doe",
    "create_stability",
    "delete_experiment",
]
