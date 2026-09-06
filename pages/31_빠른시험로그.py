"""빠른 시험 로그 — 당일 판정 반복 기록.

빠른 반복 R&D의 저마찰 랩노트. 한 세션에 여러 변형을 만들며 관찰·판정을
한 줄씩 남긴다. '접은 것도 데이터'가 되어 같은 실패를 반복하지 않는다.

verdict: keeper(안정성 큐로) / 튜닝(한 축 조정) / 접기(폐기).
데이터: experiments/trials.yaml (없으면 빈 로그).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from brandlab.experiment_edit import save_trials
from brandlab.loader import EXPERIMENTS_DIR, load_trials
from brandlab.ui import setup_korean_font

_COLS = ["date", "base", "changed", "emulsion", "ph", "sensory", "issues", "spin", "verdict", "next_idea"]
_VERDICTS = ["", "keeper", "튜닝", "접기"]
_EMUL = ["", "O", "X"]

setup_korean_font()
st.title("⚡ 빠른 시험 로그")
st.caption(
    "설계→제조→즉시판정→접기 사이클의 랩노트. 한 세션에 변형을 여러 개 남기고 "
    "판정(keeper/튜닝/접기)만 찍으세요. 접은 것도 데이터로 쌓입니다."
)
st.info(
    "표기: **유화** O(성공)/X(깨짐) · **판정** keeper(안정성 큐로)·튜닝(한 축 조정)·접기(폐기). "
    "맨 아래 빈 행에 입력하면 행이 늘어납니다. → **[💾 저장]**"
)

path = EXPERIMENTS_DIR / "trials.yaml"
log = load_trials(path)


def _emul_to_str(v) -> str:
    return "" if v is None else ("O" if v else "X")


rows = []
for t in log.trials:
    rows.append({
        "date": t.date or "", "base": t.base or "", "changed": t.changed or "",
        "emulsion": _emul_to_str(t.emulsion_ok), "ph": t.ph,
        "sensory": t.sensory or "", "issues": t.issues or "", "spin": t.spin or "",
        "verdict": t.verdict or "", "next_idea": t.next_idea or "",
    })
df = pd.DataFrame(rows, columns=_COLS)

edited = st.data_editor(
    df,
    num_rows="dynamic",
    key="trial_editor",
    column_config={
        "date": st.column_config.TextColumn("날짜", help="YYYY-MM-DD", width="small"),
        "base": st.column_config.TextColumn("기준(처방 vN)", help="예: daily-lotion v2"),
        "changed": st.column_config.TextColumn("바꾼 것", help="한 번에 한 축(예: 잔탄 0.3→0.4)"),
        "emulsion": st.column_config.SelectboxColumn("유화", options=_EMUL, width="small"),
        "ph": st.column_config.NumberColumn("pH", min_value=0.0, max_value=14.0, format="%.1f", width="small"),
        "sensory": st.column_config.TextColumn("사용감", help="발림·흡수·백탁·끈적임"),
        "issues": st.column_config.TextColumn("이슈", help="백탁·끈적임·냄새·분리 등"),
        "spin": st.column_config.TextColumn("스핀", help="원심 결과(예: 분리 없음)", width="small"),
        "verdict": st.column_config.SelectboxColumn("판정", options=_VERDICTS, width="small"),
        "next_idea": st.column_config.TextColumn("다음 가설"),
    },
)


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _emul_from_str(v):
    s = (v or "").strip().upper()
    return True if s == "O" else (False if s == "X" else None)


if st.button("💾 저장", type="primary", key="trial_save"):
    out = []
    for r in edited.to_dict(orient="records"):
        ph = r.get("ph")
        out.append({
            "date": _s(r.get("date")), "base": _s(r.get("base")), "changed": _s(r.get("changed")),
            "emulsion_ok": _emul_from_str(r.get("emulsion")),
            "ph": None if ph is None or pd.isna(ph) else float(ph),
            "sensory": _s(r.get("sensory")), "issues": _s(r.get("issues")), "spin": _s(r.get("spin")),
            "verdict": _s(r.get("verdict")), "next_idea": _s(r.get("next_idea")),
        })
    try:
        save_trials(out, path)
        st.success(f"저장됨: {path}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"저장 실패: {exc}")

# --- 요약 + keeper 큐 ---
v = edited["verdict"].fillna("").astype(str).str.strip()
total = int((edited[_COLS].apply(lambda c: c.astype(str).str.strip()).ne("").any(axis=1)).sum())
c1, c2, c3, c4 = st.columns(4)
c1.metric("전체 시험", total)
c2.metric("keeper", int((v == "keeper").sum()))
c3.metric("튜닝", int((v == "튜닝").sum()))
c4.metric("접기", int((v == "접기").sum()))

keepers = edited[v == "keeper"]
st.markdown("**🧊 keeper 큐 — 안정성으로 보낼 것**")
if keepers.empty:
    st.caption("아직 keeper가 없습니다. 당일 관찰이 좋으면 판정을 keeper로 찍으세요.")
else:
    for _, r in keepers.iterrows():
        base = str(r.get("base") or "").strip() or "(기준 미기입)"
        changed = str(r.get("changed") or "").strip()
        st.markdown(f"- **{base}** · {changed}  → `실험·안정성`에 45℃/RT/4℃/동결융해 등록")

st.caption("데이터: experiments/trials.yaml · 저장 시 .bak 백업 후 검증(실패 시 롤백).")
