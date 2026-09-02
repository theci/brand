"""공장 제출 패키지 — 제품표준서 + 공장용 커버레터/요청 체크리스트를 zip으로 묶는다.

집(R&D)에서 완성한 처방을 OEM/ODM 공장에 넘길 때 필요한 문서를 한 번에 준비한다.
  - 00_공장제출_안내.md : 제품 개요 + 동봉 문서 + 공장에 요청할 것(견적·MOQ·QA/QC·샘플) + 주의
  - 01_제품표준서_*.md  : 처방·전성분·제조·규제·안정성·원가·배치이력 (build_dossier)

※ 처방은 영업비밀이다. 커버에 NDA·규제 확인 주의를 명시한다.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

from .core.models import Formula
from .dossier import build_dossier


def factory_cover(formula: Formula, lab, *, units: int | None = None, today: date | None = None) -> str:
    """공장 제출용 커버레터 + 요청 체크리스트(markdown)."""
    today = today or date.today()
    fill = ""
    if formula.fill_volume_ml is not None:
        fill = f"{formula.fill_volume_ml:g} ml"
    elif formula.net_weight_g is not None:
        fill = f"{formula.net_weight_g:g} g"
    lines = [
        f"# 공장 제출 패키지 — {formula.product} ({formula.slug} v{formula.version})",
        "",
        f"- 생성일: {today.isoformat()}",
        f"- 레짐(적용 법규): {formula.regime}",
        f"- 제품 형태: {formula.product_type.value}"
        + (f" · 품목: {formula.product_category}" if formula.product_category else ""),
        f"- 기준 배치: {formula.base_batch_g:g} g" + (f" · 충전량: {fill}" if fill else ""),
        f"- 개발 상태: {formula.status.value}",
        "",
        "## 동봉 문서",
        f"- **01_제품표준서_{formula.slug}_v{formula.version}.md** — 처방·전성분·제조지시·"
        "품질규격·규제·안정성·원가·배치이력",
        "",
        "## 공장에 요청하는 것 (회신 요망)",
        "- [ ] 견적: 단가 · **MOQ(최소주문수량)** · 리드타임",
        "- [ ] 원료 대체 가능 여부 및 **각 원료 CoA(성적서)** 제공",
        "- [ ] 안정성·**방부력(챌린지) 시험** 대행 가능 여부(물 함유 제품 필수)",
        "- [ ] 소량 **파일럿(시생산)** 가능 여부 및 샘플 일정",
        "- [ ] **CGMP/인증** 현황, 책임판매업 위수탁 경험",
        "",
        "## QA/QC 합의 항목",
        "- 수율 · pH · 외관 · 점도 규격 및 허용 범위",
        "- 배치별 시험성적서(CoA) 발급, 보관 샘플(리테인) 정책",
        "- 보관·유통 조건(상온/냉장/차광), 사용기한 설정 근거",
        "",
        "## ⚠️ 주의",
        "- 본 처방은 **영업비밀**입니다. **NDA(비밀유지계약) 체결 후** 공유하세요.",
        "- 문서의 모든 **규제·배합한도·원가 수치는 예시**이며, 식약처·환경부 기준으로 재확인이 필요합니다.",
        "- 판매를 위해서는 **책임판매업 등록 + CGMP 공장 위탁 생산**이 전제됩니다(집에서 만든 제품 판매 불가).",
    ]
    if units:
        lines.append("")
        lines.append(f"> 원가 요약은 기준 수량 {units:,}개로 산정되었습니다(가정값 — 실제 견적으로 교체).")
    return "\n".join(lines) + "\n"


def build_package(
    formula: Formula,
    lab,
    *,
    units: int | None = None,
    stability=None,
    batches=None,
    today: date | None = None,
) -> dict[str, str]:
    """제출 패키지 파일 목록 {파일명: 내용}."""
    dossier_md = build_dossier(
        formula, lab, units=units, stability=stability or [], batches=batches or []
    )
    return {
        "00_공장제출_안내.md": factory_cover(formula, lab, units=units, today=today),
        f"01_제품표준서_{formula.slug}_v{formula.version}.md": dossier_md,
    }


def zip_package(files: dict[str, str]) -> bytes:
    """{파일명: 내용} → zip 바이트."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content.encode("utf-8"))
    return buf.getvalue()


__all__ = ["factory_cover", "build_package", "zip_package"]
