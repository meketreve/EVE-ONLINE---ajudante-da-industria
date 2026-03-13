"""
Ordens de mercado brutas coletadas pelo crawler.

Cada crawl faz upsert por order_id.
Ordens que somem no crawl seguinte são marcadas como is_stale=True
e removidas após 48h pelo job de limpeza.
"""

from datetime import datetime
from sqlalchemy import BigInteger, Integer, DateTime, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class MarketOrder(Base):
    __tablename__ = "market_orders_raw"

    order_id:      Mapped[int]      = mapped_column(BigInteger, primary_key=True)
    structure_id:  Mapped[int]      = mapped_column(BigInteger, nullable=False, index=True)
    type_id:       Mapped[int]      = mapped_column(Integer,    nullable=False, index=True)
    is_buy_order:  Mapped[bool]     = mapped_column(Boolean,    nullable=False)
    price:         Mapped[float]    = mapped_column(Float,      nullable=False)
    volume_remain: Mapped[int]      = mapped_column(Integer,    nullable=False)
    volume_total:  Mapped[int]      = mapped_column(Integer,    nullable=False)
    min_volume:    Mapped[int]      = mapped_column(Integer,    nullable=False, default=1)
    duration:      Mapped[int]      = mapped_column(Integer,    nullable=False)
    issued:        Mapped[datetime] = mapped_column(DateTime,   nullable=False)
    fetched_at:    Mapped[datetime] = mapped_column(DateTime,   nullable=False)
    is_stale:      Mapped[bool]     = mapped_column(Boolean,    nullable=False,
                                                    default=False, index=True)
