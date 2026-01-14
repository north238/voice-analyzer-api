import logging
import sys
import os

# 環境変数で DEBUG モードを制御可能に
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# 共通ロガー設定
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)
