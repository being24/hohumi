"""
リマインド除外設定管理用のDiscordコマンド
"""

import asyncio
import discord
from discord import app_commands, ui
from discord.ext import commands

from .utils.reminder_exclusions import ReminderExclusionManager


class ReminderExclusionCog(commands.Cog, name="リマインド除外管理"):
    """リマインド除外設定を管理するコマンド群"""

    def __init__(self, bot):
        self.bot = bot
        self.reminder_exclusions = ReminderExclusionManager()

        # Cog初期化時に永続化Viewを追加（ボット再起動時のため）
        self.setup_persistent_views()

    def setup_persistent_views(self):
        """永続化ビューをセットアップ"""
        # 既存のビューを確認して重複登録を防ぐ
        if not any(
            isinstance(view, PersistentAddRolesView)
            for view in self.bot.persistent_views
        ):
            self.bot.add_view(PersistentAddRolesView(self.reminder_exclusions))

    @commands.Cog.listener()
    async def on_ready(self):
        """on_ready時にテーブルを作成とViewの永続化登録"""
        await self.reminder_exclusions.create_table()

        # 永続化Viewを登録（重複チェック済み）
        self.setup_persistent_views()

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """スレッド作成時にオーナーをDBに追加し、管理者専用のユーザー追加ボタンを送信"""
        if not thread.guild:
            return

        try:
            # スレッドオーナーをDBに自動追加
            if thread.owner_id:
                await self.reminder_exclusions.add_exclusion(
                    channel_id=thread.id,
                    guild_id=thread.guild.id,
                    exclude_type="thread",
                    exclude_children=False,
                    reminder_weeks=4,  # デフォルトは4週間
                    roles=[thread.owner_id],
                )

            # ViewとUIを作成
            view = PersistentAddRolesView(self.reminder_exclusions)

            # スレッド作成直後は送信失敗しやすいので少し待つ
            await asyncio.sleep(1)
            await thread.send(
                "リマインド対象ユーザーを追加/変更する場合は下のボタンを押してください",
                view=view,
            )
        except Exception:
            # エラーが発生してもボットの動作に影響しないよう無視
            pass

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
                roles=[thread.owner_id] if thread.owner_id else [],
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

    @app_commands.command(
        name="show_reminder_roles",
        description="このスレッドのリマインド対象ユーザーを表示",
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def show_reminder_roles(self, interaction: discord.Interaction):
        """現在のスレッドのリマインド対象ユーザーを表示"""
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

        try:
            thread = interaction.channel
            exclusion = await self.reminder_exclusions.get_exclusion(
                thread.id, interaction.guild.id
            )

            if not exclusion or not exclusion.roles:
                embed = discord.Embed(
                    title="リマインド対象ユーザー",
                    description="このスレッドにはリマインド対象ユーザーが設定されていません。",
                    color=discord.Color.orange(),
                )
                await interaction.response.send_message(embed=embed)
                return

            # ユーザー情報を取得してメンション文字列を作成
            user_mentions = []
            for user_id in exclusion.roles:
                user = interaction.guild.get_member(user_id)
                if user:
                    user_mentions.append(f"• {user.mention} ({user.display_name})")
                else:
                    user_mentions.append(f"• <@{user_id}> (ユーザーが見つかりません)")

            embed = discord.Embed(
                title="リマインド対象ユーザー",
                description=f"このスレッド「{thread.name}」のリマインド対象ユーザー:\n\n"
                + "\n".join(user_mentions),
                color=discord.Color.blue(),
            )

            # リマインド期間も表示
            embed.add_field(
                name="リマインド期間",
                value=f"{exclusion.reminder_weeks}週間",
                inline=True,
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"エラーが発生しました: {str(e)}", ephemeral=True
            )

    @app_commands.command(
        name="reminder_add_button", description="このスレッドにユーザー追加ボタンを設置"
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def reminder_add_button(self, interaction: discord.Interaction):
        """現在のスレッドにユーザー追加ボタンを設置"""
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

        try:
            thread = interaction.channel

            # もしDBに設定がない場合はスレッドオーナーを追加
            exclusion = await self.reminder_exclusions.get_exclusion(
                thread.id, interaction.guild.id
            )
            if not exclusion and thread.owner_id:
                await self.reminder_exclusions.add_exclusion(
                    channel_id=thread.id,
                    guild_id=interaction.guild.id,
                    exclude_type="thread",
                    exclude_children=False,
                    reminder_weeks=4,
                    roles=[thread.owner_id],
                )

            # ボタン付きViewを作成
            view = PersistentAddRolesView(self.reminder_exclusions)

            embed = discord.Embed(
                title="ユーザー追加ボタン設置完了",
                description=f"スレッド「{thread.name}」にユーザー追加ボタンを設置しました。",
                color=discord.Color.green(),
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            await thread.send(
                "リマインド対象ユーザーを追加/変更する場合は下のボタンを押してください",
                view=view,
            )

        except Exception as e:
            await interaction.response.send_message(
                f"エラーが発生しました: {str(e)}", ephemeral=True
            )


# --- UI定義 ---
class AddRolesView(ui.View):
    """ユーザー追加ボタンのView"""

    def __init__(
        self, exclusion_manager, thread: discord.Thread, default_roles: list[int]
    ):
        super().__init__(timeout=None)
        self.exclusion_manager = exclusion_manager
        self.thread = thread
        self.default_roles = default_roles
        self.add_item(AddRolesButton(self))


class AddRolesButton(ui.Button):
    """ユーザー追加ボタン"""

    def __init__(self, parent_view):
        super().__init__(label="ユーザー追加/変更", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # 管理者権限チェック（Memberかどうか確認してからguild_permissionsにアクセス）
        if (
            not isinstance(interaction.user, discord.Member)
            or not interaction.user.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "サーバー管理権限が必要です。", ephemeral=True
            )
            return

        # UserSelectを表示
        if interaction.guild:
            select = AddRolesUserSelect(
                self.parent_view.exclusion_manager,
                self.parent_view.thread,
                self.parent_view.default_roles,
                interaction.guild,
            )
            view = ui.View()
            view.add_item(select)
            await interaction.response.send_message(
                "追加するユーザーを選択してください", view=view, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "サーバー情報が取得できませんでした。", ephemeral=True
            )


class AddRolesUserSelect(ui.UserSelect):
    """ユーザー選択Select"""

    def __init__(
        self,
        exclusion_manager,
        thread: discord.Thread,
        default_roles: list[int],
        guild: discord.Guild,
    ):
        # DBに格納されているユーザーをdefault_valuesに設定
        default_users = []
        for user_id in default_roles:
            user = guild.get_member(user_id)
            if user:
                default_users.append(user)

        super().__init__(
            placeholder="ユーザーを選択...",
            min_values=0,
            max_values=25,
            default_values=default_users,
        )
        self.exclusion_manager = exclusion_manager
        self.thread = thread
        self.default_roles = default_roles

    async def callback(self, interaction: discord.Interaction):
        # 管理者権限チェック
        if (
            not isinstance(interaction.user, discord.Member)
            or not interaction.user.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "サーバー管理権限が必要です。", ephemeral=True
            )
            return

        # 選択ユーザーIDリストでDB上書き
        user_ids = [user.id for user in self.values]

        # 既存の設定を取得して週数を保持
        existing = await self.exclusion_manager.get_exclusion(
            self.thread.id, self.thread.guild.id
        )
        weeks = existing.reminder_weeks if existing else 4

        await self.exclusion_manager.add_exclusion(
            channel_id=self.thread.id,
            guild_id=self.thread.guild.id,
            exclude_type="thread",
            exclude_children=False,
            reminder_weeks=weeks,
            roles=user_ids,
        )

        if user_ids:
            user_mentions = ", ".join([f"<@{uid}>" for uid in user_ids])
            await interaction.response.send_message(
                f"リマインド対象ユーザーを更新しました: {user_mentions}",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=False),
            )
        else:
            await interaction.response.send_message(
                "リマインド対象ユーザーをクリアしました。", ephemeral=True
            )


# --- 永続化View定義 ---
class PersistentAddRolesView(ui.View):
    """永続化されたユーザー追加ボタンのView"""

    def __init__(self, exclusion_manager):
        super().__init__(timeout=None)
        self.exclusion_manager = exclusion_manager

    @ui.button(
        label="ユーザー追加/変更",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_add_roles",
    )
    async def add_roles_button(
        self, interaction: discord.Interaction, button: ui.Button
    ):
        # 管理者権限チェック
        if (
            not isinstance(interaction.user, discord.Member)
            or not interaction.user.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "サーバー管理権限が必要です。", ephemeral=True
            )
            return

        # スレッドの確認
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "このボタンはスレッド内でのみ使用できます。", ephemeral=True
            )
            return

        thread = interaction.channel

        # 既存のrolesを取得
        if interaction.guild:
            exclusion = await self.exclusion_manager.get_exclusion(
                thread.id, interaction.guild.id
            )
            default_roles = exclusion.roles if exclusion and exclusion.roles else []

            # UserSelectを表示
            select = AddRolesUserSelect(
                self.exclusion_manager,
                thread,
                default_roles,
                interaction.guild,
            )
            view = ui.View()
            view.add_item(select)
            await interaction.response.send_message(
                "追加するユーザーを選択してください", view=view, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "サーバー情報が取得できませんでした。", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(ReminderExclusionCog(bot))
