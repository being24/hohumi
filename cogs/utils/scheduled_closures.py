import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy.schema import Column
from sqlalchemy.types import BigInteger, DateTime

try:
    from .db import engine
except ImportError:
    from db import engine


Base = declarative_base()


@dataclass
class ScheduledClosure:
    thread_id: int
    guild_id: int
    scheduled_close_time: datetime
    created_by: int


class ScheduledClosureDB(Base):
    __tablename__ = "scheduled_closures"
    thread_id = Column(BigInteger, primary_key=True)
    guild_id = Column(BigInteger, nullable=False)
    scheduled_close_time = Column(DateTime, nullable=False)
    created_by = Column(BigInteger, nullable=False)


class ScheduledClosureManager:
    def __init__(self) -> None:
        pass

    async def create_table(self) -> None:
        async with engine.begin() as conn:
            await conn.run_sync(ScheduledClosureDB.metadata.create_all)

    @staticmethod
    def return_dataclass(data: ScheduledClosureDB) -> ScheduledClosure:
        db_data = data[0]
        return ScheduledClosure(
            thread_id=db_data.thread_id,
            guild_id=db_data.guild_id,
            scheduled_close_time=db_data.scheduled_close_time,
            created_by=db_data.created_by,
        )

    @staticmethod
    def return_DBClass(data: ScheduledClosure) -> ScheduledClosureDB:
        return ScheduledClosureDB(
            thread_id=data.thread_id,
            guild_id=data.guild_id,
            scheduled_close_time=data.scheduled_close_time,
            created_by=data.created_by,
        )

    async def schedule_closure(
        self,
        thread_id: int,
        guild_id: int,
        scheduled_close_time: datetime,
        created_by: int,
    ) -> None:
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = insert(ScheduledClosureDB).values(
                    thread_id=thread_id,
                    guild_id=guild_id,
                    scheduled_close_time=scheduled_close_time,
                    created_by=created_by,
                )
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=["thread_id"],
                    set_=dict(
                        guild_id=guild_id,
                        scheduled_close_time=scheduled_close_time,
                        created_by=created_by,
                    ),
                )
                await session.execute(do_update_stmt)

    async def cancel_closure(self, thread_id: int) -> bool:
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = delete(ScheduledClosureDB).where(
                    ScheduledClosureDB.thread_id == thread_id
                )
                result = await session.execute(stmt)
                return result.rowcount > 0

    async def get_due_closures(self) -> Optional[List[ScheduledClosure]]:
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = select(ScheduledClosureDB).where(
                    ScheduledClosureDB.scheduled_close_time <= datetime.now()
                )
                result = await session.execute(stmt)
                result = result.fetchall()
                result = [self.return_dataclass(row) for row in result]
                if len(result) == 0:
                    return None
                else:
                    return result

    async def get_closure(self, thread_id: int) -> Optional[ScheduledClosure]:
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = select(ScheduledClosureDB).where(
                    ScheduledClosureDB.thread_id == thread_id
                )
                result = await session.execute(stmt)
                result = result.fetchone()
                if result is None:
                    return None
                return self.return_dataclass(result)
