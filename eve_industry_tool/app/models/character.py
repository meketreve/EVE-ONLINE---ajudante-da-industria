from datetime import datetime
from sqlalchemy import Integer, String, DateTime, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    character_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    character_name: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    corporation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def is_token_expired(self) -> bool:
        if self.token_expiry is None:
            return True
        return datetime.utcnow() >= self.token_expiry
