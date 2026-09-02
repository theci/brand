"""제형 템플릿 — 초보자가 빈 표 대신 '검증된 골격 처방'으로 시작하게 한다.

각 템플릿은 마스터에 실제 존재하는 원료만 쓰고 percent 합계 100을 맞춘다.
instantiate()가 슬러그·버전·제품명을 받아 처방 dict를 만들고, 그걸 create_formula로 저장한다.

※ 모든 함량은 '시작점 예시'다. 사전점검(HLB·배합한도)·안정성으로 반드시 다듬을 것.
"""

from __future__ import annotations

from copy import deepcopy

# key → 템플릿 정의
TEMPLATES: dict[str, dict] = {
    "reed-diffuser": {
        "name": "리드 디퓨저 (방향제)",
        "desc": "상온 블렌딩. 물·가열·유화 없음 — 가장 쉬움. 화학제품안전법.",
        "product": "리드 디퓨저",
        "regime": "chemical_safety",
        "product_type": "leave_on",
        "product_category": "방향제_지속방출형",
        "base_batch_g": 200,
        "fill_volume_ml": 200,
        "packaging": [{"id": "diffuser-bottle-200ml", "qty_per_unit": 1}],
        "phases": [
            {
                "name": "A (상온 블렌딩)",
                "process": "상온에서 용제(DPG·IPM·에탄올)에 향료를 넣고 맑아질 때까지 혼합",
                "ingredients": [
                    {"id": "dpg", "percent": 63.0},
                    {"id": "ethanol", "percent": 12.0},
                    {"id": "ipm", "percent": 5.0},
                    {"id": "lavender-eo", "percent": 20.0},
                ],
            }
        ],
        "notes": "방향제(지속방출형). 향료 20% + 용제. 향 교체로 SKU 확장 용이.",
    },
    "lip-balm": {
        "name": "립밤 (무수 고형)",
        "desc": "왁스+오일 가온 혼합. 물 없어 방부 부담 적음. 무수 입문.",
        "product": "립밤",
        "regime": "cosmetics",
        "product_type": "leave_on",
        "base_batch_g": 100,
        "packaging": [{"id": "lipbalm-tube-10ml", "qty_per_unit": 1}],
        "phases": [
            {
                "name": "A (가온 용융)",
                "process": "왁스·오일을 70~75도로 간접 가온해 완전 용해 후 튜브에 충전",
                "ingredients": [
                    {"id": "beeswax", "percent": 20.0},
                    {"id": "mct", "percent": 40.0},
                    {"id": "castor-oil", "percent": 25.0},
                    {"id": "shea-butter", "percent": 12.0},
                    {"id": "tocopherol", "percent": 3.0},
                ],
            }
        ],
        "notes": "무수 고형. 경도는 왁스 비율로 조절(사전점검엔 HLB 미해당).",
    },
    "face-oil": {
        "name": "페이스 오일 (무수)",
        "desc": "오일 블렌딩만. 산화방지제 필수. 무수 입문.",
        "product": "페이스 오일",
        "regime": "cosmetics",
        "product_type": "leave_on",
        "base_batch_g": 100,
        "packaging": [{"id": "dropper-30ml", "qty_per_unit": 1}],
        "phases": [
            {
                "name": "A (혼합)",
                "process": "상온에서 오일을 혼합하고 산화방지제(토코페롤) 첨가",
                "ingredients": [
                    {"id": "mct", "percent": 40.0},
                    {"id": "jojoba-oil", "percent": 30.0},
                    {"id": "squalane", "percent": 27.0},
                    {"id": "tocopherol", "percent": 3.0},
                ],
            }
        ],
        "notes": "무수 오일. 산패 방지 위해 토코페롤·차광 용기.",
    },
    "basic-lotion": {
        "name": "수분 로션 (O/W 유화)",
        "desc": "가장 어려운 유화. HLB 균형 맞춘 골격(사전점검 적합 기준).",
        "product": "수분 로션",
        "regime": "cosmetics",
        "product_type": "leave_on",
        "base_batch_g": 200,
        "fill_volume_ml": 50,
        "packaging": [{"id": "jar-50ml", "qty_per_unit": 1}],
        "phases": [
            {
                "name": "A (수상)",
                "process": "70~75도로 가열, 잔탄검은 글리세린에 개어 넣어 뭉침 방지",
                "ingredients": [
                    {"id": "water", "percent": 71.8},
                    {"id": "glycerin", "percent": 5.0},
                    {"id": "sodium-hyaluronate", "percent": 0.1},
                    {"id": "xanthan-gum", "percent": 0.3},
                ],
            },
            {
                "name": "B (유상)",
                "process": "70~75도로 가열해 유화제 2종·왁스·오일 완전 용해",
                "ingredients": [
                    {"id": "glyceryl-stearate-citrate", "percent": 3.0},
                    {"id": "polysorbate-80", "percent": 2.0},
                    {"id": "cetyl-alcohol", "percent": 4.0},
                    {"id": "squalane", "percent": 9.0},
                    {"id": "shea-butter", "percent": 1.0},
                ],
            },
            {
                "name": "C (냉각 첨가)",
                "process": "40도 이하로 냉각 후 보존제·향·산화방지제 투입",
                "ingredients": [
                    {"id": "phenoxyethanol", "percent": 1.0},
                    {"id": "hexanediol", "percent": 2.0},
                    {"id": "tocopherol", "percent": 0.5},
                    {"id": "lavender-eo", "percent": 0.3},
                ],
            },
        ],
        "notes": "O/W 로션. 물 함유 → 보존제 필수, 방부력 시험은 외부 랩. 사전점검 HLB 확인.",
    },
    "hydrating-toner": {
        "name": "수분 토너 (단상)",
        "desc": "수상 한 상만. 물 함유 → 보존제 필수. 입문용 수분 제품.",
        "product": "수분 토너",
        "regime": "cosmetics",
        "product_type": "leave_on",
        "base_batch_g": 200,
        "phases": [
            {
                "name": "A (수상)",
                "process": "정제수에 보습·보존 성분을 순서대로 녹이고 pH를 약산성으로 조정",
                "ingredients": [
                    {"id": "water", "percent": 91.5},
                    {"id": "glycerin", "percent": 5.0},
                    {"id": "sodium-hyaluronate", "percent": 0.2},
                    {"id": "hexanediol", "percent": 2.0},
                    {"id": "phenoxyethanol", "percent": 1.0},
                    {"id": "citric-acid", "percent": 0.3},
                ],
            }
        ],
        "notes": "단상 수분 토너. 정제수 필수, 보존제 필수. pH 4.5~6.0 목표.",
    },
}


def list_templates() -> list[tuple[str, str, str]]:
    """(key, name, desc) 목록."""
    return [(k, t["name"], t["desc"]) for k, t in TEMPLATES.items()]


def instantiate(key: str, *, slug: str, version: int = 1, product: str | None = None) -> dict:
    """템플릿을 처방 dict로 인스턴스화한다(create_formula에 넘길 형태)."""
    if key not in TEMPLATES:
        raise KeyError(f"알 수 없는 템플릿: {key}")
    t = TEMPLATES[key]
    data: dict = {
        "product": (product or t["product"]).strip(),
        "slug": slug.strip(),
        "version": int(version),
        "regime": t["regime"],
        "product_type": t["product_type"],
        "status": "개발중",
        "base_batch_g": t.get("base_batch_g", 100),
        "phases": deepcopy(t["phases"]),
    }
    if t.get("product_category"):
        data["product_category"] = t["product_category"]
    if t.get("packaging"):
        data["packaging"] = deepcopy(t["packaging"])
    if t.get("fill_volume_ml"):
        data["fill_volume_ml"] = t["fill_volume_ml"]
    if t.get("notes"):
        data["notes"] = t["notes"]
    return data


__all__ = ["TEMPLATES", "list_templates", "instantiate"]
