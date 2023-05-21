# !/usr/bin/env python3

import asyncio
import pathlib
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

import discord
from sqlalchemy import delete, exc, insert, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import Column
from sqlalchemy.types import (VARCHAR, BigInteger, Boolean, DateTime, Integer,
                              String)

try:
    from .db import engine
except ImportError:
    from db import engine

Base = declarative_base()


@dataclass
class NotifyRole:
    guild_id: int
    id: int


class NotifyRoleDB(Base):
    __tablename__ = 'notify_setting'
    guild_id = Column(BigInteger, primary_key=True, nullable=False)
    id = Column(BigInteger, primary_key=True, nullable=False)


class NotifySettingManager():
    def __init__(self) -> None:
        pass

    async def create_table(self) -> None:
        """テーブルを作成する関数
        """
        async with engine.begin() as conn:
            await conn.run_sync(NotifyRoleDB.metadata.create_all)

    @staticmethod
    def return_dataclass(data: List[NotifyRoleDB]) -> NotifyRole:

        db_data = data[0]
        processed_data = NotifyRole(
            guild_id=db_data.guild_id,
            id=db_data.id
        )

        return processed_data

    @staticmethod
    def return_DBClass(data: NotifyRole) -> NotifyRoleDB:
        db_data = data
        processed_data = NotifyRoleDB(
            guild_id=db_data.guild_id,
            id=db_data.id
        )

        return processed_data

    async def resister_notify(self, guild_id: int, role_ids: List[int]) -> None:
        """通知対象を追加する関数

        Args:
            guild_id (int): サーバーのID
            bot_role_id (int): 役職のID
        """

        async with AsyncSession(engine) as session:
            async with session.begin():
                for id in role_ids:
                    stmt = insert(NotifyRoleDB).values(
                        guild_id=guild_id, id=id)
                    do_nothing_stmt = stmt.on_conflict_do_nothing(
                        index_elements=['guild_id', 'id'])
                    await session.execute(do_nothing_stmt)

    async def delete_notify(self, guild_id: int) -> None:
        """通知対象を削除する関数

        Args:
            guild_id (int): サーバーのID
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = delete(NotifyRoleDB).where(
                    NotifyRoleDB.guild_id == guild_id)
                await session.execute(stmt)

    async def return_notified(self, guild_id: int) -> Optional[List[int]]:
        """通知対象を取得する関数

        Args:
            guild_id (int): サーバーのID

        Returns:
            Optional[List[int]]: リスト
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = select(NotifyRoleDB).where(
                    NotifyRoleDB.guild_id == guild_id)
                result = await session.execute(stmt)
                result = result.fetchall()
                result = [self.return_dataclass(
                    result).id for result in result]

                if len(result) == 0:
                    return None
                else:
                    return result


if __name__ == "__main__":
    setting_mng = NotifySettingManager()
    result = asyncio.run(
        setting_mng.return_notified(
            guild_id=609058923353341973))

    print((result))
