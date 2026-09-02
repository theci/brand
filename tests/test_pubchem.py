"""PubChem 조회 모듈 테스트(네트워크 없이 목킹)."""

from __future__ import annotations

from brandlab.pubchem import (
    collect_strings,
    fetch_pubchem,
    parse_density,
    valid_cas,
)


def test_valid_cas_checksum():
    assert valid_cas("56-81-5")  # 글리세린
    assert valid_cas("110-27-0")  # 이소프로필미리스테이트
    assert not valid_cas("56-81-4")  # 체크섬 틀림
    assert not valid_cas("1234")  # 형식 아님
    assert not valid_cas("abc-12-3")


def test_parse_density_picks_first_valid():
    assert parse_density(["1.26 g/cm³"]) == 1.26
    assert parse_density(["녹지 않음", "0.9 g/cu cm at 25 °C"]) == 0.9
    assert parse_density(["1.03 g/mL"]) == 1.03
    # 범위 밖(5)·단위 없음은 무시
    assert parse_density(["5 g/cm3", "logP 2.3"]) is None
    assert parse_density(["밀도 정보 없음"]) is None


def test_collect_strings_nested():
    obj = {
        "Record": {
            "Section": [
                {"Information": [{"Value": {"StringWithMarkup": [{"String": "1.26 g/cm³"}]}}]}
            ]
        }
    }
    assert "1.26 g/cm³" in collect_strings(obj)


def _fake_glycerin(url: str) -> dict:
    if "property" in url:
        return {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 753,
                        "MolecularWeight": "92.09",
                        "MolecularFormula": "C3H8O3",
                        "IUPACName": "propane-1,2,3-triol",
                    }
                ]
            }
        }
    if "synonyms" in url:
        return {
            "InformationList": {
                "Information": [{"CID": 753, "Synonym": ["Glycerol", "56-81-5", "glycerin"]}]
            }
        }
    if "pug_view" in url:
        return {"StringWithMarkup": [{"String": "1.26 g/cm³"}]}
    raise AssertionError(f"예상치 못한 URL: {url}")


def test_fetch_pubchem_full():
    data = fetch_pubchem(name="Glycerin", get_json=_fake_glycerin)
    assert data.found
    assert data.cid == 753
    assert data.cas == "56-81-5"
    assert data.density == 1.26
    assert data.molecular_weight == 92.09
    assert data.molecular_formula == "C3H8O3"


def test_fetch_pubchem_keeps_given_cas():
    # cas가 이미 있으면 동의어 조회 없이 그대로 사용
    def fake(url: str) -> dict:
        if "property" in url:
            return {"PropertyTable": {"Properties": [{"CID": 1, "MolecularWeight": "1"}]}}
        if "pug_view" in url:
            return {}
        raise AssertionError(f"synonyms를 호출하면 안 됨: {url}")

    data = fetch_pubchem(name="X", cas="56-81-5", get_json=fake)
    assert data.cas == "56-81-5"


def test_fetch_pubchem_not_found():
    from brandlab.pubchem import PubChemError

    def fake(url: str) -> dict:
        raise PubChemError("404")

    data = fetch_pubchem(name="폴리머혼합물", get_json=fake)
    assert not data.found
    assert data.cid is None
    assert any("찾지 못" in n for n in data.notes)
