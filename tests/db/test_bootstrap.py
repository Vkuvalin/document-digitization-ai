from pathlib import Path

import pytest
from sqlalchemy import inspect

from document_digitization_ai.db.bootstrap import create_database_schema
from document_digitization_ai.db.session import create_async_engine_from_url


@pytest.mark.asyncio
async def test_database_bootstrap_creates_expected_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "db" / "bootstrap.db"
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{database_path}"
    )
    try:
        await create_database_schema(engine)

        async with engine.connect() as connection:
            table_names = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
    finally:
        await engine.dispose()

    assert "document_jobs" in table_names
    assert "extraction_attempts" in table_names
    assert database_path.parent.is_dir()
