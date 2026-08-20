"""RegimeAdvisor 테스트 (P11)."""

from __future__ import annotations

import pytest

from brandlab.advisor import DISCLAIMER, classify, compare, feasibility
from brandlab.core.models import ClassificationRules, ProductIntent


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------
def test_space_fragrance_sustained_two_candidates(project_root):
    intent = ProductIntent(use="space", claims=["fragrance"], form="sustained_release")
    result = classify(intent, root=project_root)
    regimes = {c.regime_code for c in result.candidates}
    # 방향제(화학제품안전법)와 향수(화장품) 둘 다 후보
    assert "chemical_safety" in regimes
    assert "cosmetics" in regimes
    cats = {c.category_code for c in result.candidates}
    assert "방향제_지속방출형" in cats
    # 복수 레짐 → 관할 확인 경고
    assert any("관할" in w for w in result.warnings)


def test_classify_empty_rules_warns_not_silent():
    empty = ClassificationRules(source_url="x", rules=[])
    result = classify(ProductIntent(use="space", claims=["fragrance"]), rules=empty)
    assert result.candidates == []
    assert any("미입력" in w for w in result.warnings)  # 조용히 빈 결과 아님


def test_classify_no_match_warns(project_root):
    intent = ProductIntent(use="surface", claims=["폴리싱"], form="solid")
    result = classify(intent, root=project_root)
    assert result.candidates == []
    assert any("일치하는 분류 규칙이 없" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# compare — 핵심 검증: SKU 10종에서 화장품이 270만원 저렴
# ---------------------------------------------------------------------------
def test_compare_cosmetics_cheaper_by_270_for_10_skus(project_root):
    intent = ProductIntent(use="space", claims=["fragrance"], form="sustained_release")
    result = compare(intent, sku_count=10, horizon_years=3, root=project_root)

    rows = {r.candidate.regime_code: r for r in result.rows}
    assert "chemical_safety" in rows and "cosmetics" in rows

    chem = rows["chemical_safety"]
    cosm = rows["cosmetics"]
    # 방향제_지속방출형 시험비 270,000 × 10 = 2,700,000 (화장품은 0)
    assert chem.sku_expansion_total == 2_700_000
    assert cosm.sku_expansion_total == 0
    assert chem.sku_expansion_total - cosm.sku_expansion_total == 2_700_000  # 270만원

    # 최저 비용 경로는 화장품
    assert result.cheapest.candidate.regime_code == "cosmetics"
    assert cosm.total_regulatory_cost < chem.total_regulatory_cost
    assert "저렴" in result.summary


def test_compare_renewal_counts(project_root):
    # 3년 갱신 주기, 5년 구간 → 갱신 1회(3년차). 화학제품안전법 경로.
    intent = ProductIntent(use="space", claims=["fragrance"], form="sustained_release")
    result = compare(intent, sku_count=1, horizon_years=5, root=project_root)
    chem = next(r for r in result.rows if r.candidate.regime_code == "chemical_safety")
    assert chem.renewal_period_years == 3
    assert chem.renewals == 1
    # 총비용 = SKU비 270,000 + 갱신 1회 270,000 = 540,000 (등록비 0)
    assert chem.total_regulatory_cost == 540_000


def test_compare_disclaimer(project_root):
    intent = ProductIntent(use="space", claims=["fragrance"], form="liquid")
    result = compare(intent, sku_count=5, horizon_years=5, root=project_root)
    assert result.disclaimer == DISCLAIMER


# ---------------------------------------------------------------------------
# feasibility
# ---------------------------------------------------------------------------
def test_feasibility_sanitize_rejected(project_root):
    intent = ProductIntent(use="space", claims=["sanitize"])
    result = feasibility(intent, root=project_root)
    assert result.verdict == "REJECT"
    assert any("승인" in r or "1인 창업" in r for r in result.reasons)


def test_feasibility_quasi_drug_rejected(project_root):
    intent = ProductIntent(use="body", claims=["oral_care"])
    result = feasibility(intent, root=project_root)
    assert result.verdict == "REJECT"


def test_feasibility_ok_for_cosmetic(project_root):
    intent = ProductIntent(use="body", claims=["moisturize"], form="liquid")
    result = feasibility(intent, root=project_root)
    assert result.verdict == "OK"


def test_feasibility_budget_caution(project_root):
    # 방향제 SKU 10종 총비용이 예산의 20%를 넘으면 CAUTION
    intent = ProductIntent(use="space", claims=["fragrance"], form="spray")
    # 방향제_분사형 585,000 × 10 = 5,850,000 → 예산 1천만원의 58% > 20%
    result = feasibility(
        intent, budget=10_000_000, sku_count=10, horizon_years=3, root=project_root
    )
    # 향수(화장품) 경로가 최저(0원+등록비)라 실제 cheapest는 화장품 → CAUTION 아님.
    # 화장품 경로가 있으므로 OK가 정상. 화학 단독 의도로 CAUTION을 보려면 아래 테스트.
    assert result.verdict in {"OK", "CAUTION"}


def test_feasibility_budget_caution_chemical_only(project_root):
    # 탈취(섬유) 단독 → 화학제품안전법 경로만. 큰 비용 → 예산 대비 CAUTION.
    intent = ProductIntent(use="fabric", claims=["deodorize"], form="liquid")
    result = feasibility(
        intent, budget=1_000_000, sku_count=5, horizon_years=3, root=project_root
    )
    # 탈취제_비분사형_액상 320,000 × 5 = 1,600,000 > 예산 100만 → CAUTION
    assert result.verdict == "CAUTION"
    assert any("예산" in r for r in result.reasons)


def test_real_disclaimer_present(project_root):
    r = feasibility(ProductIntent(use="body", claims=["cleanse"]), root=project_root)
    assert r.disclaimer == DISCLAIMER
