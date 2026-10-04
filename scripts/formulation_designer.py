# -*- coding: utf-8 -*-
"""처방 설계 시트: 학습(아키타입 골격·원료) → 창작(직접 설계)의 고리 완성.

인터랙티브 엑셀(수식·드롭다운·자동검증):
 - 제형 선택 → 그 제형의 목표 골격(%)·배합 주의 자동 표시(VLOOKUP)
 - 원료·역할·투입% 입력 → 그램 자동(배치량 기준) + phase별 합계 + 경고
   (합계≠100%, 물+오일인데 유화제 없음, 수상인데 방부 없음)

데이터 출처:
 - 참고_골격 = 카드_아키타입/*.xlsx 치트시트(전형 구성·주의) 추출
 - 원료_고르기 = 원료_사전(천연, 역할별 상위) + ingredient_knowledge(기능성)

사용: uv run python scripts/formulation_designer.py
산출: 처방_설계_템플릿.xlsx
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from brandlab.herbnoori_detail import ROLE_COLORS, ROLE_ORDER

try:
    from ingredient_knowledge import PALETTE  # type: ignore
except ImportError:  # 스크립트 디렉터리 기준 import 보조
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from ingredient_knowledge import PALETTE

THIN = Side(style="thin", color="D0D5DD")
GRID = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
HDR_FILL = PatternFill("solid", fgColor="E8EEF7")
KEY_FILL = PatternFill("solid", fgColor="FCEFBE")
NOTE_FILL = PatternFill("solid", fgColor="FDECE0")


def _read_archetypes(cards_dir: Path):
    """카드 파일에서 (제형, 골격문자열, 주의) 추출."""
    out = []
    for f in sorted(cards_dir.glob("*.xlsx")):
        if f.name.startswith("~$"):
            continue
        arche = re.sub(r"^\d+_", "", f.stem)
        ws = openpyxl.load_workbook(f, read_only=True).worksheets[0]
        skel, tips = "", ""
        for row in ws.iter_rows(min_row=1, max_row=8, values_only=True):
            v = str(row[0] or "")
            if v.startswith("전형 구성"):
                skel = v.replace("전형 구성(%):", "").strip()
            elif v.startswith("⚠"):
                tips = v.replace("⚠ 이 제형 배합 주의·기본원칙", "").strip().replace("\n", " / ")
        out.append((arche, skel, tips))
    return out


def _palette_rows(glossary: Path, top_per_role: int = 12):
    """원료 고르기용: 천연(사전 역할별 상위) + 기능성 합쳐 역할별로."""
    by_role = defaultdict(list)
    if glossary.exists():
        ws = openpyxl.load_workbook(glossary, read_only=True).worksheets[0]
        # 역할(A) 원료(B) 등장수(C) 대표%(D)
        for row in ws.iter_rows(min_row=2, values_only=True):
            role, name, cnt = row[0], row[1], row[2]
            pct = row[3] if len(row) > 3 else ""
            if role in ROLE_ORDER and name:
                by_role[role].append((str(name), cnt or 0, str(pct or ""), "천연"))
    for role in by_role:
        by_role[role].sort(key=lambda x: -(x[1] or 0))
        by_role[role] = by_role[role][:top_per_role]
    # 기능성 추가
    for role, name, pct, *_ in PALETTE:
        key = role if role in ROLE_ORDER else "기타"
        by_role[key].append((name, 0, pct, "기능성"))
    return by_role


def build(out: Path = Path("처방_설계_템플릿.xlsx")) -> Path:
    arches = _read_archetypes(Path("카드_아키타입"))
    palette = _palette_rows(Path("원료_사전.xlsx"))

    wb = openpyxl.Workbook()

    # ── 시트2 준비: 참고_골격 (VLOOKUP 소스) ─────────────────────────────
    ref = wb.create_sheet("참고_골격")
    for i, t in enumerate(["제형", "목표 골격(전형 %)", "배합 주의"], 1):
        c = ref.cell(1, i, t)
        c.font = Font(bold=True)
        c.fill = HDR_FILL
    ref.column_dimensions["A"].width = 18
    ref.column_dimensions["B"].width = 70
    ref.column_dimensions["C"].width = 70
    for r, (arche, skel, tips) in enumerate(arches, 2):
        ref.cell(r, 1, arche)
        ref.cell(r, 2, skel).alignment = WRAP
        ref.cell(r, 3, tips).alignment = WRAP
        ref.row_dimensions[r].height = 40
    ref.freeze_panes = "A2"
    n_arch = len(arches)

    # ── 시트3: 원료_고르기 ───────────────────────────────────────────────
    pal = wb.create_sheet("원료_고르기")
    for i, t in enumerate(["역할", "원료", "전형/대표%", "구분"], 1):
        c = pal.cell(1, i, t)
        c.font = Font(bold=True)
        c.fill = HDR_FILL
    for col, w in zip("ABCD", (10, 40, 12, 8)):
        pal.column_dimensions[col].width = w
    r = 2
    for role in ROLE_ORDER:
        for name, _cnt, pct, kind in palette.get(role, []):
            pal.cell(r, 1, role).fill = PatternFill(
                "solid", fgColor=ROLE_COLORS.get(role, "F0F0F0"))
            pal.cell(r, 2, name)
            pal.cell(r, 3, pct).alignment = Alignment(horizontal="center")
            pal.cell(r, 4, kind).alignment = Alignment(horizontal="center")
            for ci in range(1, 5):
                pal.cell(r, ci).border = GRID
            r += 1
    pal.freeze_panes = "A2"
    pal.auto_filter.ref = f"A1:D{r - 1}"

    # ── 시트1: 설계 (작업 캔버스) ────────────────────────────────────────
    ws = wb.active
    ws.title = "설계"
    for col, w in zip("ABCDE", (28, 11, 9, 9, 30)):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["F"].width = 2
    ws.column_dimensions["G"].width = 14
    ws.column_dimensions["H"].width = 10

    ws.merge_cells("A1:E1")
    t = ws.cell(1, 1, "처방 설계 시트  —  학습한 골격으로 직접 설계")
    t.font = Font(bold=True, size=14, color="33475B")

    ws.cell(2, 1, "① 제형 선택").font = Font(bold=True)
    ws.cell(2, 1).fill = KEY_FILL
    ws.cell(2, 2).fill = KEY_FILL
    ws.cell(2, 2).border = GRID
    ws.cell(2, 4, "② 총 배치량(g)").font = Font(bold=True)
    ws.cell(2, 4).fill = KEY_FILL
    ws.cell(2, 5, 100)
    ws.cell(2, 5).fill = KEY_FILL
    ws.cell(2, 5).border = GRID
    ws.cell(2, 5).font = Font(bold=True)

    ws.cell(3, 1, "목표 골격(참고)").font = Font(bold=True, size=9, color="55606E")
    ws.merge_cells("B3:E3")
    ws.cell(3, 2, "=IFERROR(VLOOKUP($B$2,참고_골격!$A:$C,2,FALSE),"
                  "\"← 제형을 선택하세요\")").alignment = WRAP
    ws.row_dimensions[3].height = 32
    ws.cell(4, 1, "배합 주의").font = Font(bold=True, size=9, color="7A4A2A")
    ws.merge_cells("B4:E4")
    ws.cell(4, 2, "=IFERROR(VLOOKUP($B$2,참고_골격!$A:$C,3,FALSE),\"\")").alignment = WRAP
    ws.cell(4, 1).fill = NOTE_FILL
    for cc in range(2, 6):
        ws.cell(4, cc).fill = NOTE_FILL
    ws.row_dimensions[4].height = 40

    # 입력 표 헤더(6행), 입력 7~26행.
    R0, R1 = 7, 26
    for i, h in enumerate(["원료명", "역할", "투입%", "그램", "메모"], 1):
        c = ws.cell(6, i, h)
        c.font = Font(bold=True)
        c.fill = HDR_FILL
        c.border = GRID
        c.alignment = Alignment(horizontal="center")
    for r in range(R0, R1 + 1):
        for ci in range(1, 6):
            ws.cell(r, ci).border = GRID
            ws.cell(r, ci).alignment = WRAP
        # 그램 = 투입% × 총량 /100
        ws.cell(r, 4, f"=IF($C{r}=\"\",\"\",ROUND($C{r}*$E$2/100,2))")
    # 합계 행
    ws.cell(R1 + 1, 1, "합계").font = Font(bold=True)
    ws.cell(R1 + 1, 1).fill = HDR_FILL
    ws.cell(R1 + 1, 3, f"=SUM(C{R0}:C{R1})").font = Font(bold=True)
    ws.cell(R1 + 1, 4, f"=SUM(D{R0}:D{R1})").font = Font(bold=True)
    for ci in range(1, 6):
        ws.cell(R1 + 1, ci).border = GRID

    # phase 합계(우측 G:H).
    ws.cell(6, 7, "phase 합계(%)").font = Font(bold=True)
    ws.merge_cells("G6:H6")
    ws.cell(6, 7).fill = HDR_FILL
    for i, role in enumerate(ROLE_ORDER):
        rr = R0 + i
        gc = ws.cell(rr, 7, role)
        gc.fill = PatternFill("solid", fgColor=ROLE_COLORS.get(role, "F0F0F0"))
        gc.border = GRID
        hc = ws.cell(rr, 8,
                     f'=IF(SUMIF($B${R0}:$B${R1},G{rr},$C${R0}:$C${R1})=0,"",'
                     f'ROUND(SUMIF($B${R0}:$B${R1},G{rr},$C${R0}:$C${R1}),1))')
        hc.border = GRID
        hc.alignment = Alignment(horizontal="center")

    # 자동 검증(우측, phase 아래).
    cr = R0 + len(ROLE_ORDER) + 1
    ws.cell(cr, 7, "자동 점검").font = Font(bold=True)
    ws.merge_cells(start_row=cr, start_column=7, end_row=cr, end_column=8)
    ws.cell(cr, 7).fill = KEY_FILL
    checks = [
        (f'=IF(SUM(C{R0}:C{R1})=0,"→ 원료를 입력하세요",'
         f'IF(ABS(SUM(C{R0}:C{R1})-100)<0.5,"✓ 합계 100%",'
         f'"⚠ 합계 "&ROUND(SUM(C{R0}:C{R1}),1)&"% (100 맞추기)"))'),
        (f'=IF(AND(SUMIF(B{R0}:B{R1},"수상",C{R0}:C{R1})>0,'
         f'SUMIF(B{R0}:B{R1},"유상",C{R0}:C{R1})>0,'
         f'SUMIF(B{R0}:B{R1},"유화",C{R0}:C{R1})=0),'
         f'"⚠ 물+오일인데 유화제 없음 → 분리","")'),
        (f'=IF(AND(SUMIF(B{R0}:B{R1},"수상",C{R0}:C{R1})>0,'
         f'SUMIF(B{R0}:B{R1},"방부",C{R0}:C{R1})=0),'
         f'"⚠ 수상 있는데 방부 없음 → 변질 위험(무방부는 냉장·단기)","")'),
        (f'=IF(SUMIF(B{R0}:B{R1},"향",C{R0}:C{R1})>1,'
         f'"⚠ 향 1% 초과 → 자극/규제 주의","")'),
    ]
    for i, fml in enumerate(checks, 1):
        c = ws.cell(cr + i, 7, fml)
        ws.merge_cells(start_row=cr + i, start_column=7, end_row=cr + i, end_column=8)
        c.alignment = WRAP
        c.font = Font(size=9)
        ws.row_dimensions[cr + i].height = 28

    # 드롭다운: 제형(참고_골격 A열), 역할(인라인).
    dv_arche = DataValidation(
        type="list", formula1=f"=참고_골격!$A$2:$A${n_arch + 1}", allow_blank=True)
    ws.add_data_validation(dv_arche)
    dv_arche.add(ws.cell(2, 2))
    dv_role = DataValidation(
        type="list", formula1='"' + ",".join(ROLE_ORDER) + '"', allow_blank=True)
    ws.add_data_validation(dv_role)
    dv_role.add(f"B{R0}:B{R1}")

    # 사용법 메모(하단).
    ur = cr + len(checks) + 2
    ws.merge_cells(start_row=ur, start_column=1, end_row=ur, end_column=5)
    guide = ("사용법: ① 제형 선택(위 골격·주의 참고) → ② 배치량 입력 → "
             "③ 원료·역할·투입% 입력(원료는 '원료_고르기' 시트 참고). "
             "그램·phase합계·점검은 자동. ⚠ 수치는 설계 연습용 — 실제 제조 전 "
             "식약처 고시·공급사 TDS·방부력 테스트 검증.")
    gc = ws.cell(ur, 1, guide)
    gc.alignment = WRAP
    gc.font = Font(size=9, color="55606E")
    gc.fill = NOTE_FILL
    for cc in range(1, 6):
        ws.cell(ur, cc).fill = NOTE_FILL
    ws.row_dimensions[ur].height = 56

    ws.freeze_panes = "A7"
    wb.save(out)
    print(f"처방 설계 템플릿 → {out.name} (제형 {n_arch}종, 원료고르기 포함)")
    return out


if __name__ == "__main__":
    build()
