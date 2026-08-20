"""규제 판정 엔진 (RegimeAdvisor).

제품 기획 의도 → 가능한 레짐/카테고리 분류, 총 규제비용 비교, 1인 창업 적합성 판정.
이 플랫폼에서 가장 가치 있는 기능.
"""

from .regime_advisor import (
    DISCLAIMER,
    Candidate,
    ClassifyResult,
    CompareResult,
    CompareRow,
    FeasibilityResult,
    classify,
    compare,
    feasibility,
)

__all__ = [
    "DISCLAIMER",
    "Candidate",
    "ClassifyResult",
    "CompareResult",
    "CompareRow",
    "FeasibilityResult",
    "classify",
    "compare",
    "feasibility",
]
