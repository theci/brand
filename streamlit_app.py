"""brand-lab Streamlit UI (로컬 실행 전용).

실행:
    streamlit run streamlit_app.py

계산 로직은 모두 src/brandlab의 함수를 호출한다. 이 UI 계층은 표시만 담당한다.
사이드바는 st.navigation으로 **제품 개발 STEP별 섹션**으로 묶여 있다.
새 페이지를 추가하려면 pages/에 파일을 두고 아래 SECTIONS의 알맞은 STEP에 st.Page를 추가한다.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from brandlab.curriculum import (
    current_position,
    days_since_report,
    milestone_status,
    next_quests,
    save_progress,
    streak,
    toggle_quest,
)
from brandlab.dashboard import build_dashboard
from brandlab.loader import (
    load_all_fragrances,
    load_all_panel,
    load_cert_status,
    load_curriculum,
    load_inventory,
    load_progress,
)
from brandlab.ui import load_lab, load_stability_samples, setup_korean_font

st.set_page_config(page_title="brand-lab", page_icon="🧪", layout="wide")

_SEV_RENDER = {"high": st.error, "medium": st.warning, "info": st.info}


def _render_dashboard(lab) -> None:
    """🔔 오늘 할 일 — 지금 처리할 알림을 심각도 순으로 표시."""
    try:
        alerts = build_dashboard(
            lab,
            inventory=load_inventory(),
            stability_samples=load_stability_samples(),
            fragrances=load_all_fragrances(),
            cert_status=load_cert_status(),
            panel_tests=load_all_panel(),
        )
    except Exception as exc:  # noqa: BLE001 — 대시보드 실패가 홈 전체를 막지 않게
        st.caption(f"대시보드 집계 생략: {exc}")
        return

    st.markdown("#### 🔔 오늘 할 일")
    if not alerts:
        st.success("지금 처리할 알림이 없습니다. 좋아요! 👍")
        return
    for a in alerts:
        render = _SEV_RENDER.get(a.severity, st.info)
        render(f"**{a.label}** · {a.count}건  →  사이드바 **{a.page}**")
        with st.expander(f"자세히 ({a.count}건)"):
            for it in a.items[:50]:
                st.write(f"- {it}")
            if len(a.items) > 50:
                st.caption(f"… 외 {len(a.items) - 50}건")


def _render_quests(cur, prog, today) -> None:
    """📍 오늘 — 진행 상태 한 줄 + 오늘의 퀘스트(체크=완료 즉시 저장)."""
    pos = current_position(cur, prog, today)
    strk = streak(prog, today)
    dsr = days_since_report(prog, today)

    dplus = f"D+{pos.day_index}" if pos.day_index is not None else "D+—"
    act_txt = pos.act.title if pos.act else "시작 전"
    week_txt = f" · {pos.week}주차" if pos.week else ""
    fire = f"🔥 {strk}일" if strk else "스트릭 0일"
    st.markdown(f"#### 📍 오늘 · `{dplus}` · **{act_txt}**{week_txt} · {fire}")

    if prog.start_date is None:
        st.info("시작일(D0)을 정하면 며칠째인지 표시돼요 → 사이드바 **오늘·진행**에서 설정")
    if dsr is not None and dsr >= 2:
        st.warning(f"⚠️ 마지막 보고 {dsr}일 전 — **10분 법칙**으로 딱 10분만 복귀하세요. 0과 10분은 하늘과 땅 차이!")

    default_kind = "lab" if today.weekday() >= 5 else "desk"
    labels = {"desk": "🖥️ 데스크(평일)", "lab": "🧪 랩(주말)"}
    kind = st.radio(
        "퀘스트 종류",
        ["desk", "lab"],
        index=0 if default_kind == "desk" else 1,
        format_func=lambda k: labels[k],
        horizontal=True,
        label_visibility="collapsed",
    )
    done_set = set(prog.done)
    todays = next_quests(cur, prog, kind=kind, n=3)
    if not todays:
        st.success(f"{labels[kind]} 퀘스트를 모두 마쳤어요! 🎉 다른 종류나 다음 막으로 가세요.")
    for q in todays:
        est = f"  ·  ⏱ {q.est_min}분" if q.est_min else ""
        checked = st.checkbox(f"{q.text}{est}", value=q.id in done_set, key=f"home_q_{q.id}")
        if checked != (q.id in done_set):
            save_progress(toggle_quest(prog, q.id, checked))
            st.rerun()
    st.caption("체크하면 바로 저장됩니다. 전체 지도·3줄 보고는 사이드바 **오늘·진행**에서.")


def _render_milestones(cur, prog) -> None:
    """🏅 마일스톤 — 막별 진행률 막대."""
    stats = milestone_status(cur, prog)
    earned = sum(1 for m in stats if m.earned)
    st.markdown(f"#### 🏅 마일스톤 · {earned}/{len(stats)}")
    for m in stats:
        badge = "🏅" if m.earned else "⬜"
        ratio = (m.done / m.total) if m.total else 0.0
        st.progress(ratio, text=f"{badge} {m.act.milestone.badge} ({m.done}/{m.total})")


_STEP_GUIDE = """
왼쪽 사이드바는 **제품 개발 순서(STEP)** 로 묶여 있습니다. 위에서 아래로 진행하세요.

- **STEP 0 · 기획·전략** — 페르소나·페인·시장/경쟁 조사 → 문제 정의 → 포지셔닝(뾰족함) → 브랜드 코어. 모든 STEP의 뿌리
- **STEP 1 · 기획·규제** — 무슨 법이고 비용이 얼마인지 먼저 판정
- **STEP 2 · 원료·재료** — 원료·포장재 등록/수정, 재고 확인
- **STEP 3 · 처방·설계** — 처방 생성·수정, 사전점검(HLB·배합한도·**유수분 밸런스**), 조향
- **STEP 4 · 제조·기록** — 배치 실측(수율·pH) 기록
- **STEP 5 · 실험·검증** — DOE·안정성, 관능·패널 평가(시제품 수용도), 버전 비교
- **STEP 6 · 표시·검토** — 전성분·라벨, 광고 문구 검사
- **STEP 7 · 원가·구매** — 손익·마진, 구매 목록, 자금 6:4 배분·런웨이
- **STEP 8 · 문서** — 제품표준서(공장·기관 제출용)
- **STEP 9 · 디자인** — 디자인 브리프(제품 **규격**·라벨 필수기재·톤 사양) → 프롬프트→이미지→**일러스트레이터**(패키지·라벨)
- **STEP 10 · 마케팅·등록** — 개발 서사 · 이미지 프롬프트(상세페이지 소재) → **상품 등록**(상세페이지 완성 후 리스팅) → 고객 접점·후기
- **STEP 11 · 출시 준비** — 인증·시험 관문 추적(등록·시험·표시·생산)

YAML 파일을 편집하거나 화면에서 등록/수정한 뒤 **새로고침(F5)** 하면 반영됩니다.
"""


def home() -> None:
    """홈 — 오늘의 퀘스트·알림·현황을 한눈에(2열 레이아웃)."""
    font = setup_korean_font()
    lab = load_lab()
    today = date.today()
    try:
        cur, prog = load_curriculum(), load_progress()
    except Exception as exc:  # noqa: BLE001 — 커리큘럼 로드 실패가 홈을 막지 않게
        cur = prog = None
        _curr_err = str(exc)

    st.title("🧪 brand-lab")
    st.caption("화장품·생활화학·식품 1인 브랜드 처방 관리 — 로컬 도구")

    main, side = st.columns([2, 1], gap="large")

    with main:
        if cur and prog:
            with st.container(border=True):
                _render_quests(cur, prog, today)
        else:
            st.caption(f"진행 트래커 생략: {_curr_err}")
        with st.container(border=True):
            _render_dashboard(lab)

    with side:
        with st.container(border=True):
            st.markdown("#### 📊 현황")
            d1, d2, d3 = st.columns(3)
            d1.metric("처방", len(lab.formulas))
            d2.metric("원료", len(lab.ingredients.ingredients))
            d3.metric("포장재", len(lab.packaging.packaging))
        if cur and prog:
            with st.container(border=True):
                _render_milestones(cur, prog)

    with st.expander("📖 처음이신가요? 화면 사용법 (STEP 안내)"):
        st.markdown(_STEP_GUIDE)

    if font is None:
        st.caption("⚠️ 한글 폰트 미검출 — 차트 한글이 깨질 수 있습니다(맑은 고딕/나눔고딕 권장).")
    else:
        st.caption(f"차트 한글 폰트: {font}")
    st.caption(
        "ℹ️ 라벨/규정 결과는 1차 스크리닝입니다. 법적 판단이 아니며, 출시 전 식약처·환경부 "
        "고시 원문 대조와 전문가 검토가 필요합니다."
    )


# 제품 개발 STEP별 섹션 (사이드바 헤더로 표시됨)
SECTIONS = {
    "시작": [
        st.Page(home, title="홈", icon="🏠", default=True),
        st.Page("pages/29_진행.py", title="오늘·진행", icon="🎯"),
    ],
    "STEP 0 · 기획·전략": [
        st.Page("pages/25_페르소나.py", title="페르소나·JTBD", icon="🧑"),
        st.Page("pages/26_시장경쟁조사.py", title="시장·경쟁 조사", icon="🔎"),
        st.Page("pages/27_문제정의.py", title="문제 정의", icon="🎯"),
        st.Page("pages/19_포지셔닝.py", title="포지셔닝", icon="🧭"),
        st.Page("pages/16_브랜드코어.py", title="브랜드 코어", icon="🎯"),
    ],
    "STEP 1 · 기획·규제": [
        st.Page("pages/13_규제판정.py", title="규제판정", icon="⚖️"),
    ],
    "STEP 2 · 원료·재료": [
        st.Page("pages/5_원료.py", title="원료", icon="📦"),
        st.Page("pages/30_원료도감.py", title="원료 도감", icon="📚"),
        st.Page("pages/15_포장재.py", title="포장재", icon="📦"),
        st.Page("pages/10_재고.py", title="재고", icon="📊"),
    ],
    "STEP 3 · 처방·설계": [
        st.Page("pages/1_처방.py", title="처방", icon="🧪"),
        st.Page("pages/7_사전점검.py", title="사전점검", icon="🔍"),
        st.Page("pages/14_조향.py", title="조향", icon="🌸"),
    ],
    "STEP 4 · 제조·기록": [
        st.Page("pages/9_배치기록.py", title="배치기록", icon="🧾"),
    ],
    "STEP 5 · 실험·검증": [
        st.Page("pages/4_실험.py", title="실험", icon="🔬"),
        st.Page("pages/28_관능평가.py", title="관능·패널 평가", icon="🧪"),
        st.Page("pages/8_버전비교.py", title="버전비교", icon="🔀"),
    ],
    "STEP 6 · 표시·검토": [
        st.Page("pages/2_라벨.py", title="라벨", icon="🏷️"),
        st.Page("pages/6_문구검사.py", title="문구검사", icon="📝"),
    ],
    "STEP 7 · 원가·구매": [
        st.Page("pages/3_원가.py", title="원가", icon="💰"),
        st.Page("pages/11_장바구니.py", title="장바구니", icon="🛒"),
        st.Page("pages/24_자금.py", title="자금 6:4", icon="🏦"),
    ],
    "STEP 8 · 문서": [
        st.Page("pages/12_제품표준서.py", title="제품표준서", icon="📄"),
    ],
    "STEP 9 · 디자인": [
        st.Page("pages/22_디자인브리프.py", title="디자인 브리프", icon="🎨"),
    ],
    "STEP 10 · 마케팅·등록": [
        st.Page("pages/20_개발서사.py", title="개발 서사", icon="🎬"),
        st.Page("pages/18_이미지프롬프트.py", title="이미지 프롬프트", icon="🖼️"),
        st.Page("pages/17_상품등록.py", title="상품 등록", icon="📝"),
        st.Page("pages/23_고객접점.py", title="고객 접점·후기", icon="💬"),
    ],
    "STEP 11 · 출시 준비": [
        st.Page("pages/21_인증추적.py", title="인증·시험 추적", icon="✅"),
    ],
}

pg = st.navigation(SECTIONS)
pg.run()
