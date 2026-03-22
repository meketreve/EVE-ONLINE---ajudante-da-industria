"""
Production queue page — /queue
Manage the production queue and view aggregated BOM.
"""

import logging

from nicegui import ui, app as nicegui_app
from sqlalchemy import select, delete

from app.database.database import AsyncSessionLocal
from app.models.production_queue import ProductionQueue
from app.models.item import Item
from app.services.blueprint_service import get_recursive_bom, aggregate_bom_leaves
from app.services.market_service import get_prices_cache_only
from app.services.settings_service import load_settings
from app.ui.layout import page_layout

logger = logging.getLogger(__name__)


@ui.page("/queue")
async def queue_page():
    """Página da fila de produção."""
    character_id = nicegui_app.storage.general.get("character_id")
    if not character_id:
        with page_layout("Fila de Produção"):
            ui.label("Faça login para acessar a fila de produção.").classes("text-orange-5")
            ui.button("Login", on_click=lambda: ui.navigate.to("/")).props("color=primary")
        return

    queue_container = None
    bom_dialog = None

    with page_layout("Fila de Produção"):
        with ui.row().classes("items-center q-mb-md gap-3"):
            ui.label("Fila de Produção").classes("text-h5 text-white")
            ui.button(
                "Adicionar Item",
                icon="add",
                on_click=lambda: show_add_dialog(),
            ).props("unelevated color=primary").classes("q-ml-auto")
            ui.button(
                "Lista de Compras",
                icon="shopping_cart",
                on_click=lambda: show_bom_dialog(),
            ).props("flat color=grey-5")

        queue_container = ui.column().classes("w-full gap-2")
        await _render_queue(queue_container, character_id)

    async def show_add_dialog():
        """Diálogo para adicionar item à fila."""
        with ui.dialog() as dialog, ui.card().classes("q-pa-md bg-grey-9 min-w-80"):
            ui.label("Adicionar à Fila").classes("text-h6 text-white q-mb-md")

            item_input = ui.input(
                label="Item (type_id ou nome)",
                placeholder="ex: Raven ou 638",
            ).classes("w-full")
            item_input.props("outlined dense dark")

            runs_input = ui.number(
                label="Número de Runs",
                value=1,
                min=1,
                max=10000,
            ).classes("w-full")
            runs_input.props("outlined dense dark")

            async def add_item():
                raw = (item_input.value or "").strip()
                if not raw:
                    ui.notify("Informe o item.", type="warning")
                    return

                try:
                    async with AsyncSessionLocal() as db:
                        if raw.isdigit():
                            item_res = await db.execute(
                                select(Item).where(Item.type_id == int(raw))
                            )
                        else:
                            item_res = await db.execute(
                                select(Item).where(Item.type_name.ilike(f"%{raw}%"))
                            )
                        item = item_res.scalars().first()
                        if item is None:
                            ui.notify(f"Item '{raw}' não encontrado.", type="negative")
                            return

                        qty = max(1, int(runs_input.value or 1))
                        db.add(ProductionQueue(
                            character_id=character_id,
                            item_type_id=item.type_id,
                            quantity=qty,
                            status="pending",
                        ))
                        await db.commit()

                    ui.notify(f"'{item.type_name}' adicionado à fila.", type="positive")
                    dialog.close()
                    queue_container.clear()
                    await _render_queue(queue_container, character_id)
                except Exception as exc:
                    logger.error("Add to queue error: %s", exc)
                    ui.notify(f"Erro: {exc}", type="negative")

            with ui.row().classes("gap-2 q-mt-md justify-end"):
                ui.button("Cancelar", on_click=dialog.close).props("flat color=grey-5")
                ui.button("Adicionar", on_click=add_item).props("unelevated color=primary")

        dialog.open()

    async def show_bom_dialog():
        """Diálogo com lista de compras agregada."""
        with ui.dialog().props("maximized") as dialog, ui.card().classes(
            "q-pa-md bg-grey-9 w-full"
        ):
            ui.label("Lista de Compras Agregada").classes("text-h6 text-white q-mb-md")

            loading = ui.spinner("dots", size="xl", color="primary")

            try:
                async with AsyncSessionLocal() as db:
                    s = await load_settings(db)
                    me_level    = s.get("default_me_level", 0)
                    me_bonus    = s.get("default_structure_me_bonus", 0.0)
                    mkt_source  = s.get("default_market_source", "region:10000002")
                    price_src   = s.get("default_price_source", "sell")

                    try:
                        mkt_type, mkt_id_str = mkt_source.split(":", 1)
                        mkt_id = int(mkt_id_str)
                    except (ValueError, AttributeError):
                        mkt_type, mkt_id = "region", 10000002

                    result = await db.execute(
                        select(ProductionQueue).where(
                            ProductionQueue.character_id == character_id,
                            ProductionQueue.status != "completed",
                        ).order_by(ProductionQueue.created_at.desc())
                    )
                    entries = result.scalars().all()

                    if not entries:
                        loading.set_visibility(False)
                        ui.label("A fila está vazia.").classes("text-grey-5")
                        ui.button("Fechar", on_click=dialog.close).props("flat color=grey-5")
                        return

                    total_leaves: dict[int, int] = {}
                    for entry in entries:
                        # Usa configuração salva na entrada (com fallback para defaults)
                        entry_me       = entry.me_level if entry.me_level is not None else me_level
                        entry_bonus    = entry.structure_me_bonus if entry.structure_me_bonus is not None else me_bonus
                        entry_ov       = entry.get_me_overrides()       if hasattr(entry, "get_me_overrides")       else {}
                        entry_buy      = entry.get_buy_as_is()          if hasattr(entry, "get_buy_as_is")          else frozenset()
                        entry_stations = entry.get_station_overrides()  if hasattr(entry, "get_station_overrides")  else {}
                        bom = await get_recursive_bom(
                            entry.item_type_id, db,
                            runs=entry.quantity,
                            me_level=entry_me,
                            me_overrides=entry_ov,
                            buy_as_is_ids=entry_buy,
                            structure_me_bonus=entry_bonus,
                            station_overrides=entry_stations,
                        )
                        leaves = aggregate_bom_leaves(bom)
                        for tid, qty in leaves.items():
                            total_leaves[tid] = total_leaves.get(tid, 0) + qty

                    mat_ids = list(total_leaves.keys())
                    price_map, _ = await get_prices_cache_only(
                        mat_ids, mkt_type, mkt_id, price_src, db
                    )
                    name_res = await db.execute(
                        select(Item.type_id, Item.type_name).where(Item.type_id.in_(mat_ids))
                    )
                    name_map = {r.type_id: r.type_name for r in name_res.all()}

                    shopping: list[dict] = []
                    total_cost = 0.0
                    for tid, qty in sorted(total_leaves.items(), key=lambda x: name_map.get(x[0], "")):
                        price = price_map.get(tid)
                        cost  = (price or 0.0) * qty
                        total_cost += cost
                        shopping.append({
                            "name":         name_map.get(tid, f"Type {tid}"),
                            "quantity":     f"{qty:,}",
                            "quantity_raw": qty,
                            "unit_price":   f"{price:,.2f} ISK" if price else "—",
                            "total":        f"{cost:,.2f} ISK" if cost else "—",
                        })

            except Exception as exc:
                logger.error("BOM dialog error: %s", exc)
                loading.set_visibility(False)
                ui.notify(f"Erro ao calcular BOM: {exc}", type="negative")
                ui.button("Fechar", on_click=dialog.close).props("flat color=grey-5")
                return

            loading.set_visibility(False)

            with ui.row().classes("items-center justify-between q-mb-md"):
                ui.label(f"Total estimado: {total_cost:,.0f} ISK").classes(
                    "text-subtitle1 text-yellow-5"
                )

                clipboard_text = "\\n".join(
                    f"{m['name']} {m['quantity_raw']}" for m in shopping
                ).replace("'", "\\'")

                async def _copy_shopping():
                    await ui.run_javascript(
                        f"navigator.clipboard.writeText('{clipboard_text}')"
                    )
                    ui.notify("Lista copiada!", type="positive", position="top-right", timeout=2000)

                ui.button("Copiar lista", icon="content_copy", on_click=_copy_shopping).props(
                    "flat color=grey-5 dense"
                )

            columns = [
                {"name": "name",       "label": "Material",    "field": "name",       "align": "left"},
                {"name": "quantity",   "label": "Qtd.",        "field": "quantity",   "align": "right"},
                {"name": "unit_price", "label": "Unit. (ISK)", "field": "unit_price", "align": "right"},
                {"name": "total",      "label": "Total (ISK)", "field": "total",      "align": "right"},
            ]
            ui.table(columns=columns, rows=shopping, row_key="name").props(
                "dark flat bordered dense virtual-scroll"
            ).classes("w-full text-grey-3 max-h-96")

            ui.button("Fechar", on_click=dialog.close).props("flat color=grey-5 q-mt-md")

        dialog.open()


async def _render_queue(container: ui.column, character_id: int):
    """Renderiza os itens da fila."""
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(ProductionQueue).where(
                    ProductionQueue.character_id == character_id,
                ).order_by(ProductionQueue.created_at.desc())
            )
            entries = res.scalars().all()

            type_ids = [e.item_type_id for e in entries]
            if type_ids:
                name_res = await db.execute(
                    select(Item.type_id, Item.type_name).where(Item.type_id.in_(type_ids))
                )
                name_map = {r.type_id: r.type_name for r in name_res.all()}
            else:
                name_map = {}
    except Exception as exc:
        logger.error("Render queue error: %s", exc)
        with container:
            ui.notify(f"Erro ao carregar fila: {exc}", type="negative")
        return

    with container:
        if not entries:
            ui.label("A fila de produção está vazia.").classes("text-grey-6 q-pa-md")
            return

        for entry in entries:
            item_name = name_map.get(entry.item_type_id, f"Type {entry.item_type_id}")
            status_color = {
                "pending":    "grey-5",
                "running":    "blue-5",
                "completed":  "green-5",
                "failed":     "red-5",
            }.get(entry.status, "grey-5")

            # Monta linha de configuração do BOM
            me_lv     = entry.me_level if getattr(entry, "me_level", None) is not None else 0
            ov        = entry.get_me_overrides()      if hasattr(entry, "get_me_overrides")      else {}
            buy_ai    = entry.get_buy_as_is()         if hasattr(entry, "get_buy_as_is")         else frozenset()
            stations  = entry.get_station_overrides() if hasattr(entry, "get_station_overrides") else {}
            config_parts = [f"ME {me_lv}", f"{entry.quantity} run(s)"]
            if getattr(entry, "structure_me_bonus", 0):
                config_parts.append(f"struct {entry.structure_me_bonus:.1f}%")
            if ov:
                config_parts.append(f"{len(ov)} ME override(s)")
            if buy_ai:
                config_parts.append(f"{len(buy_ai)} comprar pronto")
            if stations:
                config_parts.append(f"{len(stations)} estação(ões) por sub-item")
            config_str = "  ·  ".join(config_parts)

            with ui.card().classes("q-pa-sm bg-grey-9 w-full"):
                with ui.row().classes("items-center w-full gap-2"):
                    ui.icon("precision_manufacturing").classes("text-blue-grey-4")
                    with ui.column().classes("flex-1 gap-0"):
                        with ui.row().classes("items-center gap-2 no-wrap"):
                            ui.label(item_name).classes("text-white text-body1")
                            if getattr(entry, "note", None):
                                ui.badge(entry.note, color="blue-grey-7").classes("text-caption")
                        ui.label(config_str).classes(f"text-caption text-{status_color}")

                    ui.button(
                        icon="calculate",
                        on_click=lambda eid=entry.id: ui.navigate.to(
                            f"/industry?queue_id={eid}"
                        ),
                    ).props("flat round dense color=blue-grey-5").tooltip("Abrir na calculadora")

                    async def remove(eid: int = entry.id):
                        try:
                            async with AsyncSessionLocal() as db2:
                                await db2.execute(
                                    delete(ProductionQueue).where(ProductionQueue.id == eid)
                                )
                                await db2.commit()
                            ui.notify("Item removido.", type="positive")
                            container.clear()
                            await _render_queue(container, character_id)
                        except Exception as exc:
                            ui.notify(f"Erro: {exc}", type="negative")

                    ui.button(
                        icon="delete",
                        on_click=remove,
                    ).props("flat round dense color=red-5").tooltip("Remover")
