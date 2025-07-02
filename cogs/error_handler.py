import logging

import discord
from discord.ext import commands


class CommandErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot:commands.Bot = bot
        self.logger = logging.getLogger("discord.error_handler")

    def _log_error(self, error: Exception, context_info: str) -> None:
        """エラーログを統一的に処理する"""
        self.logger.error(f"Command error occurred:\n{context_info}", exc_info=error)

    @staticmethod
    async def delete_after(msg: discord.Message, second: int = 5) -> None:
        """渡されたメッセージを指定秒数後に削除する関数

        Args:
            msg (discord.Message): 削除するメッセージオブジェクト
            second (int, optional): 秒数. Defaults to 5.
        """
        try:
            await msg.delete(delay=second)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """テキストコマンドのエラーハンドリング"""

        if hasattr(ctx.command, "on_error"):  # ローカルのハンドリングがあるコマンドは除く
            return

        if isinstance(error, commands.CommandNotFound):
            return

        elif isinstance(error, commands.DisabledCommand):
            msg = await ctx.reply(f"{ctx.command}は無効化されています")
            await self.delete_after(msg)
            return

        elif isinstance(error, commands.CheckFailure):
            msg = await ctx.reply(f"{ctx.command}を実行する権限がありません")
            await self.delete_after(msg)
            return

        elif isinstance(error, commands.NoPrivateMessage):
            try:
                msg = await ctx.reply(f"{ctx.command}はDMでは使用できません")
                await self.delete_after(msg)
            except discord.HTTPException:
                self.logger.warning("DMでのメッセージ送信に失敗しました")
            return

        elif isinstance(error, commands.BadArgument):
            msg = await ctx.reply("無効な引数です")
            await self.delete_after(msg)
            return

        elif isinstance(error, commands.MissingRequiredArgument):
            msg = await ctx.reply("必要な引数が不足しています")
            await self.delete_after(msg)
            return

        else:
            # 予期しないエラーの処理
            original_error = getattr(error, "original", error)
            context_info = (
                f"Command: {ctx.command}\n"
                f"Message: {ctx.message.content}\n"
                f"Author: {ctx.message.author}\n"
                f"Guild: {ctx.guild}\n"
                f"Channel: {ctx.channel}\n"
                f"URL: {ctx.message.jump_url}"
            )
            self._log_error(original_error, context_info)

    @commands.Cog.listener()
    async def on_application_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError) -> None:
        """スラッシュコマンドのエラーハンドリング"""

        if isinstance(error, discord.app_commands.MissingPermissions):
            command_name = interaction.command.name if interaction.command else "不明なコマンド"
            await interaction.response.send_message(
                f"{command_name}を実行する権限がありません", ephemeral=True
            )
            context_info = (
                f"Permission Error - Command: {command_name}\n"
                f"User: {interaction.user}\n"
                f"Guild: {interaction.guild}\n"
                f"Channel: {interaction.channel}"
            )
            self._log_error(error, context_info)
            return

        elif hasattr(error, 'original') and isinstance(getattr(error, 'original', None), commands.errors.MessageNotFound):
            if not interaction.response.is_done():
                await interaction.response.send_message("メッセージが見つかりません", ephemeral=True)
            else:
                await interaction.followup.send("メッセージが見つかりません", ephemeral=True)
            return

        else:
            # 予期しないエラーの処理
            original_error = getattr(error, "original", error)
            context_info = (
                f"App Command: {interaction.command.name if interaction.command else 'Unknown'}\n"
                f"User: {interaction.user}\n"
                f"Guild: {interaction.guild}\n"
                f"Channel: {interaction.channel}"
            )
            self._log_error(original_error, context_info)
            
            # ユーザーにエラーを通知
            error_msg = "予期しないエラーが発生しました"
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_msg, ephemeral=True)
                else:
                    await interaction.followup.send(error_msg, ephemeral=True)
            except discord.HTTPException:
                self.logger.error("エラーメッセージの送信に失敗しました")


async def setup(bot):
    await bot.add_cog(CommandErrorHandler(bot))
