import logging
import sys
import os
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

# 環境変数で DEBUG モードを制御可能に
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ログディレクトリの設定
# 既定はリポジトリ直下の logs/（Docker 廃止に伴い /logs から変更）
_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR = Path(os.getenv("LOG_DIR", _DEFAULT_LOG_DIR))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ログファイルのパス
LOG_FILE = LOG_DIR / "voice-analyzer.log"

# ログローテーション設定
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 14))  # デフォルト: 14日分保持


def _is_reloader_parent_process() -> bool:
    """
    Uvicornのreloader親プロセスかどうかを判定

    Docker環境では親プロセスのPIDは常に1
    子プロセス（実際のアプリ）はPID > 1

    Returns:
        bool: 親プロセスの場合True
    """
    # --reloadが有効かつPID=1の場合のみTrue
    is_reload_mode = os.getenv("ENV", "production").lower() == "development"
    return is_reload_mode and os.getpid() == 1


def setup_logger():
    """
    ロガーを初期化（reloader子プロセスでのみ実行）

    Returns:
        logging.Logger: 設定済みのロガー
    """
    # ロガーの作成
    logger = logging.getLogger(__name__)

    # reloaderの親プロセスではログ初期化をスキップ（ハンドラーチェック前に実行）
    if _is_reloader_parent_process():
        # 親プロセスでは最小限のログ設定のみ
        logger.setLevel(logging.CRITICAL)
        return logger

    # 既に設定済みの場合はスキップ（重複防止）
    if logger.handlers:
        return logger

    # ログレベルの設定
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # フォーマッターの作成
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # コンソール出力ハンドラー（既存の動作を維持）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ファイル出力ハンドラー（日付ごとのログローテーション）
    file_handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",  # 毎日午前0時にローテーション
        interval=1,  # 1日ごと
        backupCount=LOG_BACKUP_COUNT,  # 保持する世代数
        encoding="utf-8",
    )
    # ログファイル名のサフィックス（例: voice-analyzer.log.2026-01-15）
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 親ロガーへの伝播を防止（重複ログを避ける）
    logger.propagate = False

    # 起動時ログ
    logger.info(
        f"📁 ログファイル: {LOG_FILE} (日次ローテーション, {LOG_BACKUP_COUNT}日分保持)"
    )
    return logger


logger = setup_logger()
