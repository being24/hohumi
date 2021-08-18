# !/usr/bin/env python3

import asyncio
import logging
from datetime import datetime, timedelta

import discord
import tzlocal
from discord.ext import commands, tasks

from .utils.common import CommonUtil
from .utils.guild_setting import GuildSettingManager
from .utils.notify_role import NotifySettingManager
from .utils.thread_channels import ChannelData, ChannelDataManager


class Hofumi(commands.Cog, name='Thread管理用cog'):
    """
    管理用のコマンドです
    """

    def __init__(self, bot):
        self.bot = bot
        self.c = CommonUtil()

        self.guild_setting_mng = GuildSettingManager()
        self.channel_data_manager = ChannelDataManager()
        self.notify_role = NotifySettingManager()

        self.local_timezone = tzlocal.get_localzone()

    @commands.Cog.listener()
    async def on_ready(self):
        """on_ready時に発火する関数
        """
        await self.guild_setting_mng.create_table()
        await self.channel_data_manager.create_table()
        await self.notify_role.create_table()

        for guild in self.bot.guilds:
            await self.guild_setting_mng.upsert_guild(guild)

        self.watch_dog.stop()
        self.watch_dog.start()

    async def extend_archive_duration(self, thread: discord.Thread):
        """チャンネルのArchive時間を拡大する関数

        Args:
            channel (discord.Thread): 対象のスレッド
        """

        if thread.auto_archive_duration != 1440:  # 60想定
            await thread.edit(auto_archive_duration=1440)
            await asyncio.sleep(10)

        await thread.edit(auto_archive_duration=60)
        await asyncio.sleep(10)
        await thread.edit(auto_archive_duration=1440)

    async def call_of_thread(self, thread: discord.Thread) -> None:
        role_ids = await self.notify_role.return_notified(thread.guild.id)
        if role_ids is None:
            return

        content = ''

        for id in role_ids:
            role = thread.guild.get_role(id)
            if role is not None:
                content = f'{content}{role.mention}'

        msg = await thread.send("スレッドが作成されました")
        await msg.edit(content=f'{content} {msg.content}')

    def return_estimated_archive_time(
            self, thread: discord.Thread) -> datetime:
        """スレッドのArchive時間を返す関数

        Args:
            thread (discord.Thread): スレッド

        Returns:
            datetime: 推測されるArchive時間
        """
        archive_time = thread.archive_timestamp + \
            timedelta(minutes=thread.auto_archive_duration)
        return archive_time

    def log_unfounded_thread(self, channel: ChannelData) -> None:
        error_content = f'error content: unfounded_thread\nmessage_content: {channel.channel_id}\nguild : {channel.guild_id}\n{channel.archive_time}'
        logging.error(error_content, exc_info=True)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def lock_thread(self, ctx):
        if not isinstance(ctx.channel, discord.Thread):
            msg = await ctx.reply("このコマンドはスレッドチャンネル専用です")
            await self.c.autodel_msg(msg)
            return
        try:
            await ctx.channel.edit(archived=True, locked=True)
        except discord.Forbidden:
            await ctx.send("スレッドをロックできませんでした")
        await ctx.reply(f"{ctx.channel}をロックしました")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unlock_thread(self, ctx):
        if not isinstance(ctx.channel, discord.Thread):
            msg = await ctx.reply("このコマンドはスレッドチャンネル専用です")
            await self.c.autodel_msg(msg)
            return
        try:
            await ctx.channel.edit(locked=False)
        except discord.Forbidden:
            await ctx.send("スレッドをアンロックできませんでした")
        await ctx.reply(f"{ctx.channel}をアンロックしました")

    @commands.command(name='maintenance_this_thread', aliases=['m_channel'])
    @commands.has_permissions(ban_members=True)
    async def maintenance_this_thread(self, ctx, tf: bool = True):
        if not isinstance(ctx.channel, discord.Thread):
            msg = await ctx.reply("このコマンドはスレッドチャンネル専用です")
            await self.c.autodel_msg(msg)
            return

        if tf is True:
            # まず、現在管理対象であるかのチェック
            if await self.channel_data_manager.is_maintenance_channel(ctx.channel.id, guild_id=ctx.guild.id):
                mgs = await ctx.reply(f"{ctx.channel.name}は管理対象です")
                await self.c.autodel_msg(mgs)

            else:  # 対象でなければ、upsert
                archive_time = self.return_estimated_archive_time(ctx.channel)
                await self.channel_data_manager.resister_channel(channel_id=ctx.channel.id, guild_id=ctx.guild.id, archive_time=archive_time)
                mgs = await ctx.reply(f"{ctx.channel.name}を管理対象に設定しました")
                await self.c.autodel_msg(mgs)

        else:
            # まず、管理対象であるかのチェック
            if not await self.channel_data_manager.is_maintenance_channel(ctx.channel.id, guild_id=ctx.guild.id):
                mgs = await ctx.reply(f"{ctx.channel.name}は管理対象ではありません")
                await self.c.autodel_msg(mgs)
                return

            else:
                await self.channel_data_manager.set_maintenance_channel(channel_id=ctx.channel.id, guild_id=ctx.guild.id, tf=False)
                mgs = await ctx.reply(f"{ctx.channel.name}を管理対象から外しました")
                await self.c.autodel_msg(mgs)

    @commands.command(name='full_maintenance', aliases=['m_guild'])
    @commands.has_permissions(ban_members=True)
    async def full_maintenance(self, ctx, tf: bool = True):
        if isinstance(ctx.channel, discord.DMChannel):
            msg = await ctx.reply("このコマンドはサーバーチャンネル専用です")
            await self.c.autodel_msg(msg)
            return

        # DBの設定を書き換える
        await self.guild_setting_mng.set_full_maintainance(ctx.guild.id, tf)

        if tf:
            string = '有効'
        else:
            string = '無効'

        await ctx.reply(f'{ctx.guild.name}の全スレッドの保守を{string}に設定しました')

    @commands.command(name='resister_notify',
                      aliases=['add_notify'],
                      description='スレッドに自動参加する役職を登録するコマンド')
    @commands.has_permissions(ban_members=True)
    async def resister_notify(self, ctx, *bot_role: discord.Role):
        """スレッド作成時に自動参加するbot_roleを設定するコマンド"""

        role_ids = [role.id for role in bot_role]
        role_mentions = [role.mention for role in bot_role]
        role_mentions = ','.join(role_mentions)

        await self.notify_role.resister_notify(ctx.guild.id, role_ids)
        await ctx.reply(f'{ctx.guild}の新規作成スレッドには今後 {role_mentions} が自動参加します', mention_author=False, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="remove_notify",
                      description="スレッドに自動参加する役職を全削除するコマンド")
    @commands.has_permissions(ban_members=True)
    async def remove_notify(self, ctx):
        await self.notify_role.delete_notify(ctx.guild.id)
        await ctx.reply(f'{ctx.guild}の新規作成スレッドには今後自動参加しません', mention_author=False)

    @commands.command(name="keep_status_of_guild")
    @commands.has_permissions(ban_members=True)
    async def keep_status_of_guild(self, ctx):
        """サーバーのスレッドの設定を確認するコマンド"""
        guild_setting = await self.guild_setting_mng.get_guild_setting(ctx.guild.id)
        if guild_setting is None:
            msg = await ctx.reply("サーバー設定がありません")
            await self.c.autodel_msg(msg)
        else:
            await ctx.reply(f"全保守の設定は{guild_setting.keep_all}です")

        channel_data = await self.channel_data_manager.get_data_guild(
            guild_id=ctx.guild.id)
        if channel_data is None:
            msg = await ctx.reply("現在保守しているチャンネルはありません")
            await self.c.autodel_msg(msg)
        else:
            await ctx.reply(f"現在{len(channel_data)}チャンネルを保守しています")

        notify_settings = await self.notify_role.return_notified(ctx.guild.id)
        if notify_settings is None:
            msg = await ctx.reply("自動参加を設定していません")
            await self.c.autodel_msg(msg)
        else:
            roles = [ctx.guild.get_role(role_id)
                     for role_id in notify_settings]
            role_mentions = [role.mention for role in roles]
            role_mentions = ','.join(role_mentions)
            await ctx.reply(f"自動参加するroleは{role_mentions}です", allowed_mentions=discord.AllowedMentions.none())

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def thread_status(self, ctx):
        """スレッドの設定を確認するコマンド"""
        result = await self.channel_data_manager.is_maintenance_channel(channel_id=ctx.channel.id, guild_id=ctx.guild.id)
        if result:
            await ctx.reply(f"{ctx.channel.name}は管理対象です")
        else:
            await ctx.reply(f"{ctx.channel.name}は管理対象外です")

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
        # 監視対象であるか？
        if await self.channel_data_manager.is_maintenance_channel(channel_id=after.id, guild_id=after.guild.id):
            # アーカイブ時間の設定変更時にDBも書き換える
            if after.archive_timestamp != before.archive_timestamp:
                self.return_estimated_archive_time(after)
                archive_time = self.return_estimated_archive_time(after)
                await self.channel_data_manager.update_archived_time(channel_id=after.id, guild_id=after.guild.id, archive_time=archive_time)

        # アーカイブされたらkeepをfalseに、解除されたらkeepをtrueにする
        if after.archived != before.archived:
            await self.channel_data_manager.set_maintenance_channel(channel_id=after.id, guild_id=after.guild.id, tf=not after.archived)

    # 削除されたらDBから削除する
    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        if await self.channel_data_manager.is_exists(channel_id=thread.id, guild_id=thread.guild.id):
            await self.channel_data_manager.delete_channel(channel_id=thread.id, guild_id=thread.guild.id)

    # スレッドにcloseって投稿されたらアーカイブする
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if isinstance(message.channel, discord.Thread):
            if message.clean_content.lower() == 'close':
                await message.channel.edit(archived=True)

    @tasks.loop(minutes=5.0)
    async def watch_dog(self):
        # 期限短いやつを延長する
        about_to_expire = await self.channel_data_manager.get_about_to_expire_channel()
        if about_to_expire is None:
            return
        else:
            for channel in about_to_expire:
                guild = self.bot.get_guild(channel.guild_id)
                thread = guild.get_thread(channel.channel_id)
                if thread is None:
                    self.log_unfounded_thread(channel)
                    await self.channel_data_manager.set_maintenance_channel(channel_id=channel.channel_id, guild_id=channel.guild_id, tf=False)
                else:
                    await self.extend_archive_duration(thread)

                await asyncio.sleep(1)

    @watch_dog.before_loop
    async def before_printer(self):
        print('thread waiting...')
        await self.bot.wait_until_ready()


def setup(bot):
    bot.add_cog(Hofumi(bot))
