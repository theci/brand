"""규제 레짐 플러그인.

- base: Regime 프로토콜 + Finding/LabelSpec/CostBreakdown
- cosmetics: 화장품법
- unsupported: 살생물제·의약외품 (명시적 거부)
- registry: 레짐 등록·조회
"""

from .base import (
    CostBreakdown,
    Finding,
    LabelItem,
    LabelSpec,
    Regime,
    UnsupportedRegimeError,
)
from .registry import (
    UnknownRegimeError,
    available,
    get_regime,
    regime_for,
    register,
)

__all__ = [
    "Regime",
    "Finding",
    "LabelItem",
    "LabelSpec",
    "CostBreakdown",
    "UnsupportedRegimeError",
    "register",
    "available",
    "get_regime",
    "regime_for",
    "UnknownRegimeError",
]
