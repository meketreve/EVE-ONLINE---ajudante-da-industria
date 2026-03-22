"""
Items page — /items
Browse and search EVE items with pagination.
"""

import logging

from nicegui import ui, app as nicegui_app
from sqlalchemy import select, func, or_

from app.database.database import AsyncSessionLocal
from app.models.item import Item
from app.ui.layout import page_layout

logger = logging.getLogger(__name__)

PAGE_SIZE = 50

# Category id → name mapping (common EVE categories)
CATEGORY_NAMES = {
    2:  "Celestial",
    4:  "Material",
    5:  "Acessório",
    6:  "Nave",
    7:  "Módulo",
    8:  "Drone",
    16: "Habilidade",
    17: "Comodidade",
    18: "Drone",
    22: "Asteroide",
    25: "Derivado de Asteroide",
    34: "Subcomponente",
    35: "Reação Avançada",
    42: "Apparel",
    43: "Infraestrutura Implante",
    65: "Estrutura",
    66: "Módulo de Estrutura",
    87: "Fighter",
}


@ui.page("/items")
async def items_page():
    """Página de listagem e busca de itens."""
    state = {
        "search":   "",
        "category": 0,
        "page":     1,
        "total":    0,
    }

    with page_layout("Itens"):
        ui.label("Itens").classes("text-h5 text-white q-mb-md")

        # Filtros
        with ui.row().classes("gap-3 q-mb-md items-end w-full flex-wrap"):
            search_input = ui.input(
                label="Buscar por nome",
                placeholder="ex: Veldspar, Raven, Tritanium...",
            ).classes("flex-1 min-w-64")
            search_input.props("outlined dense dark clearable")

            category_options = {0: "Todas as Categorias"}
            category_options.update(CATEGORY_NAMES)
            category_select = ui.select(
                options={k: v for k, v in category_options.items()},
                value=0,
                label="Categoria",
            ).classes("min-w-48")
            category_select.props("outlined dense dark")

            ui.button("Buscar", icon="search", on_click=lambda: run_search(1)).props(
                "unelevated color=primary"
            )

        # Tabela
        table_container = ui.column().classes("w-full")

        async def run_search(page: int = 1):
            state["search"] = search_input.value or ""
            state["category"] = int(category_select.value or 0)
            state["page"] = page
            table_container.clear()
            with table_container:
                await _render_table(state)

        # Debounce na busca por texto
        async def on_search_change():
            await run_search(1)

        search_input.on("keyup.enter", lambda: run_search(1))
        category_select.on("update:model-value", lambda: run_search(1))

        # Carrega dados iniciais
        with table_container:
            await _render_table(state)


async def _render_table(state: dict):
    """Renderiza a tabela de itens com paginação."""
    search   = state.get("search", "").strip()
    category = state.get("category", 0)
    page     = state.get("page", 1)
    offset   = (page - 1) * PAGE_SIZE

    try:
        async with AsyncSessionLocal() as db:
            q = select(Item)
            count_q = select(func.count()).select_from(Item)

            if search:
                q = q.where(Item.type_name.ilike(f"%{search}%"))
                count_q = count_q.where(Item.type_name.ilike(f"%{search}%"))
            if category:
                q = q.where(Item.category_id == category)
                count_q = count_q.where(Item.category_id == category)

            total_res = await db.execute(count_q)
            total = total_res.scalar_one() or 0
            state["total"] = total

            q = q.order_by(Item.type_name).offset(offset).limit(PAGE_SIZE)
            res = await db.execute(q)
            items = res.scalars().all()
    except Exception as exc:
        logger.error("Items page error: %s", exc)
        ui.notify(f"Erro ao carregar itens: {exc}", type="negative")
        return

    if not items:
        ui.label("Nenhum item encontrado.").classes("text-grey-5 q-pa-md")
        return

    # Tabela
    columns = [
        {"name": "type_name", "label": "Nome",       "field": "type_name",  "sortable": True, "align": "left"},
        {"name": "category",  "label": "Categoria",  "field": "category",   "sortable": False, "align": "left"},
        {"name": "volume",    "label": "Volume (m³)", "field": "volume",     "sortable": True, "align": "right"},
        {"name": "action",    "label": "",            "field": "action",     "sortable": False, "align": "center"},
    ]

    rows = []
    for item in items:
        cat_name = CATEGORY_NAMES.get(item.category_id or 0, f"Cat {item.category_id or '?'}")
        vol_str = f"{item.volume:.2f}" if item.volume else "—"
        rows.append({
            "type_id":   item.type_id,
            "type_name": item.type_name,
            "category":  cat_name,
            "volume":    vol_str,
        })

    table = ui.table(columns=columns, rows=rows, row_key="type_id").classes(
        "w-full text-grey-3"
    ).props("dark flat bordered dense virtual-scroll")

    table.add_slot("body-cell-type_name", """
        <q-td :props="props">
            <span class="text-blue-4 cursor-pointer" @click="$emit('click_row', props.row)">
                {{ props.row.type_name }}
            </span>
        </q-td>
    """)

    table.on("click_row", lambda e: ui.navigate.to(f"/industry?type_id={e.args['type_id']}"))

    # Paginação
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    current_page = state["page"]

    with ui.row().classes("items-center gap-2 q-mt-md justify-center"):
        ui.label(f"Página {current_page} de {total_pages} ({total} itens)").classes("text-caption text-grey-5")
        if current_page > 1:
            ui.button(icon="chevron_left", on_click=lambda: run_search_page(current_page - 1)).props(
                "flat round dense color=grey-5"
            )
        if current_page < total_pages:
            ui.button(icon="chevron_right", on_click=lambda: run_search_page(current_page + 1)).props(
                "flat round dense color=grey-5"
            )


async def run_search_page(page: int):
    """Helper para paginação — recarrega com a nova página."""
    # Implementação simplificada: navega para a mesma página com parâmetro
    ui.navigate.to(f"/items?page={page}")
