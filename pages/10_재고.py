"""재고 페이지 — 원료 보유량·유통/개봉 기한 상태 (inventory)."""

from __future__ import annotations

from datetime import date

import streamlit as st

from brandlab.inventory import inventory_rows, unknown_inventory_ids
from brandlab.loader import load_inventory
from brandlab.ui import load_lab, setup_korean_font

st.set_page_config(page_title="재고 · brand-lab", page_icon="📦", layout="wide")
setup_korean_font()
st.title("재고 · 유통기한")
st.caption("보유 원료와 유통기한(개봉 후 사용기한 포함)을 만료/임박/신선으로 판정한다.")

lab = load_lab()
inv = load_inventory()

if not inv.ingredients and not inv.packaging:
    st.info("재고가 없습니다. `data/inventory.yaml` 을 만들어 보유 원료를 등록하세요.")
    st.stop()

unknown = unknown_inventory_ids(inv, lab.ingredients.index(), lab.packaging.index())
for u in unknown:
    st.warning(f"재고 항목 '{u}' 가 마스터(원료/포장)에 없습니다.")

near_days = st.slider("임박 기준(일)", min_value=7, max_value=90, value=30, step=1)
rows = inventory_rows(inv, lab.ingredients.index(), date.today(), near_days)

emoji = {"만료": "🔴 만료", "임박": "🟡 임박", "신선": "🟢 신선", None: "⚪ 미상"}
st.subheader("원료 재고")
st.table(
    [
        {
            "원료": r.name,
            "보유(g)": r.on_hand_g,
            "사용기한": r.effective_expiry.isoformat() if r.effective_expiry else "―",
            "남은일": r.days_left if r.days_left is not None else "―",
            "상태": emoji.get(r.status, "⚪ 미상"),
        }
        for r in rows
    ]
)

expired = [r for r in rows if r.status == "만료"]
near = [r for r in rows if r.status == "임박"]
if expired:
    st.error(f"만료 {len(expired)}종 — 폐기하고 재구매하세요: " + ", ".join(r.name for r in expired))
if near:
    st.warning(f"임박 {len(near)}종 — 우선 소진하거나 발주 준비: " + ", ".join(r.name for r in near))

if inv.packaging:
    st.subheader("포장 재고")
    pidx = lab.packaging.index()
    st.table(
        [
            {"포장재": pidx[p.id].name if p.id in pidx else p.id, "보유(개)": p.on_hand}
            for p in inv.packaging
        ]
    )
