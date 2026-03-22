"""
Structure selector component.
Dropdown for selecting manufacturing structures with ME/TE bonuses.
"""

from nicegui import ui
from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.models.manufacturing_structure import ManufacturingStructure


async def render_structure_selector(
    default_id: int = 0,
    on_change=None,
) -> ui.select:
    """
    Cria e retorna um seletor de estruturas de manufatura.

    Parameters
    ----------
    default_id : int
        ID da estrutura pré-selecionada (0 = nenhuma)
    on_change : callable | None
        Callback chamado com o ID selecionado quando o valor muda

    Returns
    -------
    ui.select component
    """
    options = {0: "Nenhuma (usar bônus global)"}

    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(ManufacturingStructure).order_by(ManufacturingStructure.name)
            )
            structs = res.scalars().all()
            for s in structs:
                options[s.id] = f"{s.name} (ME {s.me_bonus:.1f}% / TE {s.te_bonus:.1f}%)"
    except Exception:
        pass

    select_widget = ui.select(
        options=options,
        value=default_id,
        label="Estrutura de Manufatura",
    )
    select_widget.props("outlined dense dark")

    if on_change:
        select_widget.on("update:model-value", lambda e: on_change(e.args))

    return select_widget


async def get_structure_bonuses(structure_id: int) -> tuple[float, float]:
    """
    Retorna (me_bonus, te_bonus) para a estrutura selecionada.
    Retorna (0.0, 0.0) se structure_id == 0 ou não encontrado.
    """
    if not structure_id:
        return 0.0, 0.0

    try:
        async with AsyncSessionLocal() as db:
            struct = await db.get(ManufacturingStructure, structure_id)
            if struct:
                return struct.me_bonus, struct.te_bonus
    except Exception:
        pass

    return 0.0, 0.0
