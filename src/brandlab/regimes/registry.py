"""레짐 레지스트리.

새 레짐을 추가하려면: 레짐 모듈을 하나 만들고, 아래 _BUILTIN에 한 줄 추가하면 끝.
(또는 런타임에 register(code, factory)로 등록.)
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..loader import PROJECT_ROOT
from .base import Regime
from .chemical_safety import ChemicalSafetyRegime
from .cosmetics import CosmeticsRegime
from .food import FoodRegime
from .health_functional_food import HealthFunctionalFoodRegime
from .unsupported import BiocideRegime, QuasiDrugRegime

# 레짐 코드 → 팩토리(root를 받아 Regime 인스턴스를 만든다).
# ★ 새 레짐 추가는 여기 한 줄.
_BUILTIN: dict[str, Callable[[Path | str], Regime]] = {
    "cosmetics": CosmeticsRegime,
    "chemical_safety": ChemicalSafetyRegime,
    "food": FoodRegime,
    "health_functional_food": HealthFunctionalFoodRegime,
    "biocide": BiocideRegime,
    "quasi_drug": QuasiDrugRegime,
}

# 런타임 등록분(테스트·플러그인용).
_RUNTIME: dict[str, Callable[[Path | str], Regime]] = {}


class UnknownRegimeError(KeyError):
    """등록되지 않은 레짐 코드를 조회할 때 발생."""


def register(code: str, factory: Callable[[Path | str], Regime]) -> None:
    """레짐을 런타임에 등록한다(한 줄)."""
    _RUNTIME[code] = factory


def available() -> list[str]:
    return sorted({*_BUILTIN, *_RUNTIME})


def get_regime(code: str, root: Path | str = PROJECT_ROOT) -> Regime:
    """코드로 레짐 인스턴스를 얻는다."""
    factory = _RUNTIME.get(code) or _BUILTIN.get(code)
    if factory is None:
        raise UnknownRegimeError(
            f"등록되지 않은 레짐: {code!r}. 사용 가능: {available()}"
        )
    return factory(root)


def regime_for(product, root: Path | str = PROJECT_ROOT) -> Regime:
    """Formula(또는 .regime 속성을 가진 객체)에 맞는 레짐을 반환."""
    return get_regime(getattr(product, "regime", "cosmetics"), root)


__all__ = [
    "register",
    "available",
    "get_regime",
    "regime_for",
    "UnknownRegimeError",
]
