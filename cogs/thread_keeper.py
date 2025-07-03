"""
スレッド管理Cog（リファクタリング版）
"""

import asyncio
import logging
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .utils.common import CommonUtil
from .utils.guild_setting import GuildSettingManager
from .utils.notify_role import NotifySettingManager
from .utils.thread_channels import ChannelDataManager
from .utils.thread_commands import ThreadCommands
from .utils.thread_config import AutoArchiveDuration, ThreadKeeperConfig
from .utils.thread_management import ThreadManager


class ThreadKeeper(commands.Cog, name="Thread管理用cog"):
    """
    スレッド管理機能を提供するCog（リファクタリング版）
    """

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.logger = logging.getLogger("discord")
        self.config = ThreadKeeperConfig()

        # ユーティリティクラス
        self.c = CommonUtil()

        # マネージャークラスの初期化
        self.guild_setting_mng = GuildSettingManager()
        self.channel_data_manager = ChannelDataManager()
        self.notify_role = NotifySettingManager()

        # スレッド管理とコマンド処理
        self.thread_manager = ThreadManager(bot, self.logger)
        self.thread_commands = ThreadCommands(bot, self.logger)

    def _is_valid_thread_channel(self, channel) -> bool:
        """有効なスレッドチャンネルかどうかを確認"""
        return isinstance(channel, discord.Thread)

    def _is_manageable_thread(self, thread: discord.Thread) -> bool:
        """管理可能なスレッドかどうかを確認"""
        return thread.permissions_for(thread.guild.me).manage_threads

    async def setup_hook(self):
        # self.bot.tree.copy_global_to(guild=MY_GUILD)
        pass

    @commands.Cog.listener()
    async def on_ready(self):
        """on_ready時に発火する関数"""
        await self.guild_setting_mng.create_table()
        await self.channel_data_manager.create_table()
        await self.notify_role.create_table()

        for guild in self.bot.guilds:
            await self.guild_setting_mng.upsert_guild(guild)

        await self.bot.tree.sync()

        self.watch_dog.stop()
        self.watch_dog.start()

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """スレッド作成時のイベントハンドラー"""
        await thread.join()

        # OPとbotを呼ぶ処理
        await self.thread_manager.add_staff_to_thread(thread)

        # DBの設定を確認、管理対象としてDBに入れる
        if await self.guild_setting_mng.is_full_maintenance(thread.guild.id):
            archive_time = self.thread_manager.return_estimated_archive_time(thread)
            await self.channel_data_manager.resister_channel(
                channel_id=thread.id,
                guild_id=thread.guild.id,
                archive_time=archive_time,
            )

        # 低速モードを引き継ぎ
        if thread.parent is not None:
            try:
                if thread.parent.slowmode_delay != 0:
                    await thread.edit(slowmode_delay=thread.parent.slowmode_delay)
                    msg = await thread.send("低速モードを設定しました")
                    await self.c.delete_after(msg)
            except discord.Forbidden:
                self.logger.error(f"Forbidden {thread} @ extend_archive_duration")

        # フォーラムであり、タグに未解決がある場合、それをつける
        if isinstance(thread.parent, discord.ForumChannel):
            unsolved = discord.utils.get(thread.parent.available_tags, name="未解決")

            if unsolved is not None and unsolved not in thread.applied_tags:
                await thread.add_tags(unsolved)

            # 対応待ちがタグがあったらそれをつける
            waiting = discord.utils.get(thread.parent.available_tags, name="対応待ち")
            if waiting is not None and waiting not in thread.applied_tags:
                await thread.add_tags(waiting)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """メッセージ送信時のイベントハンドラー"""
        # CLOSEDプレフィックスの付いたスレッドの再開処理
        # if (isinstance(message.channel, discord.Thread) and
        #     self.config.CLOSED_THREAD_PREFIX in message.channel.name and
        #     message.author != self.bot.user):
        #     await self.thread_manager.process_closed_thread_reopening(message)

        # watch_dogタスクの監視
        if not self.watch_dog.is_running():
            self.logger.warning("watch_dog is not running!")
            self.watch_dog.start()

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        """スレッド更新時のイベントハンドラー"""
        # 権限チェック
        if not self._is_manageable_thread(after):
            self.logger.error(
                f"no permission to manage thread {after.name} of {after.guild.name} @ on_thread_update"
            )
            return

        # 監視対象スレッドの状態管理
        await self._handle_maintenance_channel_updates(before, after)

        # 名前変更の処理
        await self._handle_thread_name_change(before, after)

        if after.parent is None:
            return

        # ロック状態変更の処理
        if before.locked != after.locked:
            await self._handle_thread_lock_change(after)
            return

        # アーカイブ状態変更の処理
        if before.archived != after.archived:
            await self._handle_thread_archive_change(before, after)

    async def _handle_maintenance_channel_updates(
        self, before: discord.Thread, after: discord.Thread
    ):
        """監視対象チャンネルの状態更新を処理"""
        if not await self.channel_data_manager.is_maintenance_channel(
            channel_id=after.id, guild_id=after.guild.id
        ):
            return

        # ロック状態変更時
        if after.locked != before.locked:
            await self.channel_data_manager.set_maintenance_channel(
                channel_id=after.id, guild_id=after.guild.id, tf=not after.archived
            )

        # アーカイブ状態変更時
        if after.archived != before.archived:
            await self.channel_data_manager.set_maintenance_channel(
                channel_id=after.id, guild_id=after.guild.id, tf=not after.archived
            )

        # アーカイブ時間変更時
        if after.archive_timestamp != before.archive_timestamp:
            archive_time = self.thread_manager.return_estimated_archive_time(after)
            await self.channel_data_manager.update_archived_time(
                channel_id=after.id,
                guild_id=after.guild.id,
                archive_time=archive_time,
            )

    async def _handle_thread_name_change(
        self, before: discord.Thread, after: discord.Thread
    ):
        """スレッド名変更の処理"""
        if before.name == after.name:
            return

        try:
            # CLOSED プレフィックスの付け外しやアーカイブ状態の場合は通知しない
            if self._is_closed_prefix_change(before.name, after.name) or after.archived:
                return

            thread_kind = (
                "スレッド"
                if isinstance(before.parent, discord.TextChannel)
                else "フォーラム"
            )
            await after.send(
                f"この{thread_kind}チャンネル名が変更されました。\n{before.name}→{after.name}"
            )

        except discord.Forbidden:
            self.logger.error(
                f"Forbidden {after.name} of {after.guild.name} @rename notify"
            )

    def _is_closed_prefix_change(self, before_name: str, after_name: str) -> bool:
        """CLOSED プレフィックスの付け外しかどうかを判定"""
        prefix = self.config.CLOSED_THREAD_PREFIX
        return (prefix not in before_name and prefix in after_name) or (
            prefix in before_name and prefix not in after_name
        )

    async def _handle_thread_lock_change(self, thread: discord.Thread):
        """スレッドロック状態変更の処理"""
        if not isinstance(thread.parent, discord.TextChannel):
            return

        message = f"{thread.name}は{'ロック' if thread.locked else 'ロックが解除'}されました。"
        try:
            if not thread.is_private():
                await thread.parent.send(message)
        except discord.Forbidden:
            self.logger.error(
                f"Forbidden {thread.name} of {thread.guild.name} @lock notify"
            )

    async def _handle_thread_archive_change(
        self, before: discord.Thread, after: discord.Thread
    ):
        """スレッドアーカイブ状態変更の処理"""
        # フォーラムチャンネルの場合は何もしない
        if isinstance(after.parent, discord.ForumChannel):
            return

        # 監査ログを取得してアーカイブ実行者を特定
        log = await self._get_recent_thread_audit_log(after.guild)

        # 必要な値がNullの場合は処理を中断
        if not self._validate_archive_notification_requirements(log):
            return

        # 通知メッセージを送信
        message = self._build_archive_message(after.name, after.archived, log)
        await self._send_archive_notification(after, message)

        # アーカイブ解除時にCLOSEDプレフィックスを削除
        if not after.archived:
            await self._remove_closed_prefix(after)

    async def _get_recent_thread_audit_log(self, guild: discord.Guild):
        """最近のスレッド更新監査ログを取得"""
        try:
            logs = [
                entry
                async for entry in guild.audit_logs(
                    limit=1, action=discord.AuditLogAction.thread_update
                )
            ]
            log = logs[0] if logs else None

            # 5分以上古いログは無効とする
            if log and discord.utils.utcnow() - log.created_at > timedelta(minutes=5):
                log = None

            return log
        except discord.Forbidden:
            return None

    def _validate_archive_notification_requirements(self, log) -> bool:
        """アーカイブ通知の必要条件を検証"""
        return log is not None and log.user is not None and self.bot.user is not None

    def _build_archive_message(self, thread_name: str, is_archived: bool, log) -> str:
        """アーカイブ通知メッセージを構築"""
        action = "閉架" if is_archived else "閉架が解除"

        if log is None:
            return f"{thread_name}は{action}されました。"
        else:
            return f"{log.user}によって{thread_name}は{action}されました。"

    async def _send_archive_notification(self, thread: discord.Thread, message: str):
        """アーカイブ通知を送信"""
        try:
            if not thread.is_private() and isinstance(
                thread.parent, discord.TextChannel
            ):
                await thread.parent.send(message)
        except discord.Forbidden:
            self.logger.error(
                f"Forbidden {thread.name} of {thread.guild.name} @archive notify"
            )

    async def _remove_closed_prefix(self, thread: discord.Thread):
        """CLOSEDプレフィックスを削除"""
        try:
            cleaned_name = thread.name.replace("[CLOSED]", "")
            if cleaned_name != thread.name:
                await thread.edit(name=cleaned_name, archived=False)
        except discord.Forbidden:
            self.logger.error(f"Cannot remove CLOSED prefix from thread {thread.id}")

    @tasks.loop(minutes=15.0)
    async def watch_dog(self):
        """定期実行タスク：アーカイブ時間延長と非アクティブリマインド"""
        # 期限短いやつを延長する
        about_to_expire = await self.channel_data_manager.get_about_to_expire_channel()
        if about_to_expire is None:
            return

        for channel in about_to_expire:
            guild = self.bot.get_guild(channel.guild_id)
            if guild is None:
                continue
            thread = guild.get_thread(channel.channel_id)
            if thread is None:
                self.logger.warning(
                    f"Thread {channel.channel_id} is not found in {guild.name}"
                )
                await self.channel_data_manager.set_maintenance_channel(
                    channel_id=channel.channel_id, guild_id=channel.guild_id, tf=False
                )
                continue

            # アーカイブ期限延長
            await self.thread_manager.extend_archive_duration(thread)

            # 2週間リマインドチェック
            try:
                reminded = await self.thread_manager.check_inactivity_and_remind(thread)
                if reminded:
                    self.logger.info(
                        f"Sent inactivity reminder to thread {thread.name}"
                    )
            except Exception as e:
                self.logger.error(
                    f"Error checking inactivity for thread {thread.id}: {e}"
                )

            await asyncio.sleep(5)

    @watch_dog.before_loop
    async def before_printer(self):
        print("thread waiting...")
        await self.bot.wait_until_ready()

    @watch_dog.error
    async def watch_dog_error(self, error):
        self.logger.error(f"watch_dog error: {error}")
        return

    # ======== コマンド定義 ========

    @app_commands.command(
        name="maintenance_this_thread", description="このスレッドを保守対象に設定します"
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def maintenance_this_thread(
        self, interaction: discord.Interaction, tf: bool = True
    ):
        """スレッドを保守かどうかを設定するコマンド"""
        await self.thread_commands.maintenance_this_thread_command(interaction, tf)

    @app_commands.command(
        name="full_maintenance",
        description="このサーバーに今後作成されるスレッドを保守します",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def full_maintenance(self, interaction: discord.Interaction, tf: bool = True):
        """このサーバーの新規作成されるスレッドを保守するようにするコマンド"""
        await self.thread_commands.full_maintenance_command(interaction, tf)

    @commands.command(
        name="resister_notify", description="スレッドに自動参加するroleを登録します"
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def resister_notify(self, ctx: commands.Context, *bot_role: discord.Role):
        """スレッド作成時に自動参加するbot_roleを設定するコマンド"""
        await self.thread_commands.resister_notify_command(ctx, *bot_role)

    @commands.command(
        name="remove_notify",
        description="スレッドに自動参加する役職を全削除するコマンド",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def remove_notify(self, ctx: commands.Context):
        if ctx.guild is None:
            self.logger.warning("guild is None @remove_notify")
            return

        await self.notify_role.delete_notify(ctx.guild.id)
        await ctx.reply(
            f"{ctx.guild}の新規作成スレッドには今後自動参加を行いません",
            mention_author=False,
        )

    @app_commands.command(name="close", description="このスレッドを閉架します")
    @app_commands.guild_only()
    async def close(self, interaction: discord.Interaction):
        """スレッドを閉架するコマンド"""
        await self.thread_commands.close_command(interaction)

    @app_commands.command(
        name="close_after",
        description="このスレッドを指定時間後に自動閉架するよう設定します",
    )
    @app_commands.describe(duration="自動閉架までの時間")
    @app_commands.choices(
        duration=[
            app_commands.Choice(name="1時間", value=AutoArchiveDuration.ONE_HOUR),
            app_commands.Choice(name="1日", value=AutoArchiveDuration.ONE_DAY),
            app_commands.Choice(name="3日", value=AutoArchiveDuration.THREE_DAYS),
            app_commands.Choice(name="1週間", value=AutoArchiveDuration.ONE_WEEK),
        ]
    )
    @app_commands.guild_only()
    async def close_after(
        self,
        interaction: discord.Interaction,
        duration: AutoArchiveDuration = AutoArchiveDuration.ONE_DAY,
    ):
        """スレッドを指定時間後に自動閉架するよう設定するコマンド"""
        await self.thread_commands.close_after_command(interaction, duration)


async def setup(bot):
    await bot.add_cog(ThreadKeeper(bot))
