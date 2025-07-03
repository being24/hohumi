"""
リマインド除外設定管理用のDiscordコマンド
"""

import discord
from discord import app_commands
from discord.ext import commands

from .utils.reminder_exclusions import ReminderExclusionManager


class ReminderExclusionCog(commands.Cog, name="リマインド除外管理"):
    """リマインド除外設定を管理するコマンド群"""

    def __init__(self, bot):
        self.bot = bot
        self.reminder_exclusions = ReminderExclusionManager()

    @commands.Cog.listener()
    async def on_ready(self):
        """on_ready時にテーブルを作成"""
        await self.reminder_exclusions.create_table()

    # ======== コマンド定義 ========

    @app_commands.command(
        name="reminder_exclude_channel",
        description="このチャンネル下の全スレッドをリマインド対象から除外し、リマインダー期間を設定します (デフォルト: 4週間)",
    )
    @app_commands.describe(weeks="リマインドまでの週数（0で無効化）")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def reminder_exclude_channel(
        self, interaction: discord.Interaction, weeks: int = 4
    ):
        """現在のチャンネルをリマインド対象から除外し、リマインダー期間を設定する"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        # チャンネル内でのみ実行可能（スレッドの場合は親チャンネルを対象とする）
        if isinstance(interaction.channel, discord.Thread):
            target_channel = interaction.channel.parent
            if not target_channel:
                await interaction.response.send_message(
                    "親チャンネルが見つかりません。", ephemeral=True
                )
                return
        else:
            target_channel = interaction.channel

        if not isinstance(target_channel, (discord.TextChannel, discord.ForumChannel)):
            await interaction.response.send_message(
                "このコマンドはテキストチャンネルまたはフォーラムチャンネルでのみ使用できます。",
                ephemeral=True,
            )
            return

        if weeks < 0:
            await interaction.response.send_message(
                "リマインダー期間は0以上の値を指定してください。", ephemeral=True
            )
            return

        try:
            await self.reminder_exclusions.add_exclusion(
                channel_id=target_channel.id,
                guild_id=interaction.guild.id,
                exclude_type="channel",
                exclude_children=True,
                reminder_weeks=weeks,
            )

            if weeks == 0:
                description = f"{target_channel.mention} 下の全スレッドのリマインダーを無効化しました。"
            else:
                description = f"{target_channel.mention} 下の全スレッドのリマインダー期間を{weeks}週間に設定しました。"

            embed = discord.Embed(
                title="除外設定完了",
                description=description,
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"エラーが発生しました: {str(e)}", ephemeral=True
            )

    @app_commands.command(
        name="reminder_include_channel", description="このチャンネルの除外設定を解除"
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def reminder_include_channel(self, interaction: discord.Interaction):
        """現在のチャンネルの除外設定を解除する"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        # チャンネル内でのみ実行可能（スレッドの場合は親チャンネルを対象とする）
        if isinstance(interaction.channel, discord.Thread):
            target_channel = interaction.channel.parent
            if not target_channel:
                await interaction.response.send_message(
                    "親チャンネルが見つかりません。", ephemeral=True
                )
                return
        else:
            target_channel = interaction.channel

        if not isinstance(target_channel, (discord.TextChannel, discord.ForumChannel)):
            await interaction.response.send_message(
                "このコマンドはテキストチャンネルまたはフォーラムチャンネルでのみ使用できます。",
                ephemeral=True,
            )
            return

        try:
            success = await self.reminder_exclusions.remove_exclusion(
                channel_id=target_channel.id, guild_id=interaction.guild.id
            )

            if success:
                embed = discord.Embed(
                    title="除外解除完了",
                    description=f"{target_channel.mention} の除外設定を解除しました。",
                    color=discord.Color.green(),
                )
            else:
                embed = discord.Embed(
                    title="設定なし",
                    description=f"{target_channel.mention} は除外設定されていませんでした。",
                    color=discord.Color.orange(),
                )
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"エラーが発生しました: {str(e)}", ephemeral=True
            )

    @app_commands.command(
        name="reminder_exclude_thread",
        description="リマインド期間を設定します (デフォルト: 4週間、0で無効化)",
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def reminder_exclude_thread(
        self, interaction: discord.Interaction, weeks: int = 4
    ):
        """リマインド期間を設定"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "このコマンドはスレッド内でのみ使用できます。", ephemeral=True
            )
            return

        if weeks < 0:
            await interaction.response.send_message(
                "リマインダー期間は0以上の値を指定してください。", ephemeral=True
            )
            return

        try:
            thread = interaction.channel

            await self.reminder_exclusions.add_exclusion(
                channel_id=thread.id,
                guild_id=interaction.guild.id,
                exclude_type="thread",
                exclude_children=False,
                reminder_weeks=weeks,
            )

            if weeks == 0:
                description = (
                    f"このスレッド「{thread.name}」のリマインダーを無効化しました。"
                )
            else:
                description = f"このスレッド「{thread.name}」のリマインダー期間を{weeks}週間に設定しました。"

            embed = discord.Embed(
                title="除外設定完了",
                description=description,
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"エラーが発生しました: {str(e)}", ephemeral=True
            )

    @app_commands.command(
        name="reminder_include_thread", description="このスレッドの除外設定を解除"
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def reminder_include_thread(self, interaction: discord.Interaction):
        """現在のスレッドの除外設定を解除する"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        # スレッド内でのみ実行可能
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "このコマンドはスレッド内でのみ使用できます。", ephemeral=True
            )
            return

        try:
            thread = interaction.channel

            success = await self.reminder_exclusions.remove_exclusion(
                channel_id=thread.id, guild_id=interaction.guild.id
            )

            if success:
                embed = discord.Embed(
                    title="除外解除完了",
                    description=f"このスレッド「{thread.name}」の除外設定を解除しました。",
                    color=discord.Color.green(),
                )
            else:
                embed = discord.Embed(
                    title="設定なし",
                    description="このスレッドは除外設定されていませんでした。",
                    color=discord.Color.orange(),
                )
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"エラーが発生しました: {str(e)}", ephemeral=True
            )

    @app_commands.command(name="reminder_list", description="現在の除外設定一覧を表示")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def reminder_list(self, interaction: discord.Interaction):
        """現在の除外設定一覧を表示"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        try:
            exclusions = await self.reminder_exclusions.get_exclusions_by_guild(
                interaction.guild.id
            )

            if not exclusions:
                embed = discord.Embed(
                    title="リマインド除外設定",
                    description="現在除外設定されているチャンネル/スレッドはありません。",
                    color=discord.Color.blue(),
                )
                await interaction.response.send_message(embed=embed)
                return

            embed = discord.Embed(
                title="リマインド除外設定一覧", color=discord.Color.blue()
            )

            channel_exclusions = []
            thread_exclusions = []

            for exclusion in exclusions:
                try:
                    if exclusion.exclude_type == "channel":
                        channel = self.bot.get_channel(exclusion.channel_id)
                        if channel:
                            children_text = (
                                "（子スレッドも除外）"
                                if exclusion.exclude_children
                                else ""
                            )
                            channel_exclusions.append(
                                f"• {channel.mention} {children_text}"
                            )
                        else:
                            channel_exclusions.append(
                                f"• ID: {exclusion.channel_id} （削除済み？）"
                            )
                    else:
                        # スレッドの場合
                        thread = self.bot.get_channel(exclusion.channel_id)
                        if thread and isinstance(thread, discord.Thread):
                            thread_exclusions.append(f"• {thread.mention}")
                        else:
                            thread_exclusions.append(
                                f"• ID: {exclusion.channel_id} （削除済み？）"
                            )
                except Exception:
                    # チャンネル/スレッドの取得に失敗した場合
                    if exclusion.exclude_type == "channel":
                        channel_exclusions.append(
                            f"• ID: {exclusion.channel_id} （アクセス不可）"
                        )
                    else:
                        thread_exclusions.append(
                            f"• ID: {exclusion.channel_id} （アクセス不可）"
                        )

            if channel_exclusions:
                embed.add_field(
                    name="除外チャンネル",
                    value="\n".join(channel_exclusions),
                    inline=False,
                )

            if thread_exclusions:
                embed.add_field(
                    name="除外スレッド",
                    value="\n".join(thread_exclusions),
                    inline=False,
                )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"エラーが発生しました: {str(e)}", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(ReminderExclusionCog(bot))
