"""ログの設定。

ファイルと画面で出す量を変える。ファイルには DEBUG まで残し、画面には
WARNING 以上だけを出す。異常が起きたときにだけ画面が反応し、
後から追うための動作記録はファイル側にだけ溜まる。

出力先は標準エラー。標準出力は文字起こし結果の表示に使うため、
混ぜると `2>/dev/null` で結果だけを取り出せなくなる。
"""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# ログディレクトリの設定
# 既定はリポジトリ直下の logs/（Docker 廃止に伴い /logs から変更）
_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR = Path(os.getenv("LOG_DIR", _DEFAULT_LOG_DIR))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ログファイルのパス
LOG_FILE = LOG_DIR / "voice-analyzer.log"

# ログローテーションで保持する世代数。
# 注: 日次ローテーションは「実行された日」にしか起きないため、
#     毎日使わない場合の保持期間は世代数より長くなる
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 14))

# 画面に出す下限。これ未満はファイルにのみ残る
CONSOLE_LEVEL = logging.WARNING

# ファイルに残す下限
FILE_LEVEL = logging.DEBUG


def setup_logger():
    """ロガーを初期化する

    Returns:
        logging.Logger: 設定済みのロガー
    """
    logger = logging.getLogger(__name__)

    # 既に設定済みの場合はスキップ（重複防止）
    if logger.handlers:
        return logger

    logger.setLevel(min(CONSOLE_LEVEL, FILE_LEVEL))

    # 呼び出し元のモジュール名を含める。
    # ロガーは単一（getLogger(__name__)）のため %(name)s では常に同じ値になり区別がつかない
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(module)s: %(message)s"
    )

    # 画面（標準エラー）への出力。異常時のみ
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(CONSOLE_LEVEL)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ファイル出力（日付ごとのログローテーション）
    file_handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",  # 毎日午前0時にローテーション
        interval=1,  # 1日ごと
        backupCount=LOG_BACKUP_COUNT,  # 保持する世代数
        encoding="utf-8",
    )
    # ログファイル名のサフィックス（例: voice-analyzer.log.2026-01-15）
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(FILE_LEVEL)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 親ロガーへの伝播を防止（重複ログを避ける）
    logger.propagate = False

    return logger


logger = setup_logger()
