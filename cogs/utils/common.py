# !/usr/bin/env python3
# -*- coding: utf-8 -*-

import typing
import nextcord


class CommonUtil():
    def __init__(self):
        pass

    @staticmethod
    async def autodel_msg(msg: nextcord.Message, second: int = 5):
        """渡されたメッセージを指定秒数後に削除する関数

        Args:
            msg (nextcord.Message): 削除するメッセージオブジェクト
            second (int, optional): 秒数. Defaults to 5.
        """
        try:
            await msg.delete(delay=second)
        except nextcord.Forbidden:
            pass

    @staticmethod
    def return_member_or_role(guild: nextcord.Guild,
                              id: int) -> typing.Union[nextcord.Member,
                                                       nextcord.Role,
                                                       None]:
        """メンバーか役職オブジェクトを返す関数

        Args:
            guild (nextcord.guild): nextcordのguildオブジェクト
            id (int): 役職かメンバーのID

        Returns:
            typing.Union[nextcord.Member, nextcord.Role]: nextcord.Memberかnextcord.Role
        """
        user_or_role = guild.get_role(id)
        if user_or_role is None:
            user_or_role = guild.get_member(id)

        return user_or_role
