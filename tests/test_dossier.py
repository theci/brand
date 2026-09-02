"""제품표준서(dossier) 생성 테스트 — 실제 저장소 데이터로 통합 검증."""

from __future__ import annotations

from datetime import date

import pytest

from brandlab.dossier import build_dossier
from brandlab.loader import BrandLab, load_all_batches, load_all_stability

TODAY = date(2026, 9, 2)


@pytest.fixture(scope="module")
def lab():
    return BrandLab.load()


def _formula(lab, slug, version):
    return next(f for f in lab.formulas if f.slug == slug and f.version == version)


def test_dossier_has_core_sections(lab):
    f = _formula(lab, "daily-lotion", 1)
    md = build_dossier(
        f, lab, units=1000,
        stability=load_all_stability(), batches=load_all_batches(), today=TODAY,
    )
    for heading in [
        "# 제품표준서",
        "## 1. 제품 개요",
        "## 2. 전성분 (INCI)",
        "## 3. 제조 지시서",
        "## 4. 품질 규격 · 사전점검",
        "## 5. 규제 · 표시 사항",
        "## 6. 안정성 시험 현황",
        "## 7. 원가 요약",
        "## 9. 개정 이력",
    ]:
        assert heading in md, f"누락 섹션: {heading}"


def test_dossier_includes_inci_and_hlb(lab):
    f = _formula(lab, "daily-lotion", 1)
    md = build_dossier(f, lab, today=TODAY)
    assert "Glycerin" in md  # 전성분 INCI
    assert "HLB 유화 균형:** 적합" in md  # 유화 처방 사전점검


def test_dossier_links_stability_and_batch(lab):
    f = _formula(lab, "daily-lotion", 1)
    md = build_dossier(
        f, lab, stability=load_all_stability(), batches=load_all_batches(), today=TODAY
    )
    assert "DL-001" in md  # v1 안정성 시료
    assert "DL-20260902-01" in md  # v1 배치 기록


def test_dossier_without_units_omits_cost(lab):
    f = _formula(lab, "daily-lotion", 1)
    md = build_dossier(f, lab, today=TODAY)
    assert "## 7. 원가 요약" not in md


def test_dossier_non_emulsion_marks_hlb_na(lab):
    f = _formula(lab, "reed-diffuser", 1)
    md = build_dossier(f, lab, today=TODAY)
    assert "HLB 유화 균형:** 해당없음" in md
