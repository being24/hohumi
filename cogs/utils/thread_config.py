"""
スレッド管理に関する設定と定数
"""

from enum import IntEnum


class AutoArchiveDuration(IntEnum):
    """スレッドの自動アーカイブ時間を表すEnum

    値は分単位で、Discordの有効な設定値のみを含む
    """

    ONE_HOUR = 60  # 1時間
    ONE_DAY = 1440  # 1日
    THREE_DAYS = 4320  # 3日
    ONE_WEEK = 10080  # 1週間

    @classmethod
    def get_display_name(cls, duration: "AutoArchiveDuration") -> str:
        """表示用の文字列を取得"""
        mapping = {
            cls.ONE_HOUR: "1時間",
            cls.ONE_DAY: "1日",
            cls.THREE_DAYS: "3日",
            cls.ONE_WEEK: "1週間",
        }
        return mapping.get(duration, f"{duration.value}分")


class ThreadKeeperConfig:
    """スレッド管理の設定値"""

    # プレフィックス
    CLOSED_THREAD_PREFIX = "[CLOSED]"

    # アーカイブ時間設定
    TMP_ARCHIVE_DURATION = 60  # 一時的なアーカイブ時間
    FINAL_ARCHIVE_DURATION = 10080  # 最終的なアーカイブ時間（1週間）

    # リマインド設定
    REMINDER_WEEKS = 2  # リマインド対象期間（週）

    # 対象サーバーと除外チャンネルの設定
    REMINDER_TARGET_GUILD_IDS = [410454762522411009]
    REMINDER_EXCLUDE_CHANNEL_IDS = []

    # タスク設定
    WATCH_DOG_INTERVAL_MINUTES = 15  # watch_dogタスクの実行間隔（分）
    THREAD_PROCESSING_SLEEP_SECONDS = 5  # スレッド処理間の待機時間（秒）
    ARCHIVE_EXTENSION_SLEEP_SECONDS = 10  # アーカイブ延長処理の待機時間（秒）
