"""규제 검수 게이트 — 마케팅 텍스트를 내보내기 전 통과시키는 관문.

기존 adcopy.lint(화장품법 표현 스캐너)에 **브랜드 어휘 사전 금지어**를 더해 한 번에 검사한다.
verdict: high 위험(규제 금지표현·브랜드 금지어)이 하나도 없으면 통과.

통과했다고 합법이 아니다(1차 스크리닝). 최종은 전문가·채널 정책 확인.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .adcopy import DISCLAIMER, LintFinding, lint
from .models import AdTermList

_RISK_RANK = {"high": 3, "medium": 2, "low": 1}


@dataclass
class ComplianceResult:
    text: str
    findings: list[LintFinding]
    ok: bool  # high 위험 표현이 없으면 True
    disclaimer: str = DISCLAIMER
    warnings: list[str] = field(default_factory=list)

    def counts_by_risk(self) -> dict[str, int]:
        out = {"high": 0, "medium": 0, "low": 0}
        for f in self.findings:
            out[f.risk] = out.get(f.risk, 0) + 1
        return out


def compliance_check(
    text: str,
    *,
    terms: AdTermList | None = None,
    forbidden_words: list[str] | None = None,
) -> ComplianceResult:
    """규제 표현 + 브랜드 금지어를 함께 검사한다."""
    res = lint(text, terms)
    findings: list[LintFinding] = list(res.findings)

    for raw in forbidden_words or []:
        w = raw.strip()
        if not w:
            continue
        for m in re.finditer(re.escape(w), text):
            if m.start() == m.end():
                continue
            findings.append(
                LintFinding(
                    expression=w,
                    category="브랜드금지어",
                    risk="high",
                    start=m.start(),
                    end=m.end(),
                    matched_text=m.group(),
                    suggestion=None,
                    reference="브랜드 어휘 사전",
                )
            )

    findings.sort(key=lambda f: (f.start, -_RISK_RANK.get(f.risk, 0)))
    ok = not any(f.risk == "high" for f in findings)
    return ComplianceResult(text=text, findings=findings, ok=ok, warnings=res.warnings)


__all__ = ["ComplianceResult", "compliance_check"]
