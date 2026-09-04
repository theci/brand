"""시장·경쟁 조사 페이지 (STEP 0 기획) — 출처·시장노트·경쟁 편집.

모든 수치·주장은 출처(sources)를 참조한다. 경쟁의 gaps(빈틈)는 포지셔닝 비교표로 승격된다.
"""

from __future__ import annotations

from datetime import date as date_cls

import streamlit as st

from brandlab.core.models import Competitor, MarketNote, Research, ResearchSource
from brandlab.discovery import save_research
from brandlab.loader import load_discovery
from brandlab.ui import setup_korean_font

setup_korean_font()
st.title("시장 · 경쟁 조사 🔎")
st.caption("자료를 구조화해 쌓습니다. 출처는 1급 객체 — 모든 수치·주장이 출처를 답니다.")
st.info(
    "✍️ **이 화면은 모두 직접 입력**입니다. 칸 제목(헤더)에 마우스를 올리면 **예시**가 떠요. "
    "먼저 **출처**를 만들고, 시장·경쟁이 그 출처 id를 `source_ref`로 가리키게 하세요."
)

disc = load_discovery()
research = disc.research

_SRC_COLS = {
    "id": st.column_config.TextColumn("id", help="다른 항목이 source_ref로 참조하는 고유 id. 예: src-review-oy"),
    "title": st.column_config.TextColumn("title", help="자료 이름. 예: 올리브영 수분크림 리뷰 300건 분석"),
    "url": st.column_config.TextColumn("url", help="링크(선택). 예: https://..."),
    "kind": st.column_config.TextColumn("kind", help="자료 종류. 예: 리뷰 / 기사 / 통계 / 논문"),
    "researched_on": st.column_config.TextColumn("researched_on", help="조사일(선택). 예: 2026-03-01"),
    "reliability": st.column_config.NumberColumn("reliability", help="신뢰도 1~5. 예: 3", min_value=1, max_value=5, step=1),
}
_NOTE_COLS = {
    "topic": st.column_config.TextColumn("topic", help="시장 주제. 예: 사무직 여성 보습 니즈"),
    "summary": st.column_config.TextColumn("summary", help="요약. 예: 오후 건조·화장 들뜸 불만이 반복 등장"),
    "metric": st.column_config.TextColumn("metric", help="숫자(선택). 예: 리뷰 300건 중 42% 끈적임 언급"),
    "tags(쉼표)": st.column_config.TextColumn("tags(쉼표)", help="태그, 쉼표로. 예: 보습, 끈적임, 사무직"),
    "source_ref": st.column_config.TextColumn("source_ref", help="위 출처 id. 예: src-review-oy"),
}
_COMP_COLS = {
    "name": st.column_config.TextColumn("name", help="경쟁 제품/브랜드. 예: 대형 A사 수분크림"),
    "category": st.column_config.TextColumn("category", help="분류(선택). 예: 수분크림"),
    "price_band": st.column_config.TextColumn("price_band", help="가격대. 예: 2~3만원"),
    "claims(쉼표)": st.column_config.TextColumn("claims(쉼표)", help="그들의 주장, 쉼표로. 예: 72시간 보습"),
    "strengths(쉼표)": st.column_config.TextColumn("strengths(쉼표)", help="강점, 쉼표로. 예: 브랜드 인지도, 매장 접근성"),
    "gaps(쉼표)": st.column_config.TextColumn("gaps(쉼표)", help="빈틈 — 포지셔닝 비교표로 승격. 예: 끈적임, 흡수 느림, 강한 향"),
    "source_ref": st.column_config.TextColumn("source_ref", help="위 출처 id. 예: src-review-oy"),
}


def _csv(s) -> list[str]:
    return [x.strip() for x in str(s or "").split(",") if x.strip()]


def _s(v) -> str | None:
    return str(v or "").strip() or None


def _int(v, default=3) -> int:
    try:
        return max(1, min(5, int(float(v))))
    except (TypeError, ValueError):
        return default


def _date(v):
    if isinstance(v, date_cls):
        return v
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return date_cls.fromisoformat(s)
    except ValueError:
        return None


# --- 출처 ---
st.subheader("출처 (sources) — id는 다른 항목이 source_ref로 참조")
src_rows = st.data_editor(
    [{"id": s.id, "title": s.title, "url": s.url or "", "kind": s.kind or "",
      "researched_on": s.researched_on.isoformat() if s.researched_on else "",
      "reliability": s.reliability} for s in research.sources]
    or [{"id": "", "title": "", "url": "", "kind": "", "researched_on": "", "reliability": 3}],
    num_rows="dynamic", key="src_tbl", width="stretch", column_config=_SRC_COLS,
)

# --- 시장 노트 ---
st.subheader("시장 노트 (market_notes)")
note_rows = st.data_editor(
    [{"topic": n.topic, "summary": n.summary or "", "metric": n.metric or "",
      "tags(쉼표)": ", ".join(n.tags), "source_ref": n.source_ref or ""} for n in research.market_notes]
    or [{"topic": "", "summary": "", "metric": "", "tags(쉼표)": "", "source_ref": ""}],
    num_rows="dynamic", key="note_tbl", width="stretch", column_config=_NOTE_COLS,
)

# --- 경쟁 ---
st.subheader("경쟁 (competitors) — gaps(빈틈)는 포지셔닝 비교표로 승격")
comp_rows = st.data_editor(
    [{"name": c.name, "category": c.category or "", "price_band": c.price_band or "",
      "claims(쉼표)": ", ".join(c.claims), "strengths(쉼표)": ", ".join(c.strengths),
      "gaps(쉼표)": ", ".join(c.gaps), "source_ref": c.source_ref or ""} for c in research.competitors]
    or [{"name": "", "category": "", "price_band": "", "claims(쉼표)": "",
         "strengths(쉼표)": "", "gaps(쉼표)": "", "source_ref": ""}],
    num_rows="dynamic", key="comp_tbl", width="stretch", column_config=_COMP_COLS,
)

if st.button("💾 조사 저장", type="primary"):
    sources = [
        ResearchSource(id=_s(r.get("id")), title=_s(r.get("title")), url=_s(r.get("url")),
                       kind=_s(r.get("kind")), researched_on=_date(r.get("researched_on")),
                       reliability=_int(r.get("reliability")))
        for r in src_rows if _s(r.get("id")) and _s(r.get("title"))
    ]
    notes = [
        MarketNote(topic=_s(r.get("topic")), summary=_s(r.get("summary")), metric=_s(r.get("metric")),
                   tags=_csv(r.get("tags(쉼표)")), source_ref=_s(r.get("source_ref")))
        for r in note_rows if _s(r.get("topic"))
    ]
    comps = [
        Competitor(name=_s(r.get("name")), category=_s(r.get("category")), price_band=_s(r.get("price_band")),
                   claims=_csv(r.get("claims(쉼표)")), strengths=_csv(r.get("strengths(쉼표)")),
                   gaps=_csv(r.get("gaps(쉼표)")), source_ref=_s(r.get("source_ref")))
        for r in comp_rows if _s(r.get("name"))
    ]
    new = Research(sources=sources, market_notes=notes, competitors=comps)

    # 출처 무결성 경고(막지는 않음)
    src_ids = {s.id for s in sources}
    dangling = sorted(
        {n.source_ref for n in notes if n.source_ref and n.source_ref not in src_ids}
        | {c.source_ref for c in comps if c.source_ref and c.source_ref not in src_ids}
    )
    try:
        path = save_research(new)
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장 실패: {exc}")
    else:
        st.success(f"저장됨: {path}  (출처 {len(sources)}·노트 {len(notes)}·경쟁 {len(comps)})")
        for d in dangling:
            st.warning(f"source_ref '{d}' 가 sources에 없습니다. 출처를 추가하거나 오타를 확인하세요.")
