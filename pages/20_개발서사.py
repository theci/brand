"""개발 서사 페이지(STEP 10) — Build in Public.

이미 쌓인 개발 데이터(버전·배치·DOE·안정성)를 타임라인과 콘텐츠 소재로 바꾼다.
제품은 베껴도 '기술을 아는 창업자'의 서사는 못 베낀다.
"""

from __future__ import annotations

import streamlit as st

from brandlab.loader import load_all_batches, load_all_stability, load_brand_core
from brandlab.narrative import content_seeds, seed_to_prompt, timeline
from brandlab.ui import load_doe_designs, load_lab, setup_korean_font

setup_korean_font()
st.title("개발 서사 🎬 (Build in Public)")
st.caption(
    "버전·배치·실험·안정성 기록을 타임라인과 콘텐츠 소재로 바꿉니다. "
    "개발하는 순간을 찍어두세요 — 실패하는 과정 자체가 못 베끼는 해자(moat)입니다."
)

lab = load_lab()
if not lab.formulas:
    st.info("처방이 없습니다.")
    st.stop()

core = load_brand_core()
batches = load_all_batches()
doe = list(load_doe_designs().values())
stability = load_all_stability()

slugs = sorted({f.slug for f in lab.formulas})
slug = st.selectbox("제품(슬러그)", slugs)

# 타임라인
st.subheader("📅 개발 타임라인")
ev = timeline(slug, lab, batches=batches, doe=doe, stability=stability)
if ev:
    st.table([
        {"일자": e.date.isoformat() if e.date else "—", "구분": e.kind,
         "이벤트": e.title, "내용": e.detail}
        for e in ev
    ])
else:
    st.info("이 제품의 개발 이벤트가 없습니다.")

# 콘텐츠 소재
st.subheader("🎥 콘텐츠 소재 (마케팅 12포맷 매핑)")
seeds = content_seeds(slug, lab, batches=batches, doe=doe, stability=stability)
st.caption("초보 브랜드가 가장 저평가하는 포맷은 3(만든 이유)·11(실패담)입니다. 대기업이 못 하는 사람 이야기.")
for s in seeds:
    with st.expander(f"[{s.format_no}. {s.format_name}] {s.title}"):
        st.write(f"**각도**: {s.angle}")
        st.code(seed_to_prompt(s, core))
        st.download_button(
            "⬇️ 게시 프롬프트 (.txt)",
            seed_to_prompt(s, core),
            file_name=f"seed_{slug}_{s.format_no}.txt",
            key=f"dl_{s.format_no}_{s.title[:6]}",
        )

st.caption(
    "⚠️ 게시 프롬프트는 브랜드 자산·규제 준수·실촬영 안내가 포함됩니다. "
    "제품 실물은 반드시 실촬영하세요."
)
