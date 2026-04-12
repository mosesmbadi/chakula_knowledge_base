from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=settings.PG_POOL_MAX,
    pool_pre_ping=True,   # test connection health before use
    pool_recycle=1800,    # recycle connections after 30 min (before server kills them)
    # PgBouncer (transaction/statement pool mode) does not support prepared statements.
    # Disable both asyncpg's own cache and SQLAlchemy's per-connection wrapper cache.
    connect_args={"statement_cache_size": 0},
    prepared_statement_cache_size=0,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    __abstract__ = True
    __table_args__ = {'schema': 'foods_knowledgebase'}


async def get_db():
    async with async_session() as session:
        yield session
