from datetime import datetime
from sqlalchemy import Integer, BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    character_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("characters.character_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
