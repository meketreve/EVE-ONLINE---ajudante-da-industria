"""
Cost breakdown card component.
Shows profit banner, summary cards and detailed breakdown.
"""

from nicegui import ui


def render_cost_breakdown(
    item,
    blueprint,
    runs: int,
    sell_price,
    cost_bd,
    profit_bd,
    prices_age_str: str = "",
    active_structure=None,
):
    is_profitable = profit_bd.net_profit > 0
    margin_pct    = profit_bd.margin_pct
    total_units   = runs * blueprint.product_quantity

    # ── Banner principal: lucro + margem em destaque ──────────────────────────
    banner_color = "green-8" if is_profitable else "red-8"
    with ui.card().classes(f"q-pa-md bg-{banner_color} w-full shadow-6"):
        with ui.row().classes("items-center justify-between w-full flex-wrap gap-4"):

            # Identificação
            with ui.column().classes("gap-0 flex-1"):
                ui.label(item.type_name).classes("text-h6 text-white font-bold")
                sub = f"{runs} run(s) × {blueprint.product_quantity} un. = {total_units:,} un."
                if active_structure:
                    sub += f"  ·  {active_structure.name} (ME {active_structure.me_bonus:.1f}%)"
                ui.label(sub).classes("text-caption text-white opacity-70")
                if prices_age_str:
                    ui.label(f"Preços: {prices_age_str}").classes("text-caption text-white opacity-50")

            # Lucro líquido + margem
            with ui.row().classes("gap-6 items-center"):
                with ui.column().classes("gap-0 items-center"):
                    ui.label("LUCRO LÍQUIDO").classes("text-caption text-white opacity-70 font-bold tracking-wide")
                    ui.label(_fmt(profit_bd.net_profit)).classes("text-h5 text-white font-bold")

                ui.separator().props("vertical color=white").classes("opacity-30 q-mx-xs")

                with ui.column().classes("gap-0 items-center"):
                    ui.label("MARGEM").classes("text-caption text-white opacity-70 font-bold tracking-wide")
                    ui.label(f"{margin_pct:.1f}%").classes("text-h5 text-white font-bold")

    # ── Cards de resumo secundários ───────────────────────────────────────────
    with ui.row().classes("gap-2 q-mt-sm flex-wrap"):
        _summary_card("Custo Materiais", cost_bd.material_cost,    "inventory_2", "blue-grey-7")
        _summary_card("Custo do Job",    cost_bd.job_cost,          "work",        "blue-7")
        _summary_card("Custo Total",     cost_bd.total_cost,        "calculate",   "orange-7")
        _summary_card("Preço de Venda",
                      (sell_price or 0) * blueprint.product_quantity * runs,
                      "sell",             "teal-7")

    # ── Detalhes expandidos — aberto por padrão ───────────────────────────────
    with ui.expansion("Detalhes do Cálculo", icon="expand_more").classes(
        "w-full text-grey-4 q-mt-xs"
    ).props("default-opened"):
        with ui.grid(columns=2).classes("gap-x-8 gap-y-1 q-pa-sm text-caption"):
            _detail_row("Custo de Materiais",         cost_bd.material_cost)
            _detail_row("Custo do Job (índice+taxa)", cost_bd.job_cost)
            _detail_row("Índice de Sistema",          cost_bd.system_cost_index * 100, pct=True)
            _detail_row("Taxa da Instalação",          cost_bd.facility_tax * 100,     pct=True)
            _detail_row("SCC Surcharge",               cost_bd.scc_surcharge * 100,    pct=True)
            ui.separator().classes("col-span-2 q-my-xs")
            _detail_row("Custo Total Produção",        cost_bd.total_cost)
            _detail_row("Receita Bruta",               profit_bd.sale_price)
            _detail_row("Lucro Bruto",                 profit_bd.gross_profit)
            _detail_row("Broker Fee",                  profit_bd.broker_fee)
            _detail_row("Sales Tax",                   profit_bd.sales_tax)
            _detail_row("Lucro Líquido",               profit_bd.net_profit)
            _detail_row("Margem",                      profit_bd.margin_pct, pct=True)


def _summary_card(label: str, value: float, icon: str, color: str):
    with ui.card().classes(f"q-pa-sm bg-{color} text-white shadow-2 min-w-28"):
        with ui.row().classes("items-center gap-2"):
            ui.icon(icon).classes("text-xl opacity-80")
            with ui.column().classes("gap-0"):
                ui.label(_fmt(value)).classes("text-body1 font-bold")
                ui.label(label).classes("text-caption opacity-80")


def _detail_row(label: str, value: float, pct: bool = False):
    ui.label(label).classes("text-grey-5")
    if pct:
        ui.label(f"{value:.2f}%").classes("text-grey-3 text-right")
    else:
        color = "text-green-4" if value > 0 else "text-red-4" if value < 0 else "text-grey-3"
        ui.label(_fmt(value)).classes(f"{color} text-right")


def _fmt(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} B ISK"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f} M ISK"
    return f"{value:,.0f} ISK"
