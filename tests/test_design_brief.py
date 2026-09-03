"""디자인 브리프 생성 테스트 — 실제 저장소 데이터 통합."""

from __future__ import annotations

import pytest

from brandlab.core.models import BrandCore, BrandVisual
from brandlab.design_brief import build_brief
from brandlab.loader import BrandLab, load_discovery


@pytest.fixture(scope="module")
def lab():
    return BrandLab.load()


def _formula(lab, slug, version):
    return next(f for f in lab.formulas if f.slug == slug and f.version == version)


def test_brief_core_sections_and_label(lab):
    f = _formula(lab, "daily-lotion", 1)
    md = build_brief(f, lab)
    for h in [
        "# 디자인 브리프",
        "## 1. 제품 개요",
        "## 2. 컨셉 · 톤",
        "## 3. 라벨 법정 필수 기재",
        "### 전성분 표시(안)",
        "## 4. 용기 · 포장 규격",
        "## 5. 비주얼 코드",
        "## 6. 패키지·라벨 아트 프롬프트 (일러스트레이터용)",
        "## 7. 디자이너 확인 체크리스트",
    ]:
        assert h in md, f"누락: {h}"
    assert "Glycerin" in md  # 전성분 INCI 반영
    # 아트 프롬프트: 벡터·일러스트레이터 지정 + 실촬영 가드
    assert "VECTOR" in md and "Adobe Illustrator" in md
    assert "shot in real life" in md  # 제품 실물 실촬영 가드


def test_brief_pulls_concept_from_discovery_and_core(lab):
    f = _formula(lab, "daily-lotion", 1)
    disc = load_discovery()  # 예시 페르소나 포함
    core = BrandCore(
        promise="산뜻하게 오후까지 가는 보습",
        tone_adjectives=["담백한", "정직한"],
        forbidden_words=["완벽"],
        visual=BrandVisual(main_color="#E8F0FE", photo_note="자연광, 차분한 배경"),
    )
    md = build_brief(f, lab, core=core, discovery=disc)
    # 기획(페르소나)·브랜드(약속·톤·금지어·비주얼)가 브리프에 반영
    assert "냉난방 사무실" in md  # primary persona one_line
    assert "산뜻하게 오후까지" in md
    assert "담백한" in md
    assert "완벽" in md  # 금지어 명시
    assert "#E8F0FE" in md  # 비주얼 컬러


def test_brief_empty_concept_notes(lab):
    f = _formula(lab, "daily-lotion", 1)
    md = build_brief(f, lab)  # core·discovery 없음
    assert "비어 있음" in md  # 컨셉 섹션 안내


def test_brief_lists_packaging(lab):
    f = _formula(lab, "daily-lotion", 1)
    md = build_brief(f, lab)
    # daily-lotion 은 포장재를 참조 → 규격 표에 행이 있어야
    assert "| 포장재 | 종류 |" in md
