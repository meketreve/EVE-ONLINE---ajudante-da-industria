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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
