"""
Market data service com cache em banco de dados.

TTL do cache de preços: 5 minutos (equivalente ao cache ESI de market orders).
Passar `db` nas funções ativa o cache; sem `db` vai direto à ESI.
"""

import logging
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.services.esi_client import esi_client, ESIError
from app.models.cache import MarketPriceCache

logger = logging.getLogger(__name__)

THE_FORGE_REGION_ID = 10000002

# Região: expira em 5 min (dados ESI mudam rapidamente)
# Estrutura: expira em 4 h (dados populados pelo script atualizar_estruturas.bat
# que o usuário roda manualmente — 5 min tornaria o cache inútil)
REGION_PRICE_CACHE_TTL    = timedelta(minutes=5)
STRUCTURE_PRICE_CACHE_TTL = timedelta(hours=4)

# Sentinela para distinguir "não está no cache" de "está no cache com preço None"
_MISS = object()


def _cache_ttl(market_type: str) -> timedelta:
    return STRUCTURE_PRICE_CACHE_TTL if market_type == "structure" else REGION_PRICE_CACHE_TTL


# ---------------------------------------------------------------------------
# Helpers de cache
# ---------------------------------------------------------------------------

async def _read_price_cache(
    db: AsyncSession,
    type_id: int,
    market_type: str,
    market_id: int,
    order_type: str,
) -> float | None | object:
    """
    Retorna o preço do cache se ainda válido.
    Retorna _MISS se não houver entrada ou se expirou.
    TTL: 5 min para região, 4 h para estruturas privadas.
    """
    result = await db.execute(
        select(MarketPriceCache).where(
            MarketPriceCache.type_id == type_id,
            MarketPriceCache.market_type == market_type,
            MarketPriceCache.market_id == market_id,
            MarketPriceCache.order_type == order_type,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return _MISS
    if datetime.utcnow() - row.fetched_at > _cache_ttl(market_type):
        return _MISS
    return row.price


async def _write_price_cache(
    db: AsyncSession,
    type_id: int,
    market_type: str,
    market_id: int,
    order_type: str,
    price: float | None,
) -> None:
    """
    Upsert atômico usando INSERT OR REPLACE do SQLite.
    Evita race conditions quando múltiplos materiais são escritos em paralelo.
    """
    stmt = sqlite_insert(MarketPriceCache).values(
        type_id=type_id,
        market_type=market_type,
        market_id=market_id,
        order_type=order_type,
        price=price,
        fetched_at=datetime.utcnow(),
    ).on_conflict_do_update(
        index_elements=["type_id", "market_type", "market_id", "order_type"],
        set_={"price": price, "fetched_at": datetime.utcnow()},
    )
    await db.execute(stmt)


async def clear_price_cache(
    db: AsyncSession,
    market_type: str,
    market_id: int,
) -> int:
    """Remove todas as entradas de cache para um mercado específico. Retorna linhas deletadas."""
    result = await db.execute(
        delete(MarketPriceCache).where(
            MarketPriceCache.market_type == market_type,
            MarketPriceCache.market_id == market_id,
        )
    )
    await db.flush()
    return result.rowcount


# ---------------------------------------------------------------------------
# Mercado público (por região)
# ---------------------------------------------------------------------------

async def get_best_price(
    type_id: int,
    region_id: int = THE_FORGE_REGION_ID,
    order_type: Literal["sell", "buy"] = "sell",
    db: AsyncSession | None = None,
) -> float | None:
    """
    Melhor preço de um tipo numa região.
    Usa cache de DB quando `db` é fornecido (TTL: 5 min).
    """
    if db is not None:
        cached = await _read_price_cache(db, type_id, "region", region_id, order_type)
        if cached is not _MISS:
            return cached  # type: ignore[return-value]

    try:
        orders = await esi_client.get_market_orders(
            region_id=region_id,
            type_id=type_id,
            order_type=order_type,
        )
    except ESIError as exc:
        logger.warning("ESI market fetch falhou type_id=%s: %s", type_id, exc)
        return None

    price = (
        min(o["price"] for o in orders) if orders and order_type == "sell"
        else max(o["price"] for o in orders) if orders
        else None
    )

    if db is not None:
        await _write_price_cache(db, type_id, "region", region_id, order_type, price)

    return price


async def get_prices_for_materials(
    type_ids: list[int],
    region_id: int = THE_FORGE_REGION_ID,
    order_type: Literal["sell", "buy"] = "sell",
    db: AsyncSession | None = None,
) -> dict[int, float | None]:
    """
    Preços em bulk para uma lista de type_ids.
    Verifica cache primeiro; faz chamadas ESI apenas para os que faltam.
    """
    import asyncio

    price_map: dict[int, float | None] = {}
    missing: list[int] = []

    # Lê cache em paralelo
    if db is not None:
        cached_results = await asyncio.gather(
            *[_read_price_cache(db, tid, "region", region_id, order_type) for tid in type_ids]
        )
        for tid, cached in zip(type_ids, cached_results):
            if cached is _MISS:
                missing.append(tid)
            else:
                price_map[tid] = cached  # type: ignore[assignment]
    else:
        missing = list(type_ids)

    if not missing:
        return price_map

    # Busca apenas os que não estão em cache
    esi_results = await asyncio.gather(
        *[get_best_price(tid, region_id, order_type) for tid in missing],
        return_exceptions=True,
    )
    for tid, result in zip(missing, esi_results):
        if isinstance(result, Exception):
            logger.warning("Falha ao buscar preço type_id=%s: %s", tid, result)
            price_map[tid] = None
        else:
            price_map[tid] = result
            if db is not None:
                await _write_price_cache(db, tid, "region", region_id, order_type, result)

    return price_map


# ---------------------------------------------------------------------------
# Mercado de estrutura privada
# ---------------------------------------------------------------------------

async def get_best_price_structure(
    type_id: int,
    structure_id: int,
    token: str | None,
    order_type: Literal["sell", "buy"] = "sell",
    db: AsyncSession | None = None,
) -> float | None:
    prices = await get_prices_for_materials_structure(
        [type_id], structure_id, token, order_type, db=db
    )
    return prices.get(type_id)


async def get_prices_for_materials_structure(
    type_ids: list[int],
    structure_id: int,
    token: str | None,
    order_type: Literal["sell", "buy"] = "sell",
    db: AsyncSession | None = None,
) -> dict[int, float | None]:
    """
    Preços em bulk numa estrutura privada.
    Lê do cache DB primeiro (TTL 4 h). Só chama a ESI se houver cache miss
    E um token válido for fornecido. Sem token → retorna None para os que faltam
    (ao invés de tentar ESI e receber 403).
    """
    import asyncio

    price_map: dict[int, float | None] = {}
    missing: list[int] = []

    if db is not None:
        cached_results = await asyncio.gather(
            *[_read_price_cache(db, tid, "structure", structure_id, order_type) for tid in type_ids]
        )
        for tid, cached in zip(type_ids, cached_results):
            if cached is _MISS:
                missing.append(tid)
            else:
                price_map[tid] = cached  # type: ignore[assignment]
    else:
        missing = list(type_ids)

    if not missing:
        return price_map

    # Cache miss — só tenta ESI se tiver token
    if not token:
        logger.debug(
            "Cache miss para estrutura %s e sem token disponível — %d itens sem preço.",
            structure_id, len(missing),
        )
        for tid in missing:
            price_map[tid] = None
        return price_map

    # Uma chamada ESI para todos os orders da estrutura
    try:
        all_orders = await esi_client.get_structure_market(structure_id, token)
    except ESIError as exc:
        logger.warning("Falha ao buscar mercado estrutura %s: %s", structure_id, exc)
        for tid in missing:
            price_map[tid] = None
        return price_map

    missing_set = set(missing)
    by_type: dict[int, list[float]] = {}
    for order in all_orders:
        tid = order.get("type_id")
        if tid not in missing_set:
            continue
        is_buy = order.get("is_buy_order", False)
        if (order_type == "sell" and not is_buy) or (order_type == "buy" and is_buy):
            by_type.setdefault(tid, []).append(order["price"])

    for tid in missing:
        prices = by_type.get(tid, [])
        if not prices:
            price = None
        elif order_type == "sell":
            price = min(prices)
        else:
            price = max(prices)
        price_map[tid] = price
        if db is not None:
            await _write_price_cache(db, tid, "structure", structure_id, order_type, price)

    return price_map
