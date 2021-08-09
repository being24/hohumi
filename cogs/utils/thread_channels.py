# !/usr/bin/env python3

import asyncio
import pathlib
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import List, Optional

from discord.ext.commands.flags import F
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
class ChannelData:
    channel_id: int
    guild_id: int
    keep: bool
    archive_time: datetime


class ChannelDataDB(Base):
    __tablename__ = 'channel_setting'
    channel_id = Column(BigInteger, primary_key=True)  # channel_id
    guild_id = Column(BigInteger, primary_key=True)  # guild_id
    keep = Column(Boolean, default=True)  # keep
    archive_time = Column(DateTime, nullable=False)  # archive_time


class ChannelDataManager():
    def __init__(self) -> None:
        pass

    async def create_table(self) -> None:
        """テーブルを作成する関数
        """
        async with engine.begin() as conn:
            await conn.run_sync(ChannelDataDB.metadata.create_all)

    @staticmethod
    def return_dataclass(data: ChannelDataDB) -> ChannelData:

        db_data = data[0]
        processed_data = ChannelData(
            channel_id=db_data.channel_id,
            guild_id=db_data.guild_id,
            keep=db_data.keep,
            archive_time=db_data.archive_time
        )

        return processed_data

    @staticmethod
    def return_DBClass(data: ChannelData) -> ChannelDataDB:
        db_data = data
        processed_data = ChannelDataDB(
            channel_id=db_data.channel_id,
            guild_id=db_data.guild_id,
            keep=db_data.keep,
            archive_time=db_data.archive_time
        )

        return processed_data

    async def resister_channel(self, channel_id: int, guild_id: int, archive_time: datetime) -> None:
        """チャンネルの設定を登録する関数

        Args:
            channel_id (int): チャンネルのID
            guild_id (int): サーバーのID
            archive_time (datetime): アーカイブされる時間
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = insert(ChannelDataDB).values(
                    channel_id=channel_id, guild_id=guild_id, archive_time=archive_time)

                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=[
                        'channel_id',
                        'guild_id'],
                    set_=dict(
                        channel_id=channel_id,
                        guild_id=guild_id,
                        keep=True,
                        archive_time=archive_time))
                await session.execute(do_update_stmt)

    async def is_maintenance_channel(self, channel_id: int, guild_id: int) -> bool:
        """監視対象チャンネルかどうかを判定する関数

        Args:
            channel_id (int): チャンネルのID
            guild_id (int): サーバーのID

        Returns:
            bool: 監視対象チャンネルであればTrue、そうでなければFalse
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = select(
                    [ChannelDataDB]).where(
                    ChannelDataDB.channel_id == channel_id).where(
                    ChannelDataDB.guild_id == guild_id).where(
                    ChannelDataDB.keep)

                result = await session.execute(stmt)
                result = result.fetchone()
                if result is None:
                    return False
                else:
                    return True

    async def is_exists(self, channel_id: int, guild_id: int) -> bool:
        """チャンネルが登録されているかどうかを判定する関数

        Args:
            channel_id (int): チャンネルのID
            guild_id (int): サーバーのID

        Returns:
            bool: チャンネルが登録されていればTrue、そうでなければFalse
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = select([ChannelDataDB]).where(
                    ChannelDataDB.channel_id == channel_id).where(
                    ChannelDataDB.guild_id == guild_id)

                result = await session.execute(stmt)
                result = result.fetchone()
                if result is None:
                    return False
                else:
                    return True

    async def set_maintenance_channel(self, channel_id: int, guild_id: int, tf: bool) -> None:
        """監視対象チャンネルを無効化する関数

        Args:
            channel_id (int): チャンネルのID
            guild_id (int): サーバーのID
            tf (bool): 監視するのであればTrue、そうでなければFalse
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = update(ChannelDataDB).where(
                    ChannelDataDB.channel_id == channel_id).where(
                    ChannelDataDB.guild_id == guild_id).values(
                    keep=tf)
                await session.execute(stmt)

    async def update_archived_time(self, channel_id: int, guild_id: int, archive_time: datetime) -> None:
        """チャンネルのアーカイブ時間を更新する関数

        Args:
            channel_id (int): チャンネルのID
            guild_id (int): サーバーのID
            archive_time (datetime): アーカイブされる時間
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = update(ChannelDataDB).where(
                    ChannelDataDB.channel_id == channel_id).where(
                    ChannelDataDB.guild_id == guild_id).values(
                    archive_time=archive_time)
                await session.execute(stmt)

    async def delete_channel(self, channel_id: int, guild_id: int) -> None:
        """チャンネルを削除する関数

        Args:
            channel_id (int): チャンネルのID
            guild_id (int): サーバーのID
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = delete(ChannelDataDB).where(
                    ChannelDataDB.channel_id == channel_id).where(
                    ChannelDataDB.guild_id == guild_id)
                await session.execute(stmt)

    async def get_about_to_expire_channel(self, deltas: int = 2) -> Optional[List[ChannelData]]:
        """指定された時間以内に自動アーカイブされるチャンネルを取得する関数

        Args:
            deltas (int, optional): 指定時間. Defaults to 2.

        Returns:
            Optional[List[ChannelData]]: アーカイブされそうなチャンネルのリスト
        """
        limen_time = datetime.now() + timedelta(hours=deltas)
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = select([ChannelDataDB]).where(
                    ChannelDataDB.keep).where(
                    ChannelDataDB.archive_time < limen_time)

                result = await session.execute(stmt)
                result = result.fetchall()
                result = [self.return_dataclass(row) for row in result]
                if len(result) == 0:
                    return None
                else:
                    return result

    async def get_data_guild(self, guild_id: int) -> Optional[List[ChannelData]]:
        """指定されたサーバーのチャンネル情報をすべて取得する関数

        Args:
            guild_id (int): サーバーのID

        Returns:
            Optional[List[ChannelData]]: チャンネル情報のリスト
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = select([ChannelDataDB]).where(
                    ChannelDataDB.guild_id == guild_id)
                result = await session.execute(stmt)
                result = result.fetchall()
                result = [self.return_dataclass(row) for row in result]
                if len(result) == 0:
                    return None
                else:
                    return result

    async def get_channel_data(self, channel_id: int, guild_id: int) -> Optional[ChannelData]:
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = select([ChannelDataDB]).where(
                    ChannelDataDB.channel_id == channel_id).where(
                    ChannelDataDB.guild_id == guild_id)
                result = await session.execute(stmt)
                result = result.fetchone()
                result = self.return_dataclass(result)
                if result is None:
                    return None
                else:
                    return result


if __name__ == "__main__":
    setting_mng = ChannelDataManager()
    result = asyncio.run(
        setting_mng.get_about_to_expire_channel())

    print((result))
