"""
Settings routes.

GET  /settings       - render settings page
POST /settings       - save settings and redirect
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.database import get_db
from app.models.user_settings import UserSettings
from app.services.character_service import get_market_options, get_trading_fees_for_character, PUBLIC_MARKET_GROUPS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory="app/templates")

SETTINGS_ID = 1

DEFAULTS = {
    "default_market_source":    "region:10000002",
    "default_me_level":         0,
    "default_system_cost_index": 0.05,
    "default_facility_tax":     0.0,
    "default_scc_surcharge":    0.015,
    "default_broker_fee_pct":   0.03,
    "default_sales_tax_pct":    0.08,
    "default_price_source":     "sell",
}


async def load_settings(db: AsyncSession) -> dict:
    """Load settings from DB, falling back to defaults."""
    result = await db.execute(select(UserSettings).where(UserSettings.id == SETTINGS_ID))
    row = result.scalar_one_or_none()
    if row is None:
        return dict(DEFAULTS)
    return {
        "default_market_source":    row.default_market_source,
        "default_me_level":         row.default_me_level,
        "default_system_cost_index": row.default_system_cost_index,
        "default_facility_tax":     row.default_facility_tax,
        "default_scc_surcharge":    row.default_scc_surcharge,
        "default_broker_fee_pct":   row.default_broker_fee_pct,
        "default_sales_tax_pct":    row.default_sales_tax_pct,
        "default_price_source":     row.default_price_source,
    }


def _market_label(market_source: str, market_options: dict) -> str:
    """Return human-readable label for a market_source value."""
    for group in market_options.get("groups", []):
        for opt in group.get("markets", []):
            if opt["value"] == market_source:
                return opt["label"]
    for opt in market_options.get("private", []):
        if opt["value"] == market_source:
            return opt["label"]
    return market_source


@router.get("/", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    saved: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    character_id = request.session.get("character_id")
    character_name = request.session.get("character_name")

    settings = await load_settings(db)

    market_options = await get_market_options(int(character_id), db) if character_id else {"groups": PUBLIC_MARKET_GROUPS, "private": []}

    trading_fees = None
    if character_id:
        trading_fees = await get_trading_fees_for_character(int(character_id), db)

    return templates.TemplateResponse("settings.html", {
        "request":       request,
        "character_name": character_name,
        "settings":      settings,
        "market_options": market_options,
        "trading_fees":  trading_fees,
        "saved":         saved == "1",
    })


@router.post("/", response_class=RedirectResponse)
async def save_settings(
    request: Request,
    default_market_source:    str   = Form(default="region:10000002"),
    default_me_level:         int   = Form(default=0),
    default_system_cost_index: float = Form(default=0.05),
    default_facility_tax:     float = Form(default=0.0),
    default_scc_surcharge:    float = Form(default=0.015),
    default_broker_fee_pct:   float = Form(default=0.03),
    default_sales_tax_pct:    float = Form(default=0.08),
    default_price_source:     str   = Form(default="sell"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserSettings).where(UserSettings.id == SETTINGS_ID))
    row = result.scalar_one_or_none()

    if row is None:
        db.add(UserSettings(
            id=SETTINGS_ID,
            default_market_source=default_market_source,
            default_me_level=max(0, min(10, default_me_level)),
            default_system_cost_index=max(0.0, min(1.0, default_system_cost_index)),
            default_facility_tax=max(0.0, min(1.0, default_facility_tax)),
            default_scc_surcharge=max(0.0, min(1.0, default_scc_surcharge)),
            default_broker_fee_pct=max(0.0, min(1.0, default_broker_fee_pct)),
            default_sales_tax_pct=max(0.0, min(1.0, default_sales_tax_pct)),
            default_price_source=default_price_source if default_price_source in ("sell", "buy") else "sell",
            updated_at=datetime.utcnow(),
        ))
    else:
        row.default_market_source    = default_market_source
        row.default_me_level         = max(0, min(10, default_me_level))
        row.default_system_cost_index = max(0.0, min(1.0, default_system_cost_index))
        row.default_facility_tax     = max(0.0, min(1.0, default_facility_tax))
        row.default_scc_surcharge    = max(0.0, min(1.0, default_scc_surcharge))
        row.default_broker_fee_pct   = max(0.0, min(1.0, default_broker_fee_pct))
        row.default_sales_tax_pct    = max(0.0, min(1.0, default_sales_tax_pct))
        row.default_price_source     = default_price_source if default_price_source in ("sell", "buy") else "sell"
        row.updated_at               = datetime.utcnow()

    await db.flush()
    return RedirectResponse(url="/settings/?saved=1", status_code=303)
