"""
Item browsing routes.

GET /items                  - list all manufacturable items (search + category filter)
GET /items/{type_id}        - item detail with blueprint and cost calculation form
"""

import logging

import asyncio

from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database.database import get_db
from app.models.item import Item
from app.models.blueprint import Blueprint, BlueprintMaterial
from app.services.blueprint_service import get_blueprint_materials, get_blueprint_by_product
from app.services.character_service import get_trading_fees_for_character, get_market_options
from app.api.settings import load_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["items"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/items", response_class=HTMLResponse)
async def list_items(
    request: Request,
    search: str = Query(default="", alias="search"),
    category_id: str | None = Query(default=None, alias="category_id"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all manufacturable items.

    Supports:
    - Full-text search on item name via ?search=
    - Category filter via ?category_id=

    When called via HTMX (HX-Request header), returns only the table fragment.
    """
    cat_id: int | None = int(category_id) if category_id and category_id.strip() else None

    query = select(Item).where(Item.is_manufacturable == True)

    if search:
        query = query.where(Item.type_name.ilike(f"%{search}%"))

    if cat_id is not None:
        query = query.where(Item.category_id == cat_id)

    query = query.order_by(Item.type_name)

    result = await db.execute(query)
    items = result.scalars().all()

    # Fetch unique categories for the dropdown
    cat_result = await db.execute(
        select(Item.category_id).where(Item.is_manufacturable == True).distinct()
    )
    categories = sorted([r for r in cat_result.scalars().all() if r is not None])

    context = {
        "request": request,
        "items": items,
        "categories": categories,
        "search": search,
        "selected_category": cat_id,
        "character_name": request.session.get("character_name"),
    }

    # HTMX partial response
    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        return templates.TemplateResponse("partials/items_table.html", context)

    return templates.TemplateResponse("items.html", context)


@router.get("/items/{type_id}", response_class=HTMLResponse)
async def item_detail(
    type_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Item detail page with blueprint materials and cost calculation form."""
    result = await db.execute(select(Item).where(Item.type_id == type_id))
    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    # Find the blueprint that produces this item
    blueprint = await get_blueprint_by_product(type_id, db)
    materials = []

    if blueprint:
        # Load material details (names)
        raw_materials = await get_blueprint_materials(
            blueprint.blueprint_type_id, db, me_level=0
        )

        for mat in raw_materials:
            mat_result = await db.execute(
                select(Item).where(Item.type_id == mat["type_id"])
            )
            mat_item = mat_result.scalar_one_or_none()
            materials.append(
                {
                    "type_id": mat["type_id"],
                    "quantity": mat["quantity"],
                    "name": mat_item.type_name if mat_item else f"Type {mat['type_id']}",
                }
            )

    # Busca taxas e opções de mercado pelo personagem logado (se houver)
    character_id = request.session.get("character_id")
    trading_fees = None
    market_options = {"public": [], "private": []}
    if character_id:
        char_id_int = int(character_id)
        trading_fees, market_options = await asyncio.gather(
            get_trading_fees_for_character(char_id_int, db),
            get_market_options(char_id_int, db),
        )
    else:
        from app.services.character_service import PUBLIC_MARKET_GROUPS
        market_options = {"groups": PUBLIC_MARKET_GROUPS, "private": []}

    user_settings = await load_settings(db)

    # When trading_fees are available from skills, override the tax defaults in settings
    if trading_fees and trading_fees.get("from_skills"):
        user_settings["default_broker_fee_pct"] = trading_fees["broker_fee_pct"]
        user_settings["default_sales_tax_pct"] = trading_fees["sales_tax_pct"]

    context = {
        "request": request,
        "item": item,
        "blueprint": blueprint,
        "materials": materials,
        "trading_fees": trading_fees,
        "market_options": market_options,
        "user_settings": user_settings,
        "character_name": request.session.get("character_name"),
    }

    return templates.TemplateResponse("item_detail.html", context)
