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

from .core.models import DoeDesign, PanelTest, StabilitySample
from .loader import EXPERIMENTS_DIR, load_batch, load_doe, load_panel, load_stability
from .master_edit import save_with_backup


def _dump(data: dict) -> str:
    # default_flow_style=None: 중첩 소형 컬렉션은 flow({a: 1})로, 손으로 쓴 기존 파일과 유사.
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=None)


def _leading_comments(text: str) -> str:
    """파일 맨 위의 주석·빈 줄 블록을 반환(첫 내용 줄에서 멈춤). 재덤프 시 헤더 보존용."""
    out: list[str] = []
    for ln in text.splitlines():
        if ln.strip() == "" or ln.lstrip().startswith("#"):
            out.append(ln)
        else:
            break
    joined = "\n".join(out).rstrip("\n")
    return (joined + "\n") if joined.strip() else ""


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


def panel_path(filename: str, experiments_dir: Path | str = EXPERIMENTS_DIR) -> Path:
    return Path(experiments_dir) / "panel" / f"{filename}.yaml"


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


def create_panel(data: dict, *, path: Path) -> Path:
    """시제품 관능 평가 파일을 생성(응답 없는 골격). 실패 시 파일을 남기지 않는다."""
    return _create(data, path, PanelTest, load_panel)


def delete_experiment(path: Path | str) -> None:
    """실험 파일(DOE/안정성)을 삭제한다."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"파일이 없습니다: {path}")
    path.unlink()


# ---------------------------------------------------------------------------
# 결과 입력 — DOE 점수 / 안정성 관찰값 (기존 파일 갱신, 헤더 주석 보존, .bak 롤백)
# ---------------------------------------------------------------------------
def set_doe_scores(path: Path | str, scores_by_run: dict) -> None:
    """DOE 파일의 런별 점수를 갱신한다. scores_by_run: {run_id: {평가항목: 값|None}}."""
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    data = load_doe(path).model_dump(mode="json", exclude_none=True)
    smap = {str(k): v for k, v in scores_by_run.items()}
    for run in data.get("runs", []):
        key = str(run["run_id"])
        if key in smap:
            run["scores"] = smap[key]
    new_text = _leading_comments(original) + _dump(data)
    save_with_backup(path, new_text, load_doe)


def set_stability_observations(path: Path | str, observations: list[dict]) -> None:
    """안정성 파일의 관찰 목록을 통째로 교체한다(추가·수정·삭제 반영).

    observations의 각 항목은 최소 date를 가져야 하며, 빈 필드는 제외된다.
    """
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    data = load_stability(path).model_dump(mode="json", exclude_none=True)
    cleaned = []
    for o in observations:
        if not o.get("date"):
            continue
        cleaned.append({k: v for k, v in o.items() if v not in (None, "")})
    data["observations"] = cleaned
    new_text = _leading_comments(original) + _dump(data)
    save_with_backup(path, new_text, load_stability)


def set_batch_actuals(
    path: Path | str,
    *,
    yield_g: float | None = None,
    ph: float | None = None,
    observations: str | None = None,
    operator: str | None = None,
    actuals_by_id: dict[str, float | None] | None = None,
) -> None:
    """배치 파일의 제조 후 실측값을 갱신한다.

    수율(yield_g)·pH·관찰·작업자와 원료별 실측 무게(actual_g)를 채운다.
    값이 없으면(None/빈 문자열) 해당 필드를 제거(미기록)한다.
    """
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    data = load_batch(path).model_dump(mode="json", exclude_none=True)
    for key, val in (
        ("yield_g", yield_g), ("ph", ph),
        ("observations", observations), ("operator", operator),
    ):
        if val is None or (isinstance(val, str) and not val.strip()):
            data.pop(key, None)
        else:
            data[key] = val.strip() if isinstance(val, str) else val
    amap = actuals_by_id or {}
    for line in data.get("lines", []):
        aid = line.get("id")
        if aid in amap:
            v = amap[aid]
            if v is None:
                line.pop("actual_g", None)
            else:
                line["actual_g"] = v
    new_text = _leading_comments(original) + _dump(data)
    save_with_backup(path, new_text, load_batch)


def set_panel_responses(path: Path | str, responses: list[dict]) -> None:
    """관능 파일의 응답 목록을 통째로 교체한다(추가·수정·삭제 반영).

    각 응답은 panelist가 있어야 하며, scores의 결측(None)과 빈 필드는 제외한다.
    """
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    data = load_panel(path).model_dump(mode="json", exclude_none=True)
    cleaned: list[dict] = []
    for r in responses:
        name = (r.get("panelist") or "").strip()
        if not name:
            continue
        scores = {k: v for k, v in (r.get("scores") or {}).items() if v is not None}
        row: dict = {"panelist": name}
        if (r.get("segment") or "").strip():
            row["segment"] = r["segment"].strip()
        row["scores"] = scores
        if (r.get("comment") or "").strip():
            row["comment"] = r["comment"].strip()
        cleaned.append(row)
    data["responses"] = cleaned
    new_text = _leading_comments(original) + _dump(data)
    save_with_backup(path, new_text, load_panel)


__all__ = [
    "full_factorial_runs",
    "doe_path",
    "stability_path",
    "panel_path",
    "create_doe",
    "create_stability",
    "create_panel",
    "delete_experiment",
    "set_doe_scores",
    "set_stability_observations",
    "set_panel_responses",
    "set_batch_actuals",
]
