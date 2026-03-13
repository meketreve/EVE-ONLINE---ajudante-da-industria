"""
Discovery API — endpoints de descoberta e gestão de estruturas.

POST /discovery/assets                  → dispara discovery via personal assets
POST /discovery/structure/{id}/validate → revalida uma estrutura específica
POST /discovery/structure/{id}/crawl    → força recrawl imediato
GET  /discovery/structures              → lista todas as estruturas conhecidas
GET  /discovery/structures/{id}         → detalhe de uma estrutura
GET  /discovery/jobs                    → histórico de jobs recentes

Nenhum endpoint acessa a ESI diretamente — apenas disparam jobs assíncronos.
"""

import logging

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.models.job import DiscoveryJob, CrawlJob
from app.models.structure import Structure, DiscoverySource
from app.services.discovery_service import enqueue_asset_discovery, enqueue_validate
from app.services.crawler_service import run_crawl_job
from app.services.job_runner import crawl_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discovery", tags=["discovery"])


def _require_login(request: Request) -> int | None:
    return request.session.get("character_id")


# ── Discovery ─────────────────────────────────────────────────────────────────

@router.post("/assets")
async def trigger_asset_discovery(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Dispara discovery de estruturas via personal assets do personagem logado.
    Requer: esi-assets.read_assets.v1
    """
    character_id = _require_login(request)
    if not character_id:
        return JSONResponse({"error": "Login necessário."}, status_code=401)

    job_id = await enqueue_asset_discovery(character_id, db)
    return JSONResponse({"queued": True, "job_id": job_id, "source": "personal_assets"})


@router.post("/structure/{structure_id}/validate")
async def trigger_validate(
    request: Request,
    structure_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Revalida uma estrutura específica (resolve metadados + testa mercado)."""
    character_id = _require_login(request)
    if not character_id:
        return JSONResponse({"error": "Login necessário."}, status_code=401)

    await enqueue_validate(structure_id, character_id)
    return JSONResponse({"queued": True, "structure_id": structure_id})


@router.post("/structure/{structure_id}/crawl")
async def trigger_crawl(
    request: Request,
    structure_id: int,
):
    """Força recrawl imediato de mercado para uma estrutura."""
    character_id = _require_login(request)
    if not character_id:
        return JSONResponse({"error": "Login necessário."}, status_code=401)

    queued = await crawl_runner.enqueue(
        f"crawl:{structure_id}",
        run_crawl_job,
        structure_id,
        character_id,
    )
    return JSONResponse({"queued": queued, "structure_id": structure_id})


# ── Consultas ─────────────────────────────────────────────────────────────────

@router.get("/structures")
async def list_structures(
    request: Request,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Lista todas as estruturas conhecidas.
    Filtro opcional: ?status=market_accessible|market_denied|resolved|discovered|inactive
    """
    q = select(Structure).order_by(Structure.first_seen_at.desc())
    if status:
        q = q.where(Structure.status == status)

    result = await db.execute(q)
    structures = result.scalars().all()

    return JSONResponse([
        {
            "structure_id":          s.structure_id,
            "name":                  s.name,
            "system_name":           s.system_name,
            "owner_corporation_id":  s.owner_corporation_id,
            "status":                s.status,
            "first_seen_at":         s.first_seen_at.isoformat() if s.first_seen_at else None,
            "last_crawled_at":       s.last_crawled_at.isoformat() if s.last_crawled_at else None,
        }
        for s in structures
    ])


@router.get("/structures/{structure_id}")
async def get_structure(
    structure_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retorna detalhes de uma estrutura e suas fontes de descoberta."""
    struct = await db.get(Structure, structure_id)
    if not struct:
        return JSONResponse({"error": "Estrutura não encontrada."}, status_code=404)

    sources_result = await db.execute(
        select(DiscoverySource).where(DiscoverySource.structure_id == structure_id)
    )
    sources = sources_result.scalars().all()

    return JSONResponse({
        "structure_id":         struct.structure_id,
        "name":                 struct.name,
        "type_id":              struct.type_id,
        "owner_corporation_id": struct.owner_corporation_id,
        "system_id":            struct.system_id,
        "system_name":          struct.system_name,
        "status":               struct.status,
        "first_seen_at":        struct.first_seen_at.isoformat() if struct.first_seen_at else None,
        "last_resolved_at":     struct.last_resolved_at.isoformat() if struct.last_resolved_at else None,
        "last_crawled_at":      struct.last_crawled_at.isoformat() if struct.last_crawled_at else None,
        "discovery_sources":    [
            {
                "source":       src.source,
                "character_id": src.character_id,
                "discovered_at": src.discovered_at.isoformat(),
            }
            for src in sources
        ],
    })


@router.get("/jobs")
async def list_jobs(
    request: Request,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Histórico dos últimos jobs de discovery e crawl."""
    character_id = _require_login(request)

    disc_q = select(DiscoveryJob).order_by(desc(DiscoveryJob.created_at)).limit(limit)
    if character_id:
        disc_q = disc_q.where(DiscoveryJob.character_id == character_id)

    crawl_q = select(CrawlJob).order_by(desc(CrawlJob.created_at)).limit(limit)

    disc_result  = await db.execute(disc_q)
    crawl_result = await db.execute(crawl_q)

    disc_jobs  = disc_result.scalars().all()
    crawl_jobs = crawl_result.scalars().all()

    return JSONResponse({
        "discovery_jobs": [
            {
                "id":               j.id,
                "character_id":     j.character_id,
                "source":           j.source,
                "status":           j.status,
                "structures_found": j.structures_found,
                "error":            j.error,
                "created_at":       j.created_at.isoformat(),
                "finished_at":      j.finished_at.isoformat() if j.finished_at else None,
            }
            for j in disc_jobs
        ],
        "crawl_jobs": [
            {
                "id":             j.id,
                "structure_id":   j.structure_id,
                "status":         j.status,
                "orders_fetched": j.orders_fetched,
                "pages_fetched":  j.pages_fetched,
                "error":          j.error,
                "created_at":     j.created_at.isoformat(),
                "finished_at":    j.finished_at.isoformat() if j.finished_at else None,
            }
            for j in crawl_jobs
        ],
    })
