"""
Estruturas Upwell descobertas e seu ciclo de vida.

Structure         — registro central de uma estrutura (status, metadados)
DiscoverySource   — registra de onde cada estrutura foi descoberta
"""

from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class Structure(Base):
    """
    Registro de uma estrutura Upwell (Citadela, EC, Keepstar, etc.).

    Ciclo de vida do status:
        discovered       → encontrada em alguma fonte, metadados ainda não resolvidos
        resolved         → metadados obtidos via /universe/structures/{id}/
        market_accessible→ /markets/structures/{id}/ retornou 200
        market_denied    → /markets/structures/{id}/ retornou 403 em todos os tokens
        inactive         → /universe/structures/{id}/ retornou 404 (não existe mais)
    """
    __tablename__ = "structures"

    structure_id:          Mapped[int]           = mapped_column(BigInteger, primary_key=True)
    name:                  Mapped[str | None]     = mapped_column(String(512),  nullable=True)
    type_id:               Mapped[int | None]     = mapped_column(Integer,      nullable=True)
    owner_corporation_id:  Mapped[int | None]     = mapped_column(BigInteger,   nullable=True)
    system_id:             Mapped[int | None]     = mapped_column(Integer,      nullable=True)
    system_name:           Mapped[str | None]     = mapped_column(String(128),  nullable=True)
    status:                Mapped[str]            = mapped_column(String(32),   nullable=False,
                                                                  default="discovered", index=True)
    first_seen_at:         Mapped[datetime]       = mapped_column(DateTime,     nullable=False,
                                                                  default=datetime.utcnow)
    last_resolved_at:      Mapped[datetime | None]= mapped_column(DateTime,     nullable=True)
    last_crawled_at:       Mapped[datetime | None]= mapped_column(DateTime,     nullable=True)


class DiscoverySource(Base):
    """
    Registra de onde cada estrutura foi descoberta.
    Uma estrutura pode ter múltiplas fontes ao longo do tempo.

    source values:
        personal_assets, corporation_assets, corporation_structures,
        public_structures, industry_jobs, current_location, manual_seed
    """
    __tablename__ = "structure_discovery_sources"
    __table_args__ = (
        UniqueConstraint("structure_id", "source", "character_id", name="uq_discovery_source"),
    )

    id:           Mapped[int]           = mapped_column(Integer,   primary_key=True)
    structure_id: Mapped[int]           = mapped_column(BigInteger, nullable=False, index=True)
    source:       Mapped[str]           = mapped_column(String(64), nullable=False)
    character_id: Mapped[int | None]   = mapped_column(BigInteger, nullable=True,  index=True)
    discovered_at: Mapped[datetime]    = mapped_column(DateTime,   nullable=False,
                                                        default=datetime.utcnow)
