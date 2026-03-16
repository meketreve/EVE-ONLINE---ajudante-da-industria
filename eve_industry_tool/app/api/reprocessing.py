"""
Reprocessing calculator routes.

GET  /reprocessing/           - calculator page
POST /reprocessing/calculate  - HTMX: returns result fragment
"""

import logging
import math
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.database import get_db
from app.models.item import Item
from app.models.reprocessing import ReprocessingMaterial
from app.models.cache import MarketPriceCache
from app.models.structure import Structure
from app.services.market_service import get_prices_cache_only, refresh_prices_for_types
from app.services.character_service import get_character, get_fresh_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reprocessing", tags=["reprocessing"])
templates = Jinja2Templates(directory="app/templates")

_REGION_OPTIONS = [
    {"value": "region:10000002", "label": "Jita (The Forge)"},
    {"value": "region:10000043", "label": "Amarr (Domain)"},
    {"value": "region:10000030", "label": "Rens (Heimatar)"},
    {"value": "region:10000042", "label": "Hek (Metropolis)"},
    {"value": "region:10000032", "label": "Dodixie (Sinq Laison)"},
]


async def _load_market_options(db: AsyncSession) -> list[dict]:
    """Retorna regiões fixas + estruturas com dados em cache."""
    options = list(_REGION_OPTIONS)

    # Estruturas com dados recentes no cache
    struct_rows = await db.execute(
        select(MarketPriceCache.market_id)
        .where(MarketPriceCache.market_type == "structure")
        .distinct()
    )
    struct_ids = [r[0] for r in struct_rows.all()]

    if struct_ids:
        name_rows = await db.execute(
            select(Structure.structure_id, Structure.name)
            .where(Structure.structure_id.in_(struct_ids))
        )
        for row in name_rows.all():
            label = row.name or f"Estrutura {row.structure_id}"
            options.append({"value": f"structure:{row.structure_id}", "label": label})

    return options


@router.get("/", response_class=HTMLResponse)
async def reprocessing_page(request: Request, db: AsyncSession = Depends(get_db)):
    from app.api.settings import load_settings
    user_settings = await load_settings(db)
    market_options = await _load_market_options(db)

    # Verifica se dados de reprocessamento foram importados
    count_row = await db.execute(select(func.count()).select_from(ReprocessingMaterial))
    has_reproc_data = (count_row.scalar() or 0) > 0

    return templates.TemplateResponse("reprocessing.html", {
        "request": request,
        "character_name": request.session.get("character_name"),
        "market_options": market_options,
        "default_market": user_settings["default_market_source"],
        "has_reproc_data": has_reproc_data,
    })


@router.post("/calculate", response_class=HTMLResponse)
async def calculate_reprocessing(
    request: Request,
    items_text: str = Form(...),
    yield_pct: float = Form(default=50.0),
    market_source: str = Form(default="region:10000002"),
    force_refresh: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
):
    """
    Compara o valor de venda de cada item com o valor dos materiais de reprocessamento.
    Retorna fragmento HTML com duas listas: reprocessar / vender.
    """
    # Parse market source
    try:
        source_type, source_id_str = market_source.split(":", 1)
        market_id = int(source_id_str)
    except (ValueError, AttributeError):
        source_type = "region"
        market_id = 10000002

    # Token para estruturas privadas
    char_token: str | None = None
    if source_type == "structure":
        char_id = request.session.get("character_id")
        if char_id:
            char = await get_character(int(char_id), db)
            if char:
                char_token = await get_fresh_token(char, db)

    effective_yield = max(0.0, min(1.0, yield_pct / 100.0))

    # Parse lista de itens — aceita vários formatos do EVE Online:
    #   "Veldspar"                   → nome simples
    #   "Veldspar\t12,345"           → copiar do inventário (tab + qtd)
    #   "Veldspar x 12,345"          → formato alternativo do cliente
    #   "12,345 x Veldspar"          → formato invertido
    #   "  Veldspar  "               → espaços extras
    import re
    _qty_suffix = re.compile(r'\s+[xX]\s+[\d,\.]+$')   # "Item x 1,000"
    _qty_prefix = re.compile(r'^[\d,\.]+\s+[xX]\s+')   # "1,000 x Item"

    parsed: list[str] = []
    for raw in items_text.splitlines():
        # Pega apenas a primeira coluna se houver tab (inventário EVE)
        name = raw.split('\t')[0].strip()
        # Remove padrões de quantidade
        name = _qty_suffix.sub('', name).strip()
        name = _qty_prefix.sub('', name).strip()
        if name:
            parsed.append(name)

    item_names = list(dict.fromkeys(parsed))  # remove duplicatas mantendo ordem

    if not item_names:
        return templates.TemplateResponse("partials/reprocessing_result.html", {
            "request": request,
            "error": "Nenhum item informado.",
        })

    # Lookup itens no banco (case-insensitive)
    item_rows = await db.execute(
        select(Item).where(
            func.lower(Item.type_name).in_([n.lower() for n in item_names])
        )
    )
    found_items: dict[str, Item] = {
        row.type_name.lower(): row for row in item_rows.scalars().all()
    }

    not_found = [n for n in item_names if n.lower() not in found_items]
    found_list = list(found_items.values())

    if not found_list:
        return templates.TemplateResponse("partials/reprocessing_result.html", {
            "request": request,
            "error": f"Nenhum dos {len(item_names)} itens foi encontrado no banco de dados.",
            "not_found": not_found,
        })

    # Busca materiais de reprocessamento para os itens encontrados
    found_type_ids = [item.type_id for item in found_list]
    reproc_rows = await db.execute(
        select(ReprocessingMaterial).where(
            ReprocessingMaterial.type_id.in_(found_type_ids)
        )
    )
    reproc_by_type: dict[int, list[ReprocessingMaterial]] = {}
    all_mat_type_ids: set[int] = set()
    for row in reproc_rows.scalars().all():
        reproc_by_type.setdefault(row.type_id, []).append(row)
        all_mat_type_ids.add(row.material_type_id)

    no_reproc_ids = {item.type_id for item in found_list if item.type_id not in reproc_by_type}

    # Todos os type_ids que precisam de preço: itens + materiais
    all_price_ids = list(set(found_type_ids) | all_mat_type_ids)

    # Cache-only primeiro; força ESI se vazio ou force_refresh
    price_map, price_age = await get_prices_cache_only(
        all_price_ids, source_type, market_id, "sell", db
    )
    no_cache = all(p is None for p in price_map.values())

    if force_refresh or no_cache:
        await refresh_prices_for_types(
            all_price_ids, source_type, market_id, "sell", db, token=char_token
        )
        price_map, price_age = await get_prices_cache_only(
            all_price_ids, source_type, market_id, "sell", db
        )

    # Calcula e classifica
    to_reprocess: list[dict] = []
    to_sell: list[dict] = []

    for item in found_list:
        # Itens sem dados de reprocessamento vão direto para "vender"
        if item.type_id not in reproc_by_type:
            item_price = price_map.get(item.type_id)
            to_sell.append({
                "type_id": item.type_id,
                "type_name": item.type_name,
                "portion_size": 1,
                "item_price": item_price,
                "sell_value": item_price or 0.0,
                "reproc_value": 0.0,
                "gain": 0.0,
                "gain_pct": 0.0,
                "materials": [],
                "no_reproc": True,
            })
            continue

        portion = max(1, item.portion_size or 1)
        item_price = price_map.get(item.type_id)
        sell_value_per_batch = (item_price or 0.0) * portion

        # Valor dos materiais por batch
        mat_value_per_batch = 0.0
        mat_details: list[dict] = []
        for mat in reproc_by_type[item.type_id]:
            mat_price = price_map.get(mat.material_type_id) or 0.0
            output = math.floor(mat.quantity * effective_yield)
            value = output * mat_price
            mat_value_per_batch += value
            mat_details.append({
                "material_type_id": mat.material_type_id,
                "base_qty": mat.quantity,
                "output_qty": output,
                "unit_price": mat_price,
                "total_value": value,
            })

        gain = mat_value_per_batch - sell_value_per_batch
        entry = {
            "type_id": item.type_id,
            "type_name": item.type_name,
            "portion_size": portion,
            "item_price": item_price,
            "sell_value": sell_value_per_batch,
            "reproc_value": mat_value_per_batch,
            "gain": gain,
            "gain_pct": (gain / sell_value_per_batch * 100) if sell_value_per_batch else 0.0,
            "materials": mat_details,
            "no_reproc": False,
        }

        if mat_value_per_batch > sell_value_per_batch:
            to_reprocess.append(entry)
        else:
            to_sell.append(entry)

    to_reprocess.sort(key=lambda x: x["gain"], reverse=True)
    to_sell.sort(key=lambda x: x["gain"])  # pior ganho no topo = mais urgente vender

    # Gera strings de busca no formato da Assets Window do EVE Online
    # Sintaxe: type:Nome1 type:Nome2 type:Nome3
    reproc_search = " ".join(f'type:"{e["type_name"]}"' if " " in e["type_name"] else f'type:{e["type_name"]}' for e in to_reprocess)
    sell_search   = " ".join(f'type:"{e["type_name"]}"' if " " in e["type_name"] else f'type:{e["type_name"]}' for e in to_sell)

    # Enriquece materiais com nomes
    mat_name_rows = await db.execute(
        select(Item.type_id, Item.type_name).where(Item.type_id.in_(list(all_mat_type_ids)))
    )
    mat_names = {r.type_id: r.type_name for r in mat_name_rows.all()}
    for entry in to_reprocess + to_sell:
        for mat in entry["materials"]:
            mat["name"] = mat_names.get(mat["material_type_id"], f"Type {mat['material_type_id']}")

    # Formata idade do cache
    prices_age_str = None
    if price_age:
        secs = (datetime.utcnow() - price_age).total_seconds()
        if secs < 60:
            prices_age_str = "agora mesmo"
        elif secs < 3600:
            prices_age_str = f"{int(secs / 60)} min atrás"
        elif secs < 86400:
            prices_age_str = f"{int(secs / 3600)}h atrás"
        else:
            prices_age_str = f"{int(secs / 86400)}d atrás"

    return templates.TemplateResponse("partials/reprocessing_result.html", {
        "request": request,
        "to_reprocess": to_reprocess,
        "to_sell": to_sell,
        "not_found": not_found,
        "reproc_search": reproc_search,
        "sell_search": sell_search,
        "yield_pct": yield_pct,
        "market_source": market_source,
        "prices_age_str": prices_age_str,
    })
