"""
Jobs de discovery e crawl — rastreamento de execuções assíncronas.

DiscoveryJob — busca de estruturas a partir de uma fonte (ex: personal_assets)
CrawlJob     — coleta de ordens de mercado de uma estrutura
"""

from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class DiscoveryJob(Base):
    """
    status: pending → running → done | failed
    """
    __tablename__ = "discovery_jobs"

    id:               Mapped[int]           = mapped_column(Integer,   primary_key=True)
    character_id:     Mapped[int]           = mapped_column(BigInteger, nullable=False, index=True)
    source:           Mapped[str]           = mapped_column(String(64), nullable=False)
    status:           Mapped[str]           = mapped_column(String(16), nullable=False,
                                                            default="pending", index=True)
    structures_found: Mapped[int]           = mapped_column(Integer,   nullable=False, default=0)
    error:            Mapped[str | None]    = mapped_column(Text,      nullable=True)
    started_at:       Mapped[datetime | None]  = mapped_column(DateTime, nullable=True)
    finished_at:      Mapped[datetime | None]  = mapped_column(DateTime, nullable=True)
    created_at:       Mapped[datetime]      = mapped_column(DateTime,  nullable=False,
                                                            default=datetime.utcnow)


class CrawlJob(Base):
    """
    status: pending → running → done | failed | denied
    denied = nenhum token teve acesso (403 em todos)
    """
    __tablename__ = "crawl_jobs"

    id:             Mapped[int]           = mapped_column(Integer,    primary_key=True)
    structure_id:   Mapped[int]           = mapped_column(BigInteger, nullable=False, index=True)
    character_id:   Mapped[int | None]    = mapped_column(BigInteger, nullable=True)
    status:         Mapped[str]           = mapped_column(String(16), nullable=False,
                                                          default="pending", index=True)
    orders_fetched: Mapped[int]           = mapped_column(Integer,    nullable=False, default=0)
    pages_fetched:  Mapped[int]           = mapped_column(Integer,    nullable=False, default=0)
    error:          Mapped[str | None]    = mapped_column(Text,       nullable=True)
    started_at:     Mapped[datetime | None]  = mapped_column(DateTime, nullable=True)
    finished_at:    Mapped[datetime | None]  = mapped_column(DateTime, nullable=True)
    created_at:     Mapped[datetime]      = mapped_column(DateTime,   nullable=False,
                                                          default=datetime.utcnow)
