# !/usr/bin/env python3

import discord
from discord.commands import slash_command
from discord.ext import commands
from discord.ui import InputText, Modal


class MyModal(Modal):
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


class Modal(commands.Cog, name='Modal管理用cog'):
    """
    Modal管理
    """

    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @slash_command(name="modaltest")
    async def modal_slash(self, ctx):
        """お知らせを投稿します"""
        modal = MyModal(title="お知らせを投稿します")
        await ctx.interaction.response.send_modal(modal)


def setup(bot):
    bot.add_cog(Modal(bot))
