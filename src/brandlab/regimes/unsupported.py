"""명시적으로 지원하지 않는 레짐.

살생물제품(승인제)·의약외품(약사법)은 1인 창업 규모에 맞지 않는다.
이 레짐으로 제품을 만들려 하면 validate가 error를 반환하고 사유를 설명한다.
조용히 통과시키지 않는 것이 이 모듈의 존재 이유다.
"""

from __future__ import annotations

from pathlib import Path

from ..core.models import Formula
from ..loader import PROJECT_ROOT, load_regime_info
from .base import CostBreakdown, Finding, LabelSpec, UnsupportedRegimeError


class _UnsupportedRegime:
    """미지원 레짐 공통 구현. 거부 사유는 regime.yaml에서 읽는다."""

    def __init__(self, regime_code: str, root: Path | str = PROJECT_ROOT) -> None:
        self._root = Path(root)
        self._info = load_regime_info(regime_code, self._root / "data" / "regulatory")
        self.code = self._info.code
        self.law_name = self._info.law_name
        self.display_name = self._info.display_name

    def _reason(self) -> str:
        reason = (self._info.reject_reason or "이 카테고리는 지원하지 않습니다.").strip()
        return f"이 카테고리는 1인 창업 규모에 맞지 않습니다. 이유: {reason}"

    def validate(self, product: Formula) -> list[Finding]:
        return [
            Finding(
                level="error",
                code="regime.unsupported",
                message=self._reason(),
                reference=self._info.source_url,
            )
        ]

    def label_spec(self, product: Formula) -> LabelSpec:
        raise UnsupportedRegimeError(self._reason())

    def entry_cost(self, product: Formula) -> CostBreakdown:
        raise UnsupportedRegimeError(self._reason())

    def lead_time_days(self, product: Formula) -> int:
        raise UnsupportedRegimeError(self._reason())

    def sku_expansion_cost(self, product: Formula) -> int:
        raise UnsupportedRegimeError(self._reason())

    def renewal_period_years(self, product: Formula) -> int | None:
        raise UnsupportedRegimeError(self._reason())


class BiocideRegime(_UnsupportedRegime):
    """살생물제품(살균·살충·방충·기피) — 승인제, 약 12개월, 고액."""

    def __init__(self, root: Path | str = PROJECT_ROOT) -> None:
        super().__init__("biocide", root)


class QuasiDrugRegime(_UnsupportedRegime):
    """의약외품(치약·손소독제 등) — 약사법, 제조업 신고 + 품목허가 별도."""

    def __init__(self, root: Path | str = PROJECT_ROOT) -> None:
        super().__init__("quasi_drug", root)


__all__ = ["BiocideRegime", "QuasiDrugRegime"]
