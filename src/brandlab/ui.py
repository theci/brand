"""Streamlit UI 공통 헬퍼.

계산 로직은 여기에 두지 않는다. 데이터 로딩(캐시)·폰트·소소한 표시 헬퍼만 담는다.
캐시는 st.cache_data + 파일 mtime 키를 써서, YAML을 편집하고 새로고침하면 반영되게 한다.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from .loader import (
    PROJECT_ROOT,
    BrandLab,
    iter_doe_paths,
    load_ad_terms as _loader_load_ad_terms,
    load_all_stability,
    load_doe,
)
from .models import AdTermList, DoeDesign, Ingredient, StabilitySample


# ---------------------------------------------------------------------------
# 파일 mtime 시그니처 (캐시 무효화 키)
# ---------------------------------------------------------------------------
def data_signature(root: Path | str = PROJECT_ROOT) -> tuple[tuple[str, float], ...]:
    """data/·formulas/·experiments/ 아래 모든 YAML의 (경로, mtime) 튜플.

    파일을 편집하면 mtime이 바뀌어 캐시 키가 달라지고, 새로고침 시 재로딩된다.
    """
    root = Path(root)
    dirs = [root / "data", root / "formulas", root / "experiments"]
    paths: list[Path] = []
    for d in dirs:
        if d.exists():
            paths.extend(d.rglob("*.yaml"))
    return tuple(sorted((str(p), p.stat().st_mtime) for p in paths))


# ---------------------------------------------------------------------------
# 캐시된 로더 (시그니처를 인자로 받아 캐시 무효화)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_lab(_signature, root_str: str) -> BrandLab:
    return BrandLab.load(root_str)


@st.cache_data(show_spinner=False)
def _load_doe_designs(_signature, root_str: str) -> dict[str, DoeDesign]:
    root = Path(root_str)
    return {p.name: load_doe(p) for p in iter_doe_paths(root / "experiments")}


@st.cache_data(show_spinner=False)
def _load_stability(_signature, root_str: str) -> list[StabilitySample]:
    return load_all_stability(Path(root_str) / "experiments")


def load_lab(root: Path | str = PROJECT_ROOT) -> BrandLab:
    root = Path(root)
    return _load_lab(data_signature(root), str(root))


def load_doe_designs(root: Path | str = PROJECT_ROOT) -> dict[str, DoeDesign]:
    root = Path(root)
    return _load_doe_designs(data_signature(root), str(root))


def load_stability_samples(root: Path | str = PROJECT_ROOT) -> list[StabilitySample]:
    root = Path(root)
    return _load_stability(data_signature(root), str(root))


@st.cache_data(show_spinner=False)
def _load_ad_terms(_signature, root_str: str) -> AdTermList:
    return _loader_load_ad_terms(
        Path(root_str) / "data" / "regulatory" / "cosmetics" / "ad_terms.yaml"
    )


def load_ad_terms(root: Path | str = PROJECT_ROOT) -> AdTermList:
    root = Path(root)
    return _load_ad_terms(data_signature(root), str(root))


# ---------------------------------------------------------------------------
# 한글 폰트 (matplotlib 차트 깨짐 방지)
# ---------------------------------------------------------------------------
_KOREAN_FONTS = ["AppleGothic", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR"]


def setup_korean_font() -> str | None:
    """설치된 한글 폰트를 matplotlib 기본 폰트로 설정. 반환: 사용한 폰트명 또는 None."""
    import matplotlib
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in _KOREAN_FONTS:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name
    matplotlib.rcParams["axes.unicode_minus"] = False
    return None


# ---------------------------------------------------------------------------
# 원료 위험 플래그
# ---------------------------------------------------------------------------
def ingredient_flags(ing: Ingredient) -> list[str]:
    """원료의 위험 플래그(붉게 표시할 사유) 목록."""
    flags: list[str] = []
    if not ing.cosmetic_grade:
        flags.append("화장품용 아님")
    if not ing.has_coa:
        flags.append("CoA 없음")
    return flags


def format_won(x: float) -> str:
    return f"{x:,.0f}원"
