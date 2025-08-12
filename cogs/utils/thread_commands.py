"""
スレッド管理コマンド群
"""

import asyncio
import logging
import re

import discord
from discord.ext import commands

from .common import CommonUtil
from .guild_setting import GuildSettingManager
from .notify_role import NotifySettingManager
from .thread_channels import ChannelDataManager
from .thread_config import AutoArchiveDuration, ThreadKeeperConfig
from .thread_management import ThreadManager


class ThreadCommands:
    """スレッド管理コマンドを提供するクラス"""

    def __init__(self, bot, logger: logging.Logger):
        self.bot = bot
        self.logger = logger
        self.config = ThreadKeeperConfig()

        # 各種マネージャー
        self.thread_manager = ThreadManager(bot, logger)
        self.c = CommonUtil()
        self.guild_setting_mng = GuildSettingManager()
        self.notify_setting = NotifySettingManager()
        self.channel_data_manager = ChannelDataManager()

    # ======== スレッド管理コマンド ========

    async def maintenance_this_thread_command(
        self, interaction: discord.Interaction, tf: bool = True
    ):
        """スレッドを保守対象に設定するコマンドの実装"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "このコマンドはスレッドチャンネル専用です"
            )
            msg = await interaction.original_response()
            await self.c.delete_after(msg)
            return

        if interaction.guild is None:
            self.logger.warning("guild is None @maintenance_this_thread")
            return

        if tf:
            # 管理対象であるかのチェック
            if await self.channel_data_manager.is_maintenance_channel(
                interaction.channel.id, guild_id=interaction.guild.id
            ):
                await interaction.response.send_message(
                    f"{interaction.channel.name}は管理対象です"
                )
                msg = await interaction.original_response()
                await self.c.delete_after(msg)

            else:  # 対象でなければ、upsert
                archive_time = self.thread_manager.return_estimated_archive_time(
                    interaction.channel
                )
                await self.channel_data_manager.resister_channel(
                    channel_id=interaction.channel.id,
                    guild_id=interaction.guild.id,
                    archive_time=archive_time,
                )
                await interaction.response.send_message(
                    f"{interaction.channel.name}を管理対象に設定しました"
                )

        else:
            # 管理対象であるかのチェック
            if not await self.channel_data_manager.is_maintenance_channel(
                interaction.channel.id, guild_id=interaction.guild.id
            ):
                await interaction.response.send_message(
                    f"{interaction.channel.name}は管理対象ではありません"
                )
                msg = await interaction.original_response()
                await self.c.delete_after(msg)
                return

            else:
                await self.channel_data_manager.set_maintenance_channel(
                    channel_id=interaction.channel.id,
                    guild_id=interaction.guild.id,
                    tf=False,
                )
                await interaction.response.send_message(
                    f"{interaction.channel.name}を管理対象から外しました"
                )
                msg = await interaction.original_response()
                await self.c.delete_after(msg)

    async def full_maintenance_command(
        self, interaction: discord.Interaction, tf: bool = True
    ):
        """このサーバーの新規作成されるスレッドを保守するようにするコマンドの実装"""
        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message(
                "このコマンドはサーバーチャンネル専用です"
            )
            msg = await interaction.original_response()
            await self.c.delete_after(msg)
            return

        if interaction.guild is None:
            self.logger.warning("guild is None @full_maintenance")
            return

        # DBの設定を書き換える
        await self.guild_setting_mng.set_full_maintenance(interaction.guild.id, tf)

        status_text = "有効" if tf else "無効"
        await interaction.response.send_message(
            f"{interaction.guild.name}の全スレッドの保守を{status_text}に設定しました"
        )

    async def resister_notify_command(self, ctx: commands.Context):
        """スレッド作成時に自動参加するbot_roleをRoleSelectで設定するコマンドの実装"""
        if ctx.guild is None:
            self.logger.warning("guild is None @resister_notify")
            return

        class RoleSelect(discord.ui.Select):
            def __init__(self, roles: list[discord.Role], view: discord.ui.View):
                options = [
                    discord.SelectOption(label=role.name, value=str(role.id))
                    for role in roles
                    if not role.is_bot_managed()
                ]
                super().__init__(
                    placeholder="自動参加させる役職を選択（複数選択可）",
                    min_values=1,
                    max_values=min(25, len(options)),
                    options=options,
                )
                # discord.ui.Selectではself.viewで親Viewにアクセスできる

            async def callback(self, interaction: discord.Interaction):
                selected_role_ids = [int(v) for v in self.values]
                guild = self.view.guild
                await self.view.thread_commands.notify_setting.resister_notify(
                    guild.id, selected_role_ids
                )
                role_mentions = [
                    guild.get_role(rid).mention
                    for rid in selected_role_ids
                    if guild.get_role(rid) is not None
                ]
                await interaction.response.edit_message(
                    content=f"自動参加させる役職: {', '.join(role_mentions)}", view=None
                )

        class RoleSelectView(discord.ui.View):
            def __init__(self, thread_commands, roles, guild, timeout=60):
                super().__init__(timeout=timeout)
                self.thread_commands = thread_commands
                self.guild = guild
                self.add_item(RoleSelect(roles, self))

        roles = [
            role
            for role in ctx.guild.roles
            if role < ctx.guild.me.top_role and not role.is_default()
        ]
        view = RoleSelectView(self, roles, ctx.guild)
        await ctx.send("自動参加させる役職を選択してください（複数選択可）", view=view)

    async def get_notified_role_command(self, ctx: commands.Context):
        """設定されているnotify_roleを確認するコマンドの実装"""
        if ctx.guild is None:
            self.logger.warning("guild is None @get_notified_role")
            return

        role_ids = await self.notify_setting.return_notified(ctx.guild.id)
        if role_ids is None:
            await ctx.send("設定されていません")
        else:
            role_mentions = []
            for role_id in role_ids:
                role = ctx.guild.get_role(role_id)
                if role is not None:
                    role_mentions.append(role.mention)

            if role_mentions:
                await ctx.send(f"設定されている役職: {', '.join(role_mentions)}")
            else:
                await ctx.send("設定されている役職が見つかりません")

    async def archive_extend_command(self, interaction: discord.Interaction):
        """スレッドのアーカイブ時間を延長するコマンドの実装"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "このコマンドはスレッドチャンネル専用です", ephemeral=True
            )
            return

        await interaction.response.defer()
        await self.thread_manager.extend_archive_duration(interaction.channel)

        estimated_time = self.thread_manager.return_estimated_archive_time(
            interaction.channel
        )
        await interaction.followup.send(
            f"アーカイブ時間を延長しました。\n推定アーカイブ時刻: {estimated_time}"
        )

    async def get_archive_time_command(self, interaction: discord.Interaction):
        """スレッドの推定アーカイブ時刻を表示するコマンドの実装"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "このコマンドはスレッドチャンネル専用です", ephemeral=True
            )
            return

        estimated_time = self.thread_manager.return_estimated_archive_time(
            interaction.channel
        )
        await interaction.response.send_message(f"推定アーカイブ時刻: {estimated_time}")

    async def check_archive_time_command(self, interaction: discord.Interaction):
        """このサーバーの管理対象スレッドのアーカイブ時刻を確認するコマンドの実装"""
        if interaction.guild is None:
            await interaction.response.send_message(
                "このコマンドはサーバー専用です", ephemeral=True
            )
            return

        await interaction.response.defer()

        # DBから管理対象チャンネルを取得
        maintenance_data = await self.channel_data_manager.get_data_guild(
            interaction.guild.id
        )

        if not maintenance_data:
            await interaction.followup.send("管理対象のスレッドはありません")
            return

        # 応答メッセージの構築
        message_parts = ["**管理対象スレッドのアーカイブ時刻:**"]

        for channel_data in maintenance_data:
            channel = interaction.guild.get_channel(channel_data.channel_id)
            if channel and isinstance(channel, discord.Thread):
                archive_time = channel_data.archive_time or "不明"
                message_parts.append(f"• {channel.name}: {archive_time}")
            else:
                message_parts.append(
                    f"• ID {channel_data.channel_id}: チャンネルが見つかりません"
                )

        message = "\n".join(message_parts)

        # メッセージが長すぎる場合は分割
        if len(message) > 2000:
            await interaction.followup.send(message[:2000])
            await interaction.followup.send(message[2000:])
        else:
            await interaction.followup.send(message)

    async def add_staff_command(self, interaction: discord.Interaction):
        """現在のスレッドにスタッフを参加させるコマンドの実装"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "このコマンドはスレッドチャンネル専用です", ephemeral=True
            )
            return

        await interaction.response.defer()
        await self.thread_manager.add_staff_to_thread(interaction.channel)
        await interaction.followup.send("スタッフを追加しました")

    async def remove_mentions_and_readd(self, thread: discord.Thread) -> None:
        """
        スレッドの最初のBotメッセージからメンションを削除し、再度同じ内容を送信して全員を参加させる
        """

        # スレッドの履歴から最初のBotメッセージを取得
        async for message in thread.history(limit=5, oldest_first=True):
            if message.author == self.bot.user:
                # メンションを除去した内容を作成
                content_wo_mentions = re.sub(
                    r"<@!?[0-9]+>|<@&[0-9]+>", "", message.content
                ).strip()

                # content_wo_mentionsにマッチしない場合
                if not content_wo_mentions:
                    continue

                # 元メッセージを編集してメンションを消す
                try:
                    await message.edit(content=content_wo_mentions)
                except Exception as e:
                    self.logger.error(f"メッセージ編集失敗: {e}")

                # DBからメンション対象のロールを取得
                role_ids = await self.notify_setting.return_notified(thread.guild.id)

                role_mentions = []
                if role_ids is None:
                    self.logger.warning(
                        f"スレッド{thread.name}の通知ロールが設定されていません"
                    )
                    return
                else:
                    for role_id in role_ids:
                        role = thread.guild.get_role(role_id)
                        if role is not None:
                            role_mentions.append(role.mention)

                if role_mentions:
                    # roleのメンションにcontent_wo_mentionsを足して送る
                    content = f"{' '.join(role_mentions)} {content_wo_mentions}"
                    await message.edit(content=content)
                break

    async def close_command(self, interaction: discord.Interaction):
        """スレッドを閉架するコマンドの実装"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "このコマンドはスレッドチャンネル専用です", ephemeral=True
            )
            return

        thread = interaction.channel
        new_name = f"{self.config.CLOSED_THREAD_PREFIX}{thread.name}"

        # 名前の長さ制限をチェック（Discordの制限は100文字）
        if len(new_name) > 100:
            # プレフィックスを短縮するか、元の名前を切り詰める
            max_original_length = 100 - len(self.config.CLOSED_THREAD_PREFIX)
            truncated_name = thread.name[:max_original_length]
            new_name = f"{self.config.CLOSED_THREAD_PREFIX}{truncated_name}"

        try:
            await interaction.response.send_message("スレッドを閉架します...")
            await asyncio.sleep(1)  # 少し待機してから閉架処理を行う
            await thread.edit(name=new_name, archived=True)

            # DB上の保守対象からも除外
            if interaction.guild is not None:
                await self.channel_data_manager.set_maintenance_channel(
                    channel_id=thread.id,
                    guild_id=interaction.guild.id,
                    tf=False,
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                "スレッドを閉架する権限がありません", ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error closing thread {thread.id}: {e}")
            await interaction.response.send_message(
                "スレッドの閉架中にエラーが発生しました", ephemeral=True
            )

    async def close_after_command(
        self, interaction: discord.Interaction, duration: AutoArchiveDuration
    ):
        """指定時間後にスレッドを閉架するコマンドの実装"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "このコマンドはスレッドチャンネル専用です", ephemeral=True
            )
            return

        thread = interaction.channel
        duration_display = AutoArchiveDuration.get_display_name(duration)

        try:
            await thread.edit(auto_archive_duration=duration.value)  # type: ignore

            # DB上の保守対象からも除外
            if interaction.guild is not None:
                await self.channel_data_manager.set_maintenance_channel(
                    channel_id=thread.id,
                    guild_id=interaction.guild.id,
                    tf=False,
                )

            await interaction.response.send_message(
                f"スレッドが{duration_display}後に自動的に閉架されるように設定しました"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "スレッドの設定を変更する権限がありません", ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error setting auto-archive for thread {thread.id}: {e}")
            await interaction.response.send_message(
                "スレッドの設定変更中にエラーが発生しました", ephemeral=True
            )
