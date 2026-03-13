from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class MarketStructure(Base):
    """
    Estruturas privadas com mercado acessíveis ao(s) personagem(ns) autenticados.
    Populada pelo script atualizar_estruturas.py — não pelo servidor.
    """
    __tablename__ = "market_structures"

    structure_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    system_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    system_name: Mapped[str] = mapped_column(String(128), nullable=False, default="?")
    # character_id que descobriu essa estrutura
    character_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    character_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    last_updated: Mapped[datetime] = mapped_column(DateTime, nullable=False)
