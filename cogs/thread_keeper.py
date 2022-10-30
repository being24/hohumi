import asyncio
import logging
from datetime import datetime, timedelta
from typing import List

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .utils.common import CommonUtil
from .utils.guild_setting import GuildSettingManager
from .utils.notify_role import NotifySettingManager
from .utils.thread_channels import ChannelData, ChannelDataManager

MY_GUILD = discord.Object(id=609058923353341973)


class Hofumi(commands.Cog, name="Thread管理用cog"):
    """
    管理用のコマンドです
    """

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.c = CommonUtil()

        self.guild_setting_mng = GuildSettingManager()
        self.channel_data_manager = ChannelDataManager()
        self.notify_role = NotifySettingManager()

        self.logger = logging.getLogger("discord")

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

    # @commands.Cog.listener()
    # async def on_message(self, message: discord.Message):
    #     print(message.content)

    @app_commands.command()
    async def hello(self, interaction: discord.Interaction):
        """Says hello!"""
        await interaction.response.send_message(f"Hi, {interaction.user.mention}")

    async def extend_archive_duration(self, thread: discord.Thread):
        """チャンネルのArchive時間を延長する関数
            今指定されている時間以外の時間を指定して、その後に1wにすることでサイレントに延長する

        Args:
            thread (discord.Thread): 対象のスレッド
        """

        tmp_archive_duration = 60

        await thread.edit(auto_archive_duration=tmp_archive_duration)
        await asyncio.sleep(10)

        if thread.archived:
            return

        try:
            await thread.edit(auto_archive_duration=10080)
        except discord.Forbidden:
            self.logger.error("Forbidden @ extend_archive_duration")
        except discord.HTTPException:
            self.logger.error("HTTPException @ extend_archive_duration")
        except BaseException:
            self.logger.error("BaseException @ extend_archive_duration")

    async def add_staff_to_thread(self, thread: discord.Thread):
        """スレッドにスタッフを追加する関数

        Args:
            thread (discord.Thread): 対象のスレッド
        """

        role_ids = await self.notify_role.return_notified(thread.guild.id)
        if role_ids is None:
            return

        content = ""

        for id in role_ids:
            role = thread.guild.get_role(id)
            if role is not None:
                content = f"{content}{role.mention}"

        if isinstance(thread.parent, discord.TextChannel):
            msg = await thread.send("スレッドが作成されました")
        elif isinstance(thread.parent, discord.ForumChannel):
            msg = await thread.send("フォーラムチャンネルが作成されました")
        else:
            return

        await msg.edit(content=f"{content} {msg.content}")

    async def read_staff_to_thread(self, threads: List[discord.Thread]) -> None:
        """スレッドに新スタッフを追加する関数

        Args:
            threads (List[discord.Thread]): 対象のスレッドのリスト

        """
        if len(threads) == 0:
            return

        guild = threads[0].guild
        if guild is None:
            self.logger.warning("guild is None @readd_staff_to_thread")
            return

        role_ids = await self.notify_role.return_notified(guild.id)
        if role_ids is None:
            self.logger.info("function return due to role_ids is None @readd_staff_to_thread")
            return

        content = ""
        for id in role_ids:
            role = guild.get_role(id)
            if role is not None:
                content = f"{content}{role.mention}"

        for thread in threads:
            if isinstance(thread.parent, discord.TextChannel):
                msg = await thread.send("新スタッフを既存スレッドに参加させます")
            elif isinstance(thread.parent, discord.ForumChannel):
                msg = await thread.send("新スタッフを既存フォーラムチャンネルに参加させます")
            else:
                return

            await msg.edit(content=f"{content} {msg.content}")
            await asyncio.sleep(1)

    def return_estimated_archive_time(self, thread: discord.Thread) -> datetime:
        """スレッドのArchive時間を返す関数

        Args:
            thread (discord.Thread): スレッド

        Returns:
            datetime: 推測されるArchive時間
        """
        archive_time = thread.archive_timestamp + timedelta(minutes=thread.auto_archive_duration)
        return archive_time

    @app_commands.command(name="maintenance_this_thread", description="このスレッドを保守対象に設定します")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def maintenance_this_thread(self, interaction: discord.Interaction, tf: bool = True):
        """スレッドを保守かどうかを設定するコマンド"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("このコマンドはスレッドチャンネル専用です")
            msg = await interaction.original_response()
            await self.c.delete_after(msg)
            return

        if interaction.guild is None:
            self.logger.warning("guild is None @resister_notify")
            return

        if tf:
            # 管理対象であるかのチェック
            if await self.channel_data_manager.is_maintenance_channel(
                interaction.channel.id, guild_id=interaction.guild.id
            ):
                await interaction.response.send_message(f"{interaction.channel.name}は管理対象です")
                msg = await interaction.original_response()
                await self.c.delete_after(msg)

            else:  # 対象でなければ、upsert
                archive_time = self.return_estimated_archive_time(interaction.channel)
                await self.channel_data_manager.resister_channel(
                    channel_id=interaction.channel.id, guild_id=interaction.guild.id, archive_time=archive_time
                )
                await interaction.response.send_message(f"{interaction.channel.name}を管理対象に設定しました")

        else:
            # 管理対象であるかのチェック
            if not await self.channel_data_manager.is_maintenance_channel(
                interaction.channel.id, guild_id=interaction.guild.id
            ):
                await interaction.response.send_message(f"{interaction.channel.name}は管理対象ではありません")
                msg = await interaction.original_response()
                await self.c.delete_after(msg)
                return

            else:
                await self.channel_data_manager.set_maintenance_channel(
                    channel_id=interaction.channel.id, guild_id=interaction.guild.id, tf=False
                )
                await interaction.response.send_message(f"{interaction.channel.name}を管理対象から外しました")
                msg = await interaction.original_response()
                await self.c.delete_after(msg)

    @app_commands.command(name="full_maintenance", description="このサーバーに今後作成されるスレッドを保守します")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def full_maintenance(self, interaction: discord.Interaction, tf: bool = True):
        """このサーバーの新規作成されるスレッドを保守するようにするコマンド"""
        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("このコマンドはサーバーチャンネル専用です")
            msg = await interaction.original_response()
            await self.c.delete_after(msg)
            return

        if interaction.guild is None:
            self.logger.warning("guild is None @resister_notify")
            return
        # DBの設定を書き換える
        await self.guild_setting_mng.set_full_maintenance(interaction.guild.id, tf)

        if tf:
            string = "有効"
        else:
            string = "無効"

        await interaction.response.send_message(f"{interaction.guild.name}の全スレッドの保守を{string}に設定しました")

    @commands.command(name="resister_notify", description="スレッドに自動参加するroleを登録します")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def resister_notify(self, ctx: commands.Context, *bot_role: discord.Role):
        """スレッド作成時に自動参加するbot_roleを設定するコマンド"""

        # 可変長引数に対応したらスラコマ化を考える

        role_ids = [role.id for role in bot_role]
        role_mentions = [role.mention for role in bot_role]
        role_mentions = ",".join(role_mentions)

        if ctx.guild is None:
            self.logger.warning("guild is None @resister_notify")
            return

        await self.notify_role.resister_notify(ctx.guild.id, role_ids)
        await ctx.reply(
            f"{ctx.guild}の新規作成スレッドには今後 {role_mentions} が自動参加します",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name="remove_notify", description="スレッドに自動参加する役職を全削除するコマンド")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def remove_notify(self, ctx: commands.Context):
        if ctx.guild is None:
            self.logger.warning("guild is None @resister_notify")
            return

        await self.notify_role.delete_notify(ctx.guild.id)
        await ctx.reply(f"{ctx.guild}の新規作成スレッドには今後自動参加を行いません", mention_author=False)

    @app_commands.command(name="guild_thread_keep_status", description="サーバーのスレッドの設定を確認します")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def guild_thread_keep_status(self, interaction: discord.Interaction):
        """サーバーのスレッドの設定を確認するコマンド"""

        if interaction.guild is None:
            self.logger.warning("guild is None @thread_keep_status")
            return

        guild_setting = await self.guild_setting_mng.get_guild_setting(interaction.guild.id)
        if guild_setting is None:
            await interaction.response.send_message("サーバー設定がありません")
            # msg = await interaction.original_response()
            # await self.c.delete_after(msg)
        else:
            await interaction.response.send_message(f"保守の設定は{guild_setting.keep_all}です")

        channel_data = await self.channel_data_manager.get_data_guild(guild_id=interaction.guild.id)
        if channel_data is None:
            await interaction.followup.send("現在保守しているスレッドはありません")
            # msg = await interaction.original_response()
            # await self.c.delete_after(msg)
            return
        else:
            await interaction.followup.send(f"現在DB上では{len(channel_data)}スレッドを保守しています")

        notify_settings = await self.notify_role.return_notified(interaction.guild.id)
        if notify_settings is None:
            await interaction.followup.send("自動参加を設定していません")
            # msg = await interaction.original_response()
            # await self.c.delete_after(msg)
        else:
            roles = [interaction.guild.get_role(role_id) for role_id in notify_settings]

            role_mentions = [role.mention for role in roles if role is not None]
            role_mentions = ",".join(role_mentions)
            await interaction.followup.send(f"自動参加を設定している役職は{role_mentions}です")

    @app_commands.command(name="thread_status", description="このスレッドの保守設定を確認します")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def thread_status(self, interaction: discord.Interaction):
        """スレッドの設定を確認するコマンド"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("このコマンドはスレッドチャンネル専用です")
            msg = await interaction.original_response()
            await self.c.delete_after(msg)
            return

        if interaction.guild is None:
            self.logger.warning("guild is None @thread_status")
            return

        result = await self.channel_data_manager.is_maintenance_channel(
            channel_id=interaction.channel.id, guild_id=interaction.guild.id
        )
        if result:
            await interaction.response.send_message(f"{interaction.channel.name}は管理対象です")
        else:
            await interaction.response.send_message(f"{interaction.channel.name}は管理対象外です")

    @app_commands.command(name="join_new_staff", description="新しいスタッフを既存のスレッドに追加します")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def join_new_staff_to_exist_thread(self, interaction: discord.Interaction):
        """既存スレッドに新規スタッフを参加させるコマンド"""
        if interaction.guild is None:
            self.logger.warning("guild is None @join_new_staff_to_exist_thread")
            return

        active_threads = await interaction.guild.active_threads()

        if len(active_threads) == 0:
            await interaction.response.send_message("スレッドがありません")
            return

        notify_settings = await self.notify_role.return_notified(interaction.guild.id)
        if notify_settings is None:
            await interaction.response.send_message("自動参加を設定していません")
            return

        await interaction.response.send_message("新スタッフの追加を開始します")
        await self.read_staff_to_thread(active_threads)
        await interaction.followup.send("新スタッフの追加を終了しました")

    @app_commands.command(name="list_unkept_threads", description="保守していないスレッドの数を表示します")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def list_active_threads(self, interaction: discord.Interaction):
        """管理対象になっていないスレッドの数を表示するコマンド"""

        if interaction.guild is None:
            self.logger.warning("guild is None @list_active_threads")
            return

        threads = await interaction.guild.active_threads()
        not_maintained_threads = []
        for thread in threads:
            if not await self.channel_data_manager.is_maintenance_channel(thread.id, guild_id=interaction.guild.id):
                not_maintained_threads.append(thread)

        await interaction.response.send_message(f"{len(not_maintained_threads)}スレッドが非管理対象です")
        # not_maintained_threadsが0じゃなくて10以下ならメッセージを送る
        if len(not_maintained_threads) == 0:
            pass
        elif 0 < len(not_maintained_threads) <= 10:
            for thread in not_maintained_threads:
                await interaction.followup.send(f"{thread.name} {thread.id}")
        # 多すぎたら省略する旨を送る
        else:
            await interaction.followup.send("10以上であるため省略します")

    @app_commands.command(name="maintain_all_threads", description="このサーバーの全てのスレッドを保守します")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def maintain_all_threads(self, interaction: discord.Interaction):
        """このサーバーのすべてのスレッドを管理対象にするコマンド"""
        if interaction.guild is None:
            self.logger.warning("guild is None @maintain_all_threads")
            return

        if interaction.channel is None:
            self.logger.warning("channel is None @maintain_all_threads")
            return

        threads = await interaction.guild.active_threads()
        not_maintained_threads = []
        for thread in threads:
            if not await self.channel_data_manager.is_maintenance_channel(thread.id, guild_id=interaction.guild.id):
                not_maintained_threads.append(thread)
                self.logger.error(f"{thread.name} not in database @ maintain_all_threads")

        for thread in not_maintained_threads:
            archive_time = self.return_estimated_archive_time(thread)
            await self.channel_data_manager.resister_channel(
                channel_id=thread.id, guild_id=interaction.guild.id, archive_time=archive_time
            )

        await interaction.response.send_message(f"{len(not_maintained_threads)}スレッドを管理対象に設定しました")

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        await thread.join()

        # OPとbotを呼ぶ処理
        await self.add_staff_to_thread(thread)

        # DBの設定を確認、管理対象としてDBに入れる
        if await self.guild_setting_mng.is_full_maintenance(thread.guild.id):
            archive_time = self.return_estimated_archive_time(thread)
            await self.channel_data_manager.resister_channel(
                channel_id=thread.id, guild_id=thread.guild.id, archive_time=archive_time
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

    # todo:せんぶ変える的なコマンドを作る
    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        # closeされたときに復活させるか？
        # 権限がないのであればスルーする
        if not after.permissions_for(after.guild.me).manage_threads:
            self.logger.error(f"no permission to manage thread {after.name} of {after.guild.name} @ on_thread_update")
            return

        # 監視対象であるか？
        if await self.channel_data_manager.is_maintenance_channel(channel_id=after.id, guild_id=after.guild.id):
            if after.locked != before.locked:
                await self.channel_data_manager.set_maintenance_channel(
                    channel_id=after.id, guild_id=after.guild.id, tf=not after.archived
                )

            # アーカイブされたらkeepをfalseに、解除されたらkeepをtrueにする
            if after.archived != before.archived:
                await self.channel_data_manager.set_maintenance_channel(
                    channel_id=after.id, guild_id=after.guild.id, tf=not after.archived
                )
            # アーカイブ時間の設定変更時にDBも書き換える
            if after.archive_timestamp != before.archive_timestamp:
                self.return_estimated_archive_time(after)
                archive_time = self.return_estimated_archive_time(after)
                await self.channel_data_manager.update_archived_time(
                    channel_id=after.id, guild_id=after.guild.id, archive_time=archive_time
                )

        if before.name != after.name:
            try:
                if isinstance(before.parent, discord.TextChannel):
                    thread_kinds_name = "スレッド"
                else:
                    thread_kinds_name = "フォーラム"
                await after.send(f"この{thread_kinds_name}チャンネル名が変更されました。\n{before.name}→{after.name}")
            except discord.Forbidden:
                self.logger.error(f"Forbidden {after.name} of {after.guild.name} @rename notify")

        if after.parent is None:
            return

        # ロックされたとき
        if before.locked != after.locked:
            if isinstance(after.parent, discord.TextChannel):
                message = f"{after.name}は{'ロック' if after.locked else 'ロックが解除'}されました。"
                try:
                    await after.parent.send(message)
                except discord.Forbidden:
                    self.logger.error(f"Forbidden {after.name} of {after.guild.name} @lock notify")
            return

        # アーカイブ状態に変化があった
        if before.archived != after.archived:
            # ForumChannelであるなら何もしない
            if isinstance(after.parent, discord.ForumChannel):
                return
            # アーカイブ通知を送る
            log = None
            try:
                logs = [
                    entry
                    async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.thread_update)
                ]
                log = logs[0]
            except discord.Forbidden:
                pass

            if log is not None:
                if discord.utils.utcnow() - log.created_at > timedelta(minutes=5):
                    log = None

            if log is None:
                message = f"{after.name}は{'アーカイブ' if after.archived else 'アーカイブが解除'}されました。"
            else:
                message = f"{log.user}によって{after.name}は{'アーカイブ' if after.archived else 'アーカイブが解除'}されました。"

            # logとlog.userとself.bot.userがNoneならreturn

            if log is None:
                return

            if log.user is None:
                return

            if self.bot.user is None:
                return

            try:
                await after.parent.send(message)
            except discord.Forbidden:
                self.logger.error(f"Forbidden {after.name} of {after.guild.name} @archive notify")

            # # アーカイブされた
            # if before.archived is False:
            #     # ロックされていない
            #     if after.locked is False:
            #         # ロックする
            #         await after.edit(archived=False)
            #         await after.edit(archived=True, locked=True)

        # TODO: 解決がついたらアーカイブする
        # if isinstance(after.parent, discord.ForumChannel):
        #     if after.applied_tags != before.applied_tags:
        #         if set(after.applied_tags) - set(before.applied_tags) :
        #         # 未解決がついた
        #             if "未解決" not in before.applied_tags:
        #                 if "未解決" in after.applied_tags:
        #                     try:
        #                         await after.send("このフォーラムに未解決がつきました。")
        #                     except discord.Forbidden:
        #                         self.logger.error(f"Forbidden {after.name} of {after.guild.name} @unsolved notify")

        #         # 未解決が外された
        #         if "未解決" in after.parent.available_tags:
        #             if "未解決" in before.applied_tags:
        #                 if "未解決" not in after.applied_tags:
        #                     try:
        #                         await after.send("このフォーラムに未解決が外されました。")
        #                     except discord.Forbidden:
        #                         self.logger.error(f"Forbidden {after.name} of {after.guild.name} @unsolved notify")

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        # 削除されたらDBから削除する
        if await self.channel_data_manager.is_exists(channel_id=thread.id, guild_id=thread.guild.id):
            self.logger.info(f"delete {thread.name} of {thread.guild.name} from DB")
            await self.channel_data_manager.delete_channel(channel_id=thread.id, guild_id=thread.guild.id)

    # スレッドにcloseって投稿されたらアーカイブする
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if isinstance(message.channel, discord.Thread):
            if message.clean_content.lower() != "close":
                return

            await message.channel.edit(name=f"[CLOSED]{message.channel.name}", archived=True)

        if not self.watch_dog.is_running():
            self.logger.warning("watch_dog is not running!")
            self.watch_dog.start()

    @tasks.loop(minutes=15.0)
    async def watch_dog(self):
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
                self.logger.warning(f"Thread {channel.channel_id} is not found in {guild.name}")
                await self.channel_data_manager.set_maintenance_channel(
                    channel_id=channel.channel_id, guild_id=channel.guild_id, tf=False
                )
                continue
            await self.extend_archive_duration(thread)

            await asyncio.sleep(0.5)

    @watch_dog.before_loop
    async def before_printer(self):
        print("thread waiting...")
        await self.bot.wait_until_ready()

    @watch_dog.error
    async def watch_dog_error(self, error):
        self.logger.error(f"watch_dog error: {error}")
        return


async def setup(bot):
    await bot.add_cog(Hofumi(bot))
