import json
from datetime import datetime
from sqlalchemy import Float, Integer, BigInteger, String, DateTime, ForeignKey
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

    # Configuração do BOM salva no momento do cálculo
    me_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    me_overrides_json: Mapped[str] = mapped_column(String, default="{}", nullable=False)
    buy_as_is_json: Mapped[str] = mapped_column(String, default="[]", nullable=False)
    structure_me_bonus: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    manufacturing_struct_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    market_source: Mapped[str] = mapped_column(String(64), default="region:10000002", nullable=False)
    station_overrides_json: Mapped[str] = mapped_column(String, default="{}", nullable=False)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Helpers para serializar/desserializar os campos JSON
    def get_me_overrides(self) -> dict[int, int]:
        try:
            return {int(k): v for k, v in json.loads(self.me_overrides_json).items()}
        except Exception:
            return {}

    def set_me_overrides(self, d: dict[int, int]) -> None:
        self.me_overrides_json = json.dumps(d)

    def get_buy_as_is(self) -> frozenset[int]:
        try:
            return frozenset(json.loads(self.buy_as_is_json))
        except Exception:
            return frozenset()

    def set_buy_as_is(self, s: set[int]) -> None:
        self.buy_as_is_json = json.dumps(list(s))

    def get_station_overrides(self) -> dict[int, int]:
        """Retorna {type_id: structure_id} dos sub-componentes com estação própria."""
        try:
            return {int(k): int(v) for k, v in json.loads(self.station_overrides_json).items()}
        except Exception:
            return {}

    def set_station_overrides(self, d: dict[int, int]) -> None:
        self.station_overrides_json = json.dumps({str(k): v for k, v in d.items()})
