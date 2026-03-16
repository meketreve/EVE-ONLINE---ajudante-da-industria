"""
CRUD de estruturas de manufatura.

GET    /manufacturing-structures/        - lista todas
POST   /manufacturing-structures/        - cria nova
DELETE /manufacturing-structures/{id}    - remove
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database.database import get_db
from app.models.manufacturing_structure import ManufacturingStructure

router = APIRouter(prefix="/manufacturing-structures", tags=["manufacturing-structures"])
templates = Jinja2Templates(directory="app/templates")

STRUCTURE_TYPES = [
    {"value": "raitaru",  "label": "Raitaru (Medium EC)"},
    {"value": "azbel",    "label": "Azbel (Large EC)"},
    {"value": "sotiyo",   "label": "Sotiyo (XL EC)"},
    {"value": "custom",   "label": "Outra / Personalizado"},
]


@router.get("/", response_class=HTMLResponse)
async def list_structures(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ManufacturingStructure).order_by(ManufacturingStructure.name)
    )
    structures = result.scalars().all()
    return templates.TemplateResponse(
        "partials/manufacturing_structures_list.html",
        {"request": request, "structures": structures, "structure_types": STRUCTURE_TYPES},
    )


@router.post("/", response_class=HTMLResponse)
async def create_structure(
    request: Request,
    name: str = Form(...),
    structure_type: str = Form(default="raitaru"),
    me_bonus: float = Form(default=0.0),
    te_bonus: float = Form(default=0.0),
    db: AsyncSession = Depends(get_db),
):
    name = name.strip()
    if not name:
        return HTMLResponse("<span class='alert alert-error'>Nome é obrigatório.</span>")

    if structure_type not in [t["value"] for t in STRUCTURE_TYPES]:
        structure_type = "custom"

    db.add(ManufacturingStructure(
        name=name,
        structure_type=structure_type,
        me_bonus=max(0.0, min(100.0, me_bonus)),
        te_bonus=max(0.0, min(100.0, te_bonus)),
        created_at=datetime.utcnow(),
    ))
    await db.flush()

    result = await db.execute(
        select(ManufacturingStructure).order_by(ManufacturingStructure.name)
    )
    structures = result.scalars().all()
    return templates.TemplateResponse(
        "partials/manufacturing_structures_list.html",
        {"request": request, "structures": structures, "structure_types": STRUCTURE_TYPES},
    )


@router.delete("/{structure_id}", response_class=HTMLResponse)
async def delete_structure(
    structure_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(ManufacturingStructure).where(ManufacturingStructure.id == structure_id)
    )
    await db.flush()

    result = await db.execute(
        select(ManufacturingStructure).order_by(ManufacturingStructure.name)
    )
    structures = result.scalars().all()
    return templates.TemplateResponse(
        "partials/manufacturing_structures_list.html",
        {"request": request, "structures": structures, "structure_types": STRUCTURE_TYPES},
    )
