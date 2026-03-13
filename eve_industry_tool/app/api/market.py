"""
Market data routes.

GET  /market/                         - página de visão geral do mercado (estruturas + cache)
GET  /market/price/{type_id}          - preço atual de um item
POST /market/refresh/{type_id}        - re-busca preços de um item (HTMX)
POST /market/clear-cache              - limpa cache de um mercado específico
POST /market/structures/refresh-all   - atualiza cache de preços de todas as estruturas privadas
"""

import logging
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.models.character import Character
from app.models.market_structure import MarketStructure
from app.models.market_snapshot import MarketSnapshot
from app.models.structure import Structure
from app.models.cache import MarketPriceCache
from app.services.market_service import get_best_price, clear_price_cache, THE_FORGE_REGION_ID
from app.services.character_service import get_fresh_token
from app.services.esi_client import esi_client, ESIError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])
templates = Jinja2Templates(directory="app/templates")


# ── Página principal de mercado ───────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def market_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Visão geral do mercado: estruturas descobertas, status do crawler e estatísticas.
    """
    character_name = request.session.get("character_name")

    # Estruturas por status
    structs_result = await db.execute(
        select(Structure).order_by(Structure.status.asc(), Structure.name.asc())
    )
    all_structures = structs_result.scalars().all()

    # Contagem de snapshots por estrutura
    snap_counts_result = await db.execute(
        select(MarketSnapshot.structure_id, func.count(MarketSnapshot.type_id).label("n"))
        .group_by(MarketSnapshot.structure_id)
    )
    snap_counts: dict[int, int] = {row.structure_id: row.n for row in snap_counts_result.all()}

    # Entradas em cache de preços (região The Forge)
    cache_count_result = await db.execute(
        select(func.count()).select_from(MarketPriceCache)
        .where(MarketPriceCache.market_type == "region", MarketPriceCache.market_id == THE_FORGE_REGION_ID)
    )
    region_cache_count: int = cache_count_result.scalar_one() or 0

    # Agrupa estruturas por status para exibição
    by_status: dict[str, list] = {}
    for s in all_structures:
        entry = {
            "structure": s,
            "snapshot_count": snap_counts.get(s.structure_id, 0),
        }
        by_status.setdefault(s.status, []).append(entry)

    return templates.TemplateResponse("market.html", {
        "request": request,
        "character_name": character_name,
        "by_status": by_status,
        "total_structures": len(all_structures),
        "region_cache_count": region_cache_count,
        "forge_region_id": THE_FORGE_REGION_ID,
    })


# ── Snapshots de mercado (lidos do banco, nunca da ESI diretamente) ───────────

@router.get("/snapshot/item/{type_id}")
async def snapshot_by_item(
    type_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna o melhor preço de um item em todas as estruturas com mercado acessível,
    ordenado pelo menor sell.
    Fonte: market_snapshots (atualizado pelo crawler).
    """
    result = await db.execute(
        select(MarketSnapshot, Structure.name, Structure.system_name)
        .join(Structure, Structure.structure_id == MarketSnapshot.structure_id)
        .where(MarketSnapshot.type_id == type_id)
        .order_by(MarketSnapshot.best_sell.asc().nullslast())
    )
    rows = result.all()

    return JSONResponse([
        {
            "structure_id":  snap.structure_id,
            "structure_name": name,
            "system_name":   system,
            "best_sell":     snap.best_sell,
            "best_buy":      snap.best_buy,
            "sell_volume":   snap.sell_volume,
            "buy_volume":    snap.buy_volume,
            "spread_pct":    snap.spread_pct,
            "order_count":   snap.order_count,
            "updated_at":    snap.updated_at.isoformat(),
        }
        for snap, name, system in rows
    ])


@router.get("/snapshot/structure/{structure_id}")
async def snapshot_by_structure(
    structure_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna todos os itens com snapshot de mercado para uma estrutura específica.
    """
    struct = await db.get(Structure, structure_id)
    if not struct:
        return JSONResponse({"error": "Estrutura não encontrada."}, status_code=404)

    result = await db.execute(
        select(MarketSnapshot)
        .where(MarketSnapshot.structure_id == structure_id)
        .order_by(MarketSnapshot.type_id.asc())
    )
    snaps = result.scalars().all()

    return JSONResponse({
        "structure_id":  structure_id,
        "structure_name": struct.name,
        "system_name":   struct.system_name,
        "last_crawled":  struct.last_crawled_at.isoformat() if struct.last_crawled_at else None,
        "items": [
            {
                "type_id":    s.type_id,
                "best_sell":  s.best_sell,
                "best_buy":   s.best_buy,
                "sell_volume": s.sell_volume,
                "buy_volume": s.buy_volume,
                "spread_pct": s.spread_pct,
                "order_count": s.order_count,
                "updated_at": s.updated_at.isoformat(),
            }
            for s in snaps
        ],
    })


@router.get("/price/{type_id}")
async def get_price(
    type_id: int,
    region_id: int = Query(default=THE_FORGE_REGION_ID),
    db: AsyncSession = Depends(get_db),
):
    sell_price = await get_best_price(type_id, region_id, "sell", db=db)
    buy_price = await get_best_price(type_id, region_id, "buy", db=db)
    return JSONResponse(content={
        "type_id": type_id,
        "region_id": region_id,
        "sell": sell_price,
        "buy": buy_price,
    })


@router.post("/refresh/{type_id}", response_class=HTMLResponse)
async def refresh_price(
    request: Request,
    type_id: int,
    region_id: int = Query(default=THE_FORGE_REGION_ID),
    db: AsyncSession = Depends(get_db),
):
    sell_price = await get_best_price(type_id, region_id, "sell", db=db)
    buy_price = await get_best_price(type_id, region_id, "buy", db=db)

    sell_fmt = f"{sell_price:,.2f} ISK" if sell_price is not None else "N/A"
    buy_fmt = f"{buy_price:,.2f} ISK" if buy_price is not None else "N/A"

    return HTMLResponse(content=f"""
<span class="price-sell">Sell: <strong>{sell_fmt}</strong></span>
<span class="price-buy">Buy: <strong>{buy_fmt}</strong></span>
""")


@router.post("/clear-cache", response_class=HTMLResponse)
async def clear_market_cache(
    market_source: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Limpa o cache de preços para um mercado específico.
    market_source: "region:10000002" ou "structure:1234567890"
    Retorna um fragmento HTML para HTMX.
    """
    try:
        source_type, source_id_str = market_source.split(":", 1)
        market_id = int(source_id_str)
    except (ValueError, AttributeError):
        return HTMLResponse(content='<span class="cache-status error">Mercado inválido.</span>')

    deleted = await clear_price_cache(db, source_type, market_id)
    return HTMLResponse(
        content=f'<span class="cache-status success">Cache limpo ({deleted} entradas). Recalcule para buscar preços frescos.</span>'
    )


@router.post("/structures/refresh-all", response_class=HTMLResponse)
async def refresh_all_structures(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Atualiza o cache de preços para todas as estruturas privadas salvas no banco.

    Para cada estrutura, tenta TODOS os personagens autenticados até um ter
    acesso (200). 403 = sem docking rights para esse personagem, tenta o próximo.

    Endpoint ESI: GET /markets/structures/{structure_id}/
    Scope: esi-markets.structure_markets.v1
    """
    if not request.session.get("character_id"):
        return HTMLResponse(
            content='<span class="cache-status error">Faça login para atualizar os preços.</span>'
        )

    # 1. Carrega TODOS os personagens autenticados e renova tokens
    chars_result = await db.execute(
        select(Character).where(Character.refresh_token.isnot(None))
    )
    all_chars = chars_result.scalars().all()

    if not all_chars:
        return HTMLResponse(
            content='<span class="cache-status error">Nenhum personagem autenticado no banco.</span>'
        )

    tokens: list[tuple[str, str]] = []  # [(character_name, access_token)]
    for char in all_chars:
        try:
            token = await get_fresh_token(char, db)
            if token:
                tokens.append((char.character_name, token))
        except Exception as exc:
            logger.warning("Falha ao renovar token de %s: %s", char.character_name, exc)

    if not tokens:
        return HTMLResponse(
            content='<span class="cache-status error">Nenhum token válido disponível. Tente fazer login novamente.</span>'
        )

    # 2. Carrega estruturas
    result = await db.execute(select(MarketStructure))
    structures = result.scalars().all()

    if not structures:
        return HTMLResponse(
            content='<span class="cache-status error">Nenhuma estrutura cadastrada. Execute atualizar_estruturas.bat primeiro.</span>'
        )

    _MISS = object()  # sentinela: diferencia "nenhum token tentado" de "lista vazia"
    total_ok    = 0
    total_itens = 0
    sem_acesso: list[str] = []
    erros:      list[str] = []
    now = datetime.utcnow()

    # 3. Para cada estrutura, tenta todos os tokens até obter 200
    for struct in structures:
        orders = _MISS

        for char_name, token in tokens:
            try:
                orders = await esi_client.get_structure_market(struct.structure_id, token)
                break  # 200 — usa este resultado
            except ESIError as exc:
                if exc.status_code == 403:
                    continue  # sem acesso — tenta próximo personagem
                erros.append(f"{struct.name}: ESI {exc.status_code}.")
                orders = _MISS
                break
            except Exception as exc:
                erros.append(f"{struct.name}: {exc}.")
                orders = _MISS
                break

        if orders is _MISS:
            sem_acesso.append(struct.name)
            continue

        if not orders:
            continue  # mercado sem ordens ativas

        # 4. Calcula melhor preço por type_id
        sell: dict[int, list[float]] = defaultdict(list)
        buy:  dict[int, list[float]] = defaultdict(list)
        for order in orders:
            if order["is_buy_order"]:
                buy[order["type_id"]].append(order["price"])
            else:
                sell[order["type_id"]].append(order["price"])

        prices: dict[tuple, float] = {}
        for tid, p in sell.items():
            prices[(tid, "sell")] = min(p)
        for tid, p in buy.items():
            prices[(tid, "buy")] = max(p)

        # 5. Upsert em market_price_cache
        for (tid, order_type), price in prices.items():
            await db.execute(
                text("""
                    INSERT OR REPLACE INTO market_price_cache
                        (type_id, market_type, market_id, order_type, price, fetched_at)
                    VALUES
                        (:type_id, 'structure', :market_id, :order_type, :price, :fetched_at)
                """),
                {
                    "type_id":    tid,
                    "market_id":  struct.structure_id,
                    "order_type": order_type,
                    "price":      price,
                    "fetched_at": now,
                },
            )

        total_ok    += 1
        total_itens += len(set(tid for (tid, _) in prices))

    # 6. Monta resposta HTML
    sem_acesso_html = ""
    if sem_acesso:
        items = "".join(f"<li>{n}</li>" for n in sem_acesso)
        sem_acesso_html = (
            f'<p class="cache-warning">Sem acesso ({len(sem_acesso)}):</p>'
            f'<ul class="cache-errors">{items}</ul>'
            f'<p class="cache-hint">Faça login com um personagem que tenha docking rights nessas estruturas.</p>'
        )

    erros_html = ""
    if erros:
        items = "".join(f"<li>{e}</li>" for e in erros)
        erros_html = f'<ul class="cache-errors">{items}</ul>'

    return HTMLResponse(content=f"""
<span class="cache-status success">
  {total_ok} estrutura(s) atualizadas — {total_itens} itens no cache.
  ({len(tokens)} token(s) disponível(is))
</span>
{sem_acesso_html}
{erros_html}
""")
