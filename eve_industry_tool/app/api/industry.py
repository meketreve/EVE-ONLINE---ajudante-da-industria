"""
Industry calculation routes.

POST /industry/calculate    - calculate production cost and profit
GET  /industry/ranking      - top profitable items
"""

import logging
from typing import Literal

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.database import get_db
from app.models.item import Item
from app.models.blueprint import Blueprint
from app.services.blueprint_service import get_blueprint_materials, get_blueprint_by_product
from app.services.market_service import (
    get_best_price,
    get_prices_for_materials,
    get_best_price_structure,
    get_prices_for_materials_structure,
    clear_price_cache,
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
        is_structure = False
        market_id = 10000002

    # Limpa cache se solicitado
    if force_refresh:
        await clear_price_cache(db, source_type, market_id)

    # Token do personagem (necessário para estruturas)
    char_token: str | None = None
    if is_structure:
        char_id = request.session.get("character_id")
        if char_id:
            character = await get_character(int(char_id), db)
            if character:
                char_token = await get_fresh_token(character, db)

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

    # Get materials with ME applied
    raw_materials = await get_blueprint_materials(
        blueprint.blueprint_type_id, db, me_level=me_level
    )

    if not raw_materials:
        context = {
            "request": request,
            "error": "Blueprint has no materials defined.",
            "item": item,
        }
        return templates.TemplateResponse("partials/calculation_result.html", context)

    runs = max(1, quantity)
    all_type_ids = [m["type_id"] for m in raw_materials]

    # Fetch market prices (região pública ou estrutura privada) — com cache DB
    if is_structure and char_token:
        price_map = await get_prices_for_materials_structure(
            all_type_ids, market_id, char_token, price_source, db=db
        )
        sell_price = await get_best_price_structure(type_id, market_id, char_token, "sell", db=db)
    else:
        price_map = await get_prices_for_materials(all_type_ids, market_id, price_source, db=db)
        sell_price = await get_best_price(type_id, market_id, "sell", db=db)

    # Build Material objects (scaled by runs)
    materials_obj: list[Material] = []
    for mat in raw_materials:
        unit_price = price_map.get(mat["type_id"]) or 0.0
        materials_obj.append(
            Material(
                type_id=mat["type_id"],
                quantity=mat["quantity"] * runs,
                unit_price=unit_price,
            )
        )

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
    enriched_materials = []
    for mat_obj, raw_mat in zip(materials_obj, raw_materials):
        mat_name_result = await db.execute(
            select(Item).where(Item.type_id == mat_obj.type_id)
        )
        mat_item = mat_name_result.scalar_one_or_none()
        enriched_materials.append(
            {
                "type_id": mat_obj.type_id,
                "name": mat_item.type_name if mat_item else f"Type {mat_obj.type_id}",
                "quantity": mat_obj.quantity,
                "unit_price": mat_obj.unit_price,
                "total_cost": mat_obj.total_cost,
            }
        )

    missing_prices = sum(1 for m in enriched_materials if not m["unit_price"])

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
    }

    return templates.TemplateResponse("partials/calculation_result.html", context)


@router.get("/ranking", response_class=HTMLResponse)
async def ranking(
    request: Request,
    region_id: int = 10000002,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    Return the top profitable manufacturable items.

    Usa apenas preços em cache (sem chamadas ESI durante a request).
    Só aparece itens cujo sell price E todos os materiais já estão em cache.
    """
    from app.models.cache import MarketPriceCache
    from app.models.blueprint import BlueprintMaterial

    # 1. Itens com sell price em cache
    cached_result = await db.execute(
        select(MarketPriceCache.type_id, MarketPriceCache.price)
        .where(
            MarketPriceCache.market_type == "region",
            MarketPriceCache.market_id == region_id,
            MarketPriceCache.order_type == "sell",
            MarketPriceCache.price.isnot(None),
        )
    )
    cached_sells: dict[int, float] = {row.type_id: row.price for row in cached_result.all()}

    if not cached_sells:
        return templates.TemplateResponse("ranking.html", {
            "request": request, "ranking": [], "region_id": region_id,
            "character_name": request.session.get("character_name"),
        })

    # 2. Blueprints para esses itens
    bp_result = await db.execute(
        select(Blueprint).where(Blueprint.product_type_id.in_(list(cached_sells.keys())))
    )
    all_blueprints = bp_result.scalars().all()

    if not all_blueprints:
        return templates.TemplateResponse("ranking.html", {
            "request": request, "ranking": [], "region_id": region_id,
            "character_name": request.session.get("character_name"),
        })

    # 3. Materiais de todos os blueprints (batch)
    bp_ids = [bp.id for bp in all_blueprints]
    mat_result = await db.execute(
        select(BlueprintMaterial).where(BlueprintMaterial.blueprint_id.in_(bp_ids))
    )
    mats_by_bp: dict[int, list] = {}
    for m in mat_result.scalars().all():
        mats_by_bp.setdefault(m.blueprint_id, []).append(m)

    # 4. Preços em cache de todos os materiais (batch)
    all_mat_ids: set[int] = set()
    for bp in all_blueprints:
        for m in mats_by_bp.get(bp.id, []):
            all_mat_ids.add(m.material_type_id)
        if not mats_by_bp.get(bp.id) and bp.materials:
            for m in bp.materials:
                all_mat_ids.add(m["type_id"])

    mat_price_result = await db.execute(
        select(MarketPriceCache.type_id, MarketPriceCache.price)
        .where(
            MarketPriceCache.type_id.in_(list(all_mat_ids)),
            MarketPriceCache.market_type == "region",
            MarketPriceCache.market_id == region_id,
            MarketPriceCache.order_type == "sell",
        )
    )
    mat_price_map: dict[int, float | None] = {row.type_id: row.price for row in mat_price_result.all()}

    # 5. Nomes dos itens (batch)
    items_result = await db.execute(
        select(Item).where(Item.type_id.in_([bp.product_type_id for bp in all_blueprints]))
    )
    items_by_id = {item.type_id: item for item in items_result.scalars().all()}

    # 6. Calcula lucro para cada blueprint
    ranking_rows: list[dict] = []
    for blueprint in all_blueprints:
        item = items_by_id.get(blueprint.product_type_id)
        sell_price = cached_sells.get(blueprint.product_type_id)
        if item is None or not sell_price:
            continue

        raw_mats = mats_by_bp.get(blueprint.id)
        if raw_mats:
            mat_list = [{"type_id": m.material_type_id, "quantity": m.quantity} for m in raw_mats]
        elif blueprint.materials:
            mat_list = blueprint.materials
        else:
            continue

        materials_obj: list[Material] = []
        skip = False
        for m in mat_list:
            price = mat_price_map.get(m["type_id"])
            if not price:
                skip = True
                break
            materials_obj.append(Material(type_id=m["type_id"], quantity=m["quantity"], unit_price=price))

        if skip or not materials_obj:
            continue

        qty = blueprint.product_quantity or 1
        cost_bd = calculate_production_cost(
            materials=materials_obj,
            estimated_item_value=sell_price * qty,
        )
        profit_bd = calculate_profit(
            sale_price=sell_price * qty,
            production_cost=cost_bd.total_cost,
        )
        ranking_rows.append({
            "item": item,
            "sell_price": sell_price * qty,
            "production_cost": cost_bd.total_cost,
            "net_profit": profit_bd.net_profit,
            "margin_pct": profit_bd.margin_pct,
        })

    ranking_rows.sort(key=lambda r: r["net_profit"], reverse=True)

    return templates.TemplateResponse("ranking.html", {
        "request": request,
        "ranking": ranking_rows[:limit],
        "region_id": region_id,
        "character_name": request.session.get("character_name"),
    })
