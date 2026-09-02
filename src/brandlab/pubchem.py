"""PubChem(PUG REST) 원료 정보 조회 — 무인증·무료.

원료의 INCI명 또는 CAS로 PubChem을 조회해 CAS·밀도·분자량 등을 가져온다.
데이터 입력 잡무를 줄이는 것이 목적이며, 결과는 사용자가 검토 후 반영한다.

- 인증 불필요(공개 API). 네트워크만 있으면 동작.
- HTTP 호출은 get_json/get_view 콜러블로 주입받아, 테스트에서 목킹할 수 있게 한다.
- CAS는 동의어 목록에서 체크섬이 맞는 값만 채택한다(잘못된 번호 방지).
- 밀도는 실험값(pug_view)이라 표기가 제각각 → 파싱은 g/cm³·g/mL 단위만 신뢰.

주의: 고분자·혼합물·INCI 복합명(예: Glyceryl Stearate Citrate)은 PubChem에서
못 찾을 수 있다. 이 경우 조용히 '미발견'으로 반환한다(오류 아님).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

PUG_REST = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUG_VIEW = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"

# 밀도 신뢰 범위(g/cm³). 이 밖의 값은 파싱 오류로 보고 버린다.
DENSITY_MIN = 0.1
DENSITY_MAX = 3.0

CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
# "1.261 g/cm³", "0.9 g/cu cm at 25 °C", "1.03 g/mL" 등에서 숫자 추출
DENSITY_RE = re.compile(r"([0-9]+\.?[0-9]*)\s*g\s*/\s*(?:cm|cu cm|cc|mL|ml)", re.IGNORECASE)


class PubChemError(Exception):
    """PubChem 조회 실패(네트워크·HTTP 등)."""


@dataclass
class PubChemData:
    cid: int | None = None
    cas: str | None = None
    density: float | None = None
    molecular_weight: float | None = None
    molecular_formula: str | None = None
    iupac_name: str | None = None
    source_url: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.cid is not None


# ---------------------------------------------------------------------------
# HTTP (주입 가능)
# ---------------------------------------------------------------------------
def http_get_json(url: str, *, timeout: float = 10.0) -> dict:
    """URL에서 JSON을 가져온다. 404는 PubChemError로 변환."""
    req = urllib.request.Request(url, headers={"User-Agent": "brandlab/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise PubChemError(f"HTTP {exc.code}: {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PubChemError(f"네트워크 오류: {exc}") from exc


GetJson = Callable[[str], dict]


# ---------------------------------------------------------------------------
# CAS 체크섬
# ---------------------------------------------------------------------------
def valid_cas(cas: str) -> bool:
    """CAS 번호 형식 + 체크섬 검증.

    체크숫자 = (오른쪽부터 1,2,3… 가중치 × 각 자리 숫자)의 합 mod 10.
    """
    if not CAS_RE.match(cas):
        return False
    digits = cas.replace("-", "")
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(d) * w for w, d in enumerate(reversed(body), start=1))
    return total % 10 == check


# ---------------------------------------------------------------------------
# 개별 조회
# ---------------------------------------------------------------------------
def _get_properties(get_json: GetJson, identifier: str) -> dict:
    """이름/CAS로 CID + 분자량·분자식·IUPAC명을 한 번에 조회."""
    url = (
        f"{PUG_REST}/compound/name/{urllib.parse.quote(identifier)}"
        "/property/MolecularWeight,MolecularFormula,IUPACName/JSON"
    )
    data = get_json(url)
    props = data.get("PropertyTable", {}).get("Properties", [])
    if not props:
        raise PubChemError(f"속성 없음: {identifier}")
    return props[0]


def _get_cas(get_json: GetJson, cid: int) -> str | None:
    """동의어 목록에서 체크섬이 맞는 첫 CAS를 반환."""
    url = f"{PUG_REST}/compound/cid/{cid}/synonyms/JSON"
    data = get_json(url)
    info = data.get("InformationList", {}).get("Information", [])
    if not info:
        return None
    for syn in info[0].get("Synonym", []):
        s = syn.strip()
        if valid_cas(s):
            return s
    return None


def collect_strings(obj: object) -> list[str]:
    """중첩 JSON에서 StringWithMarkup.String 값을 모두 모은다(밀도 파싱용)."""
    out: list[str] = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key == "StringWithMarkup" and isinstance(val, list):
                for item in val:
                    s = item.get("String") if isinstance(item, dict) else None
                    if isinstance(s, str):
                        out.append(s)
            else:
                out.extend(collect_strings(val))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(collect_strings(item))
    return out


def parse_density(strings: list[str]) -> float | None:
    """밀도 문자열 목록에서 신뢰 범위 내 첫 g/cm³·g/mL 값을 파싱."""
    for s in strings:
        m = DENSITY_RE.search(s)
        if not m:
            continue
        try:
            val = float(m.group(1))
        except ValueError:
            continue
        if DENSITY_MIN <= val <= DENSITY_MAX:
            return val
    return None


def _get_density(get_json: GetJson, cid: int) -> float | None:
    url = f"{PUG_VIEW}/data/compound/{cid}/JSON?heading=Density"
    data = get_json(url)
    return parse_density(collect_strings(data))


# ---------------------------------------------------------------------------
# 오케스트레이션
# ---------------------------------------------------------------------------
def fetch_pubchem(
    *,
    name: str | None = None,
    cas: str | None = None,
    get_json: GetJson | None = None,
    get_view: GetJson | None = None,
) -> PubChemData:
    """CAS(우선)·이름 순으로 조회해 CID·분자정보·CAS·밀도를 채운다.

    못 찾아도 예외를 던지지 않고 notes에 사유를 남긴 PubChemData를 반환한다.
    (개별 세부 조회 실패도 notes로 흡수 — 부분 성공 허용)
    """
    gj = get_json or http_get_json
    gv = get_view or gj
    notes: list[str] = []

    identifiers = [x for x in (cas, name) if x]
    if not identifiers:
        return PubChemData(notes=["조회할 이름/CAS가 없습니다."])

    props = None
    used = None
    for ident in identifiers:
        try:
            props = _get_properties(gj, ident)
            used = ident
            break
        except PubChemError:
            notes.append(f"'{ident}'(으)로 조회 실패")

    if props is None:
        notes.append("PubChem에서 찾지 못했습니다(고분자·혼합물·복합 INCI명일 수 있음).")
        return PubChemData(notes=notes)

    cid = int(props["CID"])
    mw = props.get("MolecularWeight")
    try:
        mw = float(mw) if mw is not None else None
    except (TypeError, ValueError):
        mw = None

    found_cas = cas
    if not found_cas:
        try:
            found_cas = _get_cas(gj, cid)
            if not found_cas:
                notes.append("동의어에서 유효한 CAS를 찾지 못함")
        except PubChemError:
            notes.append("CAS 조회 실패")

    density = None
    try:
        density = _get_density(gv, cid)
        if density is None:
            notes.append("PubChem에 밀도 실험값 없음/파싱 실패")
    except PubChemError:
        notes.append("밀도 조회 실패")

    return PubChemData(
        cid=cid,
        cas=found_cas,
        density=density,
        molecular_weight=mw,
        molecular_formula=props.get("MolecularFormula"),
        iupac_name=props.get("IUPACName"),
        source_url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
        notes=notes + ([f"조회 식별자: {used}"] if used else []),
    )


__all__ = [
    "PubChemData",
    "PubChemError",
    "fetch_pubchem",
    "valid_cas",
    "parse_density",
    "collect_strings",
    "http_get_json",
    "PUG_REST",
    "PUG_VIEW",
]
