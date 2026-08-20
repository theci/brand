"""조향 모듈 테스트."""

from __future__ import annotations

from datetime import date

import pytest

from brandlab.fragrance import (
    blend_sheet,
    ifra_check,
    maceration_due,
    maceration_status,
    note_pyramid,
    note_pyramid_plot,
)
from brandlab.loader import (
    load_aroma_materials,
    load_all_fragrances,
    load_fragrance,
)
from brandlab.models import AromaMaterial, AromaMaterialList, Fragrance


# ---------------------------------------------------------------------------
# 통제된 픽스처
# ---------------------------------------------------------------------------
@pytest.fixture
def materials() -> AromaMaterialList:
    return AromaMaterialList(
        materials=[
            AromaMaterial(
                id="berg", 이름="베르가못", 노트="top", 계열="citrus",
                희석농도_보유=[10], ifra_한도_퍼센트=0.4,
            ),
            AromaMaterial(id="rose", 이름="로즈", 노트="middle", 계열="floral", 희석농도_보유=[10]),
            AromaMaterial(id="sand", 이름="샌달우드", 노트="base", 계열="woody", 희석농도_보유=[10]),
        ]
    )


def _fragrance(**over) -> Fragrance:
    data = {
        "name": "테스트향",
        "version": 1,
        "총량_g": 100,
        "concentration_percent": 20,
        "ethanol_percent": 75,
        "maceration_weeks": 4,
        "accords": [
            {
                "name": "A",
                "materials": [
                    {"id": "berg", "parts": 50, "dilution": 100},  # 원액
                    {"id": "rose", "parts": 30, "dilution": 10},   # 10% 희석
                    {"id": "sand", "parts": 20, "dilution": 10},   # 10% 희석
                ],
            }
        ],
    }
    data.update(over)
    return Fragrance.model_validate(data)


# ---------------------------------------------------------------------------
# 희석 환산 (핵심)
# ---------------------------------------------------------------------------
def test_dilution_conversion(materials):
    # 농도 20%, 총량 100g → 원액 총 20g. total_parts=100.
    #  berg: 50/100×20 = 10g 원액, dilution 100 → 계량 10g
    #  rose: 30/100×20 = 6g 원액, dilution 10 → 계량 60g (10% 희석)
    #  sand: 20/100×20 = 4g 원액, dilution 10 → 계량 40g
    sheet = blend_sheet(_fragrance(), materials)
    by_id = {r.material_id: r for r in sheet.rows}
    assert by_id["berg"].neat_g == pytest.approx(10.0)
    assert by_id["berg"].weigh_g == pytest.approx(10.0)
    assert by_id["rose"].neat_g == pytest.approx(6.0)
    assert by_id["rose"].weigh_g == pytest.approx(60.0)  # 6g 원액 = 60g의 10% 희석액
    # 역으로: 10% 희석 60g의 원액 환산 = 6g
    assert by_id["rose"].weigh_g * by_id["rose"].dilution / 100 == pytest.approx(6.0)


def test_blend_mass_balance(materials):
    sheet = blend_sheet(_fragrance(), materials)
    # 계량 합계 = 10 + 60 + 40 = 110g
    assert sheet.total_weigh_g == pytest.approx(110.0)
    # 희석액이 가져오는 용매 = 110 − 20(원액) = 90g
    assert sheet.solvent_in_dilutions_g == pytest.approx(90.0)
    # 목표 에탄올 = 75g, 이미 희석액에 90g 들어옴 → 추가 −15g (경고)
    assert sheet.ethanol_to_add_g == pytest.approx(-15.0)
    assert any("에탄올" in w for w in sheet.warnings)


def test_blend_positive_ethanol_case(materials):
    # 농도를 낮추면(희석액 적게) 추가 에탄올이 양수
    sheet = blend_sheet(_fragrance(concentration_percent=10), materials)
    # 원액 10g. rose 3g→30g, sand 2g→20g, berg 5g(원액)→5g. total=55
    assert sheet.total_weigh_g == pytest.approx(55.0)
    # 용매 = 55 − 10 = 45. 에탄올 목표 75 → 추가 30
    assert sheet.ethanol_to_add_g == pytest.approx(30.0)
    # 기타 = 100 − 55 − 30 = 15
    assert sheet.other_g == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# 노트 피라미드
# ---------------------------------------------------------------------------
def test_note_pyramid_ratios_sum_100(materials):
    pyr = note_pyramid(_fragrance(), materials)
    # top 10g, middle 6g, base 4g → 50/30/20
    assert pyr.ratios["top"] == pytest.approx(50.0)
    assert pyr.ratios["middle"] == pytest.approx(30.0)
    assert pyr.ratios["base"] == pytest.approx(20.0)
    assert sum(pyr.ratios.values()) == pytest.approx(100.0)


def test_note_pyramid_plot_saved(materials, tmp_path):
    pyr = note_pyramid(_fragrance(), materials)
    out = tmp_path / "pyr.png"
    note_pyramid_plot(pyr, out)
    assert out.exists() and out.stat().st_size > 0


# ---------------------------------------------------------------------------
# IFRA
# ---------------------------------------------------------------------------
def test_ifra_over_limit(materials):
    # berg 원액 10g / 100g = 10% > 한도 0.4% → 초과
    result = ifra_check(_fragrance(), materials)
    berg = next(f for f in result.findings if f.material_id == "berg")
    assert berg.usage_percent == pytest.approx(10.0)
    assert berg.over
    assert result.violations
    # rose/sand는 한도 미입력 → without_limit
    assert "로즈" in result.without_limit


# ---------------------------------------------------------------------------
# 숙성 알림
# ---------------------------------------------------------------------------
def test_maceration_status_states():
    # 시작 6/1 + 4주 = 6/29 완료
    f = _fragrance(maceration_start_date=date(2026, 6, 1), evaluations=[])
    ready = maceration_status(f, today=date(2026, 7, 10))
    assert ready.status == "시향 필요"
    assert ready.ready_date == date(2026, 6, 29)
    assert ready.days == (date(2026, 7, 10) - date(2026, 6, 29)).days

    macer = maceration_status(f, today=date(2026, 6, 10))
    assert macer.status == "숙성중"


def test_maceration_status_done_when_evaluated_after_ready():
    f = _fragrance(
        maceration_start_date=date(2026, 6, 1),
        evaluations=[{"date": date(2026, 7, 1), "timepoints": []}],
    )
    assert maceration_status(f, today=date(2026, 8, 1)).status == "완료"


def test_maceration_due_filters_and_sorts():
    f1 = _fragrance(name="A", maceration_start_date=date(2026, 6, 1), evaluations=[])
    f2 = _fragrance(name="B", maceration_start_date=date(2026, 5, 1), evaluations=[])
    due = maceration_due([f1, f2], today=date(2026, 7, 10))
    # 둘 다 시향 필요, 더 오래된 B가 먼저
    assert [s.name for s in due] == ["B", "A"]


def test_missing_start_date():
    f = _fragrance(maceration_start_date=None)
    assert maceration_status(f, today=date(2026, 8, 1)).status == "시작일 미상"
    assert maceration_due([f], today=date(2026, 8, 1)) == []


# ---------------------------------------------------------------------------
# 실데이터 로드
# ---------------------------------------------------------------------------
def test_real_fragrance_data(project_root):
    materials = load_aroma_materials(project_root / "data" / "aroma_materials.yaml")
    frag = load_fragrance(
        project_root / "formulas" / "fragrance" / "citrus-cologne-v1.yaml"
    )
    pyr = note_pyramid(frag, materials)
    assert sum(pyr.ratios.values()) == pytest.approx(100.0)
    # 베르가못 IFRA 초과가 잡혀야 함
    ifra = ifra_check(frag, materials)
    assert any(v.material_id == "bergamot" for v in ifra.violations)


def test_real_maceration_due(project_root):
    frags = load_all_fragrances(project_root / "formulas")
    due = maceration_due(frags, today=date(2026, 8, 19))
    # 우디 EDP(6/1 시작, 미시향)는 시향 필요
    assert any(s.name == "우디 EDP" for s in due)
    # 시트러스 코롱(8/14 시향함)은 제외
    assert not any(s.name == "시트러스 코롱" for s in due)
