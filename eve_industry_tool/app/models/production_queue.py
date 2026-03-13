from datetime import datetime
from sqlalchemy import Integer, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class ProductionQueue(Base):
    __tablename__ = "production_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    character_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("characters.character_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_type_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending, in_progress, completed, cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
