"""
reminder_exclusions テーブルに roles カラム（JSON文字列, デフォルト: "[]"）を追加するマイグレーションスクリプト
"""

import asyncio
import pathlib
import sys

from sqlalchemy import text

# プロジェクトのdb設定をインポート
sys.path.append(str(pathlib.Path(__file__).parents[2]))
from cogs.utils import db  # db.pyのDatabaseConfig/engineを利用


async def migrate():
    engine = db.engine
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                ALTER TABLE reminder_exclusions
                ADD COLUMN roles TEXT DEFAULT '[]'
                """
            )
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
