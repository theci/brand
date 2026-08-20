"""DOE(실험계획법) 분석.

2^k 완전요인 설계의 주효과와 2요인 교호작용을 평가 항목별로 계산하고,
주효과/교호작용 플롯(PNG)과 해석이 붙은 마크다운 리포트를 생성한다.

효과 정의(주효과·교호작용 모두 동일한 '평균 차이' 방식):
  - 주효과(A)     = mean(높은 수준 A 응답) − mean(낮은 수준 A 응답)
  - 교호작용(A×B) = mean(A·B 부호가 +인 응답) − mean(A·B 부호가 −인 응답)

결측 점수는 평균에서 제외한다(available-case). 어떤 그룹에 값이 하나도 없으면
그 효과는 None으로 둔다.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

from .models import DoeDesign, DoeRun

# 완전요인 설계로 간주하는 최소 run 수(2^3).
MIN_COMPLETE_RUNS = 8

# 낮은/높은 수준으로 해석하는 토큰.
_LOW_TOKENS = {"-", "low", "l", "lo", "-1", "low_level", False}
_HIGH_TOKENS = {"+", "high", "h", "hi", "+1", "1", "high_level", True}


@dataclass
class DoeAnalysis:
    name: str
    factors: list[str]
    response_items: list[str]
    n_runs: int
    complete: bool
    # factor -> response -> effect(None 가능)
    main_effects: dict[str, dict[str, float | None]]
    # (factorA, factorB) -> response -> effect
    interactions: dict[tuple[str, str], dict[str, float | None]]
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 부호 정규화
# ---------------------------------------------------------------------------
def _factor_signs(design: DoeDesign) -> dict[str, dict[int, int]]:
    """각 factor에 대해 run 인덱스 → +1/-1 부호 매핑을 만든다.

    factor_values가 low/high(또는 +/-, 0/1, bool)면 토큰으로,
    숫자면 그 factor의 두 수준(min=-1, max=+1)으로 판정한다.
    """
    signs: dict[str, dict[int, int]] = {}
    for factor in design.factors:
        raw = [run.factor_values.get(factor) for run in design.runs]

        # 숫자 수준인지 확인 (토큰이 아닌 실제 숫자)
        numeric_vals = [
            v
            for v in raw
            if isinstance(v, (int, float))
            and not isinstance(v, bool)
            and str(v).strip().lower() not in _HIGH_TOKENS | _LOW_TOKENS
        ]
        distinct_numeric = sorted(set(numeric_vals))
        use_numeric = len(distinct_numeric) == 2 and len(numeric_vals) == len(raw)

        run_signs: dict[int, int] = {}
        for i, v in enumerate(raw):
            if v is None:
                raise ValueError(
                    f"run {design.runs[i].run_id}에 factor '{factor}' 값이 없습니다."
                )
            if use_numeric:
                run_signs[i] = 1 if v == distinct_numeric[1] else -1
            else:
                token = str(v).strip().lower() if not isinstance(v, bool) else v
                if token in _HIGH_TOKENS:
                    run_signs[i] = 1
                elif token in _LOW_TOKENS:
                    run_signs[i] = -1
                else:
                    raise ValueError(
                        f"factor '{factor}'의 수준값 '{v}'를 low/high로 해석할 수 없습니다."
                    )
        signs[factor] = run_signs
    return signs


def _mean(values: list[float]) -> float | None:
    """결측 안전 평균. 빈 리스트면 None."""
    if not values:
        return None
    return sum(values) / len(values)


def _effect_by_sign(
    design: DoeDesign, run_sign: dict[int, int], response: str
) -> float | None:
    """부호(+1/-1)별 응답 평균의 차이(+평균 − −평균)."""
    plus: list[float] = []
    minus: list[float] = []
    for i, run in enumerate(design.runs):
        score = run.scores.get(response)
        if score is None:
            continue
        (plus if run_sign[i] == 1 else minus).append(float(score))
    m_plus, m_minus = _mean(plus), _mean(minus)
    if m_plus is None or m_minus is None:
        return None
    return m_plus - m_minus


# ---------------------------------------------------------------------------
# 분석
# ---------------------------------------------------------------------------
def doe_analysis(design: DoeDesign) -> DoeAnalysis:
    """주효과와 2요인 교호작용을 평가 항목별로 계산한다."""
    signs = _factor_signs(design)
    n = len(design.runs)
    warnings: list[str] = []
    complete = n >= MIN_COMPLETE_RUNS
    if not complete:
        warnings.append(
            f"run이 {n}개로 {MIN_COMPLETE_RUNS}개 미만입니다. 설계가 불완전하여 "
            "효과 추정이 편향될 수 있습니다(교호작용과 주효과가 교락될 수 있음)."
        )

    # 결측 점수 경고
    missing = [
        (run.run_id, item)
        for run in design.runs
        for item in design.response_items
        if run.scores.get(item) is None
    ]
    if missing:
        warnings.append(
            f"결측 점수 {len(missing)}건이 있어 해당 항목은 available-case 평균으로 계산합니다."
        )

    main_effects: dict[str, dict[str, float | None]] = {}
    for factor in design.factors:
        main_effects[factor] = {
            item: _effect_by_sign(design, signs[factor], item)
            for item in design.response_items
        }

    interactions: dict[tuple[str, str], dict[str, float | None]] = {}
    for a, b in itertools.combinations(design.factors, 2):
        combined = {i: signs[a][i] * signs[b][i] for i in range(n)}
        interactions[(a, b)] = {
            item: _effect_by_sign(design, combined, item)
            for item in design.response_items
        }

    return DoeAnalysis(
        name=design.name,
        factors=list(design.factors),
        response_items=list(design.response_items),
        n_runs=n,
        complete=complete,
        main_effects=main_effects,
        interactions=interactions,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 해석 문장
# ---------------------------------------------------------------------------
def _dominant_factor(analysis: DoeAnalysis, response: str) -> tuple[str, float] | None:
    """해당 응답에 대해 |주효과|가 가장 큰 factor와 그 효과값."""
    best: tuple[str, float] | None = None
    for factor in analysis.factors:
        eff = analysis.main_effects[factor][response]
        if eff is None:
            continue
        if best is None or abs(eff) > abs(best[1]):
            best = (factor, eff)
    return best


def interpretation_sentences(analysis: DoeAnalysis) -> list[str]:
    """'유화제가 헹굼에 가장 큰 영향(+1.5)' 형태의 해석 문장."""
    out: list[str] = []
    for response in analysis.response_items:
        dom = _dominant_factor(analysis, response)
        if dom is None:
            out.append(f"{response}: 계산 가능한 주효과가 없습니다(결측).")
            continue
        factor, eff = dom
        sign = "+" if eff >= 0 else "−"
        out.append(
            f"{factor}이(가) {response}에 가장 큰 영향({sign}{abs(eff):.2f})"
        )
    return out


# ---------------------------------------------------------------------------
# 플롯
# ---------------------------------------------------------------------------
def main_effects_plot(analysis: DoeAnalysis, path: Path | str) -> Path:
    """응답별 서브플롯으로 각 factor의 저수준→고수준 주효과를 그린다."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _set_korean_font(matplotlib)

    items = analysis.response_items
    ncols = min(3, len(items))
    nrows = (len(items) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows), squeeze=False)

    for idx, item in enumerate(items):
        ax = axes[idx // ncols][idx % ncols]
        for factor in analysis.factors:
            eff = analysis.main_effects[factor][item]
            if eff is None:
                continue
            # 저수준을 0, 고수준을 effect로 표현(상대 변화)
            ax.plot([0, 1], [0, eff], marker="o", label=factor)
        ax.axhline(0, color="gray", linewidth=0.6)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["low", "high"])
        ax.set_title(item)
        ax.legend(fontsize=7)
    # 남는 축 숨김
    for j in range(len(items), nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")

    fig.suptitle(f"주효과 플롯 — {analysis.name}")
    fig.tight_layout()
    out = Path(path)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def interaction_plot(
    analysis: DoeAnalysis, path: Path | str, response: str | None = None
) -> Path:
    """factor 쌍별 교호작용 효과를 응답 하나에 대해 막대로 그린다.

    response 미지정 시 |교호작용|이 가장 큰 응답을 자동 선택한다.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _set_korean_font(matplotlib)

    pairs = list(analysis.interactions.keys())
    if response is None:
        response = _response_with_max_interaction(analysis)

    labels = [f"{a}×{b}" for a, b in pairs]
    values = [analysis.interactions[p].get(response) or 0.0 for p in pairs]

    fig, ax = plt.subplots(figsize=(1.6 * len(pairs) + 2, 4))
    colors = ["#d9534f" if v >= 0 else "#5bc0de" for v in values]
    ax.bar(labels, values, color=colors)
    ax.axhline(0, color="gray", linewidth=0.6)
    ax.set_ylabel("교호작용 효과")
    ax.set_title(f"교호작용 플롯 ({response}) — {analysis.name}")
    fig.tight_layout()
    out = Path(path)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def _response_with_max_interaction(analysis: DoeAnalysis) -> str:
    best_item, best_mag = analysis.response_items[0], -1.0
    for item in analysis.response_items:
        for pair in analysis.interactions:
            v = analysis.interactions[pair].get(item)
            if v is not None and abs(v) > best_mag:
                best_mag, best_item = abs(v), item
    return best_item


def _set_korean_font(matplotlib) -> None:
    """한글 폰트가 있으면 설정(없으면 조용히 기본 폰트 사용)."""
    from matplotlib import font_manager

    for name in ["AppleGothic", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR"]:
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return


# ---------------------------------------------------------------------------
# 리포트
# ---------------------------------------------------------------------------
def _fmt(v: float | None) -> str:
    return "—" if v is None else f"{v:+.2f}"


def doe_report(
    design: DoeDesign,
    *,
    analysis: DoeAnalysis | None = None,
    plots: dict[str, str] | None = None,
) -> str:
    """마크다운 리포트를 생성한다. plots는 {'main': 경로, 'interaction': 경로}."""
    a = analysis or doe_analysis(design)
    lines: list[str] = []
    lines.append(f"# DOE 분석 리포트 — {a.name}")
    lines.append("")
    lines.append(f"- 인자: {', '.join(a.factors)}")
    lines.append(f"- 평가 항목: {', '.join(a.response_items)}")
    lines.append(f"- run 수: {a.n_runs} ({'완전' if a.complete else '불완전'})")
    lines.append("")

    if a.warnings:
        lines.append("## ⚠️ 경고")
        lines.append("")
        for w in a.warnings:
            lines.append(f"- {w}")
        lines.append("")

    # 주효과 표
    lines.append("## 주효과 (고수준 평균 − 저수준 평균)")
    lines.append("")
    lines.append("| 인자 | " + " | ".join(a.response_items) + " |")
    lines.append("| --- " + "| ---: " * len(a.response_items) + "|")
    for factor in a.factors:
        row = [_fmt(a.main_effects[factor][item]) for item in a.response_items]
        lines.append(f"| {factor} | " + " | ".join(row) + " |")
    lines.append("")

    # 교호작용 표
    lines.append("## 2요인 교호작용")
    lines.append("")
    lines.append("| 교호작용 | " + " | ".join(a.response_items) + " |")
    lines.append("| --- " + "| ---: " * len(a.response_items) + "|")
    for (x, y), effs in a.interactions.items():
        row = [_fmt(effs[item]) for item in a.response_items]
        lines.append(f"| {x}×{y} | " + " | ".join(row) + " |")
    lines.append("")

    # 해석
    lines.append("## 해석")
    lines.append("")
    for s in interpretation_sentences(a):
        lines.append(f"- {s}")
    lines.append("")

    if plots:
        lines.append("## 플롯")
        lines.append("")
        if plots.get("main"):
            lines.append(f"![주효과]({plots['main']})")
        if plots.get("interaction"):
            lines.append(f"![교호작용]({plots['interaction']})")
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "MIN_COMPLETE_RUNS",
    "DoeAnalysis",
    "doe_analysis",
    "doe_report",
    "interpretation_sentences",
    "main_effects_plot",
    "interaction_plot",
]
