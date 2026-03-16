from datetime import datetime
from sqlalchemy import Integer, Float, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_market_source: Mapped[str] = mapped_column(String(64), nullable=False, default="region:10000002")
    default_me_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    default_system_cost_index: Mapped[float] = mapped_column(Float, nullable=False, default=0.05)
    default_facility_tax: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    default_scc_surcharge: Mapped[float] = mapped_column(Float, nullable=False, default=0.015)
    default_broker_fee_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.03)
    default_sales_tax_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.08)
    default_price_source: Mapped[str] = mapped_column(String(8), nullable=False, default="sell")
    default_freight_cost_per_m3:   Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    default_structure_me_bonus:    Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    default_structure_te_bonus:    Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
