from sqlalchemy import Integer, String, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    type_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    group_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_manufacturable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    portion_size: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1)
