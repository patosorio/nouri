from collections.abc import AsyncGenerator
import socket

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings


def resolve_database_url(url: str | None = None) -> str:
    """Rewrite Compose hostname `db` → `localhost` when running on the host.

    Inside Docker, `db` resolves on the compose network and is left unchanged.
    Host-side tools (seed, alembic, pytest, local uvicorn) need localhost:5432.
    """
    resolved = url if url is not None else settings.database_url
    if "@db:" not in resolved and "@db/" not in resolved:
        return resolved
    try:
        socket.getaddrinfo("db", 5432)
    except OSError:
        return resolved.replace("@db:", "@localhost:").replace(
            "@db/", "@localhost/"
        )
    return resolved


engine = create_async_engine(
    resolve_database_url(),
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
