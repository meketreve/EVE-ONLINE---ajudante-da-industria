from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,  # espera até 30s por um lock em vez de falhar imediatamente
    },
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")      # leitores não bloqueiam escritores
    cursor.execute("PRAGMA synchronous=NORMAL")    # seguro com WAL, mais rápido que FULL
    cursor.execute("PRAGMA busy_timeout=30000")    # espera até 30s por lock (30000ms)
    cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables():
    # Import all models so that Base.metadata is populated before create_all
    import app.models.user  # noqa: F401
    import app.models.character  # noqa: F401
    import app.models.item  # noqa: F401
    import app.models.blueprint  # noqa: F401
    import app.models.production_queue  # noqa: F401
    import app.models.cache  # noqa: F401
    import app.models.market_structure  # noqa: F401
    import app.models.market_snapshot  # noqa: F401
    import app.models.user_settings  # noqa: F401
    import app.models.reprocessing  # noqa: F401
    import app.models.manufacturing_structure  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Migrations: adiciona colunas novas sem destruir dados existentes.
    # SQLite não suporta IF NOT EXISTS em ALTER TABLE — usa try/except por coluna.
    from sqlalchemy import text
    _migrations = [
        "ALTER TABLE market_price_cache ADD COLUMN total_volume INTEGER",
        "ALTER TABLE user_settings ADD COLUMN default_freight_cost_per_m3 REAL DEFAULT 0.0",
        "ALTER TABLE items ADD COLUMN portion_size INTEGER DEFAULT 1",
        "ALTER TABLE user_settings ADD COLUMN default_structure_me_bonus REAL DEFAULT 0.0",
        "ALTER TABLE user_settings ADD COLUMN default_structure_te_bonus REAL DEFAULT 0.0",
    ]
    for sql in _migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sql))
        except Exception:
            pass  # coluna já existe — ignora
