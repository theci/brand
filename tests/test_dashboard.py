"""dashboard: 홈 대시보드 알림 집계 테스트."""

from __future__ import annotations

from datetime import date, timedelta

from brandlab.dashboard import Alert, build_dashboard
from brandlab.loader import BrandLab
from brandlab.models import StabilitySample


def test_build_dashboard_on_real_data_returns_alerts():
    lab = BrandLab.load()
    alerts = build_dashboard(lab)
    assert isinstance(alerts, list)
    assert all(isinstance(a, Alert) for a in alerts)
    # 심각도 정렬(high가 medium/info보다 앞)
    order = {"high": 0, "medium": 1, "info": 2}
    sev = [order[a.severity] for a in alerts]
    assert sev == sorted(sev)


def test_risky_formula_detected():
    # basic-lotion v1은 HLB '위험'이라 위험 처방 알림에 잡혀야 한다.
    lab = BrandLab.load()
    alerts = {a.key: a for a in build_dashboard(lab)}
    if any(f.slug == "basic-lotion" and f.version == 1 for f in lab.formulas):
        assert "risky_formula" in alerts
        assert any("basic-lotion v1" in x for x in alerts["risky_formula"].items)


def test_overdue_stability_creates_high_alert():
    lab = BrandLab.load()
    sample = StabilitySample.model_validate(
        {
            "sample_id": "T-1",
            "condition": "45C",
            "start_date": (date.today() - timedelta(weeks=9)).isoformat(),
            "observations": [],
        }
    )
    alerts = {a.key: a for a in build_dashboard(lab, stability_samples=[sample])}
    assert "stability_due" in alerts
    assert alerts["stability_due"].severity == "high"
    assert alerts["stability_due"].count >= 1


def test_no_stability_no_alert():
    lab = BrandLab.load()
    keys = {a.key for a in build_dashboard(lab, stability_samples=[])}
    assert "stability_due" not in keys
