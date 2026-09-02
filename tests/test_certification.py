"""certification: 인증·시험 관문 추적 테스트."""

from __future__ import annotations

from datetime import date, timedelta

from brandlab.certification import (
    due_items,
    gates_with_status,
    progress,
    replace_product_entries,
    save_cert_status,
)
from brandlab.core.models import CertStatus, CertStatusEntry, CertStatusList
from brandlab.dashboard import build_dashboard
from brandlab.loader import BrandLab, load_cert_checklist, load_cert_status


def test_checklist_loads_per_regime():
    for regime in ["cosmetics", "chemical_safety", "food"]:
        cl = load_cert_checklist(regime)
        assert cl is not None and cl.regime == regime
        assert len(cl.gates) >= 3
    assert load_cert_checklist("nope") is None


def test_gates_with_status_and_progress():
    cl = load_cert_checklist("cosmetics")
    status = CertStatusList(entries=[
        CertStatusEntry(product_ref="basic-lotion v2", gate_key=cl.gates[0].key, status=CertStatus.DONE),
    ])
    rows = gates_with_status("basic-lotion v2", cl, status)
    assert len(rows) == len(cl.gates)
    done, total = progress("basic-lotion v2", cl, status)
    assert done == 1 and total == len(cl.gates)


def test_due_items_detects_overdue():
    status = CertStatusList(entries=[
        CertStatusEntry(product_ref="p v1", gate_key="stability",
                        status=CertStatus.PROGRESS, due_date=date.today() - timedelta(days=5)),
        CertStatusEntry(product_ref="p v1", gate_key="cgmp-oem",
                        status=CertStatus.DONE, due_date=date.today() - timedelta(days=5)),
    ])
    due = due_items(status)
    assert len(due) == 1 and due[0].gate_key == "stability"


def test_replace_product_entries_keeps_others():
    status = CertStatusList(entries=[
        CertStatusEntry(product_ref="a v1", gate_key="x", status=CertStatus.DONE),
        CertStatusEntry(product_ref="b v1", gate_key="y", status=CertStatus.WAITING),
    ])
    new = replace_product_entries(status, "a v1", [
        CertStatusEntry(product_ref="a v1", gate_key="z", status=CertStatus.PROGRESS),
    ])
    refs = {(e.product_ref, e.gate_key) for e in new.entries}
    assert ("b v1", "y") in refs and ("a v1", "z") in refs and ("a v1", "x") not in refs


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "brand" / "cert_status.yaml"
    status = CertStatusList(entries=[
        CertStatusEntry(product_ref="p v1", gate_key="stability",
                        status=CertStatus.PROGRESS, due_date=date(2026, 12, 1), cost=300000, owner="나"),
    ])
    save_cert_status(status, path)
    loaded = load_cert_status(path)
    assert loaded.entries[0].cost == 300000
    assert loaded.entries[0].status == CertStatus.PROGRESS


def test_dashboard_cert_overdue_alert():
    lab = BrandLab.load()
    status = CertStatusList(entries=[
        CertStatusEntry(product_ref="basic-lotion v2", gate_key="challenge-test",
                        status=CertStatus.WAITING, due_date=date.today() - timedelta(days=3)),
    ])
    alerts = {a.key: a for a in build_dashboard(lab, cert_status=status)}
    assert "cert_due" in alerts and alerts["cert_due"].severity == "high"
