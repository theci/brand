"""인증·시험 추적 — '팔기 위해 뭘 언제까지' 관문 체크리스트와 진행 상태.

레짐별 관문(checklist.yaml)에 제품별 진행 상태(cert_status.yaml)를 얹어 진척·지연을 본다.
지연(기한 경과 + 미완료)은 홈 대시보드 '밀린 인증'으로 올라간다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from .core.models import (
    CertChecklist,
    CertGate,
    CertStatus,
    CertStatusEntry,
    CertStatusList,
)
from .loader import DATA_DIR


@dataclass
class GateRow:
    gate: CertGate
    entry: CertStatusEntry | None  # 없으면 기본 대기


def _index(status: CertStatusList) -> dict[tuple[str, str], CertStatusEntry]:
    return {(e.product_ref, e.gate_key): e for e in status.entries}


def gates_with_status(
    product_ref: str, checklist: CertChecklist, status: CertStatusList
) -> list[GateRow]:
    """관문 정의에 제품별 상태를 결합한다."""
    idx = _index(status)
    return [GateRow(gate=g, entry=idx.get((product_ref, g.key))) for g in checklist.gates]


def progress(product_ref: str, checklist: CertChecklist, status: CertStatusList) -> tuple[int, int]:
    """(완료 수, 전체 수)."""
    idx = _index(status)
    total = len(checklist.gates)
    done = sum(
        1
        for g in checklist.gates
        if (e := idx.get((product_ref, g.key))) and e.status == CertStatus.DONE
    )
    return done, total


def due_items(status: CertStatusList, today: date | None = None) -> list[CertStatusEntry]:
    """기한이 지났는데 아직 완료가 아닌 관문(지연 큰 순)."""
    today = today or date.today()
    due = [
        e
        for e in status.entries
        if e.due_date and e.status != CertStatus.DONE and e.due_date < today
    ]
    due.sort(key=lambda e: e.due_date or today)
    return due


def replace_product_entries(
    status: CertStatusList, product_ref: str, entries: list[CertStatusEntry]
) -> CertStatusList:
    """특정 제품의 상태를 새 목록으로 교체(다른 제품 상태는 유지)."""
    kept = [e for e in status.entries if e.product_ref != product_ref]
    return CertStatusList(entries=kept + entries)


def save_cert_status(
    status: CertStatusList, path: Path | str = DATA_DIR / "brand" / "cert_status.yaml"
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(status.model_dump(exclude_none=True, mode="json"),
                       allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


__all__ = [
    "GateRow",
    "gates_with_status",
    "progress",
    "due_items",
    "replace_product_entries",
    "save_cert_status",
]
