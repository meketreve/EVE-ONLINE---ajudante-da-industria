from sqlalchemy import Integer, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class Blueprint(Base):
    __tablename__ = "blueprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    blueprint_type_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    product_type_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    product_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    time_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # JSON list: [{"type_id": int, "quantity": int}, ...]
    materials: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class BlueprintMaterial(Base):
    __tablename__ = "blueprint_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    blueprint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("blueprints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_type_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
