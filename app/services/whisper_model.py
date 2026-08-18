"""Whisper モデルのロード。

モデルはロードに時間がかかる（実測でキャッシュ済みでも約1.2秒）ため、
シングルトンとして保持して使い回す。
"""

import time
from typing import Optional

from config import settings
from faster_whisper import WhisperModel
from utils.logger import logger

_whisper_model: Optional[WhisperModel] = None


def get_whisper_model() -> WhisperModel:
    """Whisper モデルを取得する（シングルトン）"""
    global _whisper_model
    if _whisper_model is None:
        started = time.perf_counter()
        _whisper_model = WhisperModel(
            settings.WHISPER_MODEL_SIZE,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
            cpu_threads=settings.WHISPER_CPU_THREADS,
            num_workers=settings.WHISPER_NUM_WORKERS,
        )
        # ロード時間は冒頭の取りこぼし（R-6）を調べるときの手がかりになるため残す。
        # 正常時は無情報なので画面には出さない
        logger.debug(
            f"モデルをロード: {settings.WHISPER_MODEL_SIZE} "
            f"({time.perf_counter() - started:.2f}秒)"
        )
    return _whisper_model
