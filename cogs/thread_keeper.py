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

        # self.watch_dog.stop()
        # self.watch_dog.start()

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
            channel (discord.Thread): 対象のスレッド
        """

        # とりあえず60mに指定する、もしも60mになっていたら1440mにする
        if thread.auto_archive_duration != 60:
            tmp_archive_duration = 60
        else:
            tmp_archive_duration = 1440

        await thread.edit(auto_archive_duration=tmp_archive_duration)
        await asyncio.sleep(10)

        if thread.archived:
            return

        try:
            await thread.edit(auto_archive_duration=1440)
        except discord.Forbidden:
            print("Forbidden")
        except discord.HTTPException:
            print("HTTPException")
        except BaseException:
            print("BaseException")

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

    async def readd_staff_to_thread(self, threads: List[discord.Thread]):

        if len(threads) == 0:
            return

        guild = threads[0].guild
        if guild is None:
            logging.warning("guild is None @readd_staff_to_thread")
            return

        role_ids = await self.notify_role.return_notified(guild.id)
        if role_ids is None:
            logging.info("function return due to role_ids is None @readd_staff_to_thread")
            return

        content = ""
        for id in role_ids:
            role = guild.get_role(id)
            if role is not None:
                content = f"{content}{role.mention}"

        for thread in threads:
            msg = await thread.send("新スタッフを既存スレッドに参加させます")
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
    async def maintenance_this_thread(self, interaction: discord.Interaction, tf: bool = True):
        """スレッドを保守かどうかを設定するコマンド"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("このコマンドはスレッドチャンネル専用です")
            msg = await interaction.original_response()
            await self.c.delete_after(msg)
            return

        if interaction.guild is None:
            logging.warning("guild is None @resister_notify")
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
            if not await self.channel_data_manager.is_maintenance_channel(interaction.channel.id, guild_id=guild.id):
                await interaction.response.send_message(f"{interaction.channel.name}は管理対象ではありません")
                msg = await interaction.original_response()
                await self.c.delete_after(msg)
                return

            else:
                await self.channel_data_manager.set_maintenance_channel(
                    channel_id=interaction.channel.id, guild_id=guild.id, tf=False
                )
                await interaction.response.send_message(f"{interaction.channel.name}を管理対象から外しました")
                msg = await interaction.original_response()
                await self.c.delete_after(msg)

    @app_commands.command(name="full_maintenance", description="このサーバーに今後作成されるスレッドを保守します")
    @app_commands.guild_only()
    async def full_maintenance(self, interaction: discord.Interaction, tf: bool = True):
        """このサーバーの新規作成されるスレッドを保守するようにするコマンド"""
        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message("このコマンドはサーバーチャンネル専用です")
            msg = await interaction.original_response()
            await self.c.delete_after(msg)
            return

        if interaction.guild is None:
            logging.warning("guild is None @resister_notify")
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
            logging.warning("guild is None @resister_notify")
            return

        await self.notify_role.resister_notify(ctx.guild.id, role_ids)
        await ctx.reply(
            f"{ctx.guild}の新規作成スレッドには今後 {role_mentions} が自動参加します",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name="remove_notify", description="スレッドに自動参加する役職を全削除するコマンド")
    @commands.has_permissions(manage_guild=True)
    async def remove_notify(self, ctx: commands.Context):
        if ctx.guild is None:
            logging.warning("guild is None @resister_notify")
            return

        await self.notify_role.delete_notify(ctx.guild.id)
        await ctx.reply(f"{ctx.guild}の新規作成スレッドには今後自動参加を行いません", mention_author=False)

    '''
    @slash_command(name='keep_status_of_guild')
    @commands.has_permissions(ban_members=True)
    async def keep_status_of_guild(self, ctx):
        """サーバーのスレッドの設定を確認するコマンド"""
        guild_setting = await self.guild_setting_mng.get_guild_setting(ctx.guild.id)
        response_txt = ''
        if guild_setting is None:
            msg = await ctx.send("サーバー設定がありません")
            await self.c.autodel_msg(msg)
        else:
            response_txt += f"全保守の設定は{guild_setting.keep_all}です\n"

        channel_data = await self.channel_data_manager.get_data_guild(
            guild_id=ctx.guild.id)
        if channel_data is None:
            msg = await ctx.send("現在保守しているチャンネルはありません")
            await self.c.autodel_msg(msg)
        else:
            response_txt += f"現在{len(channel_data)}チャンネルを保守しています\n"

        notify_settings = await self.notify_role.return_notified(ctx.guild.id)
        if notify_settings is None:
            msg = await ctx.send("自動参加を設定していません")
            await self.c.autodel_msg(msg)
        else:
            roles = [ctx.guild.get_role(role_id)
                     for role_id in notify_settings]
            role_mentions = [role.mention for role in roles]
            role_mentions = ','.join(role_mentions)
            response_txt += f"自動参加を設定している役職は{role_mentions}です"

        await ctx.respond(f"{response_txt}", allowed_mentions=discord.AllowedMentions.none())

    @slash_command(name='thread_status')
    @commands.has_permissions(ban_members=True)
    async def thread_status(self, ctx):
        """スレッドの設定を確認するコマンド"""
        if not isinstance(ctx.channel, discord.Thread):
            msg = await ctx.respond("このコマンドはスレッドチャンネル専用です")
            await self.c.autodel_msg(msg)
            return

        result = await self.channel_data_manager.is_maintenance_channel(channel_id=ctx.channel.id, guild_id=ctx.guild.id)
        if result:
            await ctx.respond(f"{ctx.channel.name}は管理対象です")
        else:
            await ctx.respond(f"{ctx.channel.name}は管理対象外です")

    @slash_command(name='join_new_staff_to_exist_thread')
    @commands.has_permissions(ban_members=True)
    async def join_new_staff_to_exist_thread(self, ctx):
        """既存スレッドに新規スタッフを参加させるコマンド"""
        active_threads = await ctx.guild.active_threads()

        await ctx.respond("新スタッフの追加を開始します")
        # len==0ならこっち側で止める
        await self.recall_of_thread(active_threads, ctx.guild.id)
        await ctx.respond("新スタッフの追加を終了しました")

    @slash_command(name='list_active_threads')
    @commands.has_permissions(ban_members=True)
    async def list_active_threads(self, ctx):
        """管理対象になっていないスレッドの数を表示するコマンド"""
        threads = await ctx.guild.active_threads()
        not_maintained_threads = []
        for thread in threads:
            if not await self.channel_data_manager.is_maintenance_channel(thread.id, guild_id=ctx.guild.id):
                not_maintained_threads.append(thread)

        await ctx.respond(f"{len(not_maintained_threads)}チャンネルが非管理対象です")

    @slash_command(name='maintain_all_threads')
    @commands.has_permissions(ban_members=True)
    async def maintain_all_threads(self, ctx):
        """このサーバーのすべてのスレッドを管理対象にするコマンド"""
        threads = await ctx.guild.active_threads()
        not_maintained_threads = []
        for thread in threads:
            if not await self.channel_data_manager.is_maintenance_channel(thread.id, guild_id=ctx.guild.id):
                not_maintained_threads.append(thread)
                print(thread.name)

        for thread in not_maintained_threads:
            archive_time = self.return_estimated_archive_time(thread)
            await self.channel_data_manager.resister_channel(channel_id=ctx.channel.id, guild_id=ctx.guild.id, archive_time=archive_time)

        await ctx.respond(f"{len(not_maintained_threads)}チャンネルを管理対象に設定しました")

    @commands.Cog.listener()
    async def on_thread_join(self, thread: discord.Thread):
        if not thread.me:
            await thread.join()
            return

        # OPとbotを呼ぶ処理
        await self.call_of_thread(thread)

        # DBの設定を確認、管理対象としてDBに入れる
        if await self.guild_setting_mng.is_full_maintainance(thread.guild.id):
            archive_time = self.return_estimated_archive_time(thread)
            await self.channel_data_manager.resister_channel(channel_id=thread.id, guild_id=thread.guild.id, archive_time=archive_time)

        # 低速モードを引き継ぎ
        if thread.parent is not None:
            try:
                if thread.parent.slowmode_delay == 0:
                    return
                await thread.edit(slowmode_delay=thread.parent.slowmode_delay)
                msg = await thread.send("低速モードを設定しました")
                await self.c.autodel_msg(msg)
            except discord.Forbidden:
                print("権限不足")
                print(thread)

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        # 権限がないのであればスルーする
        if not after.permissions_for(after.guild.me).manage_threads:
            return

        # 監視対象であるか？
        if await self.channel_data_manager.is_maintenance_channel(channel_id=after.id, guild_id=after.guild.id):
            if after.locked != before.locked:
                await self.channel_data_manager.set_maintenance_channel(channel_id=after.id, guild_id=after.guild.id, tf=not after.archived)

            # アーカイブされたらkeepをfalseに、解除されたらkeepをtrueにする
            if after.archived != before.archived:
                await self.channel_data_manager.set_maintenance_channel(channel_id=after.id, guild_id=after.guild.id, tf=not after.archived)
            # アーカイブ時間の設定変更時にDBも書き換える
            if after.archive_timestamp != before.archive_timestamp:
                self.return_estimated_archive_time(after)
                archive_time = self.return_estimated_archive_time(after)
                await self.channel_data_manager.update_archived_time(channel_id=after.id, guild_id=after.guild.id, archive_time=archive_time)

        if before.name != after.name:
            try:
                await after.send(f"このチャンネル名が変更されました。\n{before.name}→{after.name}")
            except discord.Forbidden:
                self.log_error(f"forbidden {after.name}")

        if after.parent is None:
            return

        # ロックされたとき
        if before.locked != after.locked:
            message = f"{after.name}は{'ロック' if after.locked else 'ロックが解除'}されました。"
            try:
                await after.parent.send(message)
            except discord.Forbidden:
                self.log_error(f"forbidden {after.name}")

            return

            # アーカイブ状態に変化があった
        if before.archived != after.archived:
            # アーカイブ通知を送る
            log = None
            try:
                logs = await after.guild.audit_logs(limit=1).flatten()
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

            if log is None or log.user.id != self.bot.user.id:
                try:
                    await after.parent.send(message)
                except discord.Forbidden:
                    print(message)

            # アーカイブされた
            if before.archived is False:
                # ロックされていない
                if after.locked is False:
                    # ロックする
                    await after.edit(archived=False)
                    await after.edit(archived=True, locked=True)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        # 削除されたらDBから削除する
        if await self.channel_data_manager.is_exists(channel_id=thread.id, guild_id=thread.guild.id):
            print(f'{thread.name}の情報を削除しました')
            await self.channel_data_manager.delete_channel(channel_id=thread.id, guild_id=thread.guild.id)

    # スレッドにcloseって投稿されたらアーカイブする
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if isinstance(message.channel, discord.Thread):
            if message.clean_content.lower() == 'close':
                await message.channel.edit(archived=True)

    @tasks.loop(minutes=15.0)
    async def watch_dog(self):
        # 期限短いやつを延長する
        about_to_expire = await self.channel_data_manager.get_about_to_expire_channel()
        if about_to_expire is None:
            return
        else:
            for channel in about_to_expire:
                guild = self.bot.get_guild(channel.guild_id)
                if guild is None:
                    continue
                thread = guild.get_thread(channel.channel_id)
                if thread is None:
                    self.log_unfounded_thread(channel)
                    await self.channel_data_manager.set_maintenance_channel(channel_id=channel.channel_id, guild_id=channel.guild_id, tf=False)
                else:
                    await self.extend_archive_duration(thread)

                await asyncio.sleep(0.5)

    @watch_dog.before_loop
    async def before_printer(self):
        print('thread waiting...')
        await self.bot.wait_until_ready()

    @watch_dog.error
    async def watch_dog_error(self, error):
        self.log_error(error)
        return
    '''


async def setup(bot):
    await bot.add_cog(Hofumi(bot))
