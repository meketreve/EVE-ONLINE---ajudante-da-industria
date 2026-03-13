"""
EVE Industry Profit Tool - FastAPI application entry point.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database.database import create_tables
from app.api import auth, items, industry, market

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _scheduler_loop() -> None:
    """
    Scheduler periódico (sem Redis/Celery).
    - A cada 15 min: recrawl de todas as estruturas com mercado acessível
    - A cada 1h:     limpeza de ordens stale antigas
    - A cada 6h:     rediscovery de assets para todos os personagens
    """
    from app.services.crawler_service import schedule_recrawl_all, cleanup_stale_orders
    from app.services.discovery_service import _do_asset_discovery_all

    CRAWL_INTERVAL    = 15 * 60   # segundos
    CLEANUP_INTERVAL  = 60 * 60
    DISCOVER_INTERVAL = 6 * 60 * 60

    last_crawl    = 0.0
    last_cleanup  = 0.0
    last_discover = 0.0

    while True:
        await asyncio.sleep(60)  # tick a cada minuto
        now = asyncio.get_event_loop().time()

        if now - last_crawl >= CRAWL_INTERVAL:
            last_crawl = now
            try:
                await schedule_recrawl_all()
            except Exception as exc:
                logger.error("[scheduler] recrawl falhou: %s", exc)

        if now - last_cleanup >= CLEANUP_INTERVAL:
            last_cleanup = now
            try:
                await cleanup_stale_orders()
            except Exception as exc:
                logger.error("[scheduler] cleanup falhou: %s", exc)

        if now - last_discover >= DISCOVER_INTERVAL:
            last_discover = now
            try:
                await _do_asset_discovery_all()
            except Exception as exc:
                logger.error("[scheduler] discovery geral falhou: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: cria tabelas, inicia workers e scheduler. Shutdown: libera recursos."""
    logger.info("Starting up — criando tabelas do banco...")

    # Importa todos os modelos para garantir que as tabelas sejam criadas
    import app.models.user, app.models.character, app.models.item
    import app.models.blueprint, app.models.production_queue
    import app.models.cache, app.models.market_structure
    import app.models.structure, app.models.market_order
    import app.models.market_snapshot, app.models.job
    import app.models.user_settings

    await create_tables()
    logger.info("Tabelas prontas.")

    # Inicia workers das filas
    from app.services.job_runner import discovery_runner, crawl_runner
    discovery_runner.start()
    crawl_runner.start()
    logger.info("Workers iniciados.")

    # Inicia scheduler
    scheduler_task = asyncio.create_task(_scheduler_loop(), name="scheduler")
    logger.info("Scheduler iniciado.")

    yield

    # Shutdown
    scheduler_task.cancel()
    await discovery_runner.stop()
    await crawl_runner.stop()

    from app.services.esi_client import esi_client
    await esi_client.close()
    logger.info("Shutdown concluído.")


app = FastAPI(
    title="EVE Industry Profit Tool",
    description="Local web application for EVE Online industry cost and profit analysis.",
    version="1.0.0",
    lifespan=lifespan,
)

# Session middleware (uses itsdangerous under the hood via Starlette)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="eve_industry_session",
    max_age=86400 * 7,  # 7 days
    same_site="lax",
    https_only=False,  # local dev, no HTTPS required
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Routers
app.include_router(auth.router)
app.include_router(items.router)
app.include_router(industry.router)
app.include_router(market.router)

from app.api import discovery
app.include_router(discovery.router)

from app.api import settings as settings_api
app.include_router(settings_api.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Dashboard / home page."""
    character_name = request.session.get("character_name")
    character_id = request.session.get("character_id")

    context = {
        "request": request,
        "character_name": character_name,
        "character_id": character_id,
    }
    return templates.TemplateResponse("index.html", context)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Standalone login page."""
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "character_name": request.session.get("character_name")},
    )


@app.get("/queue", response_class=HTMLResponse)
async def production_queue_page(request: Request):
    """Production queue page."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.database.database import AsyncSessionLocal
    from app.models.production_queue import ProductionQueue
    from app.models.item import Item

    character_id = request.session.get("character_id")
    queue_items: list[dict] = []

    if character_id:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ProductionQueue).where(
                    ProductionQueue.character_id == character_id
                ).order_by(ProductionQueue.created_at.desc())
            )
            queue_entries = result.scalars().all()

            for entry in queue_entries:
                item_result = await db.execute(
                    select(Item).where(Item.type_id == entry.item_type_id)
                )
                item = item_result.scalar_one_or_none()
                queue_items.append(
                    {
                        "id": entry.id,
                        "item_name": item.type_name if item else f"Type {entry.item_type_id}",
                        "type_id": entry.item_type_id,
                        "quantity": entry.quantity,
                        "status": entry.status,
                        "created_at": entry.created_at,
                    }
                )

    return templates.TemplateResponse(
        "production_queue.html",
        {
            "request": request,
            "character_name": request.session.get("character_name"),
            "queue_items": queue_items,
        },
    )


@app.post("/queue/add")
async def add_to_queue(request: Request):
    """Add an item to the production queue (requires login)."""
    from fastapi.responses import RedirectResponse
    from app.database.database import AsyncSessionLocal
    from app.models.production_queue import ProductionQueue

    character_id = request.session.get("character_id")
    if not character_id:
        return RedirectResponse(url="/login", status_code=303)

    form = await request.form()
    type_id = int(form.get("type_id", 0))
    quantity = int(form.get("quantity", 1))

    if type_id:
        async with AsyncSessionLocal() as db:
            entry = ProductionQueue(
                character_id=character_id,
                item_type_id=type_id,
                quantity=max(1, quantity),
                status="pending",
            )
            db.add(entry)
            await db.commit()

    return RedirectResponse(url="/queue", status_code=303)


@app.delete("/queue/{entry_id}")
async def remove_from_queue(entry_id: int, request: Request):
    """Remove an item from the production queue."""
    from fastapi.responses import Response
    from sqlalchemy import select, delete
    from app.database.database import AsyncSessionLocal
    from app.models.production_queue import ProductionQueue

    character_id = request.session.get("character_id")
    if not character_id:
        return Response(status_code=401)

    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(ProductionQueue).where(
                ProductionQueue.id == entry_id,
                ProductionQueue.character_id == character_id,
            )
        )
        await db.commit()

    return Response(status_code=200)
