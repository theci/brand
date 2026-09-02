"""brandlab CLI (typer + rich).

예:
    brandlab batch cleansing-balm v1 --grams 500
    brandlab batch cleansing-balm v1 --grams 500 --sheet   # 마크다운 배치 지시서
"""

from __future__ import annotations

from datetime import date as date_cls
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .adcopy import lint as lint_text
from .advisor import classify, compare, feasibility
from .batch import batch_sheet, scale, scale_report
from .batchrecord import (
    batch_record_to_yaml_dict,
    batch_summary,
    make_batch_id,
    new_batch_record,
)
from .checks import check_formula
from .core.models import ProductIntent
from .diff import formula_diff
from .ingredient_edit import set_ingredient_fields
from .pubchem import PubChemError, fetch_pubchem, http_get_json
from .cost import (
    breakeven,
    min_price_for_margin,
    moq_bottleneck,
    price_simulator,
    unit_cost,
)
from .doe import (
    doe_analysis,
    doe_report,
    interaction_plot,
    interpretation_sentences,
    main_effects_plot,
)
from .food import nutrition_facts
from .fragrance import blend_sheet, ifra_check, maceration_due, note_pyramid
from .labeling import screen
from .loader import (
    DATA_DIR,
    EXPERIMENTS_DIR,
    BrandLab,
    iter_batch_paths,
    iter_fragrance_paths,
    load_ad_terms,
    load_all_batches,
    load_all_fragrances,
    load_all_stability,
    load_aroma_materials,
    load_doe,
    load_fragrance,
    load_ingredients,
)
from .models import Formula, Fragrance
from .stability import stability_due, stability_summary

app = typer.Typer(help="화장품 1인 브랜드 처방 관리 도구", no_args_is_help=True)
console = Console()


@app.callback()
def _root() -> None:
    """단일 명령이라도 'batch'를 하위 명령으로 유지하기 위한 콜백."""


def _parse_version(version: str) -> int:
    v = version.strip().lstrip("vV")
    try:
        return int(v)
    except ValueError as exc:
        raise typer.BadParameter(
            f"버전은 'v1' 또는 '1' 형식이어야 합니다: {version!r}"
        ) from exc


def _find_formula(lab: BrandLab, slug: str, version: int) -> Formula:
    for f in lab.formulas:
        if f.slug == slug and f.version == version:
            return f
    available = ", ".join(
        f"{f.slug} v{f.version}" for f in lab.formulas
    ) or "(없음)"
    raise typer.BadParameter(
        f"처방을 찾을 수 없습니다: {slug} v{version}\n사용 가능: {available}"
    )


@app.command()
def batch(
    slug: str = typer.Argument(..., help="처방 슬러그 (예: cleansing-balm)"),
    version: str = typer.Argument(..., help="버전 (예: v1)"),
    grams: float = typer.Option(..., "--grams", "-g", help="목표 배치 크기(g)"),
    sheet: bool = typer.Option(
        False, "--sheet", help="마크다운 배치 지시서로 출력"
    ),
) -> None:
    """처방을 목표 배치 크기로 환산한다."""
    ver = _parse_version(version)
    lab = BrandLab.load()
    formula = _find_formula(lab, slug, ver)
    ingredients = lab.ingredients

    if sheet:
        # 파이프/파일 저장이 쉽도록 순수 마크다운을 그대로 출력
        typer.echo(batch_sheet(formula, grams, ingredients=ingredients))
        return

    result = scale(formula, grams, ingredients=ingredients)

    console.print(
        Panel.fit(
            f"[bold]{result.product}[/bold]  ([cyan]{result.slug}[/cyan] v{result.version})\n"
            f"목표 배치: [bold]{result.target_g:g} g[/bold]   "
            f"제품 형태: {formula.product_type.value}   상태: {formula.status.value}",
            title="배치 환산",
        )
    )

    for phase in result.phases:
        title = f"상 {phase.name}"
        if phase.process:
            title += f" — {phase.process}"
        table = Table(title=title, title_justify="left", header_style="bold")
        table.add_column("원료")
        table.add_column("목표 %", justify="right")
        table.add_column("목표 g", justify="right")
        for ing in phase.ingredients:
            name = ing.name if ing.weighable else f"[yellow]{ing.name} ⚠[/yellow]"
            table.add_row(name, f"{ing.percent:g}", f"{ing.grams:.2f}")
        table.add_section()
        table.add_row("[bold]소계[/bold]", "", f"[bold]{phase.subtotal_g:.2f}[/bold]")
        console.print(table)

    total_style = "green" if result.total_ok else "red"
    console.print(
        f"[{total_style}]전체 합계: {result.total_g:.2f} g "
        f"(목표 {result.target_g:g} g)[/{total_style}]"
    )

    if result.warnings:
        console.print()
        for w in result.warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]")

    # 스케일업 리스크 리포트 (base_batch_g → 목표)
    report = scale_report(
        formula, formula.base_batch_g, grams, ingredients=ingredients
    )
    color = "red" if report.risk_level == "높음" else "green"
    body = "\n".join(f"• {w}" for w in report.warnings)
    console.print()
    console.print(
        Panel(
            body,
            title=f"스케일업 리스크: [{color}]{report.risk_level}[/{color}] "
            f"(왁스/버터 {report.wax_butter_percent:g}%)",
            border_style=color,
        )
    )


@app.command()
def label(
    slug: str = typer.Argument(..., help="처방 슬러그 (예: cleansing-balm)"),
    version: str = typer.Argument(..., help="버전 (예: v1)"),
) -> None:
    """전성분 표시·알러젠·표시의무·배합한도를 1차 스크리닝한다."""
    ver = _parse_version(version)
    lab = BrandLab.load()
    formula = _find_formula(lab, slug, ver)
    result = screen(formula, lab)

    console.print(
        Panel.fit(
            f"[bold]{formula.product}[/bold]  ([cyan]{formula.slug}[/cyan] v{formula.version})\n"
            f"제품 형태: {formula.product_type.value}   상태: {formula.status.value}",
            title="라벨 스크리닝",
        )
    )

    # 규제 데이터 최신성 (맨 위에서 먼저 경고)
    if result.freshness.warnings:
        for w in result.freshness.warnings:
            console.print(f"[red]⚠ 규제데이터: {w}[/red]")
        console.print()

    # 1) 전성분 표시 문자열
    console.print("[bold]■ 전성분 표시(안)[/bold]")
    console.print(result.inci.text or "[dim](없음)[/dim]")
    for w in result.inci.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")
    console.print()

    # 2) 알러젠 판정
    a = result.allergens
    atable = Table(
        title=f"알러젠 판정 (임계값 {a.threshold_percent:g}% / {a.product_type.value})",
        title_justify="left",
        header_style="bold",
    )
    atable.add_column("성분")
    atable.add_column("INCI")
    atable.add_column("완제품 농도%", justify="right")
    atable.add_column("표기", justify="center")
    for f in a.declared:
        atable.add_row(
            f.name, f.inci, f"{f.concentration_percent:g}", "[red]표기 필요[/red]"
        )
    for f in a.below_threshold:
        atable.add_row(
            f"[dim]{f.name}[/dim]",
            f"[dim]{f.inci}[/dim]",
            f"[dim]{f.concentration_percent:g}[/dim]",
            "[dim]이하[/dim]",
        )
    if not a.declared and not a.below_threshold:
        atable.add_row("[dim]해당 없음[/dim]", "", "", "")
    console.print(atable)
    for w in a.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")
    console.print()

    # 3) 표시 의무(용량 기준)
    req = result.requirement
    size = f"{req.size_value:g}{req.size_unit}" if req.size_value is not None else "미상"
    body = f"내용량: {size}   구분: [bold]{req.tier}[/bold]\n"
    body += "표시 항목: " + ", ".join(req.required_items) + "\n"
    body += "\n".join(req.notes)
    console.print(Panel(body, title="표시 의무", border_style="cyan"))

    # 4) 배합한도
    lc = result.limits
    if not lc.has_data:
        console.print(f"[red]⚠ {lc.warnings[0]}[/red]")
    else:
        ltable = Table(title="배합한도 체크", title_justify="left", header_style="bold")
        ltable.add_column("원료")
        ltable.add_column("함량%", justify="right")
        ltable.add_column("한도%", justify="right")
        ltable.add_column("판정", justify="center")
        for f in lc.findings:
            verdict = "[red]초과[/red]" if f.exceeded else "[green]적합[/green]"
            ltable.add_row(f.name, f"{f.percent:g}", f"{f.max_percent:g}", verdict)
        if not lc.findings:
            ltable.add_row("[dim]대조 대상 없음[/dim]", "", "", "")
        console.print(ltable)
    console.print()

    # 면책 문구 — 반드시 맨 아래
    console.print(Panel(result.disclaimer, border_style="red"))


@app.command()
def nutrition(
    slug: str = typer.Argument(..., help="처방 슬러그 (예: low-sugar-jelly)"),
    version: str = typer.Argument(..., help="버전 (예: v1)"),
) -> None:
    """식품 처방의 영양성분표(100g·1회 제공량)를 계산한다."""
    ver = _parse_version(version)
    lab = BrandLab.load()
    formula = _find_formula(lab, slug, ver)

    if formula.regime != "food":
        console.print(
            f"[yellow]⚠ 이 처방의 레짐은 '{formula.regime}'입니다. "
            "영양성분 계산은 식품(food) 처방을 위한 기능입니다.[/yellow]"
        )

    facts = nutrition_facts(formula, lab.ingredients)

    console.print(
        Panel.fit(
            f"[bold]{formula.product}[/bold]  ([cyan]{formula.slug}[/cyan] v{formula.version})",
            title="영양성분 계산",
        )
    )

    table = Table(title="영양성분표", title_justify="left", header_style="bold")
    table.add_column("항목")
    table.add_column("100g당", justify="right")
    serving = formula.net_weight_g
    if facts.per_serving is not None:
        table.add_column(f"1회 제공량({serving:g}g)", justify="right")

    rows = [
        ("열량(kcal)", facts.per_100g.kcal, facts.per_serving.kcal if facts.per_serving else None),
        ("단백질(g)", facts.per_100g.protein_g, facts.per_serving.protein_g if facts.per_serving else None),
        ("지방(g)", facts.per_100g.fat_g, facts.per_serving.fat_g if facts.per_serving else None),
        ("탄수화물(g)", facts.per_100g.carb_g, facts.per_serving.carb_g if facts.per_serving else None),
        ("당류(g)", facts.per_100g.sugar_g, facts.per_serving.sugar_g if facts.per_serving else None),
        ("나트륨(mg)", facts.per_100g.sodium_mg, facts.per_serving.sodium_mg if facts.per_serving else None),
    ]
    for name, v100, vserv in rows:
        if facts.per_serving is not None:
            table.add_row(name, f"{v100:.1f}", f"{vserv:.1f}")
        else:
            table.add_row(name, f"{v100:.1f}")
    console.print(table)

    for flag in facts.emphasis_flags:
        console.print(f"[green]· {flag}[/green]")
    for w in facts.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")

    console.print(
        Panel(
            "이 계산은 원료 영양성분(예시값 포함)의 가중합입니다. 실제 표시 전 "
            "공인 영양성분 분석과 식약처 표시기준을 확인하십시오.",
            border_style="red",
        )
    )


@app.command()
def cost(
    slug: str = typer.Argument(..., help="처방 슬러그 (예: cleansing-balm)"),
    version: str = typer.Argument(..., help="버전 (예: v1)"),
    units: int = typer.Option(..., "--units", "-u", help="생산(주문) 수량"),
    price: float = typer.Option(..., "--price", "-p", help="소비자 판매가(부가세 포함)"),
    fixed: float = typer.Option(
        None, "--fixed", help="손익분기용 고정비(기본: MOQ 총 선투입 자본)"
    ),
) -> None:
    """개당 원가·손익·MOQ 병목을 계산한다."""
    ver = _parse_version(version)
    lab = BrandLab.load()
    formula = _find_formula(lab, slug, ver)
    econ = lab.config.economics

    uc = unit_cost(formula, units, ingredients=lab.ingredients, packaging=lab.packaging)
    sim = price_simulator(uc, price, economics=econ)
    mb = moq_bottleneck(formula, units, ingredients=lab.ingredients, packaging=lab.packaging)

    def won(x: float) -> str:
        return f"{x:,.0f}원"

    console.print(
        Panel.fit(
            f"[bold]{formula.product}[/bold]  ([cyan]{formula.slug}[/cyan] v{formula.version})\n"
            f"주문 수량: [bold]{units:,}개[/bold]   판매가: [bold]{won(price)}[/bold]",
            title="원가 · 손익",
        )
    )

    # 원가 내역
    ct = Table(title="개당 원가 내역", title_justify="left", header_style="bold")
    ct.add_column("항목")
    ct.add_column("내역")
    ct.add_column("개당 원가", justify="right")
    for l in uc.material_lines:
        ct.add_row(f"[원료] {l.name}", l.detail, won(l.cost))
    for l in uc.packaging_lines:
        ct.add_row(f"[부자재] {l.name}", l.detail, won(l.cost))
    ct.add_section()
    ct.add_row("원료비 합계", "", won(uc.material_cost))
    ct.add_row("부자재비 합계", "", won(uc.packaging_cost))
    ct.add_row("[bold]개당 원가[/bold]", "", f"[bold]{won(uc.unit_cost)}[/bold]")
    console.print(ct)
    for w in uc.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")

    # 손익 요약
    tgt = econ.target_margin
    min_price = min_price_for_margin(uc, tgt, economics=econ) if tgt is not None else None
    st = Table(title="개당 손익 요약", title_justify="left", header_style="bold")
    st.add_column("항목")
    st.add_column("값", justify="right")
    st.add_row("실매출(부가세 제외)", won(sim.net_revenue))
    st.add_row("− 채널 수수료", won(sim.channel_fee))
    st.add_row("− 배송비", won(sim.shipping))
    st.add_row("− 개당 원가", won(sim.unit_cost))
    st.add_row("− 반품 비용", won(sim.return_cost))
    st.add_section()
    st.add_row("[bold]개당 공헌이익[/bold]", f"[bold]{won(sim.contribution)}[/bold]")
    st.add_row("마진율(실매출 대비)", f"{sim.margin_on_net:.1%}")
    st.add_row("마진율(판매가 대비)", f"{sim.margin_on_price:.1%}")
    if tgt is not None:
        target_str = won(min_price) if min_price else "달성 불가"
        st.add_row(f"목표마진 {tgt:.0%} 최소판매가", target_str)
    console.print(st)
    for w in sim.warnings:
        console.print(f"[red]⚠ {w}[/red]")

    # 손익분기
    fixed_cost = fixed if fixed is not None else mb.total_upfront_capital
    be = breakeven(fixed_cost, sim.contribution)
    be_str = f"{be:,}개" if be is not None else "달성 불가(공헌이익 ≤ 0)"
    console.print(
        f"손익분기 수량: [bold]{be_str}[/bold] "
        f"(고정비 {won(fixed_cost)} ÷ 공헌이익 {won(sim.contribution)})"
    )

    # MOQ 병목
    mt = Table(title="MOQ 병목", title_justify="left", header_style="bold")
    mt.add_column("부자재")
    mt.add_column("필요", justify="right")
    mt.add_column("MOQ", justify="right")
    mt.add_column("발주", justify="right")
    mt.add_column("사장재고", justify="right")
    mt.add_column("자본", justify="right")
    for it in mb.items:
        dead = f"[red]{it.dead_qty:,}[/red]" if it.dead_qty else "0"
        mt.add_row(
            it.name,
            f"{it.need_qty:,}",
            f"{it.moq:,}" if it.moq else "-",
            f"{it.order_qty:,}",
            dead,
            won(it.capital),
        )
    console.print(mt)
    if mb.bottleneck is not None:
        console.print(
            f"[yellow]초도 물량 병목: [bold]{mb.bottleneck.name}[/bold] "
            f"→ 사장 재고 없이 만들려면 최소 {mb.min_units_no_waste:,}개 생산 필요[/yellow]"
        )
    console.print(
        f"총 선투입 자본: [bold]{won(mb.total_upfront_capital)}[/bold] "
        f"(원료 {won(mb.material_capital)} + 부자재 {won(mb.packaging_capital)}) · "
        f"사장 재고 자본 {won(uc.dead_stock_capital)}"
    )

    # 가정 명시
    console.print()
    console.print("[dim]■ 가정/출처[/dim]")
    for a in uc.assumptions + sim.assumptions:
        console.print(f"[dim]  · {a}[/dim]")


doe_app = typer.Typer(help="DOE(실험계획법) 분석", no_args_is_help=True)
app.add_typer(doe_app, name="doe")


@doe_app.command("analyze")
def doe_analyze(
    file: Path = typer.Argument(..., help="DOE YAML 파일 경로"),
) -> None:
    """DOE 파일을 분석하고 리포트·플롯(PNG)을 생성한다."""
    design = load_doe(file)
    analysis = doe_analysis(design)

    out_dir = file.parent
    main_png = out_dir / f"{file.stem}-main-effects.png"
    inter_png = out_dir / f"{file.stem}-interaction.png"
    main_effects_plot(analysis, main_png)
    interaction_plot(analysis, inter_png)

    report = doe_report(
        design,
        analysis=analysis,
        plots={"main": main_png.name, "interaction": inter_png.name},
    )
    report_path = out_dir / f"{file.stem}-report.md"
    report_path.write_text(report, encoding="utf-8")

    if analysis.warnings:
        for w in analysis.warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]")

    # 주효과 표
    table = Table(title=f"주효과 — {analysis.name}", title_justify="left", header_style="bold")
    table.add_column("인자")
    for item in analysis.response_items:
        table.add_column(item, justify="right")
    for factor in analysis.factors:
        row = [factor]
        for item in analysis.response_items:
            eff = analysis.main_effects[factor][item]
            row.append("—" if eff is None else f"{eff:+.2f}")
        table.add_row(*row)
    console.print(table)

    console.print("\n[bold]해석[/bold]")
    for s in interpretation_sentences(analysis):
        console.print(f"  · {s}")

    console.print(
        f"\n[green]저장:[/green] {report_path.name}, {main_png.name}, {inter_png.name} "
        f"([dim]{out_dir}[/dim])"
    )


stability_app = typer.Typer(help="안정성 시험 트래커", no_args_is_help=True)
app.add_typer(stability_app, name="stability")


@stability_app.command("due")
def stability_due_cmd() -> None:
    """오늘 기준으로 관찰이 밀린 시료를 출력한다."""
    samples = load_all_stability()
    due = stability_due(samples)
    if not due:
        console.print("[green]밀린 관찰이 없습니다.[/green]")
        return
    table = Table(
        title="⏰ 밀린 관찰 (지연 큰 순)", title_justify="left", header_style="bold red"
    )
    table.add_column("시료")
    table.add_column("조건")
    table.add_column("주차", justify="right")
    table.add_column("예정일")
    table.add_column("지연(일)", justify="right")
    for d in due:
        table.add_row(
            d.sample_id,
            d.condition,
            f"{d.week}주",
            d.due_date.isoformat(),
            f"[red]{d.days_overdue}[/red]",
        )
    console.print(table)
    console.print(
        "[yellow]관찰일을 놓치면 그 시점 데이터가 사라집니다. 우선 처리하세요.[/yellow]"
    )


@stability_app.command("summary")
def stability_summary_cmd() -> None:
    """조건별 시료 시계열(체크포인트 상태) 요약."""
    samples = load_all_stability()
    summary = stability_summary(samples)
    if not summary:
        console.print("[dim]안정성 시료가 없습니다.[/dim]")
        return
    mark = {"done": "[green]✓[/green]", "overdue": "[red]✗[/red]", "upcoming": "·"}
    for condition, timelines in summary.items():
        table = Table(
            title=f"조건: {condition}", title_justify="left", header_style="bold"
        )
        table.add_column("시료")
        for w in (1, 2, 4, 8):
            table.add_column(f"{w}주", justify="center")
        for tl in timelines:
            row = [tl.sample_id]
            for cs in tl.checkpoints:
                cell = mark.get(cs.status, "?")
                if cs.status == "overdue":
                    cell += f" ({cs.days_overdue}d)"
                row.append(cell)
            table.add_row(*row)
        console.print(table)


fragrance_app = typer.Typer(help="조향 관리", no_args_is_help=True)
app.add_typer(fragrance_app, name="fragrance")


def _find_fragrance(name: str, version: int) -> Fragrance:
    for p in iter_fragrance_paths():
        f = load_fragrance(p)
        stem = p.stem.lower()
        slug = stem.rsplit("-v", 1)[0] if "-v" in stem else stem
        if f.version == version and name.lower() in {f.name.lower(), stem, slug}:
            return f
    available = ", ".join(
        f"{load_fragrance(p).name} v{load_fragrance(p).version} ({p.stem})"
        for p in iter_fragrance_paths()
    ) or "(없음)"
    raise typer.BadParameter(
        f"향 처방을 찾을 수 없습니다: {name} v{version}\n사용 가능: {available}"
    )


@fragrance_app.command("blend")
def fragrance_blend(
    name: str = typer.Argument(..., help="향 처방 이름 또는 파일 슬러그"),
    version: str = typer.Argument(..., help="버전 (예: v1)"),
) -> None:
    """희석 배율을 반영한 계량표 + 노트 피라미드 + IFRA 체크."""
    ver = _parse_version(version)
    fragrance = _find_fragrance(name, ver)
    materials = load_aroma_materials()

    sheet = blend_sheet(fragrance, materials)
    pyramid = note_pyramid(fragrance, materials)
    ifra = ifra_check(fragrance, materials)

    console.print(
        Panel.fit(
            f"[bold]{sheet.name}[/bold] v{sheet.version}\n"
            f"총량 {sheet.총량_g:g}g · 농도 {sheet.concentration_percent:g}% "
            f"(향 원액 {sheet.concentrate_g:g}g)",
            title="블렌드 계량표",
        )
    )

    table = Table(header_style="bold", title="계량표", title_justify="left")
    table.add_column("어코드")
    table.add_column("원료")
    table.add_column("희석%", justify="right")
    table.add_column("parts", justify="right")
    table.add_column("원액 g", justify="right")
    table.add_column("계량 g", justify="right")
    for r in sheet.rows:
        table.add_row(
            r.accord,
            r.name,
            f"{r.dilution:g}",
            f"{r.parts:g}",
            f"{r.neat_g:g}",
            f"[bold]{r.weigh_g:g}[/bold]",
        )
    console.print(table)

    console.print(
        f"희석액 계량 합계 {sheet.total_weigh_g:g}g · "
        f"추가 에탄올 [bold]{sheet.ethanol_to_add_g:g}g[/bold] · "
        f"기타(물 등) {sheet.other_g:g}g"
    )
    for w in sheet.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")

    # 노트 피라미드
    console.print(
        f"\n[bold]노트 피라미드[/bold]  "
        f"Top {pyramid.ratios['top']:g}% · "
        f"Middle {pyramid.ratios['middle']:g}% · "
        f"Base {pyramid.ratios['base']:g}%  (합계 {sum(pyramid.ratios.values()):g}%)"
    )

    # IFRA
    itable = Table(header_style="bold", title="IFRA 체크", title_justify="left")
    itable.add_column("원료")
    itable.add_column("사용률%", justify="right")
    itable.add_column("한도%", justify="right")
    itable.add_column("판정", justify="center")
    for f in ifra.findings:
        limit = f"{f.limit_percent:g}" if f.limit_percent is not None else "-"
        if f.limit_percent is None:
            verdict = "[dim]한도없음[/dim]"
        elif f.over:
            verdict = "[red]초과[/red]"
        else:
            verdict = "[green]적합[/green]"
        itable.add_row(f.name, f"{f.usage_percent:g}", limit, verdict)
    console.print(itable)
    for w in ifra.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")


@fragrance_app.command("macerate")
def fragrance_macerate() -> None:
    """숙성이 끝났는데 아직 시향하지 않은(시향 필요) 처방을 알린다."""
    fragrances = load_all_fragrances()
    due = maceration_due(fragrances)
    if not due:
        console.print("[green]시향 필요한 처방이 없습니다.[/green]")
        return
    table = Table(
        title="🧴 시향 필요 (숙성 완료, 미시향)",
        title_justify="left",
        header_style="bold",
    )
    table.add_column("향")
    table.add_column("버전", justify="right")
    table.add_column("숙성완료일")
    table.add_column("경과(일)", justify="right")
    for s in due:
        table.add_row(
            s.name,
            f"v{s.version}",
            s.ready_date.isoformat() if s.ready_date else "-",
            f"[red]{s.days}[/red]",
        )
    console.print(table)


@app.command("lint")
def lint_cmd(
    file: Path = typer.Argument(..., help="검사할 텍스트 파일(상세페이지 문구)"),
) -> None:
    """상세페이지 문구에서 금지·주의 표현을 1차로 걸러낸다."""
    if not file.exists():
        raise typer.BadParameter(f"파일이 없습니다: {file}")
    text = file.read_text(encoding="utf-8")
    terms = load_ad_terms()
    result = lint_text(text, terms)

    for w in result.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")

    if not result.findings:
        console.print("[green]등록된 문제 표현을 찾지 못했습니다.[/green]")
    else:
        counts = result.counts_by_risk()
        console.print(
            f"[bold]문제 표현 {len(result.findings)}건[/bold] "
            f"(high {counts['high']} · medium {counts['medium']} · low {counts['low']})"
        )
        risk_style = {"high": "red", "medium": "yellow", "low": "cyan"}
        table = Table(header_style="bold")
        table.add_column("위치", justify="right")
        table.add_column("표현")
        table.add_column("매칭")
        table.add_column("카테고리")
        table.add_column("위험도")
        table.add_column("대체안")
        for f in result.findings:
            style = risk_style.get(f.risk, "white")
            table.add_row(
                str(f.start),
                f.expression,
                f.matched_text,
                f.category,
                f"[{style}]{f.risk}[/{style}]",
                f.suggestion or "-",
            )
        console.print(table)

    console.print(Panel(result.disclaimer, border_style="red"))


def _won(x: int) -> str:
    return f"{x:,}원"


@app.command("advise")
def advise(
    use: str = typer.Option(None, "--use", help="용도: body/space/fabric/surface"),
    claim: list[str] = typer.Option(
        None, "--claim", help="기능(복수 가능): fragrance/cleanse/deodorize/moisturize/sanitize…"
    ),
    form: str = typer.Option(None, "--form", help="제형: liquid/solid/spray/sustained_release"),
    skus: int = typer.Option(1, "--skus", help="예상 SKU 수"),
    years: int = typer.Option(5, "--years", help="검토 기간(년)"),
    budget: int = typer.Option(None, "--budget", help="총 예산(원). 주면 적합성 CAUTION 판정에 사용"),
    interactive: bool = typer.Option(False, "--interactive", help="대화형으로 의도 입력"),
) -> None:
    """제품 의도의 규제 레짐을 분류·비교·판정한다."""
    if interactive:
        use = typer.prompt("용도 (body/space/fabric/surface)", default=use or "space")
        claim_raw = typer.prompt(
            "기능 (쉼표로 구분: fragrance,deodorize,…)", default=",".join(claim or ["fragrance"])
        )
        claim = [c.strip() for c in claim_raw.split(",") if c.strip()]
        form = typer.prompt("제형 (liquid/solid/spray/sustained_release)", default=form or "liquid")
        skus = int(typer.prompt("예상 SKU 수", default=str(skus)))
        years = int(typer.prompt("검토 기간(년)", default=str(years)))

    intent = ProductIntent(use=use, claims=list(claim or []), form=form)

    cls = classify(intent)
    cmp = compare(intent, skus, years)
    feas = feasibility(intent, budget=budget, sku_count=skus, horizon_years=years)

    console.print(
        Panel.fit(
            f"용도 [bold]{intent.use or '-'}[/bold] · 기능 [bold]{', '.join(intent.claims) or '-'}[/bold] · "
            f"제형 [bold]{intent.form or '-'}[/bold]\nSKU {skus}종 · 검토 {years}년"
            + (f" · 예산 {_won(budget)}" if budget else ""),
            title="규제 판정 (RegimeAdvisor)",
        )
    )

    # 분류 후보
    if not cls.candidates:
        console.print("[yellow]분류 후보 없음[/yellow]")
    else:
        ctable = Table(title="가능한 레짐/카테고리", title_justify="left", header_style="bold")
        ctable.add_column("레짐")
        ctable.add_column("카테고리")
        ctable.add_column("비고")
        for c in cls.candidates:
            ctable.add_row(c.regime_code, c.label, c.note or "")
        console.print(ctable)
    for w in cls.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")

    # 비용 비교
    if cmp.rows:
        mtable = Table(title="규제비용 비교", title_justify="left", header_style="bold")
        mtable.add_column("경로")
        mtable.add_column("등록비", justify="right")
        mtable.add_column(f"SKU×{skus}", justify="right")
        mtable.add_column("갱신비", justify="right")
        mtable.add_column("총 규제비용", justify="right")
        mtable.add_column("기간(일)", justify="right")
        for r in cmp.rows:
            if not r.supported:
                mtable.add_row(r.candidate.label, "-", "-", "-", "[red]미지원[/red]", "-")
                continue
            mark = "  ⭐" if r is cmp.cheapest else ""
            mtable.add_row(
                r.candidate.label + mark,
                _won(r.registration_cost),
                _won(r.sku_expansion_total),
                _won(r.renewal_cost),
                f"[bold]{_won(r.total_regulatory_cost)}[/bold]",
                str(r.lead_time_days),
            )
        console.print(mtable)
        console.print(f"[green]{cmp.summary}[/green]")

    # 적합성
    color = {"OK": "green", "CAUTION": "yellow", "REJECT": "red"}.get(feas.verdict, "white")
    body = "\n".join(f"• {r}" for r in feas.reasons)
    console.print(Panel(body, title=f"적합성: [{color}]{feas.verdict}[/{color}]", border_style=color))

    console.print(Panel(cls.disclaimer, border_style="red"))


@app.command("diff")
def diff_cmd(
    slug: str = typer.Argument(..., help="처방 슬러그 (예: daily-toner)"),
    old_version: str = typer.Argument(..., help="이전 버전 (예: v1)"),
    new_version: str = typer.Argument(..., help="비교할 버전 (예: v2)"),
    units: int = typer.Option(1000, "--units", "-u", help="원가 비교 기준 수량"),
) -> None:
    """두 처방 버전의 원료·함량·개당원가 변화를 비교한다."""
    ov = _parse_version(old_version)
    nv = _parse_version(new_version)
    lab = BrandLab.load()
    old = _find_formula(lab, slug, ov)
    new = _find_formula(lab, slug, nv)
    d = formula_diff(
        old, new, ingredients=lab.ingredients, packaging=lab.packaging, cost_units=units
    )

    console.print(
        Panel.fit(
            f"[cyan]{d.slug}[/cyan]  v{d.old_version} → v{d.new_version}\n"
            f"{d.old_product}  →  {d.new_product}",
            title="처방 비교(diff)",
        )
    )

    mark = {"신규": "green", "삭제": "red", "증량": "yellow", "감량": "yellow", "유지": "dim"}
    table = Table(title="원료 함량 변화", title_justify="left", header_style="bold")
    table.add_column("원료")
    table.add_column(f"v{d.old_version} %", justify="right")
    table.add_column(f"v{d.new_version} %", justify="right")
    table.add_column("Δ", justify="right")
    table.add_column("변화")
    for l in d.lines:
        color = mark.get(l.change, "white")
        old_s = f"{l.old_percent:g}" if l.old_percent is not None else "―"
        new_s = f"{l.new_percent:g}" if l.new_percent is not None else "―"
        delta_s = f"{l.delta:+g}" if l.delta is not None else ""
        table.add_row(l.name, old_s, new_s, delta_s, f"[{color}]{l.change}[/{color}]")
    console.print(table)

    # 원가 변화
    c = d.cost
    if c.note:
        console.print(f"[yellow]⚠ {c.note}[/yellow]")
    else:
        def won(x: float | None) -> str:
            return f"{x:,.0f}원" if x is not None else "-"

        def signed(x: float | None) -> str:
            if x is None:
                return "-"
            color = "red" if x > 0 else "green" if x < 0 else "dim"
            return f"[{color}]{x:+,.0f}원[/{color}]"

        ctable = Table(
            title=f"개당 원가 변화 (수량 {units:,}개 기준)",
            title_justify="left",
            header_style="bold",
        )
        ctable.add_column("항목")
        ctable.add_column(f"v{d.old_version}", justify="right")
        ctable.add_column(f"v{d.new_version}", justify="right")
        ctable.add_column("Δ", justify="right")
        ctable.add_row("개당 원료비", won(c.old_material), won(c.new_material), signed(c.material_delta))
        ctable.add_row("개당 원가", won(c.old_unit), won(c.new_unit), signed(c.unit_delta))
        console.print(ctable)

    for w in d.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")


@app.command("check")
def check_cmd(
    slug: str = typer.Argument(..., help="처방 슬러그 (예: daily-lotion)"),
    version: str = typer.Argument(..., help="버전 (예: v1)"),
) -> None:
    """제조 전 사전점검: HLB 유화 균형 + 배합한도 스캔."""
    ver = _parse_version(version)
    lab = BrandLab.load()
    formula = _find_formula(lab, slug, ver)
    result = check_formula(formula, ingredients=lab.ingredients, limits=lab.limits)

    console.print(
        Panel.fit(
            f"[bold]{formula.product}[/bold]  ([cyan]{formula.slug}[/cyan] v{formula.version})",
            title="처방 사전점검(check)",
        )
    )

    # HLB
    h = result.hlb
    hcolor = {"적합": "green", "주의": "yellow", "위험": "red", "해당없음": "dim"}.get(
        h.verdict, "white"
    )
    console.print(
        Panel(
            h.message
            + (
                f"\n유화제: {', '.join(h.emulsifiers)}\n유상: {', '.join(h.oils)}"
                if h.applicable
                else ""
            ),
            title=f"HLB 균형: [{hcolor}]{h.verdict}[/{hcolor}]",
            border_style=hcolor,
        )
    )

    # 배합한도
    if not result.limit_findings:
        console.print("[green]✓ 배합한도 초과·근접 원료 없음[/green]")
    else:
        ltable = Table(title="배합한도 점검", title_justify="left", header_style="bold")
        ltable.add_column("원료")
        ltable.add_column("함량 %", justify="right")
        ltable.add_column("한도 %", justify="right")
        ltable.add_column("출처")
        ltable.add_column("판정")
        for f in result.limit_findings:
            scolor = "red" if f.status == "초과" else "yellow"
            ltable.add_row(
                f.name,
                f"{f.percent:g}",
                f"{f.limit:g}",
                f.source,
                f"[{scolor}]{f.status}[/{scolor}]",
            )
        console.print(ltable)

    verdict = "[green]통과[/green]" if result.ok else "[red]확인 필요[/red]"
    console.print(f"종합: {verdict}")


batchlog_app = typer.Typer(help="배치 기록(실측 결과)", no_args_is_help=True)
app.add_typer(batchlog_app, name="batchlog")


@batchlog_app.command("new")
def batchlog_new(
    slug: str = typer.Argument(..., help="처방 슬러그 (예: daily-toner)"),
    version: str = typer.Argument(..., help="버전 (예: v1)"),
    grams: float = typer.Option(..., "--grams", "-g", help="목표 배치 크기(g)"),
) -> None:
    """목표 무게를 채운 빈 배치 기록 YAML을 experiments/batches/에 생성한다."""
    ver = _parse_version(version)
    lab = BrandLab.load()
    formula = _find_formula(lab, slug, ver)

    today = date_cls.today()
    # 같은 처방·같은 날짜의 기존 기록 수 + 1 로 시퀀스 결정
    existing = [p.name for p in iter_batch_paths()]
    prefix = make_batch_id(slug, today, 0).rsplit("-", 1)[0]  # 접두어-날짜
    seq = sum(1 for n in existing if n.startswith(prefix)) + 1
    batch_id = make_batch_id(slug, today, seq)

    record = new_batch_record(
        formula, grams, ingredients=lab.ingredients, batch_id=batch_id, on_date=today
    )
    out_dir = EXPERIMENTS_DIR / "batches"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{batch_id}.yaml"
    if out_path.exists():
        raise typer.BadParameter(f"이미 존재합니다: {out_path}")

    with out_path.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(
            batch_record_to_yaml_dict(record),
            fp,
            allow_unicode=True,
            sort_keys=False,
        )

    console.print(
        Panel.fit(
            f"배치 기록 생성: [bold]{batch_id}[/bold]\n{out_path}\n\n"
            "→ 제조 후 [bold]actual_g / yield_g / ph / observations[/bold] 를 채우세요.",
            title="batchlog new",
        )
    )


@batchlog_app.command("summary")
def batchlog_summary() -> None:
    """배치 기록들을 수율·pH 표로 요약한다."""
    records = load_all_batches()
    rows = batch_summary(records)
    if not rows:
        console.print("[dim]배치 기록이 없습니다. 'brandlab batchlog new'로 시작하세요.[/dim]")
        return
    table = Table(title="배치 기록 요약", title_justify="left", header_style="bold")
    table.add_column("배치ID")
    table.add_column("처방")
    table.add_column("일자")
    table.add_column("목표g", justify="right")
    table.add_column("회수g", justify="right")
    table.add_column("수율", justify="right")
    table.add_column("pH", justify="right")
    for r in rows:
        yield_s = f"{r.yield_g:g}" if r.yield_g is not None else "―"
        pct_s = f"{r.yield_percent:g}%" if r.yield_percent is not None else "―"
        if r.ph is None:
            ph_s = "―"
        else:
            pcolor = "green" if r.ph_ok else "red"
            ph_s = f"[{pcolor}]{r.ph:g}[/{pcolor}]"
        table.add_row(
            r.batch_id, r.formula_ref, r.date.isoformat(), f"{r.target_g:g}", yield_s, pct_s, ph_s
        )
    console.print(table)


ingredient_app = typer.Typer(help="원료 데이터 관리", no_args_is_help=True)
app.add_typer(ingredient_app, name="ingredient")


@ingredient_app.command("enrich")
def ingredient_enrich(
    ing_id: str = typer.Argument(..., help="원료 id (예: glycerin)"),
    write: bool = typer.Option(
        False, "--write", help="누락 필드(cas·density)를 ingredients.yaml에 반영"
    ),
    force: bool = typer.Option(False, "--force", help="이미 값이 있어도 덮어씀"),
    timeout: float = typer.Option(10.0, "--timeout", help="조회 타임아웃(초)"),
) -> None:
    """PubChem(무인증)에서 원료의 CAS·밀도·분자정보를 조회한다.

    기본은 조회만(dry-run). --write 를 주면 비어 있는 필드만 채운다.
    """
    lab = BrandLab.load()
    ing = lab.ingredients.index().get(ing_id)
    if ing is None:
        available = ", ".join(sorted(lab.ingredients.index()))
        raise typer.BadParameter(f"원료 id를 찾을 수 없습니다: {ing_id}\n사용 가능: {available}")

    console.print(
        Panel.fit(
            f"[bold]{ing.name}[/bold]  ([cyan]{ing.id}[/cyan])\nINCI: {ing.inci}",
            title="PubChem 원료 조회(enrich)",
        )
    )

    with console.status("PubChem 조회 중…"):
        data = fetch_pubchem(
            name=ing.inci,
            cas=ing.cas,
            get_json=lambda u: http_get_json(u, timeout=timeout),
        )

    if not data.found:
        console.print("[yellow]PubChem에서 원료를 찾지 못했습니다.[/yellow]")
        for n in data.notes:
            console.print(f"[dim]  · {n}[/dim]")
        return

    # 채울 수 있는 모델 필드: cas, density (MW·분자식은 정보 표시만)
    proposals: dict[str, object] = {}
    table = Table(title="조회 결과", title_justify="left", header_style="bold")
    table.add_column("필드")
    table.add_column("현재값")
    table.add_column("PubChem")
    table.add_column("반영")

    def plan(field: str, current: object, suggested: object) -> str:
        if suggested is None:
            return "-"
        if current is not None and not force:
            return "[dim]유지[/dim]"  # 이미 값 있음
        proposals[field] = suggested
        return "[green]채움[/green]" if write else "[cyan]제안[/cyan]"

    table.add_row("CAS", str(ing.cas or "―"), str(data.cas or "―"), plan("cas", ing.cas, data.cas))
    table.add_row(
        "density", str(ing.density or "―"), str(data.density or "―"),
        plan("density", ing.density, data.density),
    )
    table.add_row("분자량", "―", str(data.molecular_weight or "―"), "[dim]정보[/dim]")
    table.add_row("분자식", "―", str(data.molecular_formula or "―"), "[dim]정보[/dim]")
    console.print(table)
    if data.source_url:
        console.print(f"[dim]출처: {data.source_url}[/dim]")
    for n in data.notes:
        console.print(f"[dim]  · {n}[/dim]")

    if not write:
        if proposals:
            console.print(
                "\n[dim]--write 를 주면 위 '제안' 필드를 ingredients.yaml에 반영합니다.[/dim]"
            )
        return

    if not proposals:
        console.print("[green]반영할 새 값이 없습니다(이미 채워져 있음).[/green]")
        return

    # 원문 텍스트를 주석 보존 방식으로 갱신 → 재검증(실패 시 롤백)
    path = DATA_DIR / "ingredients.yaml"
    original = path.read_text(encoding="utf-8")
    new_text, applied = set_ingredient_fields(original, ing_id, proposals)
    path.write_text(new_text, encoding="utf-8")
    try:
        load_ingredients(path)
    except Exception as exc:  # noqa: BLE001 — 어떤 검증 오류든 롤백
        path.write_text(original, encoding="utf-8")
        raise typer.Exit(code=1) from exc

    console.print("[green]✓ ingredients.yaml 갱신:[/green] " + ", ".join(f"{k}={v}" for k, v in applied.items()))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
