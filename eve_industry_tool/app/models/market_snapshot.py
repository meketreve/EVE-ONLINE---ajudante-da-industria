"""
Snapshot agregado de mercado por (structure_id, type_id).

Recalculado após cada crawl completo de uma estrutura.
É a tabela que o frontend lê — nunca market_orders_raw diretamente.
"""

from datetime import datetime
from sqlalchemy import BigInteger, Integer, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    structure_id: Mapped[int]           = mapped_column(BigInteger, primary_key=True)
    type_id:      Mapped[int]           = mapped_column(Integer,    primary_key=True)

    best_sell:    Mapped[float | None]  = mapped_column(Float,   nullable=True)  # min sell
    best_buy:     Mapped[float | None]  = mapped_column(Float,   nullable=True)  # max buy
    sell_volume:  Mapped[int | None]    = mapped_column(Integer, nullable=True)  # total volume_remain sell
    buy_volume:   Mapped[int | None]    = mapped_column(Integer, nullable=True)  # total volume_remain buy
    spread_pct:   Mapped[float | None]  = mapped_column(Float,   nullable=True)  # (sell-buy)/sell*100
    order_count:  Mapped[int | None]    = mapped_column(Integer, nullable=True)  # ordens ativas

    updated_at:   Mapped[datetime]      = mapped_column(DateTime, nullable=False)
