# !/usr/bin/env python3

import discord
from discord.commands import slash_command
from discord.ext import commands
from discord.ui import InputText, Modal


class SendModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(
            InputText(
                label="内容",
                placeholder="ここに内容を入力",
                required=True,
                style=discord.InputTextStyle.long,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        msg = self.children[0].value
        await interaction.response.send_message(msg)


class MyModal(commands.Cog, name='Modal管理用cog'):
    """
    Modal管理
    """

    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @slash_command(name="proxy_transmission")
    async def proxy_transmission(self, ctx):
        """代理送信するコマンド"""
        modal = SendModal(title="お知らせを投稿します")
        await ctx.send_modal(modal)

    @slash_command(name="edit_transmission")
    async def edit_transmission(self, ctx, message_id: discord.Message):
        """代理送信したメッセージを編集するコマンドです"""
        message = message_id

        class EditModal(Modal):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)

                self.add_item(
                    InputText(
                        label="内容",
                        placeholder="ここに内容を入力",
                        value=message.content,
                        style=discord.InputTextStyle.long
                    )
                )

            async def callback(self, interaction: discord.Interaction):
                msg = self.children[0].value
                await message.edit(content=msg)
                await interaction.response.send_message('更新しました', delete_after=10)

        modal = EditModal(title="お知らせを更新します")
        await ctx.interaction.response.send_modal(modal)


def setup(bot):
    bot.add_cog(MyModal(bot))
