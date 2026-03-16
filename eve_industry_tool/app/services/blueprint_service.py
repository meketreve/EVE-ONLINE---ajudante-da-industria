"""
Blueprint and invention service.

Provides helpers for:
- Fetching blueprint materials with ME reduction applied
- Recursive BOM (Bill of Materials) expansion
- Calculating invention costs
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.blueprint import Blueprint, BlueprintMaterial
from app.services.industry_calculator import apply_me_level

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recursive BOM
# ---------------------------------------------------------------------------

@dataclass
class BOMNode:
    """
    Nó da árvore de materiais recursiva.

    - quantity    : unidades necessárias pelo nível pai (ou produzidas na raiz)
    - is_manufactured : True se existe blueprint para fabricar este item
    - children    : materiais necessários para fabricá-lo (vazio se leaf/buy)
    - blueprint_runs  : quantas runs de blueprint são necessárias
    - product_per_run : quantidade produzida por run do blueprint
    """
    type_id: int
    type_name: str
    quantity: int
    is_manufactured: bool
    blueprint_type_id: int | None = None
    blueprint_runs: int = 0
    product_per_run: int = 1
    me_level: int = 0
    unit_price: float = 0.0
    buy_as_is: bool = False
    children: list["BOMNode"] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children


async def get_recursive_bom(
    product_type_id: int,
    db: AsyncSession,
    runs: int = 1,
    me_level: int = 0,
    me_overrides: dict[int, int] | None = None,
    buy_as_is_ids: frozenset[int] = frozenset(),
    structure_me_bonus: float = 0.0,
    _visited: frozenset[int] = frozenset(),
) -> BOMNode:
    """
    Constrói a árvore de materiais recursiva para `runs` runs do item.

    Para cada material do BOM: se tiver blueprint, expande recursivamente.
    Caso contrário, é um nó folha (deve ser comprado).

    `me_overrides`: {type_id: me_level} — sobrescreve o ME global por item.
    `buy_as_is_ids`: type_ids marcados pelo usuário para comprar prontos (não atomizar).
    `structure_me_bonus`: bônus ME total da estrutura em % (ex: 3.0 = -3% materiais).
    Detecção de ciclos via `_visited` (não ocorre no EVE, mas é segurança).
    """
    from app.models.item import Item

    if me_overrides is None:
        me_overrides = {}

    # ME efetivo para este item
    effective_me = me_overrides.get(product_type_id, me_level)

    # Nome do item
    item_row = await db.execute(select(Item).where(Item.type_id == product_type_id))
    item = item_row.scalar_one_or_none()
    item_name = item.type_name if item else f"Type {product_type_id}"

    blueprint = await get_blueprint_by_product(product_type_id, db)

    if blueprint is None or product_type_id in _visited:
        return BOMNode(
            type_id=product_type_id,
            type_name=item_name,
            quantity=runs,
            is_manufactured=False,
        )

    base_mats = await get_blueprint_materials(blueprint.blueprint_type_id, db, effective_me, structure_me_bonus)

    node = BOMNode(
        type_id=product_type_id,
        type_name=item_name,
        quantity=runs * blueprint.product_quantity,
        is_manufactured=True,
        blueprint_type_id=blueprint.blueprint_type_id,
        blueprint_runs=runs,
        product_per_run=blueprint.product_quantity,
        me_level=effective_me,
    )

    new_visited = _visited | {product_type_id}

    for mat in base_mats:
        needed = mat["quantity"] * runs
        mat_bp = await get_blueprint_by_product(mat["type_id"], db)

        # Buy-as-is: treat as leaf even if blueprint exists
        if mat["type_id"] in buy_as_is_ids:
            mat_row = await db.execute(select(Item).where(Item.type_id == mat["type_id"]))
            mat_item = mat_row.scalar_one_or_none()
            mat_name = mat_item.type_name if mat_item else f"Type {mat['type_id']}"
            child = BOMNode(
                type_id=mat["type_id"],
                type_name=mat_name,
                quantity=needed,
                is_manufactured=True,  # has blueprint but user chose to buy
                buy_as_is=True,
            )
        elif mat_bp and mat["type_id"] not in new_visited:
            sub_runs = math.ceil(needed / mat_bp.product_quantity)
            child = await get_recursive_bom(
                mat["type_id"], db,
                runs=sub_runs,
                me_level=me_level,
                me_overrides=me_overrides,
                buy_as_is_ids=buy_as_is_ids,
                structure_me_bonus=structure_me_bonus,
                _visited=new_visited,
            )
            child.quantity = needed  # unidades necessárias pelo pai
        else:
            mat_row = await db.execute(select(Item).where(Item.type_id == mat["type_id"]))
            mat_item = mat_row.scalar_one_or_none()
            mat_name = mat_item.type_name if mat_item else f"Type {mat['type_id']}"
            child = BOMNode(
                type_id=mat["type_id"],
                type_name=mat_name,
                quantity=needed,
                is_manufactured=False,
            )

        node.children.append(child)

    return node


def aggregate_bom_leaves(node: BOMNode) -> dict[int, int]:
    """
    Retorna {type_id: quantidade_total} de todos os materiais base (folhas).
    Estes são os itens que precisam ser comprados.
    """
    if node.is_leaf:
        return {node.type_id: node.quantity}
    result: dict[int, int] = {}
    for child in node.children:
        for tid, qty in aggregate_bom_leaves(child).items():
            result[tid] = result.get(tid, 0) + qty
    return result


def bom_to_display_rows(node: BOMNode, depth: int = 0) -> list[dict]:
    """
    Serializa a árvore BOM em lista plana de dicts para renderização no template.
    Cada row inclui `depth` para calcular indentação visual.
    """
    rows = [{
        "depth": depth,
        "type_id": node.type_id,
        "type_name": node.type_name,
        "quantity": node.quantity,
        "is_manufactured": node.is_manufactured,
        "is_leaf": node.is_leaf,
        "buy_as_is": node.buy_as_is,
        "blueprint_runs": node.blueprint_runs,
        "product_per_run": node.product_per_run,
        "unit_price": 0.0,
        "total_cost": 0.0,
    }]
    for child in node.children:
        rows.extend(bom_to_display_rows(child, depth + 1))
    return rows


async def get_blueprint_materials(
    blueprint_type_id: int,
    db: AsyncSession,
    me_level: int = 0,
    structure_me_bonus: float = 0.0,
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
        adj_qty = apply_me_level(mat["quantity"], me_level, structure_me_bonus)
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
