from sqlalchemy import Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base


class ReprocessingMaterial(Base):
    __tablename__ = "reprocessing_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    material_type_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("type_id", "material_type_id", name="uq_reproc_type_mat"),
    )
