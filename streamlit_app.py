"""brand-lab Streamlit UI (로컬 실행 전용).

실행:
    uv run streamlit run streamlit_app.py

계산 로직은 모두 src/brandlab의 함수를 호출한다. 이 UI 계층은 표시만 담당한다.
왼쪽 사이드바에서 페이지(처방/라벨/원가/실험/원료)를 선택한다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.ui import load_lab, setup_korean_font

st.set_page_config(page_title="brand-lab", page_icon="🧪", layout="wide")
setup_korean_font()

st.title("🧪 brand-lab")
st.caption("화장품 1인 브랜드 처방 관리 — 로컬 도구")

lab = load_lab()
font = setup_korean_font()

col1, col2, col3 = st.columns(3)
col1.metric("처방", f"{len(lab.formulas)}종")
col2.metric("원료", f"{len(lab.ingredients.ingredients)}종")
col3.metric("포장재", f"{len(lab.packaging.packaging)}종")

st.markdown(
    """
### 페이지 (왼쪽 사이드바)

**처방·제조·라벨·원가**
- **처방** — 생성·수정(새 버전/덮어쓰기)·삭제 + 상별 표, 배치 크기 슬라이더로 g 실시간 환산, 배치 지시서 다운로드
- **라벨** — 전성분 문자열, 알러젠 판정, 표시 의무, 배합한도 체크
- **원가** — 수량·판매가 입력 → 원가·손익·MOQ 병목, 마진 곡선

**R&D 개발 루프**
- **사전점검** — HLB 유화 균형 + 배합한도 (제조 전 실패 차단)
- **버전비교** — 처방 v1↔v2 원료·함량·원가 변화
- **배치기록** — 실측(수율·pH) 기록·요약, 새 기록지 생성
- **실험** — DOE 설계 생성(2^k 자동)·안정성 시료 등록 + DOE 주효과 플롯, 안정성 현황·밀린 관찰 알림

**원료·재고·구매**
- **원료** — 조회·검색 + 등록·수정·삭제 + PubChem 자동채움(CAS·밀도)
- **포장재** — 병·튜브·박스 등 부자재 조회 + 등록·수정·삭제
- **재고** — 보유량·유통기한(만료/임박/신선)
- **장바구니** — 재고 차감 후 구매 목록·비용

**문서·규제·조향·문구**
- **제품표준서** — 처방·전성분·제조·규제·안정성·원가를 1문서로
- **규제판정** — 의도 → 레짐 분류·비용비교·적합성
- **조향** — 블렌드 계량표·노트 피라미드·IFRA·숙성 알림
- **문구검사** — 상세페이지 금지·주의 표현 하이라이트

YAML 파일을 편집한 뒤 **새로고침**하면 반영됩니다.
"""
)

if font is None:
    st.warning(
        "한글 폰트를 찾지 못했습니다. 차트의 한글이 깨질 수 있습니다 "
        "(AppleGothic/NanumGothic 등 설치 권장)."
    )
else:
    st.caption(f"차트 한글 폰트: {font}")

st.info(
    "이 도구의 라벨/규정 결과는 1차 스크리닝입니다. 법적 판단이 아니며, "
    "출시 전 반드시 식약처 고시 원문과 대조하고 전문가 검토를 받으십시오."
)
