"""
Settings service — load and save user settings from the database.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user_settings import UserSettings

SETTINGS_ID = 1

DEFAULTS = {
    "default_market_source":        "region:10000002",
    "default_me_level":             0,
    "default_system_cost_index":    0.05,
    "default_facility_tax":         0.0,
    "default_scc_surcharge":        0.015,
    "default_broker_fee_pct":       0.03,
    "default_sales_tax_pct":        0.08,
    "default_price_source":         "sell",
    "default_freight_cost_per_m3":  0.0,
    "default_structure_me_bonus":   0.0,
    "default_structure_te_bonus":   0.0,
}


async def load_settings(db: AsyncSession) -> dict:
    """Load settings from DB, falling back to defaults."""
    result = await db.execute(select(UserSettings).where(UserSettings.id == SETTINGS_ID))
    row = result.scalar_one_or_none()
    if row is None:
        return dict(DEFAULTS)
    return {
        "default_market_source":       row.default_market_source,
        "default_me_level":            row.default_me_level,
        "default_system_cost_index":   row.default_system_cost_index,
        "default_facility_tax":        row.default_facility_tax,
        "default_scc_surcharge":       row.default_scc_surcharge,
        "default_broker_fee_pct":      row.default_broker_fee_pct,
        "default_sales_tax_pct":       row.default_sales_tax_pct,
        "default_price_source":        row.default_price_source,
        "default_freight_cost_per_m3": getattr(row, "default_freight_cost_per_m3", 0.0),
        "default_structure_me_bonus":  getattr(row, "default_structure_me_bonus", 0.0),
        "default_structure_te_bonus":  getattr(row, "default_structure_te_bonus", 0.0),
    }


async def save_settings(db: AsyncSession, data: dict) -> None:
    """Persist settings to DB."""
    result = await db.execute(select(UserSettings).where(UserSettings.id == SETTINGS_ID))
    row = result.scalar_one_or_none()

    def _clamp(v, lo, hi):
        return max(lo, min(hi, v))

    if row is None:
        db.add(UserSettings(
            id=SETTINGS_ID,
            default_market_source=data.get("default_market_source", DEFAULTS["default_market_source"]),
            default_me_level=_clamp(int(data.get("default_me_level", 0)), 0, 10),
            default_system_cost_index=_clamp(float(data.get("default_system_cost_index", 0.05)), 0.0, 1.0),
            default_facility_tax=_clamp(float(data.get("default_facility_tax", 0.0)), 0.0, 1.0),
            default_scc_surcharge=_clamp(float(data.get("default_scc_surcharge", 0.015)), 0.0, 1.0),
            default_broker_fee_pct=_clamp(float(data.get("default_broker_fee_pct", 0.03)), 0.0, 1.0),
            default_sales_tax_pct=_clamp(float(data.get("default_sales_tax_pct", 0.08)), 0.0, 1.0),
            default_price_source=data.get("default_price_source", "sell") if data.get("default_price_source") in ("sell", "buy") else "sell",
            default_freight_cost_per_m3=max(0.0, float(data.get("default_freight_cost_per_m3", 0.0))),
            default_structure_me_bonus=_clamp(float(data.get("default_structure_me_bonus", 0.0)), 0.0, 100.0),
            default_structure_te_bonus=_clamp(float(data.get("default_structure_te_bonus", 0.0)), 0.0, 100.0),
            updated_at=datetime.utcnow(),
        ))
    else:
        row.default_market_source       = data.get("default_market_source", row.default_market_source)
        row.default_me_level            = _clamp(int(data.get("default_me_level", row.default_me_level)), 0, 10)
        row.default_system_cost_index   = _clamp(float(data.get("default_system_cost_index", row.default_system_cost_index)), 0.0, 1.0)
        row.default_facility_tax        = _clamp(float(data.get("default_facility_tax", row.default_facility_tax)), 0.0, 1.0)
        row.default_scc_surcharge       = _clamp(float(data.get("default_scc_surcharge", row.default_scc_surcharge)), 0.0, 1.0)
        row.default_broker_fee_pct      = _clamp(float(data.get("default_broker_fee_pct", row.default_broker_fee_pct)), 0.0, 1.0)
        row.default_sales_tax_pct       = _clamp(float(data.get("default_sales_tax_pct", row.default_sales_tax_pct)), 0.0, 1.0)
        row.default_price_source        = data.get("default_price_source", row.default_price_source) if data.get("default_price_source") in ("sell", "buy") else row.default_price_source
        row.default_freight_cost_per_m3 = max(0.0, float(data.get("default_freight_cost_per_m3", getattr(row, "default_freight_cost_per_m3", 0.0))))
        row.default_structure_me_bonus  = _clamp(float(data.get("default_structure_me_bonus", getattr(row, "default_structure_me_bonus", 0.0))), 0.0, 100.0)
        row.default_structure_te_bonus  = _clamp(float(data.get("default_structure_te_bonus", getattr(row, "default_structure_te_bonus", 0.0))), 0.0, 100.0)
        row.updated_at                  = datetime.utcnow()

    await db.flush()
