"""
Import page — /ranking
Tab 1: Oportunidades de importação (ranking automático).
Tab 2: Comparador de lista — dado um conjunto de itens, calcula se é mais barato
       comprar no mercado local ou importar de outro hub.
"""

import logging
import re
from datetime import datetime, timedelta

from nicegui import ui, app as nicegui_app
from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.models.item import Item
from app.models.cache import MarketPriceCache
from app.models.market_snapshot import MarketSnapshot
from app.services.market_service import (
    refresh_region_market_prices,
    get_prices_cache_only,
    refresh_prices_for_types,
)
from app.services.character_service import get_character, get_fresh_token, get_market_options
from app.services.settings_service import load_settings
from app.ui.layout import page_layout

logger = logging.getLogger(__name__)

# Threshold para exibir aviso visual de dados velhos (sem auto-refresh automático)
_STALE_WARN_THRESHOLD = timedelta(hours=1)


def _fmt_age(dt: datetime | None) -> str:
    """Retorna string legível da idade de um timestamp."""
    if dt is None:
        return "sem dados"
    secs = (datetime.utcnow() - dt).total_seconds()
    if secs < 60:
        return "agora mesmo"
    if secs < 3600:
        return f"{int(secs / 60)} min atrás"
    return f"{int(secs / 3600)}h atrás"


SOURCE_OPTIONS = {
    "region:10000002": "Jita (The Forge)",
    "region:10000043": "Amarr (Domain)",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_item_list(text: str) -> list[tuple[str, int]]:
    """
    Converte texto no formato 'Nome do Item 1000' (um por linha) em lista de (nome, qtd).
    Aceita separadores como ' x ', ' X ', tabulação, vírgulas e pontos em números.
    Exemplo de linhas válidas:
        Tritanium 150000
        Pyerite x 50,000
        Mexallon	12000
    """
    result = []
    for raw in text.strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        # Separa número (com possível 'x' antes) no final da linha
        m = re.match(r"^(.+?)\s+[xX]?\s*([\d,\.]+)\s*$", line)
        if not m:
            continue
        name = m.group(1).strip()
        qty_str = re.sub(r"[,\.](?=\d{3})", "", m.group(2))  # remove separadores de milhar
        try:
            qty = int(float(qty_str))
            if qty > 0:
                result.append((name, qty))
        except ValueError:
            pass
    return result


def _split_market_key(key: str) -> tuple[str, int]:
    try:
        mtype, mid = key.split(":", 1)
        return mtype, int(mid)
    except (ValueError, AttributeError):
        return "region", 10000002


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@ui.page("/ranking")
async def ranking_page(source: str = "region:10000002", min_profit: float = 0, min_volume: int = 0):
    """Página de importação — duas abas: ranking automático e comparador de lista."""
    if source not in SOURCE_OPTIONS:
        source = "region:10000002"

    # Carrega opções de mercado e configurações
    market_options: dict[str, str] = {}
    default_local = "region:10000002"
    default_freight = 500.0

    try:
        async with AsyncSessionLocal() as db:
            s = await load_settings(db)
            default_local = s.get("default_market_source", "region:10000002")
            default_freight = s.get("default_freight_cost_per_m3", 500.0)
            opts = await get_market_options(0, db)
            for group in opts["groups"]:
                for m in group["markets"]:
                    market_options[m["value"]] = m["label"]
            for m in opts.get("private", []):
                market_options[m["value"]] = m["label"]
    except Exception as exc:
        logger.warning("Failed to load market options: %s", exc)

    if not market_options:
        market_options = dict(SOURCE_OPTIONS)

    if default_local not in market_options:
        default_local = "region:10000002"

    with page_layout("Importação"):
        ui.label("Importação").classes("text-h5 text-white q-mb-sm")

        with ui.tabs().classes("text-white") as tabs:
            ui.tab("oportunidades", label="Oportunidades", icon="leaderboard")
            ui.tab("comparador",    label="Comparador de Lista", icon="compare_arrows")

        with ui.tab_panels(tabs, value="oportunidades").classes("w-full q-mt-md"):
            with ui.tab_panel("oportunidades"):
                await _build_ranking_tab(source, min_profit, min_volume, market_options)

            with ui.tab_panel("comparador"):
                await _build_comparator_tab(market_options, default_local, default_freight)


# ---------------------------------------------------------------------------
# Tab 1 — Ranking automático
# ---------------------------------------------------------------------------

async def _build_ranking_tab(
    source: str,
    min_profit: float,
    min_volume: int,
    market_options: dict[str, str],
):
    result_container = ui.column().classes("w-full gap-3")
    status_label_ref: list = [None]

    with ui.row().classes("items-center gap-3 q-mb-sm flex-wrap"):
        source_select = ui.select(
            options=SOURCE_OPTIONS,
            value=source,
            label="Mercado Fonte",
        ).classes("min-w-40")
        source_select.props("outlined dense dark")

        min_profit_input = ui.number(
            label="Lucro Mínimo (ISK)",
            value=min_profit,
            min=0,
        ).classes("min-w-36")
        min_profit_input.props("outlined dense dark")

        min_vol_input = ui.number(
            label="Volume Mínimo",
            value=min_volume,
            min=0,
        ).classes("min-w-28")
        min_vol_input.props("outlined dense dark")

        ui.button(
            "Filtrar",
            icon="filter_list",
            on_click=lambda: refresh_ranking(),
        ).props("unelevated color=primary")

    with ui.row().classes("items-center gap-3 q-mb-md flex-wrap"):
        ui.button(
            "Atualizar Preços",
            icon="download",
            on_click=lambda: do_refresh_prices(),
        ).props("unelevated color=teal")
        status_label_ref[0] = ui.label("").classes("text-caption text-grey-5")

    async def do_refresh_prices():
        import asyncio as _asyncio

        src = source_select.value or "region:10000002"
        src_type, src_market_id = _split_market_key(src)

        if src_type != "region":
            ui.notify("Atualização em massa apenas para mercados de região.", type="warning")
            return

        lbl = status_label_ref[0]
        try:
            if lbl:
                lbl.set_text("Atualizando em segundo plano...")
        except RuntimeError:
            pass

        ui.notify(
            "Baixando ordens de mercado em segundo plano. O ranking será atualizado automaticamente.",
            type="info",
            timeout=8000,
        )

        async def _run_refresh():
            try:
                count_src = 0
                count_local = 0
                async with AsyncSessionLocal() as db:
                    count_src = await refresh_region_market_prices(src_market_id, db)

                    s = await load_settings(db)
                    local_market = s.get("default_market_source", "region:10000002")
                    local_type, local_market_id = _split_market_key(local_market)
                    if local_type == "region" and local_market_id != src_market_id:
                        count_local = await refresh_region_market_prices(local_market_id, db)

                    await db.commit()

                msg = f"Fonte: {count_src} itens"
                if count_local:
                    msg += f" | Local: {count_local} itens"
                try:
                    if lbl:
                        lbl.set_text(msg)
                    await refresh_ranking()
                except RuntimeError:
                    logger.debug("Client disconnected during price refresh; UI update skipped.")
            except Exception as exc:
                logger.error("Price refresh error: %s", exc, exc_info=True)
                try:
                    if lbl:
                        lbl.set_text(f"Erro: {exc}")
                    ui.notify(f"Erro ao atualizar: {exc}", type="negative")
                except RuntimeError:
                    pass

        _asyncio.create_task(_run_refresh())

    async def refresh_ranking():
        result_container.clear()
        with result_container:
            await _render_ranking(
                source_select.value or "region:10000002",
                float(min_profit_input.value or 0),
                int(min_vol_input.value or 0),
            )

    with result_container:
        await _render_ranking(source, min_profit, min_volume)


# ---------------------------------------------------------------------------
# Tab 2 — Comparador de lista
# ---------------------------------------------------------------------------

async def _build_comparator_tab(
    market_options: dict[str, str],
    default_local: str,
    default_freight: float,
):
    result_container = ui.column().classes("w-full gap-3")

    with ui.row().classes("gap-4 w-full items-start flex-wrap"):
        # Formulário
        with ui.card().classes("q-pa-md bg-grey-9 flex-1 min-w-72"):
            ui.label("Parâmetros").classes("text-subtitle1 text-white font-bold q-mb-sm")

            local_select = ui.select(
                options=market_options,
                value=default_local if default_local in market_options else next(iter(market_options)),
                label="Mercado Local (destino)",
            ).classes("w-full")
            local_select.props("outlined dense dark")

            import_select = ui.select(
                options=market_options,
                value="region:10000002" if "region:10000002" in market_options else next(iter(market_options)),
                label="Mercado de Importação (fonte)",
            ).classes("w-full")
            import_select.props("outlined dense dark")

            freight_input = ui.number(
                label="Custo de Frete (ISK/m³)",
                value=default_freight,
                min=0,
                step=100,
            ).classes("w-full")
            freight_input.props("outlined dense dark")

            ui.label("Lista de Itens (nome + quantidade por linha):").classes(
                "text-grey-4 text-caption q-mt-sm"
            )
            items_textarea = ui.textarea(
                placeholder=(
                    "Tritanium 150000\n"
                    "Pyerite x 50,000\n"
                    "Mexallon 12000"
                ),
            ).classes("w-full font-mono text-sm")
            items_textarea.props("outlined dark rows=10")

            with ui.row().classes("gap-2 q-mt-md"):
                ui.button(
                    "Calcular",
                    icon="calculate",
                    on_click=lambda: do_compare(),
                ).props("unelevated color=primary")

                ui.button(
                    "Atualizar Preços",
                    icon="refresh",
                    on_click=lambda: do_compare(force_refresh=True),
                ).props("flat color=grey-5")

        # Resultado
        result_container_col = ui.column().classes("flex-2 min-w-72 gap-3")
        with result_container_col:
            ui.label("Preencha os parâmetros e clique em Calcular.").classes("text-grey-6 q-pa-md")

    async def do_compare(force_refresh: bool = False):
        result_container_col.clear()

        raw_text = items_textarea.value or ""
        parsed = _parse_item_list(raw_text)
        if not parsed:
            ui.notify("Nenhum item válido na lista. Use o formato 'Nome Quantidade' por linha.", type="warning")
            return

        local_key = local_select.value or "region:10000002"
        import_key = import_select.value or "region:10000002"
        freight_m3 = float(freight_input.value or 0)

        local_type, local_id = _split_market_key(local_key)
        import_type, import_id = _split_market_key(import_key)

        with result_container_col:
            spinner = ui.spinner("dots", size="xl", color="primary").classes("q-ma-auto")

        try:
            async with AsyncSessionLocal() as db:
                s = await load_settings(db)
                sales_tax  = s.get("default_sales_tax_pct", 0.08)
                broker_fee = s.get("default_broker_fee_pct", 0.03)

                # Resolve nomes → type_ids
                name_map: dict[str, int] = {}     # nome original → type_id
                type_id_map: dict[int, str] = {}  # type_id → nome canônico
                not_found: list[str] = []

                for name, _qty in parsed:
                    # Primeiro tenta match exato, depois parcial
                    res = await db.execute(
                        select(Item.type_id, Item.type_name).where(
                            Item.type_name.ilike(name)
                        ).limit(1)
                    )
                    row = res.first()
                    if row is None:
                        res = await db.execute(
                            select(Item.type_id, Item.type_name).where(
                                Item.type_name.ilike(f"%{name}%")
                            ).limit(1)
                        )
                        row = res.first()
                    if row:
                        name_map[name] = row.type_id
                        type_id_map[row.type_id] = row.type_name
                    else:
                        not_found.append(name)

                type_ids = list(type_id_map.keys())

                # Volume m³ dos itens
                vol_res = await db.execute(
                    select(Item.type_id, Item.volume).where(Item.type_id.in_(type_ids))
                )
                vol_map: dict[int, float] = {r.type_id: (r.volume or 0.0) for r in vol_res.all()}

                # Tokens para estruturas privadas
                local_token = import_token = None
                char_id = nicegui_app.storage.general.get("character_id")
                if char_id:
                    char = await get_character(int(char_id), db)
                    if char:
                        tok = await get_fresh_token(char, db)
                        if local_type == "structure":
                            local_token = tok
                        if import_type == "structure":
                            import_token = tok

                # Preços locais
                local_prices, _ = await get_prices_cache_only(
                    type_ids, local_type, local_id, "sell", db
                )
                # Preços de importação
                import_prices, _ = await get_prices_cache_only(
                    type_ids, import_type, import_id, "sell", db
                )

                no_local  = all(p is None for p in local_prices.values())
                no_import = all(p is None for p in import_prices.values())

                if force_refresh or no_local or no_import:
                    if no_local or force_refresh:
                        await refresh_prices_for_types(
                            type_ids, local_type, local_id, "sell", db, token=local_token
                        )
                    if (no_import or force_refresh) and import_key != local_key:
                        await refresh_prices_for_types(
                            type_ids, import_type, import_id, "sell", db, token=import_token
                        )
                    local_prices, _ = await get_prices_cache_only(
                        type_ids, local_type, local_id, "sell", db
                    )
                    import_prices, _ = await get_prices_cache_only(
                        type_ids, import_type, import_id, "sell", db
                    )

        except Exception as exc:
            logger.error("Comparator error: %s", exc, exc_info=True)
            result_container_col.clear()
            with result_container_col:
                ui.notify(f"Erro: {exc}", type="negative")
            return

        # Monta resultados
        results = []
        for name, qty in parsed:
            tid = name_map.get(name)
            if tid is None:
                continue
            canonical = type_id_map.get(tid, name)
            vol_m3 = vol_map.get(tid, 0.0)
            freight_unit = freight_m3 * vol_m3

            lp = local_prices.get(tid)
            ip = import_prices.get(tid)

            # Custo local: preço de venda local
            local_total = lp * qty if lp else None
            # Custo importação: preço fonte + frete, sem contar taxas de venda
            # (assumimos que o usuário está COMPRANDO nesses mercados)
            import_total = (ip + freight_unit) * qty if ip else None

            if local_total is not None and import_total is not None:
                if import_total < local_total:
                    rec = "Importar"
                    saving = local_total - import_total
                else:
                    rec = "Local"
                    saving = import_total - local_total
            else:
                rec = "Sem dados"
                saving = None

            results.append({
                "name":          canonical,
                "qty":           qty,
                "vol_m3":        vol_m3,
                "local_unit":    lp,
                "import_unit":   ip,
                "freight_unit":  freight_unit,
                "local_total":   local_total,
                "import_total":  import_total,
                "rec":           rec,
                "saving":        saving,
            })

        # Ordena: importar primeiro (maior economia), depois local, depois sem dados
        results.sort(key=lambda x: (
            0 if x["rec"] == "Importar" else (1 if x["rec"] == "Local" else 2),
            -(x["saving"] or 0),
        ))

        result_container_col.clear()
        with result_container_col:
            if not_found:
                ui.label(f"Itens não encontrados: {', '.join(not_found)}").classes(
                    "text-orange-4 text-caption q-mb-sm"
                )

            if not results:
                ui.label("Nenhum resultado — verifique os nomes dos itens.").classes("text-grey-5 q-pa-md")
                return

            # Resumo rápido
            import_count = sum(1 for r in results if r["rec"] == "Importar")
            local_count  = sum(1 for r in results if r["rec"] == "Local")
            total_import = sum(r["import_total"] for r in results if r["import_total"] is not None and r["rec"] == "Importar")
            total_local_of_importables = sum(r["local_total"] for r in results if r["local_total"] is not None and r["rec"] == "Importar")
            total_economy = total_local_of_importables - total_import

            with ui.card().classes("q-pa-sm bg-grey-8 w-full"):
                with ui.row().classes("gap-4 flex-wrap items-center"):
                    ui.badge(f"{import_count} para importar", color="teal").classes("text-sm")
                    ui.badge(f"{local_count} comprar local", color="blue").classes("text-sm")
                    if total_economy > 0:
                        ui.label(f"Economia total importando: {total_economy:,.0f} ISK").classes(
                            "text-green-4 text-body2 font-bold"
                        )

            # Tabela detalhada
            with ui.card().classes("q-pa-md bg-grey-9 w-full"):
                columns = [
                    {"name": "name",         "label": "Item",          "field": "name",         "align": "left",  "sortable": True},
                    {"name": "qty",          "label": "Qtd.",          "field": "qty",          "align": "right"},
                    {"name": "local_unit",   "label": "Local/un",      "field": "local_unit",   "align": "right", "sortable": True},
                    {"name": "import_unit",  "label": "Fonte/un",      "field": "import_unit",  "align": "right", "sortable": True},
                    {"name": "freight_unit", "label": "Frete/un",      "field": "freight_unit", "align": "right"},
                    {"name": "local_total",  "label": "Total Local",   "field": "local_total",  "align": "right", "sortable": True},
                    {"name": "import_total", "label": "Total Import.", "field": "import_total", "align": "right", "sortable": True},
                    {"name": "saving",       "label": "Economia",      "field": "saving",       "align": "right", "sortable": True},
                    {"name": "rec",          "label": "Recomendação",  "field": "rec",          "align": "center"},
                ]

                rows = []
                for r in results:
                    rows.append({
                        "name":         r["name"],
                        "qty":          f"{r['qty']:,}",
                        "local_unit":   f"{r['local_unit']:,.2f}" if r["local_unit"] else "—",
                        "import_unit":  f"{r['import_unit']:,.2f}" if r["import_unit"] else "—",
                        "freight_unit": f"{r['freight_unit']:,.2f}" if r["freight_unit"] else "—",
                        "local_total":  f"{r['local_total']:,.0f}" if r["local_total"] else "—",
                        "import_total": f"{r['import_total']:,.0f}" if r["import_total"] else "—",
                        "saving":       f"{r['saving']:,.0f}" if r["saving"] else "—",
                        "rec":          r["rec"],
                    })

                table = ui.table(columns=columns, rows=rows, row_key="name").props(
                    "dark flat bordered dense virtual-scroll"
                ).classes("w-full text-grey-3 max-h-screen")

                table.add_slot("body-cell-rec", """
                    <q-td :props="props">
                        <q-badge
                            :color="props.row.rec === 'Importar' ? 'teal'
                                   : props.row.rec === 'Local' ? 'blue'
                                   : 'grey'"
                            :label="props.row.rec"
                        />
                    </q-td>
                """)
                table.add_slot("body-cell-saving", """
                    <q-td :props="props">
                        <span :class="props.row.saving !== '—' ? 'text-green-4' : 'text-grey-6'">
                            {{ props.row.saving }}
                        </span>
                    </q-td>
                """)

            # ── Listas de compra exportáveis ──────────────────────────────────
            import_src_label  = import_select.value or "região fonte"
            import_local_label = local_select.value or "mercado local"

            import_lines = "\n".join(
                f"{r['name']} {r['qty']}"
                for r in results if r["rec"] == "Importar"
            )
            local_lines = "\n".join(
                f"{r['name']} {r['qty']}"
                for r in results if r["rec"] == "Local"
            )
            nodata_lines = "\n".join(
                f"{r['name']} {r['qty']}"
                for r in results if r["rec"] == "Sem dados"
            )

            ui.add_css("""
                .export-list textarea {
                    user-select: text !important;
                    cursor: text !important;
                    font-family: monospace;
                    font-size: 0.8rem;
                }
            """)

            with ui.row().classes("gap-3 w-full q-mt-sm flex-wrap"):
                # Lista: comprar na fonte (importar)
                with ui.card().classes("q-pa-sm bg-grey-9 flex-1 min-w-48"):
                    with ui.row().classes("items-center justify-between q-mb-xs"):
                        with ui.row().classes("items-center gap-1"):
                            ui.icon("flight_land").classes("text-teal-4 text-sm")
                            ui.label(f"Importar ({import_count})").classes(
                                "text-caption text-teal-4 font-bold"
                            )
                            ui.label("— comprar na fonte").classes("text-caption text-grey-6")
                        if import_lines:
                            async def _copy_import(txt=import_lines):
                                await ui.run_javascript(
                                    f"navigator.clipboard.writeText({repr(txt)})"
                                )
                                ui.notify("Lista copiada!", type="positive", timeout=1500)
                            ui.button(icon="content_copy", on_click=_copy_import).props(
                                "flat round dense size=xs color=grey-5"
                            ).tooltip("Copiar")
                    ui.textarea(value=import_lines or "(nenhum item para importar)").props(
                        "outlined dark readonly rows=8"
                    ).classes("w-full export-list").style("font-size: 0.8rem;")

                # Lista: comprar local
                with ui.card().classes("q-pa-sm bg-grey-9 flex-1 min-w-48"):
                    with ui.row().classes("items-center justify-between q-mb-xs"):
                        with ui.row().classes("items-center gap-1"):
                            ui.icon("store").classes("text-blue-4 text-sm")
                            ui.label(f"Comprar Local ({local_count})").classes(
                                "text-caption text-blue-4 font-bold"
                            )
                            ui.label("— comprar no mercado local").classes("text-caption text-grey-6")
                        if local_lines:
                            async def _copy_local(txt=local_lines):
                                await ui.run_javascript(
                                    f"navigator.clipboard.writeText({repr(txt)})"
                                )
                                ui.notify("Lista copiada!", type="positive", timeout=1500)
                            ui.button(icon="content_copy", on_click=_copy_local).props(
                                "flat round dense size=xs color=grey-5"
                            ).tooltip("Copiar")
                    ui.textarea(value=local_lines or "(nenhum item para comprar local)").props(
                        "outlined dark readonly rows=8"
                    ).classes("w-full export-list").style("font-size: 0.8rem;")

            # Lista: sem dados de preço (opcional, colapsada)
            if nodata_lines:
                with ui.expansion(
                    f"Sem dados de preço ({sum(1 for r in results if r['rec'] == 'Sem dados')})",
                    icon="help_outline",
                ).classes("w-full text-grey-6 q-mt-xs"):
                    ui.textarea(value=nodata_lines).props(
                        "outlined dark readonly rows=4"
                    ).classes("w-full export-list").style("font-size: 0.8rem;")


# ---------------------------------------------------------------------------
# Renderização do ranking automático (aba 1)
# ---------------------------------------------------------------------------

async def _render_ranking(source: str, min_profit: float, min_volume: int):
    """Renderiza o ranking de importação."""
    with ui.spinner("dots", size="xl", color="primary").classes("q-ma-auto"):
        pass

    # Variáveis de resultado coletadas dentro do bloco async
    same_market      = False
    opportunities:   list[dict] = []
    src_age:         datetime | None = None
    local_age:       datetime | None = None
    local_label:     str = "local"
    local_count:     int = 0
    src_count:       int = 0
    local_no_data:   bool = False

    try:
        async with AsyncSessionLocal() as db:
            s = await load_settings(db)
            local_market   = s["default_market_source"]
            freight_per_m3 = s["default_freight_cost_per_m3"]
            sales_tax      = s["default_sales_tax_pct"]
            broker_fee     = s["default_broker_fee_pct"]

            src_type, src_market_id = _split_market_key(source)
            try:
                local_type, local_market_id = _split_market_key(local_market)
            except Exception:
                local_type, local_market_id = "region", 10000002

            same_market = (src_type == local_type and src_market_id == local_market_id)

            # ── Mercado fonte ────────────────────────────────────────────────
            def _src_query():
                return select(
                    MarketPriceCache.type_id,
                    MarketPriceCache.price,
                    MarketPriceCache.total_volume,
                    MarketPriceCache.fetched_at,
                ).where(
                    MarketPriceCache.market_type == src_type,
                    MarketPriceCache.market_id   == src_market_id,
                    MarketPriceCache.order_type  == "sell",
                    MarketPriceCache.price.isnot(None),
                )

            src_rows_data = (await db.execute(_src_query())).all()

            # Calcula idade do cache fonte
            if src_rows_data:
                src_age = min(r.fetched_at for r in src_rows_data)

            # Auto-refresh: somente quando cache está completamente vazio
            if not src_rows_data and src_type == "region":
                src_count = await refresh_region_market_prices(src_market_id, db)
                await db.commit()
                src_rows_data = (await db.execute(_src_query())).all()
                if src_rows_data:
                    src_age = min(r.fetched_at for r in src_rows_data)

            if not src_rows_data:
                ui.label(
                    "Sem dados de preço para o mercado fonte. "
                    "Clique em 'Atualizar Preços' para baixar."
                ).classes("text-orange-5 q-pa-md")
                return

            source_prices = {
                r.type_id: {"price": r.price, "volume": r.total_volume}
                for r in src_rows_data
            }
            src_count = src_count or len(source_prices)

            # ── Mercado local ────────────────────────────────────────────────
            if local_type == "structure":
                local_rows_data = (await db.execute(
                    select(
                        MarketSnapshot.type_id,
                        MarketSnapshot.best_sell.label("price"),
                        MarketSnapshot.sell_volume.label("volume"),
                        MarketSnapshot.updated_at.label("fetched_at"),
                    ).where(MarketSnapshot.structure_id == local_market_id)
                )).all()
                if local_rows_data:
                    local_age = min(r.fetched_at for r in local_rows_data)
                local_label = "estrutura"
            else:
                def _local_query():
                    return select(
                        MarketPriceCache.type_id,
                        MarketPriceCache.price,
                        MarketPriceCache.total_volume.label("volume"),
                        MarketPriceCache.fetched_at,
                    ).where(
                        MarketPriceCache.market_type == local_type,
                        MarketPriceCache.market_id   == local_market_id,
                        MarketPriceCache.order_type  == "sell",
                    )

                local_rows_data = (await db.execute(_local_query())).all()
                if local_rows_data:
                    local_age = min(r.fetched_at for r in local_rows_data)

                # Auto-refresh local: somente quando cache está vazio
                if not local_rows_data and not same_market:
                    await refresh_region_market_prices(local_market_id, db)
                    await db.commit()
                    local_rows_data = (await db.execute(_local_query())).all()
                    if local_rows_data:
                        local_age = min(r.fetched_at for r in local_rows_data)
                local_label = "região"

            local_prices = {
                r.type_id: {"price": r.price, "volume": r.volume}
                for r in local_rows_data
            }
            local_count    = len(local_prices)
            local_no_data  = local_count == 0

            # ── Calcula oportunidades ────────────────────────────────────────
            items_res = await db.execute(
                select(Item.type_id, Item.type_name, Item.volume)
                .where(Item.type_id.in_(list(source_prices.keys())))
            )
            items_map = {r.type_id: r for r in items_res.all()}

            for type_id, src in source_prices.items():
                item_row = items_map.get(type_id)
                if not item_row:
                    continue
                local = local_prices.get(type_id)
                if not (local and local["price"]):
                    continue

                item_vol_m3  = item_row.volume or 0.0
                freight_unit = freight_per_m3 * item_vol_m3
                local_sell   = local["price"]
                local_vol    = local["volume"] or 0
                net_revenue  = local_sell * (1.0 - sales_tax - broker_fee)
                net_profit   = net_revenue - src["price"] - freight_unit
                margin_pct   = (net_profit / src["price"] * 100) if src["price"] else 0.0

                if net_profit < min_profit:
                    continue
                if min_volume and local_vol < min_volume:
                    continue

                opportunities.append({
                    "type_id":       type_id,
                    "type_name":     item_row.type_name,
                    "volume_m3":     item_vol_m3,
                    "source_sell":   src["price"],
                    "source_volume": src["volume"],
                    "local_sell":    local_sell,
                    "local_volume":  local_vol,
                    "freight_unit":  freight_unit,
                    "net_profit":    net_profit,
                    "margin_pct":    margin_pct,
                })

            opportunities.sort(key=lambda x: x["net_profit"], reverse=True)

    except Exception as exc:
        logger.error("Ranking error: %s", exc, exc_info=True)
        ui.notify(f"Erro ao carregar ranking: {exc}", type="negative")
        return

    if same_market:
        ui.label(
            "Mercado fonte e local são iguais. Configure um mercado local diferente nas Configurações."
        ).classes("text-orange-5 q-pa-md")
        return

    # ── Barra de status dos dados ────────────────────────────────────────────
    def _is_stale(dt: datetime | None) -> bool:
        return dt is not None and (datetime.utcnow() - dt) > _STALE_WARN_THRESHOLD

    with ui.row().classes("items-center gap-3 q-mb-sm flex-wrap"):
        src_name  = SOURCE_OPTIONS.get(source, source)
        src_stale = _is_stale(src_age)
        ui.badge(
            f"Fonte ({src_name}): {_fmt_age(src_age)}  •  {src_count:,} itens"
            + (" ⚠ desatualizado" if src_stale else ""),
            color="orange-8" if src_stale else "blue-grey-7",
        ).classes("text-caption")

        if local_no_data:
            ui.badge(
                f"Local ({local_label}): sem dados — "
                + ("aguardando crawler" if local_label == "estrutura" else "clique em Atualizar Preços"),
                color="negative",
            ).classes("text-caption")
        else:
            local_stale = _is_stale(local_age)
            ui.badge(
                f"Local ({local_label}): {_fmt_age(local_age)}  •  {local_count:,} itens"
                + (" ⚠ desatualizado" if local_stale else ""),
                color="orange-8" if local_stale else "teal-8",
            ).classes("text-caption")

    if local_no_data:
        if local_label == "estrutura":
            ui.label(
                "O mercado local é uma estrutura privada sem dados no cache. "
                "Vá em Configurações → Estruturas e Mercado e force um crawl da estrutura."
            ).classes("text-orange-5 q-pa-md")
        else:
            ui.label(
                "O mercado local não tem dados no cache. "
                "Clique em 'Atualizar Preços' para baixar as ordens."
            ).classes("text-orange-5 q-pa-md")
        return

    if not opportunities:
        ui.label(
            f"Nenhuma oportunidade encontrada com os filtros atuais. "
            f"({local_count} itens no mercado local, {src_count} na fonte)"
        ).classes("text-grey-5 q-pa-md")
        return

    # Tabela
    with ui.card().classes("q-pa-md bg-grey-9 w-full"):
        with ui.row().classes("items-center gap-2 q-mb-sm"):
            ui.icon("leaderboard").classes("text-yellow-5")
            ui.label(f"Oportunidades ({len(opportunities)})").classes(
                "text-subtitle1 text-white font-bold"
            )

        columns = [
            {"name": "type_name",    "label": "Item",          "field": "type_name",    "align": "left",  "sortable": True},
            {"name": "source_sell",  "label": "Fonte (ISK)",   "field": "source_sell",  "align": "right", "sortable": True},
            {"name": "local_sell",   "label": "Local (ISK)",   "field": "local_sell",   "align": "right", "sortable": True},
            {"name": "freight_unit", "label": "Frete/un",      "field": "freight_unit", "align": "right"},
            {"name": "net_profit",   "label": "Lucro (ISK)",   "field": "net_profit",   "align": "right", "sortable": True},
            {"name": "margin_pct",   "label": "Margem %",      "field": "margin_pct",   "align": "right", "sortable": True},
        ]

        rows = [
            {
                "type_id":       o["type_id"],
                "type_name":     o["type_name"],
                "source_sell":   f"{o['source_sell']:,.2f}",
                "local_sell":    f"{o['local_sell']:,.2f}",
                "freight_unit":  f"{o['freight_unit']:,.0f}",
                "net_profit":    f"{o['net_profit']:,.0f}",
                "margin_pct":    f"{o['margin_pct']:.1f}%",
            }
            for o in opportunities[:200]
        ]

        table = ui.table(columns=columns, rows=rows, row_key="type_id").props(
            "dark flat bordered dense virtual-scroll"
        ).classes("w-full text-grey-3")

        table.add_slot("body-cell-type_name", """
            <q-td :props="props">
                <span class="text-blue-4 cursor-pointer"
                      @click="$emit('row_click', props.row)">
                    {{ props.row.type_name }}
                </span>
            </q-td>
        """)
        table.add_slot("body-cell-net_profit", """
            <q-td :props="props">
                <span :class="parseFloat(props.row.net_profit.replace(/,/g,'')) > 0 ? 'text-green-5' : 'text-red-5'">
                    {{ props.row.net_profit }}
                </span>
            </q-td>
        """)

        table.on(
            "row_click",
            lambda e: ui.navigate.to(f"/ranking_item?type_id={e.args['type_id']}"),
        )
