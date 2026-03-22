"""
Ranking item detail page — /ranking_item
Shows market history charts and stats for a specific item.
"""

import logging
from datetime import datetime, timedelta

from nicegui import ui, app as nicegui_app
from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.models.item import Item
from app.models.cache import MarketPriceCache
from app.models.market_snapshot import MarketSnapshot
from app.services.settings_service import load_settings
from app.services.esi_client import esi_client, ESIError
from app.ui.layout import page_layout

logger = logging.getLogger(__name__)

_REGION_LABELS = {
    10000002: "Jita (The Forge)",
    10000043: "Amarr (Domain)",
    10000032: "Dodixie (Sinq Laison)",
    10000030: "Rens (Heimatar)",
    10000042: "Hek (Metropolis)",
}

SOURCE_OPTIONS = {
    "region:10000002": "Jita (The Forge)",
    "region:10000043": "Amarr (Domain)",
}


@ui.page("/ranking_item")
async def ranking_item_page(type_id: int = 0, source: str = "region:10000002", window: int = 7):
    """Página de detalhe de um item do ranking."""
    if not type_id:
        with page_layout("Detalhe do Item"):
            ui.label("type_id inválido.").classes("text-orange-5")
            ui.button("Voltar", on_click=lambda: ui.navigate.to("/ranking")).props("flat color=grey-5")
        return

    if source not in SOURCE_OPTIONS:
        source = "region:10000002"

    window = max(7, min(30, window))

    try:
        src_type, src_id_str = source.split(":", 1)
        src_region_id = int(src_id_str) if src_type == "region" else None
    except (ValueError, AttributeError):
        src_type, src_region_id = "region", 10000002

    item = None
    source_sell = None
    source_vol  = None
    local_sell  = None
    local_vol   = None
    net_profit  = None
    local_market = "region:10000002"
    freight_per_m3 = 0.0
    sales_tax = 0.08
    broker_fee = 0.03

    try:
        async with AsyncSessionLocal() as db:
            item_res = await db.execute(select(Item).where(Item.type_id == type_id))
            item = item_res.scalar_one_or_none()
            if item is None:
                with page_layout("Detalhe do Item"):
                    ui.label(f"Item {type_id} não encontrado.").classes("text-orange-5")
                    ui.button("Voltar", on_click=lambda: ui.navigate.to("/ranking")).props("flat color=grey-5")
                return

            s = await load_settings(db)
            local_market    = s["default_market_source"]
            freight_per_m3  = s["default_freight_cost_per_m3"]
            sales_tax       = s["default_sales_tax_pct"]
            broker_fee      = s["default_broker_fee_pct"]

            # Preço na fonte
            src_cache = await db.execute(
                select(MarketPriceCache.price, MarketPriceCache.total_volume).where(
                    MarketPriceCache.type_id == type_id,
                    MarketPriceCache.market_type == src_type,
                    MarketPriceCache.market_id == int(src_id_str),
                    MarketPriceCache.order_type == "sell",
                )
            )
            src_row = src_cache.one_or_none()
            source_sell = src_row.price        if src_row else None
            source_vol  = src_row.total_volume if src_row else None

            # Preço no mercado local
            try:
                local_type, local_id_str = local_market.split(":", 1)
                local_id = int(local_id_str)
            except (ValueError, AttributeError):
                local_type, local_id = "region", 10000002

            if local_type == "structure":
                local_row_res = await db.execute(
                    select(MarketSnapshot.best_sell, MarketSnapshot.sell_volume).where(
                        MarketSnapshot.structure_id == local_id,
                        MarketSnapshot.type_id == type_id,
                    )
                )
                lrow = local_row_res.one_or_none()
            else:
                local_cache = await db.execute(
                    select(MarketPriceCache.price, MarketPriceCache.total_volume).where(
                        MarketPriceCache.type_id == type_id,
                        MarketPriceCache.market_type == local_type,
                        MarketPriceCache.market_id == local_id,
                        MarketPriceCache.order_type == "sell",
                    )
                )
                lrow = local_cache.one_or_none()

            if lrow:
                local_sell = lrow[0]
                local_vol  = lrow[1]

            # Calcula lucro
            if source_sell and local_sell:
                freight_unit = freight_per_m3 * (item.volume or 0.0)
                net_revenue  = local_sell * (1.0 - sales_tax - broker_fee)
                net_profit   = net_revenue - source_sell - freight_unit

    except Exception as exc:
        logger.error("Ranking item load error: %s", exc)

    with page_layout(f"Ranking — {item.type_name if item else type_id}"):
        with ui.row().classes("items-center gap-3 q-mb-sm"):
            ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/ranking")).props(
                "flat round dense color=grey-5"
            )
            ui.label(item.type_name if item else f"Type {type_id}").classes("text-h5 text-white")

        # Sumário de preços (dados do banco — disponíveis imediatamente)
        with ui.row().classes("gap-4 q-mb-lg flex-wrap"):
            _price_card("Fonte", SOURCE_OPTIONS.get(source, source), source_sell, source_vol, "blue-8")
            _price_card("Local", local_market, local_sell, local_vol, "teal-8")
            if net_profit is not None:
                profit_color = "green-8" if net_profit > 0 else "red-8"
                with ui.card().classes(f"q-pa-md bg-{profit_color} text-white shadow-4 min-w-40"):
                    ui.label("Lucro Líq./un").classes("text-caption opacity-80")
                    ui.label(f"{net_profit:,.0f} ISK").classes("text-h6 font-bold")

        # Seletor de janela de tempo
        with ui.row().classes("items-center gap-3 q-mb-md"):
            ui.label("Janela:").classes("text-grey-5 text-caption")
            for w in [7, 14, 30]:
                is_active = w == window
                ui.button(
                    f"{w}d",
                    on_click=lambda w_=w: ui.navigate.to(
                        f"/ranking_item?type_id={type_id}&source={source}&window={w_}"
                    ),
                ).props(
                    f"{'unelevated color=primary' if is_active else 'flat color=grey-5'} dense"
                )

        # Histórico: renderiza spinner imediatamente, busca ESI em segundo plano
        history_container = ui.column().classes("w-full")

        if not src_region_id:
            with history_container:
                ui.label("Histórico disponível apenas para mercados de região.").classes("text-grey-5")
        else:
            with history_container:
                with ui.row().classes("items-center gap-2 q-pa-md"):
                    ui.spinner("dots", color="grey-5")
                    ui.label("Carregando histórico de mercado...").classes("text-grey-5 text-caption")

            _tid_hist    = type_id
            _region_hist = src_region_id
            _win_hist    = window
            _name_hist   = item.type_name if item else str(type_id)

            async def _load_history():
                hist: list[dict] = []
                hist_error: str | None = None
                try:
                    raw = await esi_client.get_market_history(_region_hist, _tid_hist)
                    raw.sort(key=lambda x: x["date"])
                    cutoff = (datetime.utcnow() - timedelta(days=_win_hist)).strftime("%Y-%m-%d")
                    hist = [r for r in raw if r["date"] >= cutoff]
                except ESIError as exc:
                    hist_error = f"Erro ESI {exc.status_code}"
                except Exception as exc:
                    hist_error = str(exc)

                history_container.clear()
                with history_container:
                    if hist_error:
                        ui.label(f"Erro ao carregar histórico: {hist_error}").classes("text-orange-5")
                    elif not hist:
                        ui.label("Nenhum dado histórico disponível.").classes("text-grey-5")
                    else:
                        volumes    = [h["volume"]  for h in hist]
                        avg_prices = [h["average"] for h in hist]
                        stats = {
                            "avg_daily_vol": sum(volumes) / len(volumes),
                            "proj_weekly":   sum(volumes) / len(volumes) * 7,
                            "avg_price":     sum(avg_prices) / len(avg_prices),
                            "min_price":     min(h["lowest"]  for h in hist),
                            "max_price":     max(h["highest"] for h in hist),
                        }

                        with ui.row().classes("gap-3 q-mb-md flex-wrap"):
                            _stat_card("Vol. Médio/dia", f"{stats['avg_daily_vol']:,.0f}", "bar_chart")
                            _stat_card("Proj. Semanal",  f"{stats['proj_weekly']:,.0f}",  "date_range")
                            _stat_card("Preço Médio",    f"{stats['avg_price']:,.2f} ISK","price_check")
                            _stat_card("Min Preço",      f"{stats['min_price']:,.2f} ISK","trending_down")
                            _stat_card("Max Preço",      f"{stats['max_price']:,.2f} ISK","trending_up")

                        from app.ui.components.price_chart import render_price_charts
                        render_price_charts(hist, _name_hist)

                        with ui.card().classes("q-pa-md bg-grey-9 w-full"):
                            ui.label("Histórico Detalhado").classes(
                                "text-subtitle1 text-white q-mb-sm font-bold"
                            )
                            columns = [
                                {"name": "date",    "label": "Data",    "field": "date",    "align": "left",  "sortable": True},
                                {"name": "volume",  "label": "Volume",  "field": "volume",  "align": "right", "sortable": True},
                                {"name": "lowest",  "label": "Mínimo",  "field": "lowest",  "align": "right"},
                                {"name": "average", "label": "Médio",   "field": "average", "align": "right"},
                                {"name": "highest", "label": "Máximo",  "field": "highest", "align": "right"},
                            ]
                            rows = [
                                {
                                    "date":    h["date"],
                                    "volume":  f"{h['volume']:,}",
                                    "lowest":  f"{h['lowest']:,.2f}",
                                    "average": f"{h['average']:,.2f}",
                                    "highest": f"{h['highest']:,.2f}",
                                }
                                for h in reversed(hist)
                            ]
                            ui.table(columns=columns, rows=rows, row_key="date").props(
                                "dark flat bordered dense virtual-scroll"
                            ).classes("w-full text-grey-3 max-h-64")

            ui.timer(0.1, _load_history, once=True)


def _price_card(label: str, market_name: str, price, volume, color: str):
    with ui.card().classes(f"q-pa-md bg-{color} text-white shadow-4 min-w-44"):
        ui.label(label).classes("text-caption opacity-80")
        ui.label(market_name).classes("text-caption opacity-70 text-xs q-mb-xs")
        if price:
            ui.label(f"{price:,.2f} ISK").classes("text-h6 font-bold")
            if volume:
                ui.label(f"Vol: {volume:,}").classes("text-caption opacity-80")
        else:
            ui.label("Sem dados").classes("text-caption opacity-70")


def _stat_card(label: str, value: str, icon: str):
    with ui.card().classes("q-pa-sm bg-grey-9 text-white shadow-2 min-w-32"):
        with ui.row().classes("items-center gap-2"):
            ui.icon(icon).classes("text-grey-5")
            with ui.column().classes("gap-0"):
                ui.label(value).classes("text-body1 font-bold")
                ui.label(label).classes("text-caption text-grey-5")
