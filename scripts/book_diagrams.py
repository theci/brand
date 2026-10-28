"""print_book.py 용 개념 도식(SVG). 표에서 나오는 도식은 워크북 값을 직접 읽는다(창작 아님).

viewBox 폭 600 = 본문 폭 148mm (1 단위 ≈ 0.25mm, 글자 11 ≈ 7.8pt).
"""

from __future__ import annotations

import html

NAVY, NAVY2, ACC, SKY, PALE, GREEN, LINE, INK, GRAY = (
    "#1f3a5f", "#33475b", "#b5562b", "#ddebf7", "#f3f6fa", "#2f6b3a", "#c9d3de", "#1d2733", "#6b7886",
)
WATER, OIL = "#d7ecf7", "#f6e3b4"


def _e(s) -> str:
    return html.escape(str(s))


def wrap(s: str, n: int) -> list[str]:
    """n자 안팎으로 줄 나눔(공백 우선)."""
    out, cur = [], ""
    for w in str(s).split(" "):
        while len(w) > n:
            if cur:
                out.append(cur)
                cur = ""
            out.append(w[:n])
            w = w[n:]
        if len(cur) + len(w) + (1 if cur else 0) > n:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        out.append(cur)
    return out


def T(x, y, s, size=11, weight=400, anchor="start", fill=INK, lh=1.3, n=None):
    lines = wrap(s, n) if n else [str(s)]
    spans = "".join(
        f'<tspan x="{x}" dy="{0 if i == 0 else size * lh:.1f}">{_e(l)}</tspan>' for i, l in enumerate(lines)
    )
    return f'<text x="{x}" y="{y}" font-family="P" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{spans}</text>'


def R(x, y, w, h, fill=PALE, stroke="none", rx=6, sw=1.2, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'


def A(x1, y1, x2, y2, color=GRAY, w=1.6):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}" marker-end="url(#ah)"/>'


def svg(h, body, caption) -> str:
    defs = (
        '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{GRAY}"/></marker></defs>'
    )
    return (
        f'<figure class="diagram"><svg viewBox="0 0 600 {h}" xmlns="http://www.w3.org/2000/svg">{defs}{body}</svg>'
        f"<figcaption>{_e(caption)}</figcaption></figure>"
    )


def _cells(ws, r, n):
    return [("" if ws.cell(r, c).value is None else str(ws.cell(r, c).value)) for c in range(1, n + 1)]


def _find(ws, prefix, col=1):
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, col).value
        if isinstance(v, str) and v.startswith(prefix):
            return r
    raise KeyError(prefix)


# ── 1권 ────────────────────────────────────────────────────────────────────
def daily_loop(wb):
    ws = wb["읽어보기"]
    r0 = _find(ws, "■ 하루 1원료 루프")
    steps = [_cells(ws, r0 + i, 2) for i in range(1, 5)]
    pos = [(300, 60), (500, 160), (300, 260), (100, 160)]
    b = [f'<circle cx="300" cy="160" r="62" fill="{SKY}"/>', T(300, 154, "하루 1원료", 14, 800, "middle", NAVY), T(300, 174, "15분", 12, 600, "middle", ACC)]
    for i, ((x, y), (lab, desc)) in enumerate(zip(pos, steps)):
        b.append(R(x - 92, y - 40, 184, 80, "#fff", NAVY, 8))
        b.append(T(x, y - 18, lab, 12, 800, "middle", NAVY))
        b.append(T(x, y + 1, desc.split("—")[0].split(".")[0], 9.5, 400, "middle", INK, n=22))
    for (x1, y1, x2, y2) in [(392, 75, 470, 118), (470, 202, 392, 245), (208, 245, 130, 202), (130, 118, 208, 75)]:
        b.append(A(x1, y1, x2, y2, ACC, 2))
    return svg(320, "".join(b), "하루 1원료 루프 — 읽기 → 손 → 기록 → 비교 (읽어보기)")


def card_anatomy(wb):
    ws = wb["원료 카드"]
    groups = []
    for m in sorted(ws.merged_cells.ranges, key=lambda m: m.min_col):
        if m.min_row == 3 and m.max_row == 3:
            groups.append(str(ws.cell(3, m.min_col).value))
    groups = [g for g in groups if not g.startswith("✍")]  # 내 기록 = 아래 노란 줄
    b = [R(40, 10, 520, 290, "#fff", "#9fb0c3", 8)]
    b.append(R(40, 10, 520, 38, NAVY, "none", 8))
    b.append(T(56, 35, "No  원료 이름  INCI", 12, 700, "start", "#fff"))
    b.append(T(544, 35, "역할 · ✓보유", 10, 700, "end", "#fff"))
    half = (len(groups) + 1) // 2
    for i, g in enumerate(groups):
        col, row = (0, i) if i < half else (1, i - half)
        x, y = 56 + col * 256, 62 + row * 62
        b.append(R(x, y, 236, 52, PALE, "none", 4))
        b.append(T(x + 10, y + 20, g.split("—")[0].strip(), 11, 700, "start", ACC))
        if "—" in g:
            b.append(T(x + 10, y + 38, g.split("—", 1)[1].strip(), 9.5, 400, "start", GRAY, n=30))
    b.append(R(40, 262, 520, 38, "#fffbea", "none", 0))
    b.append(T(56, 286, "✍ 손테스트 ☐   숙련도 0 모름 · 1 읽음 · 2 만져봄 · 3 처방에 씀   메모 ____", 10, 600, "start", GRAY))
    return svg(310, "".join(b), "원료 카드 읽는 법 — 왼쪽 위 ①부터 차례로, 아래 노란 줄은 손으로 적는 칸")


def emulsion(wb):
    b = []
    panels = [
        ("가용화 (토너·미스트)", "물 + 소량 오일·향을 미셀로 감싸 투명", "water_micelle"),
        ("O/W 유화 (로션·크림)", "물 속 기름 방울을 유화제가 둘러쌈 → 유백", "emul"),
        ("젤 (잔탄·카보머)", "고분자 망이 물을 붙잡아 점도", "gel"),
    ]
    for i, (t, d, kind) in enumerate(panels):
        x = 10 + i * 200
        b.append(R(x, 10, 180, 180, WATER, "none", 90 if False else 10))
        cx, cy = x + 90, 100
        if kind == "water_micelle":
            for dx, dy in [(-40, -30), (35, -35), (0, 10), (-35, 45), (40, 40)]:
                b.append(f'<circle cx="{cx + dx}" cy="{cy + dy}" r="7" fill="{OIL}" stroke="{ACC}" stroke-width="1.2" stroke-dasharray="2 2"/>')
        elif kind == "emul":
            for dx, dy, r in [(-38, -30, 22), (36, -26, 18), (-10, 32, 26), (44, 40, 14)]:
                b.append(f'<circle cx="{cx + dx}" cy="{cy + dy}" r="{r}" fill="{OIL}" stroke="{ACC}" stroke-width="2.2"/>')
            b.append(T(cx - 38, cy - 26, "오일", 9, 700, "middle", ACC))
        else:
            import math
            for k in range(7):
                y0 = 30 + k * 22
                pts = " ".join(f"{x + 12 + j * 12},{y0 + 8 * math.sin(j + k)}" for j in range(14))
                b.append(f'<polyline points="{pts}" fill="none" stroke="{NAVY2}" stroke-width="1.3" opacity=".7"/>')
        b.append(T(x + 90, 212, t, 11.5, 800, "middle", NAVY))
        b.append(T(x + 90, 230, d, 9.5, 400, "middle", GRAY, n=20))
    b.append(T(300, 275, "파란 바탕 = 물(수상)   노란 방울 = 기름(유상)   주황 테두리 = 유화제·가용화제", 9.5, 600, "middle", GRAY))
    return svg(285, "".join(b), "제형의 뼈대 3가지 — 같은 물·기름이라도 무엇이 잡아 주느냐로 제형이 갈린다")


def texture_levers(wb):
    ws = wb["감촉 레버"]
    want = {}
    for r in range(5, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if a:
            want[str(a)] = str(ws.cell(r, 2).value or "")
    corners = [
        ("더 쫀쫀(바디감)", 300, 40),
        ("더 묽게(로션화)", 300, 330),
        ("더 산뜻하게(덜 끈적)", 95, 185),
        ("보호막·리치하게", 505, 185),
    ]
    b = [A(300, 185, 300, 72, NAVY), A(300, 185, 300, 298, NAVY), A(300, 185, 182, 185, NAVY), A(300, 185, 418, 185, NAVY)]
    b.append(f'<circle cx="300" cy="185" r="46" fill="{SKY}"/>')
    b.append(T(300, 180, "지금 배치", 11, 800, "middle", NAVY))
    b.append(T(300, 196, "한 번에 한 변수", 9, 600, "middle", ACC))
    for lab, x, y in corners:
        if lab not in want:
            continue
        b.append(R(x - 92, y - 28, 184, 56, "#fff", NAVY, 8))
        b.append(T(x, y - 8, lab, 11, 800, "middle", NAVY))
        b.append(T(x, y + 10, "↑ " + want[lab], 9.5, 500, "middle", ACC, n=24))
    return svg(370, "".join(b), "감촉 레버 지도 — 가고 싶은 방향의 '올리기' 원료 하나만 바꿔 다시 만든다 (표의 일부)")


# ── 2권 ────────────────────────────────────────────────────────────────────
def dev_loop(wb):
    ws = wb["읽어보기"]
    r0 = _find(ws, "처음이라면")
    steps = [str(ws.cell(r0 + i, 2).value) for i in range(1, 6)]
    labels = ["레시피 고르기", "100g 만들기", "개발일지 한 줄", "트러블슈팅", "한 가지만 바꿔 다시"]
    import math

    b = [f'<circle cx="300" cy="170" r="58" fill="{SKY}"/>', T(300, 166, "개발의 전부", 13, 800, "middle", NAVY), T(300, 184, "이 반복", 11, 600, "middle", ACC)]
    pts = []
    for i in range(5):
        ang = -math.pi / 2 + i * 2 * math.pi / 5
        pts.append((300 + 205 * math.cos(ang), 170 + 125 * math.sin(ang)))
    for i, (x, y) in enumerate(pts):
        b.append(R(x - 88, y - 30, 176, 60, "#fff", NAVY, 8))
        b.append(T(x, y - 10, f"{'①②③④⑤'[i]} {labels[i]}", 11, 800, "middle", NAVY))
        desc = steps[i][2:].split("—")[0].split("(")[0].strip()
        b.append(T(x, y + 7, desc, 8.6, 400, "middle", GRAY, n=26))
    for i in range(5):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % 5]
        mx1, my1 = x1 + (x2 - x1) * 0.3, y1 + (y2 - y1) * 0.3
        mx2, my2 = x1 + (x2 - x1) * 0.7, y1 + (y2 - y1) * 0.7
        b.append(A(mx1, my1, mx2, my2, ACC, 2))
    return svg(345, "".join(b), "처음이라면 — 이렇게 시작 (읽어보기)")


def stock_flow(wb):
    items = [("최초보유", "원료 시트", PALE), ("+ 구매", "입출고", "#e6f2e6"), ("± 조정", "입출고(흘림·폐기 −)", "#fdf0e3"), ("− 제조사용", "개발일지 배치량g × 처방%", "#fbe3e3")]
    b = []
    x = 8
    for lab, src, fill in items:
        b.append(R(x, 20, 112, 70, fill, LINE, 6))
        b.append(T(x + 56, 50, lab, 12.5, 800, "middle", NAVY))
        b.append(T(x + 56, 68, src, 8.8, 500, "middle", GRAY, n=14))
        x += 120
    b.append(T(x + 2, 62, "=", 22, 800, "middle", NAVY))
    b.append(R(x + 18, 14, 104, 82, NAVY, "none", 8))
    b.append(T(x + 70, 52, "현재고", 14, 800, "middle", "#fff"))
    b.append(T(x + 70, 72, "음수면 '사야 함'", 9, 500, "middle", "#dce6f1"))
    return svg(110, "".join(b), "재고가 맞춰지는 원리 — 엑셀은 자동, 책에서는 원료 시트·입출고·개발일지에 손으로 적어 맞춘다")


def three_phase(wb):
    b = []
    b.append(R(10, 10, 180, 86, WATER, "none", 8))
    b.append(T(100, 34, "A 수상 70~75℃", 12, 800, "middle", NAVY))
    b.append(T(100, 54, "정제수·글리세린·판테놀·검(선분산)", 9.2, 400, "middle", INK, n=20))
    b.append(T(100, 86, "HS5Pro 자석교반", 8.6, 600, "middle", GRAY))
    b.append(R(10, 112, 180, 86, OIL, "none", 8))
    b.append(T(100, 136, "B 유상 70~75℃", 12, 800, "middle", ACC))
    b.append(T(100, 156, "오일·세틸알코올·몬타노브68", 9.2, 400, "middle", INK, n=20))
    b.append(T(100, 188, "중탕 · 완전 용해", 8.6, 600, "middle", GRAY))
    b.append(A(190, 53, 236, 92, GRAY, 2))
    b.append(A(190, 155, 236, 116, GRAY, 2))
    steps = [
        ("유화", "두 상 ±5℃ → B를 A에, 호모 HZ-400 2~5분", "#fff"),
        ("냉각 교반", "오버헤드 OC-15S 저속, 40℃까지", "#fff"),
        ("C 냉각첨가 ≤40℃", "보존제·향·열에 약한 활성", "#fbe3e3"),
        ("pH · 판정", "pH 5.0~5.5 보정 → 원심 LC-8S 분리mm", "#fff"),
    ]
    y = 70
    x = 240
    for i, (t, d, fill) in enumerate(steps):
        b.append(R(x, y, 82, 76, fill, NAVY, 7))
        b.append(T(x + 41, y + 20, t, 10.5, 800, "middle", NAVY, n=9))
        b.append(T(x + 41, y + 40 + (8 if len(t) > 9 else 0), d, 8, 400, "middle", GRAY, n=11))
        if i < 3:
            b.append(A(x + 82, y + 38, x + 90, y + 38, GRAY, 2))
        x += 90
    b.append(T(300, 222, "토너·앰플·젤처럼 물만 쓰는 제품은 A → C → pH만 거친다", 9.5, 600, "middle", GRAY))
    return svg(232, "".join(b), "3상(A·B·C) 공정 — 유화 제품(로션·크림) 기준, 상세 순서는 각 레시피 '만드는 법'")


def ratio_ladder(wb):
    ws = wb["역설계 심화"]
    r0 = _find(ws, "비율·제형 사다리")
    groups = []
    r = r0 + 1
    while r <= ws.max_row and ws.cell(r, 1).value:
        a, bv = ws.cell(r, 1).value, ws.cell(r, 2).value
        if not bv:
            groups.append((str(a), []))
        elif groups:
            groups[-1][1].append((str(a), str(bv).split("\n")[0]))
        r += 1
    b = []
    y = 6
    for name, steps in groups:
        b.append(T(0, y + 14, name, 10.5, 800, "start", NAVY))
        n = len(steps)
        w = 600 / max(n, 1)
        for i, (rng, desc) in enumerate(steps):
            x = i * w
            shade = ["#eef3f9", "#dce6f1", "#c3d4e8", "#a9c1dd"][min(i, 3)]
            b.append(R(x + 1, y + 22, w - 3, 52, shade, "none", 4))
            b.append(T(x + 8, y + 38, rng, 9.5, 800, "start", NAVY))
            b.append(T(x + 8, y + 53, desc.split("/")[0].strip(), 8, 400, "start", INK, n=int(w / 8.4)))
        y += 86
    return svg(y, "".join(b), "비율·제형 사다리 — 같은 원료군도 %에 따라 제형이 바뀐다 (아래 표를 한눈에)")


def ten_steps(wb):
    ws = wb["개발→창업 워크플로우"]
    r0 = _find(ws, "§1.")
    rows = [_cells(ws, r0 + 2 + i, 4) for i in range(10)]
    b = [R(8, 6, 12, 12, "#eef5ec", GREEN, 3), T(26, 16, "집(홈랩)에서 개발·검증 ①~⑥", 9.5, 700, "start", GREEN)]
    b += [R(250, 6, 12, 12, "#fdf0e3", ACC, 3), T(268, 16, "이관 → OEM 양산 · 출시 ⑦~⑩", 9.5, 700, "start", ACC)]
    for i, (step, home, book, biz) in enumerate(rows):
        row, col = divmod(i, 5)
        x = 8 + col * 118
        y = 30 + row * 112
        out = biz.split("산출:")[-1].strip() if "산출:" in biz else biz.split("(")[0].strip()
        home_side = i < 6
        b.append(R(x, y, 108, 76, "#eef5ec" if home_side else "#fdf0e3", GREEN if home_side else ACC, 7))
        b.append(T(x + 54, y + 20, step, 10.5, 800, "middle", NAVY, n=10))
        b.append(T(x + 54, y + 44, out, 8, 400, "middle", GRAY, n=14))
        if col < 4:
            b.append(A(x + 108, y + 38, x + 118, y + 38, GRAY, 1.6))
    b.append(A(544, 106, 64, 140, GRAY, 1.2))
    return svg(222, "".join(b), "한 제품의 개발→출시 10단계 — 각 칸 아래는 그 단계의 산출물")


def demand_stairs(wb):
    ws = wb["수요검증"]
    r0 = _find(ws, "§1.")
    rows = [_cells(ws, r0 + 2 + i, 4) for i in range(6)]
    b = []
    for i, (st, todo, signal, cost) in enumerate(rows):
        x = 4 + i * 99
        h = 50 + i * 30
        y = 230 - h
        b.append(R(x, y, 93, h, ["#eef3f9", "#dce6f1", "#c3d4e8", "#a9c1dd", "#8eaed2", NAVY][i], "none", 5))
        fg = "#fff" if i >= 4 else NAVY
        code, _, name = st.partition(" ")
        b.append(T(x + 46, y + 20, code, 13, 800, "middle", fg))
        b.append(T(x + 46, y + 36, name, 9, 700, "middle", fg, n=10))
        b.append(T(x + 46, 248, cost.split("·")[0].strip(), 8.2, 500, "middle", GRAY, n=12))
    b.append(T(596, 16, "낯선 사람의 '돈·행동'이 쌓일수록 한 칸씩", 9.5, 700, "end", ACC))
    return svg(262, "".join(b), "수요검증 6단계 — 각 단계 통과 기준을 넘어야 다음 칸으로 (아래 표 §1)")


REGISTRY = {f.__name__: f for f in [daily_loop, card_anatomy, emulsion, texture_levers, dev_loop, stock_flow, three_phase, ratio_ladder, ten_steps, demand_stairs]}


def render(name: str, wb) -> str:
    return REGISTRY[name](wb)
