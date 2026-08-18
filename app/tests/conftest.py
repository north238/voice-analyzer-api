"""pytest の共通設定

インポートパスの調整と、テスト中のログの隔離を行う。
"""

import logging
import os
import sys
import tempfile
from pathlib import Path

import pytest

# プロジェクトルート（voice-analyzer-api/）をPYTHONPATHに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# appディレクトリ（voice-analyzer-api/app/）もPYTHONPATHに追加
# これにより、services/内のファイルから "from utils.logger import" が動作する
app_dir = Path(__file__).parent.parent
sys.path.insert(0, str(app_dir))

# ロガーは import された時点でログファイルを開く。
# 実際の logs/ を汚さないよう、utils.logger が読み込まれる前に差し替える
os.environ.setdefault(
    "LOG_DIR", tempfile.mkdtemp(prefix="voice-analyzer-test-logs-")
)


@pytest.fixture
def logs(caplog):
    """ログの内容を検査するための fixture

    アプリのロガーは propagate を切っているため、caplog では拾えない。
    テストの間だけ caplog のハンドラを直接つなぐ。
    """
    from utils.logger import logger

    caplog.set_level(logging.DEBUG)
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)
