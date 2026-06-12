from sqlalchemy.ext.asyncio import AsyncEngine

from document_digitization_ai.db.base import Base


async def create_database_schema(engine: AsyncEngine) -> None:
    import document_digitization_ai.db.models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
