"""Whisper モデルのロード。

モデルはロードに時間がかかる（実測でキャッシュ済みでも約1.2秒）ため、
シングルトンとして保持して使い回す。
"""

from typing import Optional

from config import settings
from faster_whisper import WhisperModel
from utils.logger import logger

_whisper_model: Optional[WhisperModel] = None


def get_whisper_model() -> WhisperModel:
    """Whisper モデルを取得する（シングルトン）"""
    global _whisper_model
    if _whisper_model is None:
        logger.info(f"🔧 Whisperモデルをロード中: {settings.WHISPER_MODEL_SIZE}")
        _whisper_model = WhisperModel(
            settings.WHISPER_MODEL_SIZE,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
            cpu_threads=settings.WHISPER_CPU_THREADS,
            num_workers=settings.WHISPER_NUM_WORKERS,
        )
        logger.info("✅ Whisperモデルのロード完了")
    return _whisper_model
