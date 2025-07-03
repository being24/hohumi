"""
リマインド除外設定管理
"""

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy.schema import Column
from sqlalchemy.types import BigInteger, Boolean, String

try:
    from .db import engine
except ImportError:
    from db import engine
    from thread_channels import Base


@dataclass
class ReminderExclusion:
    channel_id: int
    guild_id: int
    exclude_type: str  # 'channel' or 'thread'
    exclude_children: bool


class ReminderExclusionDB(Base):
    __tablename__ = "reminder_exclusions"
    channel_id = Column(BigInteger, primary_key=True)
    guild_id = Column(BigInteger, primary_key=True)
    exclude_type = Column(String(10), default="channel")  # 'channel' or 'thread'
    exclude_children = Column(Boolean, default=True)


class ReminderExclusionManager:
    def __init__(self) -> None:
        pass

    async def create_table(self) -> None:
        """テーブルを作成する関数"""
        async with engine.begin() as conn:
            await conn.run_sync(ReminderExclusionDB.metadata.create_all)

    @staticmethod
    def return_dataclass(data) -> ReminderExclusion:
        db_data = data[0]
        processed_data = ReminderExclusion(
            channel_id=db_data.channel_id,
            guild_id=db_data.guild_id,
            exclude_type=db_data.exclude_type,
            exclude_children=db_data.exclude_children,
        )
        return processed_data

    async def add_exclusion(
        self,
        channel_id: int,
        guild_id: int,
        exclude_type: str = "channel",
        exclude_children: bool = True,
    ) -> None:
        """除外設定を追加する関数"""
        try:
            async with AsyncSession(engine) as session:
                async with session.begin():
                    stmt = insert(ReminderExclusionDB).values(
                        channel_id=channel_id,
                        guild_id=guild_id,
                        exclude_type=exclude_type,
                        exclude_children=exclude_children,
                    )

                    do_update_stmt = stmt.on_conflict_do_update(
                        index_elements=["channel_id", "guild_id"],
                        set_=dict(
                            exclude_type=exclude_type,
                            exclude_children=exclude_children,
                        ),
                    )
                    await session.execute(do_update_stmt)
        except Exception as e:
            # ログ出力などのエラーハンドリングを追加可能
            raise e

    async def remove_exclusion(self, channel_id: int, guild_id: int) -> bool:
        """除外設定を削除する関数"""
        try:
            async with AsyncSession(engine) as session:
                async with session.begin():
                    stmt = delete(ReminderExclusionDB).where(
                        ReminderExclusionDB.channel_id == channel_id,
                        ReminderExclusionDB.guild_id == guild_id,
                    )
                    result = await session.execute(stmt)
                    return result.rowcount > 0
        except Exception as e:
            # ログ出力などのエラーハンドリングを追加可能
            raise e

    async def is_excluded(
        self, channel_id: int, guild_id: int, parent_channel_id: Optional[int] = None
    ) -> bool:
        """チャンネル/スレッドが除外されているかチェック"""
        try:
            async with AsyncSession(engine) as session:
                async with session.begin():
                    # 直接的な除外設定をチェック
                    stmt = select(ReminderExclusionDB).where(
                        ReminderExclusionDB.channel_id == channel_id,
                        ReminderExclusionDB.guild_id == guild_id,
                    )
                    result = await session.execute(stmt)
                    if result.fetchone():
                        return True

                    # 親チャンネルの除外設定をチェック（スレッドの場合）
                    if parent_channel_id:
                        stmt = select(ReminderExclusionDB).where(
                            ReminderExclusionDB.channel_id == parent_channel_id,
                            ReminderExclusionDB.guild_id == guild_id,
                            ReminderExclusionDB.exclude_children,
                        )
                        result = await session.execute(stmt)
                        if result.fetchone():
                            return True

                    return False
        except Exception:
            # エラーが発生した場合は安全側に倒して除外しない
            return False

    async def get_exclusions_by_guild(
        self, guild_id: int
    ) -> Optional[List[ReminderExclusion]]:
        """ギルドの除外設定一覧を取得"""
        try:
            async with AsyncSession(engine) as session:
                async with session.begin():
                    stmt = select(ReminderExclusionDB).where(
                        ReminderExclusionDB.guild_id == guild_id
                    )
                    result = await session.execute(stmt)
                    exclusions = result.fetchall()

                    if not exclusions:
                        return None

                    return [
                        ReminderExclusion(
                            channel_id=exc[0].channel_id,
                            guild_id=exc[0].guild_id,
                            exclude_type=exc[0].exclude_type,
                            exclude_children=exc[0].exclude_children,
                        )
                        for exc in exclusions
                    ]
        except Exception:
            # エラーが発生した場合は空のリストを返す
            return None

    async def is_channel_excluded(self, channel_id: int, guild_id: int) -> bool:
        """チャンネルが除外されているかの簡易チェック"""
        return await self.is_excluded(channel_id, guild_id)

    async def is_thread_excluded(
        self, thread_id: int, guild_id: int, parent_channel_id: int
    ) -> bool:
        """スレッドが除外されているかの簡易チェック"""
        return await self.is_excluded(thread_id, guild_id, parent_channel_id)
