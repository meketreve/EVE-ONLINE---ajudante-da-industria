"""
Serviço de descoberta de estruturas Upwell.

Fluxo completo:
  1. run_asset_discovery()   → busca assets do personagem, extrai structure_ids
  2. _validate_structure()   → resolve metadados + testa acesso ao mercado
  3. Enfileira crawl se mercado acessível

Regras:
  - location_id >= 1_000_000_000_000  →  candidato a estrutura Upwell
  - Deduplicar antes de validar
  - /universe/structures/{id}/ 404   →  inactive
  - /universe/structures/{id}/ 403   →  mantém discovered (tenta outro personagem depois)
  - /markets/structures/{id}/  200   →  market_accessible  →  enfileira crawl
  - /markets/structures/{id}/  403   →  market_denied
"""

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.models.job import DiscoveryJob, CrawlJob
from app.models.structure import Structure, DiscoverySource
from app.services.esi_client import esi_client, ESIError
from app.services.job_runner import discovery_runner, crawl_runner

logger = logging.getLogger(__name__)

# Faixa de IDs de estruturas Upwell (Citadelas, ECs, Keepstars…)
UPWELL_MIN_ID = 1_000_000_000_000


# ── Ponto de entrada público ──────────────────────────────────────────────────

async def enqueue_asset_discovery(character_id: int, db: AsyncSession) -> int:
    """
    Cria um DiscoveryJob no banco e enfileira o job de assets.
    Retorna o job_id criado.
    Chamado pelo controller — não acessa a ESI diretamente.
    """
    job = DiscoveryJob(
        character_id=character_id,
        source="personal_assets",
        status="pending",
    )
    db.add(job)
    await db.flush()
    job_id = job.id

    await discovery_runner.enqueue(
        f"discovery:assets:{character_id}",
        _run_asset_discovery_job,
        job_id,
        character_id,
    )

    return job_id


async def enqueue_validate(structure_id: int, character_id: int) -> None:
    """Enfileira validação de uma estrutura específica."""
    await discovery_runner.enqueue(
        f"validate:{structure_id}",
        _validate_structure_job,
        structure_id,
        character_id,
    )


# ── Jobs internos (executados pelos workers) ──────────────────────────────────

async def _run_asset_discovery_job(job_id: int, character_id: int) -> None:
    """
    Worker: busca assets, extrai Upwell structure_ids, persiste e enfileira validações.
    Cria sua própria sessão de DB.
    """
    async with AsyncSessionLocal() as db:
        # Marca job como running
        job = await db.get(DiscoveryJob, job_id)
        if job:
            job.status     = "running"
            job.started_at = datetime.utcnow()
            await db.commit()

        try:
            structures_found = await _do_asset_discovery(character_id, db)

            if job:
                job.status          = "done"
                job.structures_found = structures_found
                job.finished_at     = datetime.utcnow()
                await db.commit()

            logger.info(
                "[discovery:assets] char=%d → %d candidato(s) encontrado(s).",
                character_id, structures_found,
            )

        except Exception as exc:
            logger.error("[discovery:assets] char=%d falhou: %s", character_id, exc, exc_info=True)
            if job:
                job.status      = "failed"
                job.error       = str(exc)
                job.finished_at = datetime.utcnow()
                await db.commit()


async def _do_asset_discovery(character_id: int, db: AsyncSession) -> int:
    """
    Lógica principal: assets → Upwell IDs → upsert structures → enfileira validações.
    Retorna número de candidatos novos inseridos.
    """
    from app.services.character_service import get_character, get_fresh_token

    char = await get_character(character_id, db)
    if not char:
        raise ValueError(f"Personagem {character_id} não encontrado no banco.")

    token = await get_fresh_token(char, db)
    if not token:
        raise ValueError(f"Sem token válido para personagem {character_id}.")

    # Busca todos os assets (paginado)
    assets = await esi_client.get_character_assets(character_id, token)
    logger.debug("[discovery:assets] char=%d → %d assets recebidos.", character_id, len(assets))

    # Extrai e deduplica structure_ids Upwell
    candidate_ids: set[int] = set()
    for asset in assets:
        loc_id = asset.get("location_id", 0)
        if loc_id >= UPWELL_MIN_ID:
            candidate_ids.add(loc_id)

    logger.info(
        "[discovery:assets] char=%d → %d assets, %d candidatos Upwell.",
        character_id, len(assets), len(candidate_ids),
    )

    new_count = 0
    now = datetime.utcnow()

    for structure_id in candidate_ids:
        # Upsert: só insere se não existir (não rebaixa status mais avançado)
        result = await db.execute(
            text("""
                INSERT INTO structures (structure_id, status, first_seen_at)
                VALUES (:sid, 'discovered', :now)
                ON CONFLICT (structure_id) DO NOTHING
            """),
            {"sid": structure_id, "now": now},
        )
        if result.rowcount > 0:
            new_count += 1

        # Registra fonte de descoberta
        await db.execute(
            text("""
                INSERT INTO structure_discovery_sources
                    (structure_id, source, character_id, discovered_at)
                VALUES (:sid, 'personal_assets', :char_id, :now)
                ON CONFLICT (structure_id, source, character_id) DO NOTHING
            """),
            {"sid": structure_id, "char_id": character_id, "now": now},
        )

        # Enfileira validação (deduplicada por job_id)
        await discovery_runner.enqueue(
            f"validate:{structure_id}",
            _validate_structure_job,
            structure_id,
            character_id,
        )

    await db.commit()
    return new_count


async def _validate_structure_job(structure_id: int, character_id: int) -> None:
    """
    Worker: resolve metadados via ESI e testa acesso ao mercado.
    """
    async with AsyncSessionLocal() as db:
        try:
            await _do_validate_structure(structure_id, character_id, db)
        except Exception as exc:
            logger.error(
                "[validate] structure=%d falhou: %s", structure_id, exc, exc_info=True
            )


async def _do_validate_structure(
    structure_id: int, character_id: int, db: AsyncSession
) -> None:
    from app.services.character_service import get_character, get_fresh_token

    struct = await db.get(Structure, structure_id)
    if struct and struct.status == "inactive":
        return  # não reprocessa estruturas inativas

    char = await get_character(character_id, db)
    if not char:
        return

    token = await get_fresh_token(char, db)
    if not token:
        return

    # ── Etapa 1: Resolve metadados ────────────────────────────────────────
    try:
        info = await esi_client.get_structure_info(structure_id, token)
    except ESIError as exc:
        if exc.status_code == 404:
            await _set_status(db, structure_id, "inactive")
            logger.info("[validate] %d → inactive (404)", structure_id)
            return
        if exc.status_code == 403:
            # Personagem sem acesso — mantém discovered para tentar outro depois
            logger.debug("[validate] %d → 403 ao resolver metadados, mantém discovered.", structure_id)
            return
        raise

    # Resolve nome do sistema
    system_name = str(info.get("solar_system_id", ""))
    try:
        system_name = await esi_client.get_system_name(info["solar_system_id"])
    except Exception:
        pass

    now = datetime.utcnow()
    if struct is None:
        db.add(Structure(
            structure_id=structure_id,
            status="resolved",
            first_seen_at=now,
        ))
        struct = await db.get(Structure, structure_id)

    if struct:
        struct.name                 = info.get("name", f"Structure {structure_id}")
        struct.type_id              = info.get("type_id")
        struct.owner_corporation_id = info.get("owner_id")
        struct.system_id            = info.get("solar_system_id")
        struct.system_name          = system_name
        struct.status               = "resolved"
        struct.last_resolved_at     = now

    await db.flush()

    # ── Etapa 2: Testa acesso ao mercado (apenas página 1) ────────────────
    try:
        await esi_client._get(
            f"{settings.ESI_BASE_URL}/markets/structures/{structure_id}/",
            token=token,
            params={"page": 1},
        )
        # 200 → mercado acessível
        if struct:
            struct.status = "market_accessible"
        await db.commit()

        logger.info("[validate] %d → market_accessible", structure_id)

        # Enfileira crawl completo
        await crawl_runner.enqueue(
            f"crawl:{structure_id}",
            _crawl_market_job,
            structure_id,
            character_id,
        )

    except ESIError as exc:
        if exc.status_code == 403:
            if struct:
                struct.status = "market_denied"
            await db.commit()
            logger.info("[validate] %d → market_denied (403)", structure_id)
        else:
            await db.commit()
            raise


async def _set_status(db: AsyncSession, structure_id: int, status: str) -> None:
    struct = await db.get(Structure, structure_id)
    if struct:
        struct.status = status
    else:
        db.add(Structure(
            structure_id=structure_id,
            status=status,
            first_seen_at=datetime.utcnow(),
        ))
    await db.commit()


# ── Crawl enfileirado pela validação ─────────────────────────────────────────
# (implementação completa em crawler_service.py)

async def _crawl_market_job(structure_id: int, character_id: int) -> None:
    from app.services.crawler_service import run_crawl_job
    await run_crawl_job(structure_id, character_id)


# ── Discovery periódico (chamado pelo scheduler) ──────────────────────────────

async def _do_asset_discovery_all() -> None:
    """
    Enfileira discovery de assets para todos os personagens autenticados.
    Chamado pelo scheduler a cada 6h.
    Utiliza asyncio.gather para paralelizar o enfileiramento.
    """
    import asyncio
    from app.models.character import Character
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Character.character_id)
            .where(Character.refresh_token.isnot(None))
        )
        char_ids = [row[0] for row in result.all()]

    async def _enqueue_one(char_id: int) -> None:
        await discovery_runner.enqueue(
            f"discovery:assets:{char_id}",
            _run_asset_discovery_job,
            0,      # job_id placeholder (sem registro no DB nesta chamada)
            char_id,
        )

    await asyncio.gather(*[_enqueue_one(cid) for cid in char_ids])
