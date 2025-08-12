"""
リマインド除外設定管理
"""

import json
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

Base = declarative_base()


@dataclass
class ReminderExclusion:
    channel_id: int
    guild_id: int
    exclude_type: str  # 'channel' or 'thread'
    exclude_children: bool
    reminder_weeks: int  # リマインダー期間（週単位）
    roles: Optional[list[int]] = None  # メンション対象ロールIDリスト


class ReminderExclusionDB(Base):
    __tablename__ = "reminder_exclusions"
    channel_id = Column(BigInteger, primary_key=True)
    guild_id = Column(BigInteger, primary_key=True)
    exclude_type = Column(String(10), default="channel")  # 'channel' or 'thread'
    exclude_children = Column(Boolean, default=True)
    reminder_weeks = Column(BigInteger, default=4)  # デフォルトは4週間
    roles = Column(String, default="[]")  # メンション対象ロールIDリスト(JSON文字列)


class ReminderExclusionManager:
    def __init__(self) -> None:
        pass

    async def create_table(self) -> None:
        """テーブルを作成する関数"""
        async with engine.begin() as conn:
            await conn.run_sync(ReminderExclusionDB.metadata.create_all)

    @staticmethod
    def parse_roles(roles_field) -> list[int]:
        """rolesカラム(JSON文字列)をlist[int]に変換"""
        if hasattr(roles_field, "__str__") and roles_field:
            try:
                return json.loads(roles_field)
            except Exception:
                return []
        return []

    @staticmethod
    def dump_roles(roles: Optional[list[int]]) -> str:
        """rolesリストをJSON文字列に変換"""
        try:
            return json.dumps(roles) if roles is not None else "[]"
        except Exception:
            return "[]"

    def return_dataclass(self, data) -> ReminderExclusion:
        db_data = data[0]
        processed_data = ReminderExclusion(
            channel_id=db_data.channel_id,
            guild_id=db_data.guild_id,
            exclude_type=db_data.exclude_type,
            exclude_children=db_data.exclude_children,
            reminder_weeks=db_data.reminder_weeks,
            roles=self.parse_roles(getattr(db_data, "roles", None)),
        )
        return processed_data

    async def add_exclusion(
        self,
        channel_id: int,
        guild_id: int,
        exclude_type: str = "channel",
        reminder_weeks: int = 4,
        exclude_children: bool = True,
        roles: Optional[list[int]] = None,
    ) -> None:
        """除外設定を追加する関数"""
        try:
            async with AsyncSession(engine) as session:
                async with session.begin():
                    stmt = insert(ReminderExclusionDB).values(
                        channel_id=channel_id,
                        guild_id=guild_id,
                        exclude_type=exclude_type,
                        reminder_weeks=reminder_weeks,
                        exclude_children=exclude_children,
                        roles=self.dump_roles(roles),
                    )

                    do_update_stmt = stmt.on_conflict_do_update(
                        index_elements=["channel_id", "guild_id"],
                        set_=dict(
                            exclude_type=exclude_type,
                            reminder_weeks=reminder_weeks,
                            exclude_children=exclude_children,
                            roles=self.dump_roles(roles),
                        ),
                    )
                    await session.execute(do_update_stmt)
        except Exception as e:
            print(f"Error in add_exclusion: {e}")
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
                            reminder_weeks=exc[0].reminder_weeks,
                            roles=self.parse_roles(getattr(exc[0], "roles", None)),
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

    async def get_exclusion(
        self, channel_id: int, guild_id: int
    ) -> Optional[ReminderExclusion]:
        """特定の除外設定を取得"""
        try:
            async with AsyncSession(engine) as session:
                async with session.begin():
                    stmt = select(ReminderExclusionDB).where(
                        ReminderExclusionDB.channel_id == channel_id,
                        ReminderExclusionDB.guild_id == guild_id,
                    )
                    result = await session.execute(stmt)
                    exclusion = result.fetchone()

                    if not exclusion:
                        return None

                    return ReminderExclusion(
                        channel_id=exclusion[0].channel_id,
                        guild_id=exclusion[0].guild_id,
                        exclude_type=exclusion[0].exclude_type,
                        exclude_children=exclusion[0].exclude_children,
                        reminder_weeks=exclusion[0].reminder_weeks,
                        roles=self.parse_roles(getattr(exclusion[0], "roles", None)),
                    )
        except Exception as e:
            print(f"Error fetching exclusion: {e}")
            return None
