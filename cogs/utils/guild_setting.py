import asyncio
import pathlib
from dataclasses import dataclass
from datetime import datetime
import re
from typing import List, Optional

import discord
from sqlalchemy import delete, exc, insert, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import Column
from sqlalchemy.types import VARCHAR, BigInteger, Boolean, DateTime, Integer, String

try:
    from .db import engine
except ImportError:
    from db import engine

Base = declarative_base()


@dataclass
class SettingData:
    guild_id: int
    guild_name: str
    keep_all: bool
    default_archive_duration: int


class GuildSettingDB(Base):
    __tablename__ = "guild_setting"
    guild_id = Column(BigInteger, primary_key=True)  # guild_id
    guild_name = Column(String)  # guild_name
    keep_all = Column(Boolean, default=True)  # 全Threadを保持するか
    default_archive_duration = Column(Integer, default=1440)  # 保持時間：24時間


class GuildSettingManager:
    def __init__(self) -> None:
        pass

    async def create_table(self) -> None:
        """テーブルを作成する関数"""
        async with engine.begin() as conn:
            await conn.run_sync(GuildSettingDB.metadata.create_all)

    @staticmethod
    def return_dataclass(data: List[GuildSettingDB]) -> SettingData:
        db_data = data[0]
        processed_data = SettingData(
            guild_id=db_data.guild_id,
            guild_name=db_data.guild_name,
            keep_all=db_data.keep_all,
            default_archive_duration=db_data.default_archive_duration,
        )

        return processed_data

    @staticmethod
    def return_DBClass(data: SettingData) -> GuildSettingDB:
        db_data = data
        processed_data = GuildSettingDB(
            guild_id=db_data.guild_id,
            guild_name=db_data.guild_name,
            keep_all=db_data.keep_all,
            default_archive_duration=db_data.default_archive_duration,
        )

        return processed_data

    async def upsert_guild(self, guild: discord.Guild) -> None:
        """ギルドをupsertする関数

        Args:
            guild_id (int): guildのid
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = insert(GuildSettingDB).values(
                    guild_id=guild.id, guild_name=guild.name
                )
                do_nothing_stmt = stmt.on_conflict_do_nothing(
                    index_elements=["guild_id"]
                )
                await session.execute(do_nothing_stmt)

    async def set_full_maintenance(self, guild_id: int, tf: bool) -> None:
        """サーバーのスレッドをすべて延命するか切り替える関数

        Args:
            guild_id (int): サーバーID
            tf (bool): スレッドを延命するかどうか
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = (
                    update(GuildSettingDB)
                    .where(GuildSettingDB.guild_id == guild_id)
                    .values(keep_all=tf)
                )
                await session.execute(stmt)

    async def is_full_maintenance(self, guild_id: int) -> bool:
        """サーバーのスレッドをすべて延命するかどうかを確認する関数

        Args:
            guild_id ([int]): サーバーID

        Returns:
            bool: するならTrue、しないならFalse
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = select(GuildSettingDB.keep_all).where(
                    GuildSettingDB.guild_id == guild_id
                )
                result = await session.execute(stmt)
                result = result.fetchone()
                result = result[0]
                return result

    async def get_guild_setting(self, guild_id: int) -> Optional[SettingData]:
        """guild_idに対応するguild_settingを取得する関数

        Args:
            guild_id (int): サーバーID

        Returns:
            Optional[SettingData]: 設定情報
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                stmt = select(GuildSettingDB).where(GuildSettingDB.guild_id == guild_id)
                result = await session.execute(stmt)
                result = result.fetchone()
                if result is None:
                    return None
                else:
                    return self.return_dataclass(result)


if __name__ == "__main__":
    setting_mng = GuildSettingManager()
    result = asyncio.run(setting_mng.get_guild_setting(guild_id=609058923353341973))

    print((result))
