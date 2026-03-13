"""
Blueprint and invention service.

Provides helpers for:
- Fetching blueprint materials with ME reduction applied
- Calculating invention costs
"""

import logging
import math
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.blueprint import Blueprint, BlueprintMaterial
from app.services.industry_calculator import apply_me_level

logger = logging.getLogger(__name__)


async def get_blueprint_materials(
    blueprint_type_id: int,
    db: AsyncSession,
    me_level: int = 0,
) -> list[dict[str, Any]]:
    """
    Return the list of materials for a blueprint, adjusted for ME level.

    Each entry: {"type_id": int, "quantity": int}

    ME level ranges from 0 to 10 (industry standard).
    """
    result = await db.execute(
        select(Blueprint).where(Blueprint.blueprint_type_id == blueprint_type_id)
    )
    blueprint = result.scalar_one_or_none()

    if blueprint is None:
        logger.warning("Blueprint not found: blueprint_type_id=%s", blueprint_type_id)
        return []

    # Materials may be stored in the JSON column or in the BlueprintMaterial rows
    # Prefer the normalised BlueprintMaterial table when it has rows
    mat_result = await db.execute(
        select(BlueprintMaterial).where(BlueprintMaterial.blueprint_id == blueprint.id)
    )
    material_rows = mat_result.scalars().all()

    if material_rows:
        materials_raw = [
            {"type_id": m.material_type_id, "quantity": m.quantity} for m in material_rows
        ]
    elif blueprint.materials:
        materials_raw = blueprint.materials  # list of {"type_id": int, "quantity": int}
    else:
        return []

    adjusted = []
    for mat in materials_raw:
        adj_qty = apply_me_level(mat["quantity"], me_level)
        adjusted.append({"type_id": mat["type_id"], "quantity": adj_qty})

    return adjusted


def calculate_invention_cost(
    datacore_prices: dict[int, float],
    datacore_type_ids: list[int],
    decryptor_price: float = 0.0,
    success_chance: float = 0.34,
) -> dict[str, float]:
    """
    Calculate the amortised cost of one successful invention attempt.

    Parameters
    ----------
    datacore_prices:
        Mapping of type_id -> unit price for each required datacore.
    datacore_type_ids:
        List of datacore type_ids required (may contain duplicates for qty > 1).
    decryptor_price:
        Price of the decryptor used (0 if no decryptor).
    success_chance:
        Probability of success (0.0 – 1.0). Typical base T2 is 0.34.

    Returns
    -------
    {
        "datacore_cost":       float,   # total cost of datacores per attempt
        "decryptor_cost":      float,   # cost of decryptor per attempt
        "cost_per_attempt":    float,   # total per attempt
        "cost_per_success":    float,   # amortised per successful run
        "success_chance":      float,
    }
    """
    if success_chance <= 0:
        raise ValueError("success_chance must be greater than 0")

    datacore_cost = sum(datacore_prices.get(tid, 0.0) for tid in datacore_type_ids)
    cost_per_attempt = datacore_cost + decryptor_price
    cost_per_success = cost_per_attempt / success_chance

    return {
        "datacore_cost": datacore_cost,
        "decryptor_cost": decryptor_price,
        "cost_per_attempt": cost_per_attempt,
        "cost_per_success": cost_per_success,
        "success_chance": success_chance,
    }


async def get_blueprint_by_product(
    product_type_id: int,
    db: AsyncSession,
) -> Blueprint | None:
    """Look up the blueprint that produces a given product type."""
    result = await db.execute(
        select(Blueprint).where(Blueprint.product_type_id == product_type_id)
    )
    return result.scalar_one_or_none()
