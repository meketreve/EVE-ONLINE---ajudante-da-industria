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
    - station_id  : ID da ManufacturingStructure usada para este nó (None = global)
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
    station_id: int | None = None
    children: list["BOMNode"] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children


def _collect_required_type_ids(
    product_type_id: int,
    blueprints_by_product: dict[int, "Blueprint"],
    materials_by_blueprint: dict[int, list[dict]],
    visited: frozenset[int] = frozenset(),
) -> set[int]:
    """
    Coleta todos os type_ids necessários para expandir o BOM recursivamente.
    Usado para pré-carregar itens e blueprints em batch.
    """
    ids: set[int] = {product_type_id}
    if product_type_id in visited:
        return ids
    bp = blueprints_by_product.get(product_type_id)
    if bp is None:
        return ids
    new_visited = visited | {product_type_id}
    for mat in materials_by_blueprint.get(bp.blueprint_type_id, []):
        ids.add(mat["type_id"])
        ids |= _collect_required_type_ids(
            mat["type_id"], blueprints_by_product, materials_by_blueprint, new_visited
        )
    return ids


async def _prefetch_bom_data(
    root_type_id: int,
    db: AsyncSession,
) -> tuple[dict[int, "Blueprint"], dict[int, list[dict]], dict[int, str]]:
    """
    Pré-carrega todos blueprints, materiais e nomes de itens necessários para
    expandir o BOM do `root_type_id`, fazendo apenas 2+1 queries ao banco.

    Retorna:
      blueprints_by_product: {product_type_id: Blueprint}
      materials_by_blueprint: {blueprint_type_id: [{"type_id": int, "quantity": int}]}
      item_names: {type_id: name}
    """
    from app.models.item import Item

    blueprints_by_product: dict[int, Blueprint] = {}
    materials_by_blueprint: dict[int, list[dict]] = {}
    item_names: dict[int, str] = {}

    # Fila BFS para descobrir todos os type_ids necessários iterativamente
    to_check: set[int] = {root_type_id}
    checked:  set[int] = set()

    while to_check:
        batch = to_check - checked
        if not batch:
            break
        checked |= batch

        # Busca blueprints em batch
        bp_result = await db.execute(
            select(Blueprint).where(Blueprint.product_type_id.in_(list(batch)))
        )
        new_bps = bp_result.scalars().all()
        for bp in new_bps:
            blueprints_by_product[bp.product_type_id] = bp

        # Busca materiais para esses blueprints em batch
        bp_type_ids = [bp.blueprint_type_id for bp in new_bps]
        if bp_type_ids:
            # Tenta BlueprintMaterial normalizado primeiro
            mat_result = await db.execute(
                select(BlueprintMaterial).where(BlueprintMaterial.blueprint_id.in_(
                    [bp.id for bp in new_bps]
                ))
            )
            mat_rows = mat_result.scalars().all()

            # Agrupa por blueprint_id → blueprint_type_id
            bp_id_to_type_id = {bp.id: bp.blueprint_type_id for bp in new_bps}
            mats_by_bp_id: dict[int, list[BlueprintMaterial]] = {}
            for m in mat_rows:
                mats_by_bp_id.setdefault(m.blueprint_id, []).append(m)

            for bp in new_bps:
                raw_mats = mats_by_bp_id.get(bp.id)
                if raw_mats:
                    adj = [
                        {"type_id": m.material_type_id, "quantity": m.quantity}
                        for m in raw_mats
                    ]
                elif bp.materials:
                    adj = [
                        {"type_id": m["type_id"], "quantity": m["quantity"]}
                        for m in bp.materials
                    ]
                else:
                    adj = []
                materials_by_blueprint[bp.blueprint_type_id] = adj
                # Adiciona type_ids dos materiais para a próxima iteração
                for m in adj:
                    to_check.add(m["type_id"])

    # Carrega todos os nomes de uma vez
    all_type_ids = checked | to_check
    name_result = await db.execute(
        select(Item.type_id, Item.type_name).where(Item.type_id.in_(list(all_type_ids)))
    )
    item_names = {r.type_id: r.type_name for r in name_result.all()}

    return blueprints_by_product, materials_by_blueprint, item_names


def _build_bom_node(
    product_type_id: int,
    runs: int,
    me_level: int,
    me_overrides: dict[int, int],
    buy_as_is_ids: frozenset[int],
    structure_me_bonus: float,
    blueprints_by_product: dict[int, "Blueprint"],
    materials_by_blueprint: dict[int, list[dict]],
    item_names: dict[int, str],
    _visited: frozenset[int] = frozenset(),
    station_overrides: dict[int, int] | None = None,
    stations_map: dict[int, float] | None = None,
) -> BOMNode:
    """
    Constrói o BOM recursivamente usando dicionários pré-carregados (sem queries por nó).

    `station_overrides`: {type_id: structure_id} — estação por sub-componente.
    `stations_map`: {structure_id: me_bonus} — bônus da estrutura (pré-carregado).
    """
    if station_overrides is None:
        station_overrides = {}
    if stations_map is None:
        stations_map = {}

    effective_me = me_overrides.get(product_type_id, me_level)
    item_name = item_names.get(product_type_id, f"Type {product_type_id}")

    # Resolve bônus ME da estação para este nó (override ou global)
    station_id = station_overrides.get(product_type_id)
    effective_me_bonus = stations_map.get(station_id, structure_me_bonus) if station_id else structure_me_bonus

    bp = blueprints_by_product.get(product_type_id)
    if bp is None or product_type_id in _visited:
        return BOMNode(
            type_id=product_type_id,
            type_name=item_name,
            quantity=runs,
            is_manufactured=False,
        )

    # Aplica ME do nó atual (override ou global) + bônus da estação sobre as quantidades brutas
    raw_mats = materials_by_blueprint.get(bp.blueprint_type_id, [])
    base_mats = [
        {
            "type_id":  m["type_id"],
            "quantity": apply_me_level(m["quantity"], effective_me, effective_me_bonus),
        }
        for m in raw_mats
    ]

    node = BOMNode(
        type_id=product_type_id,
        type_name=item_name,
        quantity=runs * bp.product_quantity,
        is_manufactured=True,
        blueprint_type_id=bp.blueprint_type_id,
        blueprint_runs=runs,
        product_per_run=bp.product_quantity,
        me_level=effective_me,
        station_id=station_id,
    )

    new_visited = _visited | {product_type_id}

    for mat in base_mats:
        needed = mat["quantity"] * runs
        mat_bp = blueprints_by_product.get(mat["type_id"])
        mat_name = item_names.get(mat["type_id"], f"Type {mat['type_id']}")

        if mat["type_id"] in buy_as_is_ids:
            child = BOMNode(
                type_id=mat["type_id"],
                type_name=mat_name,
                quantity=needed,
                is_manufactured=True,
                buy_as_is=True,
            )
        elif mat_bp and mat["type_id"] not in new_visited:
            sub_runs = math.ceil(needed / mat_bp.product_quantity)
            child = _build_bom_node(
                mat["type_id"], sub_runs, me_level, me_overrides,
                buy_as_is_ids, structure_me_bonus,
                blueprints_by_product, materials_by_blueprint, item_names,
                new_visited,
                station_overrides=station_overrides,
                stations_map=stations_map,
            )
            child.quantity = needed
        else:
            child = BOMNode(
                type_id=mat["type_id"],
                type_name=mat_name,
                quantity=needed,
                is_manufactured=False,
            )

        node.children.append(child)

    return node


async def get_recursive_bom(
    product_type_id: int,
    db: AsyncSession,
    runs: int = 1,
    me_level: int = 0,
    me_overrides: dict[int, int] | None = None,
    buy_as_is_ids: frozenset[int] = frozenset(),
    structure_me_bonus: float = 0.0,
    station_overrides: dict[int, int] | None = None,
    _visited: frozenset[int] = frozenset(),
) -> BOMNode:
    """
    Constrói a árvore de materiais recursiva para `runs` runs do item.

    Para cada material do BOM: se tiver blueprint, expande recursivamente.
    Caso contrário, é um nó folha (deve ser comprado).

    `me_overrides`: {type_id: me_level} — sobrescreve o ME global por item.
    `buy_as_is_ids`: type_ids marcados pelo usuário para comprar prontos (não atomizar).
    `structure_me_bonus`: bônus ME total da estrutura em % (ex: 3.0 = -3% materiais).
    `station_overrides`: {type_id: structure_id} — estação por sub-componente.
    Detecção de ciclos via `_visited` (não ocorre no EVE, mas é segurança).

    Usa pré-carregamento em batch para evitar N+1 queries.
    """
    if me_overrides is None:
        me_overrides = {}
    if station_overrides is None:
        station_overrides = {}

    # Pré-carrega bônus das estações referenciadas em station_overrides
    stations_map: dict[int, float] = {}
    if station_overrides:
        from app.models.manufacturing_structure import ManufacturingStructure
        station_ids = list(set(station_overrides.values()))
        res = await db.execute(
            select(ManufacturingStructure).where(ManufacturingStructure.id.in_(station_ids))
        )
        for s in res.scalars().all():
            stations_map[s.id] = s.me_bonus

    # Pré-carrega todos os dados necessários em batch (quantidades brutas, sem ME)
    blueprints_by_product, materials_by_blueprint, item_names = await _prefetch_bom_data(
        product_type_id, db
    )

    # Constrói a árvore em memória sem mais queries ao banco
    return _build_bom_node(
        product_type_id, runs, me_level, me_overrides,
        buy_as_is_ids, structure_me_bonus,
        blueprints_by_product, materials_by_blueprint, item_names,
        _visited,
        station_overrides=station_overrides,
        stations_map=stations_map,
    )


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


def enrich_bom_costs(node: BOMNode, prices_map: dict[int, float]) -> None:
    """
    Preenche unit_price e total_cost em toda a árvore BOM (bottom-up).

    Folhas e nós buy_as_is: preço de mercado × quantidade.
    Nós fabricados: soma dos custos dos filhos (custo de fabricação).
    """
    if node.is_leaf or node.buy_as_is:
        node.unit_price = prices_map.get(node.type_id) or 0.0
        node.total_cost = node.unit_price * node.quantity
    else:
        for child in node.children:
            enrich_bom_costs(child, prices_map)
        node.total_cost = sum(c.total_cost for c in node.children)
        node.unit_price = node.total_cost / node.quantity if node.quantity > 0 else 0.0


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
