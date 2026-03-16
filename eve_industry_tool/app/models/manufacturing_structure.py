"""
Estruturas de manufatura cadastradas manualmente pelo usuário.

A ESI não expõe rigs/fitting de estruturas — portanto o usuário cadastra
o nome, tipo e bônus totais (ME + TE) de cada estrutura para uso no BOM.
"""
from datetime import datetime
from sqlalchemy import Integer, String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class ManufacturingStructure(Base):
    """
    Registro manual de uma estrutura de manufatura.

    `me_bonus` e `te_bonus` representam a redução percentual TOTAL,
    somando o bônus base da estrutura com os rigs instalados.

    Exemplo: Azbel base -1% ME + Standup M-Set ME I -2% = me_bonus = 3.0
    """
    __tablename__ = "manufacturing_structures"

    id:             Mapped[int]      = mapped_column(Integer,     primary_key=True, autoincrement=True)
    name:           Mapped[str]      = mapped_column(String(256), nullable=False)
    structure_type: Mapped[str]      = mapped_column(String(64),  nullable=False, default="raitaru")
    me_bonus:       Mapped[float]    = mapped_column(Float,       nullable=False, default=0.0)
    te_bonus:       Mapped[float]    = mapped_column(Float,       nullable=False, default=0.0)
    created_at:     Mapped[datetime] = mapped_column(DateTime,    nullable=False, default=datetime.utcnow)
