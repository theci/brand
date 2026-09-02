"""홈 대시보드 — '지금 처리할 것'을 한곳에 모은다.

각 항목은 이미 있는 계산 함수(stability_due·inventory_rows·check_formula·maceration_due)를
재사용해 Alert 목록으로 집계한다. UI(streamlit_app.home)는 이 목록을 표시만 한다.

퇴근 후 도구를 열자마자 '오늘 뭘 해야 하는지'가 보이게 하는 것이 목적이다
(밀린 안정성 관찰·유통기한·위험 처방·CoA 누락·시향 필요).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .certification import due_items as cert_due_items
from .checks import check_formula
from .fragrance import maceration_due
from .inventory import inventory_rows
from .stability import stability_due

# 심각도 정렬 순서
_SEVERITY_ORDER = {"high": 0, "medium": 1, "info": 2}


@dataclass
class Alert:
    key: str
    label: str
    count: int
    items: list[str] = field(default_factory=list)  # 표시용 요약 문자열
    severity: str = "info"  # "high" | "medium" | "info"
    page: str = ""  # 관련 페이지(사용자 안내)


def build_dashboard(
    lab,
    *,
    inventory=None,
    stability_samples=None,
    fragrances=None,
    cert_status=None,
    today: date | None = None,
    near_days: int = 30,
) -> list[Alert]:
    """대시보드 알림 목록을 심각도 순으로 반환한다.

    lab: BrandLab (formulas·ingredients·limits 사용)
    inventory / stability_samples / fragrances: 없으면 해당 항목은 건너뛴다.
    """
    today = today or date.today()
    alerts: list[Alert] = []

    # 1) 밀린 안정성 관찰 — 놓치면 그 시점 데이터가 사라진다(가장 급함)
    if stability_samples:
        due = stability_due(stability_samples, today=today)
        if due:
            items = [
                f"{d.sample_id} · {d.condition} · {d.week}주 (+{d.days_overdue}일 지연)"
                for d in due
            ]
            alerts.append(Alert("stability_due", "밀린 안정성 관찰", len(due), items, "high", "실험"))

    # 1.5) 밀린 인증·시험 관문(기한 경과 + 미완료)
    if cert_status is not None:
        cdue = cert_due_items(cert_status, today=today)
        if cdue:
            items = [
                f"{e.product_ref} · {e.gate_key} (기한 {e.due_date})" for e in cdue
            ]
            alerts.append(Alert("cert_due", "밀린 인증·시험", len(cdue), items, "high", "출시 준비"))

    # 2) 유통기한 만료/임박 원료
    if inventory is not None:
        rows = inventory_rows(inventory, lab.ingredients.index(), today, near_days)
        expired = [r for r in rows if r.status == "만료"]
        near = [r for r in rows if r.status == "임박"]
        if expired:
            alerts.append(
                Alert("expired", "유통기한 만료 원료", len(expired),
                      [r.name for r in expired], "high", "재고")
            )
        if near:
            alerts.append(
                Alert("near_expiry", f"유통기한 임박(≤{near_days}일)", len(near),
                      [f"{r.name} ({r.days_left}일 남음)" for r in near], "medium", "재고")
            )

    # 3) 사전점검 '위험' 처방 — 유화 깨짐(HLB) 또는 배합한도 초과
    risky: list[str] = []
    for f in lab.formulas:
        try:
            res = check_formula(f, ingredients=lab.ingredients, limits=lab.limits)
        except Exception:  # noqa: BLE001 — 개별 처방 검사 실패는 건너뛴다
            continue
        reasons: list[str] = []
        if res.hlb.verdict == "위험":
            reasons.append("HLB 위험(층분리)")
        over = [lf.name for lf in res.limit_findings if lf.status == "초과"]
        if over:
            reasons.append("배합한도 초과: " + ", ".join(over))
        if reasons:
            risky.append(f"{f.slug} v{f.version} — {'; '.join(reasons)}")
    if risky:
        alerts.append(Alert("risky_formula", "사전점검 위험 처방", len(risky), risky, "high", "사전점검"))

    # 4) CoA(성적서) 없는 원료 — 공장 이관·규제에 필요
    no_coa = [ing.name for ing in lab.ingredients.ingredients if not ing.has_coa]
    if no_coa:
        alerts.append(Alert("no_coa", "CoA(성적서) 없는 원료", len(no_coa), no_coa, "medium", "원료"))

    # 5) 시향 필요한 향(숙성 완료)
    if fragrances:
        sniff = maceration_due(fragrances, today=today)
        if sniff:
            items = [f"{s.name} v{s.version} (숙성 후 {s.days}일)" for s in sniff]
            alerts.append(Alert("maceration_due", "시향 필요(숙성 완료)", len(sniff), items, "medium", "조향"))

    # 6) 개발중 처방 — 진행 중 작업 목록(정보)
    developing = [f"{f.slug} v{f.version} — {f.product}" for f in lab.formulas if f.status.value == "개발중"]
    if developing:
        alerts.append(Alert("developing", "개발중 처방", len(developing), developing, "info", "처방"))

    alerts.sort(key=lambda a: _SEVERITY_ORDER.get(a.severity, 9))
    return alerts


__all__ = ["Alert", "build_dashboard"]
