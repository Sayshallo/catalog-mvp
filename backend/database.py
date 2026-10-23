import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
db_url = os.getenv("DATABASE_URL")

if not db_url:
    raise RuntimeError("Не был задан DATABASE_URL")

engine = create_async_engine(
    db_url,
    echo = False,
    pool_pre_ping = True,
    pool_size = 10,
    max_overflow = 10
)

async_session = async_sessionmaker(
    bind = engine,
    class_ = AsyncSession,
    expire_on_commit = False
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with async_session() as session:
        yield session