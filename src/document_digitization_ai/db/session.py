from collections.abc import Callable
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_async_engine_from_url(
    database_url: str,
    *,
    echo: bool = False,
) -> AsyncEngine:
    _ensure_sqlite_parent_dir(database_url)
    return create_async_engine(database_url, echo=echo)


def create_async_session_factory(
    engine: AsyncEngine,
) -> Callable[[], AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return
    if url.database is None or url.database in {"", ":memory:"}:
        return
    if url.database.startswith("file:"):
        return

    parent = Path(url.database).expanduser().parent
    if parent != Path("."):
        parent.mkdir(parents=True, exist_ok=True)
