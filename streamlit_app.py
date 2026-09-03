"""brand-lab Streamlit UI (로컬 실행 전용).

실행:
    streamlit run streamlit_app.py

계산 로직은 모두 src/brandlab의 함수를 호출한다. 이 UI 계층은 표시만 담당한다.
사이드바는 st.navigation으로 **제품 개발 STEP별 섹션**으로 묶여 있다.
새 페이지를 추가하려면 pages/에 파일을 두고 아래 SECTIONS의 알맞은 STEP에 st.Page를 추가한다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.dashboard import build_dashboard
from brandlab.loader import load_all_fragrances, load_cert_status, load_inventory
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
        )
    except Exception as exc:  # noqa: BLE001 — 대시보드 실패가 홈 전체를 막지 않게
        st.caption(f"대시보드 집계 생략: {exc}")
        return

    st.subheader("🔔 오늘 할 일")
    if not alerts:
        st.success("✅ 지금 처리할 알림이 없습니다. 좋아요!")
        return
    for a in alerts:
        render = _SEV_RENDER.get(a.severity, st.info)
        render(f"**{a.label}** · {a.count}건  →  사이드바 **{a.page}**")
        with st.expander(f"{a.label} 자세히 ({a.count})"):
            for it in a.items[:50]:
                st.write(f"- {it}")
            if len(a.items) > 50:
                st.caption(f"… 외 {len(a.items) - 50}건")


def home() -> None:
    """홈 — 오늘 할 일(대시보드) + 개요 + 데이터 현황."""
    font = setup_korean_font()
    st.title("🧪 brand-lab")
    st.caption("화장품·생활화학·식품 1인 브랜드 처방 관리 — 로컬 도구")

    lab = load_lab()
    _render_dashboard(lab)

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("처방", f"{len(lab.formulas)}종")
    c2.metric("원료", f"{len(lab.ingredients.ingredients)}종")
    c3.metric("포장재", f"{len(lab.packaging.packaging)}종")

    st.markdown(
        """
### 사용법
왼쪽 사이드바는 **제품 개발 순서(STEP)** 로 묶여 있습니다. 위에서 아래로 진행하세요.

- **STEP 0 · 기획·전략** — 페르소나·페인·시장/경쟁 조사 → 문제 정의 → 포지셔닝(뾰족함) → 브랜드 코어. 모든 STEP의 뿌리
- **STEP 1 · 기획·규제** — 무슨 법이고 비용이 얼마인지 먼저 판정
- **STEP 2 · 원료·재료** — 원료·포장재 등록/수정, 재고 확인
- **STEP 3 · 처방·설계** — 처방 생성·수정, 사전점검(HLB·배합한도), 조향
- **STEP 4 · 제조·기록** — 배치 실측(수율·pH) 기록
- **STEP 5 · 실험·검증** — DOE·안정성, 버전 비교
- **STEP 6 · 표시·검토** — 전성분·라벨, 광고 문구 검사
- **STEP 7 · 원가·구매** — 손익·마진, 구매 목록
- **STEP 8 · 문서** — 제품표준서(공장·기관 제출용)
- **STEP 9 · 상품 등록** — 상세페이지·리스팅 자료 + 규제 검수 게이트
- **STEP 10 · 마케팅** — 개발 서사(Build in Public) · 이미지 프롬프트 빌더 (브랜드 코어는 STEP 0으로 이동)
- **STEP 11 · 출시 준비** — 인증·시험 관문 추적(등록·시험·표시·생산)

YAML 파일을 편집하거나 화면에서 등록/수정한 뒤 **새로고침(F5)** 하면 반영됩니다.
"""
    )

    if font is None:
        st.warning(
            "한글 폰트를 찾지 못했습니다. 차트의 한글이 깨질 수 있습니다 "
            "(맑은 고딕/나눔고딕 등 설치 권장)."
        )
    else:
        st.caption(f"차트 한글 폰트: {font}")

    st.info(
        "이 도구의 라벨/규정 결과는 1차 스크리닝입니다. 법적 판단이 아니며, "
        "출시 전 반드시 식약처·환경부 고시 원문과 대조하고 전문가 검토를 받으십시오."
    )


# 제품 개발 STEP별 섹션 (사이드바 헤더로 표시됨)
SECTIONS = {
    "시작": [
        st.Page(home, title="홈", icon="🏠", default=True),
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
        st.Page("pages/8_버전비교.py", title="버전비교", icon="🔀"),
    ],
    "STEP 6 · 표시·검토": [
        st.Page("pages/2_라벨.py", title="라벨", icon="🏷️"),
        st.Page("pages/6_문구검사.py", title="문구검사", icon="📝"),
    ],
    "STEP 7 · 원가·구매": [
        st.Page("pages/3_원가.py", title="원가", icon="💰"),
        st.Page("pages/11_장바구니.py", title="장바구니", icon="🛒"),
    ],
    "STEP 8 · 문서": [
        st.Page("pages/12_제품표준서.py", title="제품표준서", icon="📄"),
    ],
    "STEP 9 · 상품 등록": [
        st.Page("pages/17_상품등록.py", title="상품 등록", icon="📝"),
    ],
    "STEP 10 · 마케팅": [
        st.Page("pages/20_개발서사.py", title="개발 서사", icon="🎬"),
        st.Page("pages/18_이미지프롬프트.py", title="이미지 프롬프트", icon="🖼️"),
    ],
    "STEP 11 · 출시 준비": [
        st.Page("pages/21_인증추적.py", title="인증·시험 추적", icon="✅"),
    ],
}

pg = st.navigation(SECTIONS)
pg.run()
