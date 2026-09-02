"""포장재 페이지 — packaging.yaml 조회 + 등록·삭제.

원료 페이지와 대칭. 추가 전 pydantic 검증, 쓰기 전 .bak 백업, 쓴 뒤 전체 재검증
실패 시 롤백. 삭제는 처방이 참조 중이면 막는다(참조 무결성 보호).
"""

from __future__ import annotations

import streamlit as st

from brandlab.core.models import Packaging
from brandlab.loader import DATA_DIR, load_packaging
from brandlab.master_edit import (
    append_item,
    delete_item,
    render_packaging_block,
    save_with_backup,
)
from brandlab.ui import format_won, load_lab, setup_korean_font

st.set_page_config(page_title="포장재 · brand-lab", page_icon="📦", layout="wide")
setup_korean_font()
st.title("포장재")
st.caption("병·튜브·박스 등 부자재 마스터. 원가·MOQ·장바구니 계산의 기준이 됩니다.")

PKG_PATH = DATA_DIR / "packaging.yaml"


def _num(s: str) -> float | None:
    s = (s or "").strip()
    return None if s == "" else float(s)


def _int(s: str) -> int | None:
    s = (s or "").strip()
    return None if s == "" else int(s)


lab = load_lab()
pkgs = lab.packaging.packaging

with st.expander("➕ 새 포장재 등록"):
    with st.form("add_packaging"):
        st.caption("id·이름·형태는 필수. 나머지는 비워두면 생략됩니다.")
        c1, c2, c3 = st.columns(3)
        new_id = c1.text_input("id (예: jar-30ml)")
        new_name = c2.text_input("이름")
        new_type = c3.text_input("형태(jar/tube/bottle/box/pouch 등)")
        c4, c5, c6 = st.columns(3)
        new_volume = c4.text_input("용량(ml)")
        new_material = c5.text_input("재질(유리/PP/종이 등)")
        new_price = c6.text_input("개당 단가(원)")
        c7, c8 = st.columns(2)
        new_moq = c7.text_input("MOQ(최소주문수량)")
        new_supplier = c8.text_input("공급처")
        new_notes = st.text_input("메모")
        submitted = st.form_submit_button("등록")
    if submitted:
        try:
            fields = {
                "id": new_id.strip(),
                "name": new_name.strip(),
                "type": new_type.strip(),
                "volume_ml": _num(new_volume),
                "material": new_material.strip() or None,
                "unit_price": _num(new_price),
                "moq": _int(new_moq),
                "supplier": new_supplier.strip() or None,
                "notes": new_notes.strip() or None,
            }
            Packaging.model_validate({k: v for k, v in fields.items() if v is not None})
            if fields["id"] in lab.packaging.index():
                st.error(f"이미 존재하는 id입니다: {fields['id']}")
            else:
                block = render_packaging_block(fields)
                original = PKG_PATH.read_text(encoding="utf-8")
                save_with_backup(PKG_PATH, append_item(original, block), load_packaging)
                st.success(f"등록됨: {fields['id']}  (백업: packaging.yaml.bak)")
                st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"등록 실패: {exc}")

with st.expander("🗑️ 포장재 삭제"):
    if not pkgs:
        st.info("삭제할 포장재가 없습니다.")
    else:
        del_options = {f"{p.name} ({p.id})": p.id for p in pkgs}
        del_label = st.selectbox("삭제할 포장재", list(del_options), key="del_pkg_sel")
        del_id = del_options[del_label]
        users = [
            f"{f.slug} v{f.version}"
            for f in lab.formulas
            if any(ref.id == del_id for ref in f.packaging)
        ]
        if users:
            st.warning(
                f"이 포장재를 사용하는 처방이 있어 삭제할 수 없습니다: {', '.join(users)}. "
                "먼저 해당 처방에서 제거하세요."
            )
        else:
            confirm = st.checkbox(f"정말 '{del_id}' 를 삭제합니다", key="del_pkg_confirm")
            if st.button("삭제", type="primary", disabled=not confirm, key="del_pkg_btn"):
                try:
                    original = PKG_PATH.read_text(encoding="utf-8")
                    save_with_backup(
                        PKG_PATH, delete_item(original, del_id), load_packaging
                    )
                    st.success(f"삭제됨: {del_id}  (백업: packaging.yaml.bak)")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"삭제 실패: {exc}")

st.divider()
st.subheader(f"등록된 포장재 {len(pkgs)}종")
st.table(
    [
        {
            "id": p.id,
            "이름": p.name,
            "형태": p.type,
            "용량(ml)": p.volume_ml if p.volume_ml is not None else "-",
            "재질": p.material or "-",
            "단가": format_won(p.unit_price) if p.unit_price is not None else "-",
            "MOQ": p.moq if p.moq is not None else "-",
            "공급처": p.supplier or "-",
        }
        for p in pkgs
    ]
)
st.caption("추가·삭제는 백업(.bak) 후 반영되며, 검증 실패 시 자동 롤백됩니다.")
