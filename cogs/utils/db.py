"""
データベース接続設定
"""

import pathlib
from typing import Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine


class DatabaseConfig:
    """データベース設定を管理するクラス"""

    def __init__(self, db_name: str = "data.sqlite3"):
        self.db_name = db_name
        self._engine: Optional[AsyncEngine] = None
        self._db_path: Optional[pathlib.Path] = None

    @property
    def db_path(self) -> pathlib.Path:
        """データベースファイルのパスを取得"""
        if self._db_path is None:
            # プロジェクトルートディレクトリを基準に設定
            project_root = pathlib.Path(__file__).parents[2]
            data_dir = project_root / "data"

            # dataディレクトリが存在しない場合は作成
            data_dir.mkdir(exist_ok=True)

            self._db_path = data_dir / self.db_name

        return self._db_path

    @property
    def engine(self) -> AsyncEngine:
        """SQLAlchemy非同期エンジンを取得"""
        if self._engine is None:
            db_url = f"sqlite+aiosqlite:///{self.db_path}"
            self._engine = create_async_engine(db_url, echo=False)

        return self._engine

    def get_connection_info(self) -> dict:
        """接続情報を取得（デバッグ用）"""
        return {
            "db_path": str(self.db_path),
            "db_exists": self.db_path.exists(),
            "db_name": self.db_name,
            "connection_url": f"sqlite+aiosqlite:///{self.db_path}",
        }


# デフォルトのデータベース設定インスタンス
db_config = DatabaseConfig()

# 後方互換性のためのエンジンエクスポート
engine = db_config.engine
