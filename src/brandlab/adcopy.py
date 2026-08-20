"""상세페이지 광고 문구 검사기(1차 스크리닝).

data/regulatory/ad_terms.yaml에 등록된 표현만 찾는다. 표현 목록은 코드가 아니라
YAML에서 읽는다. 한국어 형태소 변형("미백", "미백효과", "미백에")을 잡기 위해
단순 substring이 아니라 정규식으로 매칭한다.

통과했다고 합법이 아니다. 반드시 전문가 검토가 필요하다.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from .models import AdTerm, AdTermList

DISCLAIMER = (
    "이 검사는 사전에 등록한 표현만 찾습니다. 통과했다고 해서 합법이 아닙니다. "
    "출시 전 반드시 전문가 검토를 받으십시오."
)

# 위험도 정렬용 순위(높을수록 심각).
_RISK_RANK = {"high": 3, "medium": 2, "low": 1}

# 하이라이트 색상.
_RISK_COLOR = {"high": "#ffc9c9", "medium": "#ffe8cc", "low": "#fff3bf"}

# 표현 뒤에 붙는 한글 조사/어미 변형을 흡수하는 접미 패턴(예: 미백'에', 미백'효과').
_KOREAN_SUFFIX = r"[가-힣]*"


@dataclass
class LintFinding:
    expression: str
    category: str
    risk: str
    start: int
    end: int
    matched_text: str
    suggestion: str | None
    reference: str | None


@dataclass
class LintResult:
    text: str
    findings: list[LintFinding]
    disclaimer: str = DISCLAIMER
    warnings: list[str] = field(default_factory=list)

    def counts_by_risk(self) -> dict[str, int]:
        out = {"high": 0, "medium": 0, "low": 0}
        for f in self.findings:
            out[f.risk] = out.get(f.risk, 0) + 1
        return out


def _compile(term: AdTerm) -> re.Pattern[str]:
    """표현에서 형태소 변형을 잡는 정규식을 만든다.

    - pattern이 지정되면 그대로 사용.
    - 아니면 공백은 \\s*(띄어쓰기 변형), 끝에는 한글 접미(조사/어미) 허용.
    """
    if term.pattern:
        return re.compile(term.pattern)
    tokens = term.expression.split()
    body = r"\s*".join(re.escape(t) for t in tokens)
    return re.compile(body + _KOREAN_SUFFIX)


def lint(text: str, terms: AdTermList | None = None) -> LintResult:
    """텍스트에서 등록된 표현을 찾아 위치·위험도·대체안을 반환한다.

    terms가 없으면 기본 경로(data/regulatory/ad_terms.yaml)에서 로드한다.
    """
    if terms is None:
        from .loader import load_ad_terms

        terms = load_ad_terms()

    warnings: list[str] = []
    if not terms.terms:
        warnings.append(
            "등록된 표현이 없습니다(ad_terms.yaml 비어 있음). 검사를 수행하지 못했습니다(통과가 아님)."
        )

    findings: list[LintFinding] = []
    for term in terms.terms:
        try:
            pat = _compile(term)
        except re.error as exc:
            warnings.append(f"'{term.expression}' 패턴 오류로 건너뜀: {exc}")
            continue
        for m in pat.finditer(text):
            if m.start() == m.end():  # 빈 매치 방지
                continue
            findings.append(
                LintFinding(
                    expression=term.expression,
                    category=term.category.value,
                    risk=term.risk.value,
                    start=m.start(),
                    end=m.end(),
                    matched_text=m.group(),
                    suggestion=term.suggestion,
                    reference=term.reference,
                )
            )

    # 위치순, 같은 위치면 위험도 높은 순
    findings.sort(key=lambda f: (f.start, -_RISK_RANK.get(f.risk, 0)))
    return LintResult(text=text, findings=findings, warnings=warnings)


def highlight_html(text: str, findings: list[LintFinding]) -> str:
    """문제 표현을 위험도 색상으로 감싼 HTML을 만든다.

    겹치는 매치는 문자 단위로 가장 높은 위험도를 적용해 태그 중첩을 피한다.
    HTML은 이스케이프한다.
    """
    n = len(text)
    if n == 0:
        return ""
    risk_at: list[str | None] = [None] * n
    for f in findings:
        for i in range(f.start, min(f.end, n)):
            cur = risk_at[i]
            if cur is None or _RISK_RANK.get(f.risk, 0) > _RISK_RANK.get(cur, 0):
                risk_at[i] = f.risk

    parts: list[str] = []
    i = 0
    while i < n:
        risk = risk_at[i]
        j = i
        while j < n and risk_at[j] == risk:
            j += 1
        chunk = html.escape(text[i:j]).replace("\n", "<br>")
        if risk is None:
            parts.append(chunk)
        else:
            color = _RISK_COLOR.get(risk, "#ffe3e3")
            parts.append(
                f'<mark style="background-color:{color};padding:0 2px;border-radius:3px">'
                f"{chunk}</mark>"
            )
        i = j
    return "".join(parts)


__all__ = [
    "DISCLAIMER",
    "LintFinding",
    "LintResult",
    "lint",
    "highlight_html",
]
