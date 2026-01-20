"""
非同期処理ラッパー
同期処理をrun_in_executorで非同期化し、WebSocketをブロックしない
"""

import asyncio
import tempfile
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from faster_whisper import WhisperModel
from config import settings
from utils.logger import logger

# スレッドプールエグゼキューター
# ProcessPoolExecutorは使用しない（モデルのシリアライズ問題を回避）
_executor: Optional[ThreadPoolExecutor] = None


def get_executor() -> ThreadPoolExecutor:
    """スレッドプールエグゼキューターを取得（シングルトン）"""
    global _executor
    if _executor is None:
        # ワーカー数を2に制限（メモリ効率のため）
        _executor = ThreadPoolExecutor(max_workers=2)
    return _executor


# Whisperモデル（グローバルに保持してロード時間を節約）
_whisper_model: Optional[WhisperModel] = None


def get_whisper_model() -> WhisperModel:
    """Whisperモデルを取得（シングルトン）"""
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


def _transcribe_sync(audio_data: bytes, suffix: str = ".wav") -> str:
    """
    同期的な音声文字起こし処理

    Args:
        audio_data: 音声データのバイト列
        suffix: ファイル拡張子

    Returns:
        str: 文字起こし結果
    """
    import re
    from faster_whisper.vad import VadOptions

    tmp_path = None
    converted_path = None

    try:
        # 一時ファイル作成
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        # ffmpegで16kHz/モノラルに変換
        converted_path = tmp_path.rsplit(".", 1)[0] + "_16k.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                tmp_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-af",
                "loudnorm",
                converted_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # VADオプション
        vad_options = VadOptions(
            min_silence_duration_ms=settings.WHISPER_VAD_MIN_SILENCE_MS,
            speech_pad_ms=settings.WHISPER_VAD_SPEECH_PAD_MS,
        )

        # Whisperで文字起こし
        model = get_whisper_model()
        segments, info = model.transcribe(
            converted_path,
            language="ja",
            beam_size=settings.WHISPER_BEAM_SIZE,
            best_of=settings.WHISPER_BEST_OF,
            temperature=settings.WHISPER_TEMPERATURE,
            vad_filter=settings.WHISPER_VAD_ENABLED,
            vad_parameters=vad_options,
        )

        # セグメントからテキストを抽出
        texts = [s.text for s in segments if s.text.strip()]
        text = "".join(texts).strip()

        # 数字間の不要なスペースを削除
        text = re.sub(r"(?<=\d)[\s　]+(?=\d)", "", text)

        if not text:
            raise ValueError("音声解析結果が空でした")

        logger.info(f"🗣 Whisper出力: {text}")
        return text

    except subprocess.CalledProcessError:
        raise ValueError("音声変換に失敗しました")

    finally:
        # 一時ファイル削除
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        if converted_path and os.path.exists(converted_path):
            os.remove(converted_path)


async def transcribe_async(audio_data: bytes, suffix: str = ".wav") -> str:
    """
    非同期的な音声文字起こし処理

    Args:
        audio_data: 音声データのバイト列
        suffix: ファイル拡張子

    Returns:
        str: 文字起こし結果
    """
    loop = asyncio.get_event_loop()
    executor = get_executor()
    return await loop.run_in_executor(executor, _transcribe_sync, audio_data, suffix)


def _normalize_sync(text: str, keep_punctuation: bool = True) -> str:
    """
    同期的なひらがな正規化処理

    Args:
        text: 正規化するテキスト
        keep_punctuation: 句読点を保持するか

    Returns:
        str: ひらがな化されたテキスト
    """
    from utils.normalizer import JapaneseNormalizer

    normalizer = JapaneseNormalizer()
    return normalizer.to_hiragana(text, keep_punctuation=keep_punctuation)


async def normalize_async(text: str, keep_punctuation: bool = True) -> str:
    """
    非同期的なひらがな正規化処理

    Args:
        text: 正規化するテキスト
        keep_punctuation: 句読点を保持するか

    Returns:
        str: ひらがな化されたテキスト
    """
    loop = asyncio.get_event_loop()
    executor = get_executor()
    return await loop.run_in_executor(
        executor, _normalize_sync, text, keep_punctuation
    )


def _translate_sync(text: str) -> str:
    """
    同期的な翻訳処理

    Args:
        text: 翻訳するテキスト

    Returns:
        str: 翻訳結果
    """
    from services.translator import translate_text

    return translate_text(text)


async def translate_async(text: str) -> str:
    """
    非同期的な翻訳処理

    Args:
        text: 翻訳するテキスト

    Returns:
        str: 翻訳結果
    """
    loop = asyncio.get_event_loop()
    executor = get_executor()
    return await loop.run_in_executor(executor, _translate_sync, text)


def _add_punctuation_sync(text: str) -> str:
    """
    同期的な句読点挿入処理

    Args:
        text: 句読点を挿入するテキスト

    Returns:
        str: 句読点が挿入されたテキスト
    """
    from utils.normalizer import JapaneseNormalizer

    normalizer = JapaneseNormalizer()
    return normalizer.add_punctuation(text)


async def add_punctuation_async(text: str) -> str:
    """
    非同期的な句読点挿入処理

    Args:
        text: 句読点を挿入するテキスト

    Returns:
        str: 句読点が挿入されたテキスト
    """
    loop = asyncio.get_event_loop()
    executor = get_executor()
    return await loop.run_in_executor(executor, _add_punctuation_sync, text)


def shutdown_executor():
    """エグゼキューターをシャットダウン"""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True)
        _executor = None
        logger.info("🔧 ThreadPoolExecutorをシャットダウンしました")