"""
Industry calculation routes.

POST /industry/calculate    - calculate production cost and profit
GET  /industry/ranking      - top profitable items
"""

import json
import logging
from datetime import datetime
from typing import Literal, Annotated

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.database import get_db
from app.models.item import Item
from app.models.blueprint import Blueprint
from app.services.blueprint_service import (
    get_blueprint_materials,
    get_blueprint_by_product,
    get_recursive_bom,
    aggregate_bom_leaves,
    bom_to_display_rows,
)
from app.services.market_service import (
    get_prices_cache_only,
    refresh_prices_for_types,
    get_prices_for_materials,
    get_prices_for_materials_structure,
)
from app.services.character_service import get_character, get_fresh_token
from app.services.industry_calculator import (
    Material,
    calculate_production_cost,
    calculate_profit,
    apply_me_level,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/industry", tags=["industry"])
templates = Jinja2Templates(directory="app/templates")


@router.post("/calculate", response_class=HTMLResponse)
async def calculate(
    request: Request,
    type_id: int = Form(...),
    quantity: int = Form(default=1),
    system_cost_index: float = Form(default=0.05),
    facility_tax: float = Form(default=0.0),
    scc_surcharge: float = Form(default=0.015),
    me_level: int = Form(default=0),
    broker_fee_pct: float = Form(default=0.03),
    sales_tax_pct: float = Form(default=0.08),
    price_source: Literal["sell", "buy"] = Form(default="sell"),
    market_source: str = Form(default="region:10000002"),
    force_refresh: bool = Form(default=False),
    recursive: bool = Form(default=False),
    buy_as_is: Annotated[list[int], Form()] = [],
    me_overrides_json: str = Form(default="{}"),
    manufacturing_structure_id: int = Form(default=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Calculate production cost and profit for a given item.

    Returns an HTML fragment (HTMX target) with the breakdown.
    `market_source` format: "region:10000002" ou "structure:1234567890".
    `force_refresh`: se True, limpa o cache do mercado antes de calcular.
    """
    # --- Parse market source ---
    try:
        source_type, source_id_str = market_source.split(":", 1)
        market_id = int(source_id_str)
        is_structure = source_type == "structure"
    except (ValueError, AttributeError):
        source_type = "region"
        is_structure = False
        market_id = 10000002

    # Token do personagem (necessário para estruturas)
    char_token: str | None = None
    if is_structure:
        char_id = request.session.get("character_id")
        if char_id:
            character = await get_character(int(char_id), db)
            if character:
                char_token = await get_fresh_token(character, db)

    # Busca bônus da estrutura de manufatura
    # Prioridade: estrutura específica selecionada > bônus global das configurações
    from app.api.settings import load_settings as _load_settings
    _settings = await _load_settings(db)
    structure_me_bonus = _settings.get("default_structure_me_bonus", 0.0)
    active_structure = None
    if manufacturing_structure_id:
        from app.models.manufacturing_structure import ManufacturingStructure
        struct_result = await db.execute(
            select(ManufacturingStructure).where(ManufacturingStructure.id == manufacturing_structure_id)
        )
        active_structure = struct_result.scalar_one_or_none()
        if active_structure:
            structure_me_bonus = active_structure.me_bonus

    # Fetch item
    item_result = await db.execute(select(Item).where(Item.type_id == type_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    # Fetch blueprint
    blueprint = await get_blueprint_by_product(type_id, db)
    if blueprint is None:
        context = {
            "request": request,
            "error": f"No blueprint found for {item.type_name}",
            "item": item,
        }
        return templates.TemplateResponse("partials/calculation_result.html", context)

    # Get materials with ME applied (blueprint ME + structure bonus)
    raw_materials = await get_blueprint_materials(
        blueprint.blueprint_type_id, db, me_level=me_level,
        structure_me_bonus=structure_me_bonus,
    )

    if not raw_materials:
        context = {
            "request": request,
            "error": "Blueprint has no materials defined.",
            "item": item,
        }
        return templates.TemplateResponse("partials/calculation_result.html", context)

    runs = max(1, quantity)

    # --- BOM: flat (padrão) ou recursivo ---
    bom_tree = None
    bom_display_rows: list[dict] = []

    try:
        me_overrides: dict[int, int] = {int(k): int(v) for k, v in json.loads(me_overrides_json).items()}
    except Exception:
        me_overrides = {}

    if recursive:
        bom_tree = await get_recursive_bom(
            type_id, db, runs=runs, me_level=me_level,
            me_overrides=me_overrides,
            buy_as_is_ids=frozenset(buy_as_is),
            structure_me_bonus=structure_me_bonus,
        )
        leaf_map = aggregate_bom_leaves(bom_tree)
        mat_ids = list(leaf_map.keys())
    else:
        mat_ids = [m["type_id"] for m in raw_materials]
        leaf_map = {m["type_id"]: m["quantity"] * runs for m in raw_materials}

    # --- Busca de preços via cache (sem TTL) ---
    # ESI só é chamada na primeira vez (cache vazio) ou com force_refresh explícito.
    mat_prices, mat_age = await get_prices_cache_only(
        mat_ids, source_type, market_id, price_source, db
    )
    sell_map, sell_age = await get_prices_cache_only(
        [type_id], source_type, market_id, "sell", db
    )

    no_cache = all(p is None for p in mat_prices.values()) and sell_map.get(type_id) is None

    if force_refresh or no_cache:
        ids_mat_refresh = mat_ids[:]
        if price_source == "sell":
            ids_mat_refresh.append(type_id)
        await refresh_prices_for_types(
            ids_mat_refresh, source_type, market_id, price_source, db, token=char_token
        )
        if price_source != "sell":
            await refresh_prices_for_types(
                [type_id], source_type, market_id, "sell", db, token=char_token
            )
        mat_prices, mat_age = await get_prices_cache_only(
            mat_ids, source_type, market_id, price_source, db
        )
        sell_map, sell_age = await get_prices_cache_only(
            [type_id], source_type, market_id, "sell", db
        )

    sell_price = sell_map.get(type_id)

    # Formata idade do cache
    prices_fetched_at = min(filter(None, [mat_age, sell_age]), default=None)
    if prices_fetched_at:
        age_secs = (datetime.utcnow() - prices_fetched_at).total_seconds()
        if age_secs < 60:
            prices_age_str = "agora mesmo"
        elif age_secs < 3600:
            prices_age_str = f"{int(age_secs / 60)} min atrás"
        elif age_secs < 86400:
            prices_age_str = f"{int(age_secs / 3600)}h atrás"
        else:
            prices_age_str = f"{int(age_secs / 86400)}d atrás"
    else:
        prices_age_str = None

    price_map = mat_prices

    # Prepara rows da árvore BOM recursiva com preços nas folhas
    if bom_tree:
        bom_display_rows = bom_to_display_rows(bom_tree)
        for row in bom_display_rows:
            if row["is_leaf"]:
                row["unit_price"] = price_map.get(row["type_id"]) or 0.0
                row["total_cost"] = row["unit_price"] * row["quantity"]

    # Build Material objects — usa leaf_map (flat ou agregado recursivo)
    materials_obj: list[Material] = []
    for tid, qty in leaf_map.items():
        unit_price = price_map.get(tid) or 0.0
        materials_obj.append(Material(type_id=tid, quantity=qty, unit_price=unit_price))

    estimated_item_value = (sell_price or 0.0) * blueprint.product_quantity * runs

    cost_breakdown = calculate_production_cost(
        materials=materials_obj,
        estimated_item_value=estimated_item_value,
        system_cost_index=system_cost_index,
        facility_tax=facility_tax,
        scc_surcharge=scc_surcharge,
    )

    total_sell_revenue = (sell_price or 0.0) * blueprint.product_quantity * runs

    profit_breakdown = calculate_profit(
        sale_price=total_sell_revenue,
        production_cost=cost_breakdown.total_cost,
        broker_fee_pct=broker_fee_pct,
        sales_tax_pct=sales_tax_pct,
    )

    # Enrich materials with names for display
    all_mat_type_ids = [m.type_id for m in materials_obj]
    name_rows = await db.execute(
        select(Item.type_id, Item.type_name).where(Item.type_id.in_(all_mat_type_ids))
    )
    name_map = {r.type_id: r.type_name for r in name_rows.all()}

    enriched_materials = [
        {
            "type_id": m.type_id,
            "name": name_map.get(m.type_id, f"Type {m.type_id}"),
            "quantity": m.quantity,
            "unit_price": m.unit_price,
            "total_cost": m.total_cost,
        }
        for m in materials_obj
    ]

    missing_prices = sum(1 for m in enriched_materials if not m["unit_price"])

    # --- Preços de comparação (Jita ↔ Amarr ↔ mercado ativo) ---
    # Escolhe o mercado de comparação oposto ao ativo. Apenas cache — sem ESI.
    _JITA  = ("region", 10000002)
    _AMARR = ("region", 10000043)
    _active = (source_type, market_id)
    if _active == _JITA:
        _cmp_type, _cmp_id, compare_market_label = "region", 10000043, "Amarr"
    else:
        _cmp_type, _cmp_id, compare_market_label = "region", 10000002, "Jita"

    _cmp_raw, _ = await get_prices_cache_only(mat_ids, _cmp_type, _cmp_id, "sell", db)
    compare_prices: dict[int, float | None] = {tid: p for tid, p in _cmp_raw.items()}

    # Adiciona dados de comparação a cada material
    for mat in enriched_materials:
        cmp = compare_prices.get(mat["type_id"])
        mat["compare_price"] = cmp
        mat["compare_total"] = (cmp or 0.0) * mat["quantity"]
        if mat["unit_price"] and cmp:
            mat["savings_unit"] = mat["unit_price"] - cmp   # >0 → comparação é mais barata
        else:
            mat["savings_unit"] = None

    # Adiciona comparação nas rows da árvore BOM
    if bom_tree:
        for row in bom_display_rows:
            if row["is_leaf"] or row.get("buy_as_is"):
                cmp = compare_prices.get(row["type_id"])
                row["compare_price"] = cmp
                row["compare_total"] = (cmp or 0.0) * row["quantity"]
            else:
                row["compare_price"] = None
                row["compare_total"] = 0.0

    has_compare_data = any(v for v in compare_prices.values())

    context = {
        "request": request,
        "item": item,
        "blueprint": blueprint,
        "runs": runs,
        "sell_price": sell_price,
        "cost_breakdown": cost_breakdown,
        "profit_breakdown": profit_breakdown,
        "materials": enriched_materials,
        "me_level": me_level,
        "price_source": price_source,
        "market_source": market_source,
        "is_structure": is_structure,
        "missing_prices": missing_prices,
        "prices_age_str": prices_age_str,
        "recursive": recursive,
        "bom_display_rows": bom_display_rows,
        "buy_as_is": buy_as_is,
        "me_overrides_json": json.dumps(me_overrides),
        "manufacturing_structure_id": manufacturing_structure_id,
        "active_structure": active_structure,
        "structure_me_bonus": structure_me_bonus,
        "compare_market_label": compare_market_label,
        "has_compare_data": has_compare_data,
    }

    return templates.TemplateResponse("partials/calculation_result.html", context)


_SOURCE_OPTIONS = [
    {"value": "region:10000002", "label": "Jita (The Forge)"},
    {"value": "region:10000043", "label": "Amarr (Domain)"},
]


@router.get("/ranking", response_class=HTMLResponse)
async def import_ranking(
    request: Request,
    source: str = "region:10000002",
    db: AsyncSession = Depends(get_db),
):
    """
    Ranking de importação: compara mercado fonte (Jita/Amarr) com mercado local configurado.
    Mostra itens ausentes no local ou com margem positiva após frete e taxas.
    Usa apenas dados em cache — sem chamadas ESI durante a request.
    """
    from app.models.cache import MarketPriceCache
    from app.models.market_snapshot import MarketSnapshot
    from app.api.settings import load_settings

    user_settings = await load_settings(db)
    local_market        = user_settings["default_market_source"]
    freight_per_m3      = user_settings["default_freight_cost_per_m3"]
    sales_tax           = user_settings["default_sales_tax_pct"]
    broker_fee          = user_settings["default_broker_fee_pct"]

    # Valida e normaliza o source escolhido
    if source not in [opt["value"] for opt in _SOURCE_OPTIONS]:
        source = "region:10000002"
    source_type, source_id_str = source.split(":", 1)
    source_market_id = int(source_id_str)

    # Parse mercado local
    try:
        local_type, local_id_str = local_market.split(":", 1)
        local_market_id = int(local_id_str)
    except (ValueError, AttributeError):
        local_type = "region"
        local_market_id = 10000002

    same_market = (source_type == local_type and source_market_id == local_market_id)

    _empty = {
        "request": request,
        "character_name": request.session.get("character_name"),
        "opportunities": [], "missing_items": [],
        "source": source, "local_market": local_market,
        "same_market": same_market,
        "user_settings": user_settings,
        "source_options": _SOURCE_OPTIONS,
    }

    # 1. Preços do mercado fonte (Jita ou Amarr) — sell orders em cache
    src_rows = await db.execute(
        select(
            MarketPriceCache.type_id,
            MarketPriceCache.price,
            MarketPriceCache.total_volume,
        ).where(
            MarketPriceCache.market_type == source_type,
            MarketPriceCache.market_id == source_market_id,
            MarketPriceCache.order_type == "sell",
            MarketPriceCache.price.isnot(None),
        )
    )
    source_prices: dict[int, dict] = {
        r.type_id: {"price": r.price, "volume": r.total_volume}
        for r in src_rows.all()
    }
    if not source_prices:
        return templates.TemplateResponse("ranking.html", _empty)

    # 2. Preços do mercado local — estrutura usa market_snapshots, região usa cache
    if local_type == "structure":
        local_rows = await db.execute(
            select(
                MarketSnapshot.type_id,
                MarketSnapshot.best_sell.label("price"),
                MarketSnapshot.sell_volume.label("volume"),
            ).where(MarketSnapshot.structure_id == local_market_id)
        )
    else:
        local_rows = await db.execute(
            select(
                MarketPriceCache.type_id,
                MarketPriceCache.price,
                MarketPriceCache.total_volume.label("volume"),
            ).where(
                MarketPriceCache.market_type == local_type,
                MarketPriceCache.market_id == local_market_id,
                MarketPriceCache.order_type == "sell",
            )
        )
    local_prices: dict[int, dict] = {
        r.type_id: {"price": r.price, "volume": r.volume}
        for r in local_rows.all()
    }

    # 3. Info dos itens (nome + volume m³) — apenas os que existem na fonte
    items_result = await db.execute(
        select(Item.type_id, Item.type_name, Item.volume)
        .where(Item.type_id.in_(list(source_prices.keys())))
    )
    items_map = {r.type_id: r for r in items_result.all()}

    # 4. Calcula oportunidades
    opportunities: list[dict] = []
    missing_items: list[dict] = []

    for type_id, src in source_prices.items():
        item_row = items_map.get(type_id)
        if item_row is None:
            continue

        item_vol_m3      = item_row.volume or 0.0
        freight_per_unit = freight_per_m3 * item_vol_m3
        local            = local_prices.get(type_id)

        if local and local["price"]:
            local_sell = local["price"]
            local_vol  = local["volume"] or 0
            # Receita líquida após taxas de venda local
            net_revenue = local_sell * (1.0 - sales_tax - broker_fee)
            net_profit  = net_revenue - src["price"] - freight_per_unit

            if net_profit > 0 or local_vol < 50:
                opportunities.append({
                    "type_id":        type_id,
                    "type_name":      item_row.type_name,
                    "volume_m3":      item_vol_m3,
                    "source_sell":    src["price"],
                    "source_volume":  src["volume"],
                    "local_sell":     local_sell,
                    "local_volume":   local_vol,
                    "freight_unit":   freight_per_unit,
                    "net_profit":     net_profit,
                    "status":         "low_supply" if local_vol < 50 else "profitable",
                })
        else:
            missing_items.append({
                "type_id":       type_id,
                "type_name":     item_row.type_name,
                "volume_m3":     item_vol_m3,
                "source_sell":   src["price"],
                "source_volume": src["volume"],
                "freight_unit":  freight_per_unit,
            })

    opportunities.sort(key=lambda x: x["net_profit"], reverse=True)
    missing_items.sort(key=lambda x: x["source_volume"] or 0, reverse=True)

    return templates.TemplateResponse("ranking.html", {
        "request":        request,
        "character_name": request.session.get("character_name"),
        "opportunities":  opportunities[:150],
        "missing_items":  missing_items[:150],
        "source":         source,
        "local_market":   local_market,
        "same_market":    same_market,
        "user_settings":  user_settings,
        "source_options": _SOURCE_OPTIONS,
    })


# Mapa de region_id para nome legível (para exibição)
_REGION_LABELS = {
    10000002: "Jita (The Forge)",
    10000043: "Amarr (Domain)",
    10000032: "Dodixie (Sinq Laison)",
    10000030: "Rens (Heimatar)",
    10000042: "Hek (Metropolis)",
}


@router.get("/ranking/{type_id}", response_class=HTMLResponse)
async def ranking_item_detail(
    type_id: int,
    request: Request,
    source: str = "region:10000002",
    window: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """
    Página de detalhe de um item do ranking.
    Mostra histórico de mercado ESI e projeção de volume para a janela configurada.
    """
    from app.models.cache import MarketPriceCache
    from app.models.market_snapshot import MarketSnapshot
    from app.api.settings import load_settings
    from app.services.esi_client import esi_client, ESIError
    from datetime import timedelta

    # Valida item
    item_result = await db.execute(select(Item).where(Item.type_id == type_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    user_settings = await load_settings(db)
    local_market = user_settings["default_market_source"]
    freight_per_m3 = user_settings["default_freight_cost_per_m3"]
    sales_tax = user_settings["default_sales_tax_pct"]
    broker_fee = user_settings["default_broker_fee_pct"]

    # Valida janela de tempo (dias)
    window = max(7, min(30, window))

    # Parse do mercado fonte
    if source not in [opt["value"] for opt in _SOURCE_OPTIONS]:
        source = "region:10000002"
    src_type, src_id_str = source.split(":", 1)
    src_region_id = int(src_id_str) if src_type == "region" else None

    # Preço atual na fonte
    src_cache = await db.execute(
        select(MarketPriceCache.price, MarketPriceCache.total_volume).where(
            MarketPriceCache.type_id == type_id,
            MarketPriceCache.market_type == src_type,
            MarketPriceCache.market_id == int(src_id_str),
            MarketPriceCache.order_type == "sell",
        )
    )
    src_row = src_cache.one_or_none()
    source_sell  = src_row.price        if src_row else None
    source_vol   = src_row.total_volume if src_row else None

    # Preço atual no mercado local
    try:
        local_type, local_id_str = local_market.split(":", 1)
        local_id = int(local_id_str)
    except (ValueError, AttributeError):
        local_type, local_id = "region", 10000002

    if local_type == "structure":
        local_row = await db.execute(
            select(MarketSnapshot.best_sell, MarketSnapshot.sell_volume).where(
                MarketSnapshot.structure_id == local_id,
                MarketSnapshot.type_id == type_id,
            )
        )
        lrow = local_row.one_or_none()
        local_sell = lrow.best_sell   if lrow else None
        local_vol  = lrow.sell_volume if lrow else None
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
        local_sell = lrow.price        if lrow else None
        local_vol  = lrow.total_volume if lrow else None

    # Calcula lucro atual
    net_profit = None
    if source_sell and local_sell:
        freight_unit = freight_per_m3 * (item.volume or 0.0)
        net_revenue  = local_sell * (1.0 - sales_tax - broker_fee)
        net_profit   = net_revenue - source_sell - freight_unit

    # Histórico ESI (apenas para regiões públicas)
    history: list[dict] = []
    history_error: str | None = None
    if src_region_id:
        try:
            raw = await esi_client.get_market_history(src_region_id, type_id)
            # Ordena por data e filtra pela janela
            raw.sort(key=lambda x: x["date"])
            cutoff = (datetime.utcnow() - timedelta(days=window)).strftime("%Y-%m-%d")
            history = [r for r in raw if r["date"] >= cutoff]
        except ESIError as exc:
            history_error = f"Erro ESI {exc.status_code}: {exc}"
        except Exception as exc:
            history_error = str(exc)

    # Estatísticas do histórico
    stats: dict = {}
    if history:
        volumes    = [h["volume"] for h in history]
        avg_prices = [h["average"] for h in history]
        stats = {
            "days":           len(history),
            "total_volume":   sum(volumes),
            "avg_daily_vol":  sum(volumes) / len(volumes),
            "proj_weekly":    sum(volumes) / len(volumes) * 7,
            "proj_monthly":   sum(volumes) / len(volumes) * 30,
            "avg_price":      sum(avg_prices) / len(avg_prices),
            "min_price":      min(h["lowest"]  for h in history),
            "max_price":      max(h["highest"] for h in history),
        }

    return templates.TemplateResponse("ranking_item.html", {
        "request":          request,
        "character_name":   request.session.get("character_name"),
        "item":             item,
        "source":           source,
        "source_label":     _REGION_LABELS.get(src_region_id, source) if src_region_id else source,
        "local_market":     local_market,
        "source_sell":      source_sell,
        "source_vol":       source_vol,
        "local_sell":       local_sell,
        "local_vol":        local_vol,
        "net_profit":       net_profit,
        "freight_per_m3":   freight_per_m3,
        "window":           window,
        "history":          history,
        "stats":            stats,
        "history_error":    history_error,
        "source_options":   _SOURCE_OPTIONS,
        "user_settings":    user_settings,
    })
