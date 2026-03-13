"""
Crawler de mercado para estruturas privadas Upwell.

Fluxo por estrutura:
  1. Tenta TODOS os personagens autenticados até um ter acesso (200)
  2. Busca todas as páginas de /markets/structures/{id}/
  3. Faz upsert de ordens brutas em market_orders_raw
  4. Marca como is_stale as ordens que não apareceram neste crawl
  5. Agrega snapshots (best_sell, best_buy, volumes, spread) em market_snapshots
  6. Atualiza status da estrutura e registra CrawlJob

A ESI NUNCA é chamada no request do usuário — apenas por este serviço,
disparado pelos workers de job_runner.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import AsyncSessionLocal
from app.models.job import CrawlJob
from app.models.market_order import MarketOrder
from app.models.market_snapshot import MarketSnapshot
from app.models.structure import Structure
from app.services.esi_client import esi_client, ESIError

logger = logging.getLogger(__name__)

STALE_DELETE_AFTER = timedelta(hours=48)


# ── Ponto de entrada público ──────────────────────────────────────────────────

async def run_crawl_job(structure_id: int, preferred_character_id: int) -> None:
    """
    Executado pelo worker do crawl_runner.
    Cria CrawlJob no banco, executa o crawl, atualiza o job.
    """
    async with AsyncSessionLocal() as db:
        job = CrawlJob(
            structure_id=structure_id,
            character_id=preferred_character_id,
            status="running",
            started_at=datetime.utcnow(),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        try:
            result = await _do_crawl(structure_id, preferred_character_id, db)

            job.status         = result["status"]
            job.orders_fetched = result["orders_fetched"]
            job.pages_fetched  = result["pages_fetched"]
            job.character_id   = result.get("used_character_id", preferred_character_id)
            job.finished_at    = datetime.utcnow()
            await db.commit()

        except Exception as exc:
            logger.error("[crawl] structure=%d falhou: %s", structure_id, exc, exc_info=True)
            job.status      = "failed"
            job.error       = str(exc)
            job.finished_at = datetime.utcnow()
            await db.commit()


# ── Lógica principal ──────────────────────────────────────────────────────────

async def _do_crawl(
    structure_id: int,
    preferred_character_id: int,
    db: AsyncSession,
) -> dict:
    """
    Tenta todos os personagens disponíveis.
    Retorna dict com status, orders_fetched, pages_fetched, used_character_id.
    """
    tokens = await _get_all_tokens(preferred_character_id, db)

    orders:             list[dict] | None = None
    used_character_id:  int | None        = None
    pages_fetched = 0

    for char_id, char_name, token in tokens:
        try:
            orders, pages_fetched = await _fetch_all_orders(structure_id, token)
            used_character_id = char_id
            logger.info(
                "[crawl] structure=%d → %d ordens em %d página(s)  (char: %s)",
                structure_id, len(orders), pages_fetched, char_name,
            )
            break  # sucesso

        except ESIError as exc:
            if exc.status_code == 403:
                logger.debug("[crawl] structure=%d char=%s 403 — próximo.", structure_id, char_name)
                continue
            if exc.status_code == 404:
                await _set_structure_status(db, structure_id, "inactive")
                return {"status": "failed", "orders_fetched": 0, "pages_fetched": 0}
            raise

    if orders is None:
        # Nenhum personagem teve acesso
        await _set_structure_status(db, structure_id, "market_denied")
        logger.warning("[crawl] structure=%d → market_denied (403 em todos os tokens)", structure_id)
        return {"status": "denied", "orders_fetched": 0, "pages_fetched": 0}

    fetched_at = datetime.utcnow()

    # Persiste ordens brutas
    order_ids = await _upsert_orders(db, structure_id, orders, fetched_at)

    # Marca stale as ordens que não vieram neste crawl
    await _mark_stale(db, structure_id, order_ids)

    # Agrega snapshots
    await _update_snapshots(db, structure_id, fetched_at)

    # Atualiza status da estrutura
    struct = await db.get(Structure, structure_id)
    if struct:
        struct.status          = "market_accessible"
        struct.last_crawled_at = fetched_at
    await db.commit()

    return {
        "status":            "done",
        "orders_fetched":    len(orders),
        "pages_fetched":     pages_fetched,
        "used_character_id": used_character_id,
    }


_TRANSIENT_ESI_ERRORS = {502, 503, 504}
_MAX_RETRIES = 3


async def _fetch_all_orders(structure_id: int, token: str) -> tuple[list[dict], int]:
    """
    Busca todas as páginas de /markets/structures/{id}/.
    Retorna (lista de ordens, total de páginas buscadas).
    Levanta ESIError em qualquer erro, incluindo 403.
    Retenta até 3x em erros transitórios (502/503/504) com backoff: 2s, 4s, 8s.
    """
    import asyncio

    all_orders: list[dict] = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        last_exc: ESIError | None = None

        for attempt in range(_MAX_RETRIES):
            if attempt > 0:
                delay = 2 ** attempt  # 2s, 4s, 8s
                logger.info(
                    "[crawl] structure=%d page=%d → ESI %d, tentativa %d/%d em %ds...",
                    structure_id, page, last_exc.status_code, attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)

            try:
                response_data, x_pages = await esi_client.get_structure_market_page(
                    structure_id, token, page
                )
                all_orders.extend(response_data)
                total_pages = x_pages
                page += 1
                last_exc = None
                break  # página obtida com sucesso

            except ESIError as exc:
                if exc.status_code in _TRANSIENT_ESI_ERRORS:
                    last_exc = exc
                    continue  # retenta
                raise  # 403, 404, outros — não retenta

        if last_exc is not None:
            raise last_exc  # esgotou retentativas sem sucesso

    return all_orders, total_pages


async def _upsert_orders(
    db: AsyncSession,
    structure_id: int,
    orders: list[dict],
    fetched_at: datetime,
) -> set[int]:
    """
    Upsert em lotes de 500. Retorna conjunto de order_ids recebidos.
    """
    order_ids: set[int] = set()

    for order in orders:
        order_ids.add(order["order_id"])

    # Batch upsert via INSERT OR REPLACE — commit por lote para liberar o lock de escrita
    BATCH = 500
    for i in range(0, len(orders), BATCH):
        batch = orders[i : i + BATCH]
        for o in batch:
            await db.execute(
                text("""
                    INSERT INTO market_orders_raw
                        (order_id, structure_id, type_id, is_buy_order, price,
                         volume_remain, volume_total, min_volume, duration, issued,
                         fetched_at, is_stale)
                    VALUES
                        (:order_id, :structure_id, :type_id, :is_buy_order, :price,
                         :volume_remain, :volume_total, :min_volume, :duration, :issued,
                         :fetched_at, 0)
                    ON CONFLICT (order_id) DO UPDATE SET
                        price         = excluded.price,
                        volume_remain = excluded.volume_remain,
                        fetched_at    = excluded.fetched_at,
                        is_stale      = 0
                """),
                {
                    "order_id":     o["order_id"],
                    "structure_id": structure_id,
                    "type_id":      o["type_id"],
                    "is_buy_order": 1 if o["is_buy_order"] else 0,
                    "price":        o["price"],
                    "volume_remain": o["volume_remain"],
                    "volume_total":  o["volume_total"],
                    "min_volume":    o.get("min_volume", 1),
                    "duration":      o["duration"],
                    "issued":        o["issued"],
                    "fetched_at":    fetched_at,
                },
            )
        # Commit a cada lote: libera o lock de escrita entre lotes (~1s por lote)
        # evita segurar o lock por 30s inteiros com 21k ordens
        await db.commit()

    return order_ids


async def _mark_stale(
    db: AsyncSession, structure_id: int, seen_order_ids: set[int]
) -> None:
    """
    Marca como is_stale as ordens desta estrutura que não apareceram no crawl.
    Ordens stale são deletadas após STALE_DELETE_AFTER pelo job de limpeza.
    """
    if not seen_order_ids:
        return

    # SQLite não suporta NOT IN com conjuntos grandes — usa subquery
    ids_str = ",".join(str(oid) for oid in seen_order_ids)
    await db.execute(
        text(f"""
            UPDATE market_orders_raw
            SET is_stale = 1
            WHERE structure_id = :sid
              AND is_stale = 0
              AND order_id NOT IN ({ids_str})
        """),
        {"sid": structure_id},
    )
    await db.flush()


async def _update_snapshots(
    db: AsyncSession, structure_id: int, updated_at: datetime
) -> None:
    """
    Agrega ordens ativas (is_stale=0) em market_snapshots.
    Faz upsert por (structure_id, type_id).
    """
    # Busca todas as ordens ativas desta estrutura
    result = await db.execute(
        select(
            MarketOrder.type_id,
            MarketOrder.is_buy_order,
            MarketOrder.price,
            MarketOrder.volume_remain,
        ).where(
            MarketOrder.structure_id == structure_id,
            MarketOrder.is_stale == False,  # noqa: E712
        )
    )
    rows = result.all()

    # Agrega em Python por type_id
    sell_prices:   dict[int, list[float]] = defaultdict(list)
    buy_prices:    dict[int, list[float]] = defaultdict(list)
    sell_volumes:  dict[int, int]         = defaultdict(int)
    buy_volumes:   dict[int, int]         = defaultdict(int)

    for type_id, is_buy, price, vol in rows:
        if is_buy:
            buy_prices[type_id].append(price)
            buy_volumes[type_id] += vol
        else:
            sell_prices[type_id].append(price)
            sell_volumes[type_id] += vol

    all_type_ids = set(sell_prices) | set(buy_prices)

    for type_id in all_type_ids:
        best_sell   = min(sell_prices[type_id])  if sell_prices[type_id]  else None
        best_buy    = max(buy_prices[type_id])   if buy_prices[type_id]   else None
        sell_vol    = sell_volumes.get(type_id, 0)
        buy_vol     = buy_volumes.get(type_id, 0)
        order_count = len(sell_prices[type_id]) + len(buy_prices[type_id])

        spread_pct = None
        if best_sell and best_buy and best_sell > 0:
            spread_pct = round((best_sell - best_buy) / best_sell * 100, 4)

        await db.execute(
            text("""
                INSERT INTO market_snapshots
                    (structure_id, type_id, best_sell, best_buy,
                     sell_volume, buy_volume, spread_pct, order_count, updated_at)
                VALUES
                    (:sid, :tid, :best_sell, :best_buy,
                     :sell_vol, :buy_vol, :spread_pct, :order_count, :updated_at)
                ON CONFLICT (structure_id, type_id) DO UPDATE SET
                    best_sell   = excluded.best_sell,
                    best_buy    = excluded.best_buy,
                    sell_volume = excluded.sell_volume,
                    buy_volume  = excluded.buy_volume,
                    spread_pct  = excluded.spread_pct,
                    order_count = excluded.order_count,
                    updated_at  = excluded.updated_at
            """),
            {
                "sid":         structure_id,
                "tid":         type_id,
                "best_sell":   best_sell,
                "best_buy":    best_buy,
                "sell_vol":    sell_vol,
                "buy_vol":     buy_vol,
                "spread_pct":  spread_pct,
                "order_count": order_count,
                "updated_at":  updated_at,
            },
        )

    await db.flush()


# ── Limpeza de ordens stale antigas ──────────────────────────────────────────

async def cleanup_stale_orders() -> int:
    """Remove ordens stale mais antigas que STALE_DELETE_AFTER. Retorna contagem."""
    cutoff = datetime.utcnow() - STALE_DELETE_AFTER
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                DELETE FROM market_orders_raw
                WHERE is_stale = 1
                  AND fetched_at < :cutoff
            """),
            {"cutoff": cutoff},
        )
        await db.commit()
        deleted = result.rowcount
        if deleted:
            logger.info("[cleanup] %d ordens stale removidas.", deleted)
        return deleted


# ── Scheduler: recrawl de todas as estruturas acessíveis ─────────────────────

async def schedule_recrawl_all() -> int:
    """
    Enfileira recrawl para todas as estruturas com status market_accessible.
    Ordena pelas mais antigas (last_crawled_at ASC) para priorizar frescor.
    Retorna número de estruturas enfileiradas.
    """
    from app.services.job_runner import crawl_runner

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Structure.structure_id, Structure.last_crawled_at)
            .where(Structure.status == "market_accessible")
            .order_by(Structure.last_crawled_at.asc().nullsfirst())
        )
        structures = result.all()

    enqueued = 0
    for structure_id, _ in structures:
        queued = await crawl_runner.enqueue(
            f"crawl:{structure_id}",
            run_crawl_job,
            structure_id,
            0,  # preferred_character_id=0 → usa todos disponíveis
        )
        if queued:
            enqueued += 1

    logger.info("[scheduler] %d/%d estruturas enfileiradas para recrawl.", enqueued, len(structures))
    return enqueued


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_all_tokens(
    preferred_character_id: int, db: AsyncSession
) -> list[tuple[int, str, str]]:
    """
    Retorna lista de (character_id, character_name, access_token) de todos os
    personagens autenticados, com o preferido na frente.
    """
    from sqlalchemy import select as sa_select
    from app.models.character import Character
    from app.services.character_service import get_fresh_token

    result = await db.execute(
        sa_select(Character)
        .where(Character.refresh_token.isnot(None))
        .order_by(Character.updated_at.desc())
    )
    chars = result.scalars().all()

    # Coloca preferido na frente
    chars_ordered = sorted(
        chars,
        key=lambda c: 0 if c.character_id == preferred_character_id else 1,
    )

    tokens = []
    for char in chars_ordered:
        try:
            token = await get_fresh_token(char, db)
            if token:
                tokens.append((char.character_id, char.character_name, token))
        except Exception as exc:
            logger.warning("[crawl] Falha ao renovar token de %s: %s", char.character_name, exc)

    return tokens


async def _set_structure_status(db: AsyncSession, structure_id: int, status: str) -> None:
    struct = await db.get(Structure, structure_id)
    if struct:
        struct.status = status
        await db.commit()
