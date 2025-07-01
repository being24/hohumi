import logging

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput

from .utils.common import CommonUtil


class ProxyModal(Modal, title="代理投稿を行います"):
    """代理投稿用のモーダル"""
    
    def __init__(self):
        super().__init__()
        self.answer = TextInput(
            label="投稿内容", 
            style=discord.TextStyle.paragraph,
            placeholder="投稿したい内容を入力してください...",
            max_length=2000
        )
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        """モーダル送信時の処理"""
        try:
            if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
                await interaction.response.send_message(
                    "このコマンドはテキストチャンネルまたはスレッドでのみ使用できます", 
                    ephemeral=True
                )
                return
            
            await interaction.channel.send(self.answer.value)
            await interaction.response.send_message("代理投稿を行いました", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("メッセージを送信する権限がありません", ephemeral=True)
        except Exception as e:
            logging.error(f"代理投稿でエラーが発生しました: {e}")
            await interaction.followup.send("代理投稿中にエラーが発生しました", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """モーダルエラー時の処理"""
        logging.error(f"ProxyModal でエラーが発生しました: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("エラーが発生しました", ephemeral=True)
            else:
                await interaction.followup.send("エラーが発生しました", ephemeral=True)
        except Exception:
            pass


class EditModal(Modal, title="メッセージを編集します"):
    """メッセージ編集用のモーダル"""
    
    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message
        self.answer = TextInput(
            label="編集内容", 
            style=discord.TextStyle.paragraph,
            default=message.content,
            max_length=2000
        )
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        """モーダル送信時の処理"""
        try:
            await self.message.edit(content=self.answer.value)
            await interaction.response.send_message("メッセージの編集を行いました", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send("メッセージを編集する権限がありません", ephemeral=True)
        except discord.NotFound:
            await interaction.followup.send("編集対象のメッセージが見つかりません", ephemeral=True)
        except Exception as e:
            logging.error(f"メッセージ編集でエラーが発生しました: {e}")
            await interaction.followup.send("メッセージ編集中にエラーが発生しました", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """モーダルエラー時の処理"""
        logging.error(f"EditModal でエラーが発生しました: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("エラーが発生しました", ephemeral=True)
            else:
                await interaction.followup.send("エラーが発生しました", ephemeral=True)
        except Exception:
            pass


class Announcement(commands.Cog, name="アナウンス機能"):
    """
    代理投稿とメッセージ編集機能を提供するCog
    """

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.c = CommonUtil()
        self.logger = logging.getLogger("discord")

        # コンテキストメニューの設定
        self.ctx_menu = app_commands.ContextMenu(
            name="メッセージを編集",
            callback=self.edit_message_context,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        """Cogアンロード時にコンテキストメニューを削除"""
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    def _validate_channel(self, channel) -> bool:
        """チャンネルが有効かどうかを確認"""
        return isinstance(channel, (discord.TextChannel, discord.Thread))

    def _validate_bot_message(self, message: discord.Message) -> bool:
        """メッセージがbotのものかどうかを確認"""
        return (
            self.bot.user is not None and 
            message.author.id == self.bot.user.id
        )

    @app_commands.command(name="proxy_transmission", description="代理投稿を行います")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def proxy_transmission(self, interaction: discord.Interaction):
        """代理投稿を行うコマンド"""
        try:
            if not self._validate_channel(interaction.channel):
                await interaction.response.send_message(
                    "このコマンドはテキストチャンネルまたはスレッドでのみ使用できます", 
                    ephemeral=True
                )
                return
            
            await interaction.response.send_modal(ProxyModal())
            
        except Exception as e:
            self.logger.error(f"proxy_transmission でエラーが発生しました: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("エラーが発生しました", ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def edit_message_context(self, interaction: discord.Interaction, message: discord.Message):
        """コンテキストメニューからメッセージを編集"""
        try:
            if not self._validate_bot_message(message):
                await interaction.response.send_message(
                    "自分のメッセージのみ編集できます", 
                    ephemeral=True
                )
                return

            if not self._validate_channel(interaction.channel):
                await interaction.response.send_message(
                    "このチャンネルでは編集できません", 
                    ephemeral=True
                )
                return

            await interaction.response.send_modal(EditModal(message))
            
        except Exception as e:
            self.logger.error(f"edit_message_context でエラーが発生しました: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("エラーが発生しました", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Announcement(bot))
