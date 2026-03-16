"""
Tabelas de cache para dados externos (ESI).

MarketPriceCache  — preços de mercado por tipo/mercado/ordem (TTL: 5 min)
StructureCache    — nome e sistema de estruturas privadas  (TTL: 24 h)
SkillCache        — skills de personagens                  (TTL: 1 h)
"""

from datetime import datetime

from sqlalchemy import BigInteger, Float, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class MarketPriceCache(Base):
    __tablename__ = "market_price_cache"
    __table_args__ = (
        UniqueConstraint(
            "type_id", "market_type", "market_id", "order_type",
            name="uq_market_price",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # "region" ou "structure"
    market_type: Mapped[str] = mapped_column(String(16), nullable=False)
    market_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # "sell" ou "buy"
    order_type: Mapped[str] = mapped_column(String(8), nullable=False)
    # None significa "sem ordens disponíveis naquele momento"
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Volume total de unidades disponíveis (soma de volume_remain de todas as ordens)
    total_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class StructureCache(Base):
    __tablename__ = "structure_cache"

    structure_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    system_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    system_name: Mapped[str] = mapped_column(String(128), nullable=False, default="?")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class SkillCache(Base):
    __tablename__ = "skill_cache"

    character_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # JSON: {"skill_id": level, ...}
    skills_json: Mapped[str] = mapped_column(String, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
