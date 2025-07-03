"""
スレッド管理機能（アーカイブ延長、スタッフ追加など）
"""

import asyncio
import logging
from datetime import datetime, timedelta

import discord

from .thread_config import ThreadKeeperConfig
from .notify_role import NotifySettingManager
from .thread_channels import ChannelDataManager
from .reminder_exclusions import ReminderExclusionManager


class ThreadManager:
    """スレッド管理機能を提供するクラス"""

    def __init__(self, bot, logger: logging.Logger):
        self.bot = bot
        self.logger = logger
        self.config = ThreadKeeperConfig()

        # マネージャークラス
        self.channel_data_manager = ChannelDataManager()
        self.notify_role = NotifySettingManager()
        self.reminder_exclusions = ReminderExclusionManager()

    async def _should_exclude_from_reminder(self, thread: discord.Thread) -> bool:
        """2週間リマインドから除外すべきかどうかを確認"""
        guild_id = thread.guild.id

        # フォーラムチャンネルは除外
        if isinstance(thread.parent, discord.ForumChannel):
            return True

        # 対象サーバーのチェック（空の場合は全サーバーが対象）
        if (
            self.config.REMINDER_TARGET_GUILD_IDS
            and guild_id not in self.config.REMINDER_TARGET_GUILD_IDS
        ):
            return True

        # DBから除外設定をチェック
        parent_id = thread.parent.id if thread.parent else None
        if await self.reminder_exclusions.is_excluded(thread.id, guild_id, parent_id):
            return True

        return False

    async def _build_role_mentions(self, guild: discord.Guild) -> str:
        """ロールメンション文字列を構築"""
        role_ids = await self.notify_role.return_notified(guild.id)
        if role_ids is None:
            return ""

        mentions = []
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if role is not None:
                mentions.append(role.mention)

        return " ".join(mentions)

    async def _handle_maintenance_error(self, thread: discord.Thread, operation: str):
        """保守エラー時の共通処理"""
        self.logger.error(f"Forbidden @ {operation} @{thread.id} stop maintenance")
        await self.channel_data_manager.set_maintenance_channel(
            channel_id=thread.id, guild_id=thread.guild.id, tf=False
        )

    async def extend_archive_duration(self, thread: discord.Thread):
        """スレッドのアーカイブ時間を延長する

        一時的に短い時間を設定してから1週間に戻すことで、
        サイレントにアーカイブ時間を延長する
        """
        try:
            # type: ignore を使用して型エラーを回避
            await thread.edit(auto_archive_duration=self.config.TMP_ARCHIVE_DURATION)  # type: ignore
        except (discord.Forbidden, discord.HTTPException, Exception):
            await self._handle_maintenance_error(thread, "extend_archive_duration")
            return

        await asyncio.sleep(self.config.ARCHIVE_EXTENSION_SLEEP_SECONDS)

        if thread.archived:
            return

        try:
            # type: ignore を使用して型エラーを回避
            await thread.edit(auto_archive_duration=self.config.FINAL_ARCHIVE_DURATION)  # type: ignore
        except (discord.Forbidden, discord.HTTPException, Exception):
            await self._handle_maintenance_error(thread, "extend_archive_duration")

    async def add_staff_to_thread(self, thread: discord.Thread):
        """スレッドにスタッフロールを追加する"""
        role_mentions = await self._build_role_mentions(thread.guild)
        if not role_mentions:
            return

        # メッセージ内容を決定
        if isinstance(thread.parent, discord.TextChannel):
            content = "スレッドが作成されました"
        elif isinstance(thread.parent, discord.ForumChannel):
            content = "フォーラムチャンネルが作成されました"
        else:
            return

        try:
            msg = await thread.send(content)
            await msg.edit(content=f"{role_mentions} {content}")
        except discord.Forbidden:
            self.logger.error(f"Cannot add staff to thread {thread.id}")

    def return_estimated_archive_time(self, thread: discord.Thread) -> datetime:
        """スレッドの推定アーカイブ時間を計算"""
        return thread.archive_timestamp + timedelta(
            minutes=thread.auto_archive_duration
        )

    async def get_last_human_message_time(
        self, thread: discord.Thread
    ) -> datetime | None:
        """スレッドの最後の人間のメッセージ時刻を取得

        まずlast_messageを確認し、それが人間のメッセージでなければ
        履歴を検索する（効率化のため）
        """
        try:
            # まずlast_messageをチェック
            if thread.last_message is not None and not thread.last_message.author.bot:
                return thread.last_message.created_at

            # last_messageがbotの場合はhistoryを確認
            async for message in thread.history(limit=50):
                if not message.author.bot:
                    return message.created_at

        except discord.Forbidden:
            self.logger.error(f"Cannot access message history for thread {thread.id}")
        except Exception as e:
            self.logger.error(
                f"Error getting message history for thread {thread.id}: {e}"
            )

        return None

    async def send_inactivity_reminder(self, thread: discord.Thread):
        """非アクティブスレッドにリマインダーを送信"""
        try:
            # スレッドのリマインダー期間を取得
            exclusion = await self.reminder_exclusions.get_exclusion(
                thread.id, thread.guild.id
            )
            reminder_weeks = (
                exclusion.reminder_weeks if exclusion else self.config.REMINDER_WEEKS
            )

            role_mentions = await self._build_role_mentions(thread.guild)
            message_parts = []

            if role_mentions:
                message_parts.append(role_mentions)

            message_parts.append(
                f"⚠️ このスレッドは{reminder_weeks}週間以上新しい書き込みがありません。\n"
                "まだ活動中の場合は何か書き込みをお願いします。"
            )

            await thread.send("\n".join(message_parts))
            self.logger.info(
                f"Sent inactivity reminder to thread {thread.name} in {thread.guild.name}"
            )

        except discord.Forbidden:
            self.logger.error(
                f"Cannot send reminder to thread {thread.id} in {thread.guild.name}"
            )
        except Exception as e:
            self.logger.error(f"Error sending reminder to thread {thread.id}: {e}")

    async def process_closed_thread_reopening(self, message: discord.Message):
        """CLOSEDプレフィックス付きスレッドの再開処理"""
        thread = message.channel
        if not isinstance(thread, discord.Thread):
            return

        try:
            await thread.edit(archived=False)
            await thread.edit(
                name=thread.name.replace(self.config.CLOSED_THREAD_PREFIX, "")
            )

            # DBに保守対象として登録
            if message.guild is not None:
                if not await self.channel_data_manager.is_maintenance_channel(
                    thread.id, guild_id=message.guild.id
                ):
                    archive_time = self.return_estimated_archive_time(thread)
                    await self.channel_data_manager.resister_channel(
                        channel_id=thread.id,
                        guild_id=message.guild.id,
                        archive_time=archive_time,
                    )
                    self.logger.info(
                        f"Re-registered thread {thread.name} for maintenance after reopening"
                    )
        except Exception as e:
            self.logger.error(f"Error reopening closed thread {thread.id}: {e}")

    async def read_staff_to_thread(self, threads: list[discord.Thread]) -> None:
        """既存スレッドに新スタッフを追加する"""
        if not threads:
            return

        guild = threads[0].guild
        if guild is None:
            self.logger.warning("guild is None @read_staff_to_thread")
            return

        role_mentions = await self._build_role_mentions(guild)
        if not role_mentions:
            self.logger.info("No roles configured for staff addition")
            return

        for thread in threads:
            try:
                # メッセージ内容を決定
                if isinstance(thread.parent, discord.TextChannel):
                    content = "新スタッフを既存スレッドに参加させます"
                elif isinstance(thread.parent, discord.ForumChannel):
                    content = "新スタッフを既存フォーラムチャンネルに参加させます"
                else:
                    continue

                msg = await thread.send(content)
                await msg.edit(content=f"{role_mentions} {content}")
                await asyncio.sleep(1)

            except discord.Forbidden:
                self.logger.error(f"Cannot add staff to thread {thread.id}")
            except Exception as e:
                self.logger.error(f"Error adding staff to thread {thread.id}: {e}")

    async def check_inactivity_and_remind(self, thread: discord.Thread) -> bool:
        """スレッドの非アクティブ状態をチェックしてリマインドを送信

        Returns:
            bool: リマインドを送信した場合はTrue
        """
        # 除外チェック
        if await self._should_exclude_from_reminder(thread):
            return False

        # 指定週間前の時刻を計算
        weeks_ago = discord.utils.utcnow() - timedelta(weeks=self.config.REMINDER_WEEKS)

        last_message_time = None

        # まずthread.last_messageを確認
        if isinstance(thread.last_message, discord.Message):
            last_message_time = thread.last_message.created_at
        elif thread.last_message_id:
            # thread.last_messageが使えない場合はfetch_messageを使用
            try:
                last_message = await thread.fetch_message(thread.last_message_id)
                last_message_time = last_message.created_at
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                self.logger.error(
                    f"Cannot fetch last message {thread.last_message_id} from thread {thread.id}: {e}"
                )
                # メッセージ取得に失敗した場合はthread.created_atを使用
                last_message_time = thread.created_at
        else:
            # last_messageもlast_message_idもない場合はthread.created_atを使用
            last_message_time = thread.created_at

        # 指定週間以上経過している場合
        if last_message_time and last_message_time < weeks_ago:
            await self.send_inactivity_reminder(thread)
            return True

        return False
