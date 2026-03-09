import tempfile
import subprocess
import os
import re

from faster_whisper import WhisperModel
from faster_whisper.vad import VadOptions
from fastapi import UploadFile, HTTPException

from config import settings
from services.text_filter import is_valid_text
from utils.logger import logger

whisper_model = WhisperModel(
    settings.WHISPER_MODEL_SIZE,
    device=settings.WHISPER_DEVICE,
    compute_type=settings.WHISPER_COMPUTE_TYPE,
    cpu_threads=settings.WHISPER_CPU_THREADS,
    num_workers=settings.WHISPER_NUM_WORKERS,
)


async def transcribe_audio(file: UploadFile) -> str:
    tmp_path = None
    converted_path = None
    try:
        # 一時ファイル作成
        suffix = os.path.splitext(file.filename)[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # ffmpegで16kHz/モノラルに変換（Whisper最適化）
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
                "loudnorm",  # 音量正規化
                converted_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        vad_options = VadOptions(
            min_silence_duration_ms=settings.WHISPER_VAD_MIN_SILENCE_MS,
            speech_pad_ms=settings.WHISPER_VAD_SPEECH_PAD_MS,
        )

        # transcribeのパラメータを構築
        transcribe_params = {
            "language": "ja",
            "beam_size": settings.WHISPER_BEAM_SIZE,
            "best_of": settings.WHISPER_BEST_OF,
            "temperature": settings.WHISPER_TEMPERATURE,
            "vad_filter": settings.WHISPER_VAD_ENABLED,
            "vad_parameters": vad_options,
            # Phase 12: ハルシネーション抑制パラメータ
            "condition_on_previous_text": settings.WHISPER_CONDITION_ON_PREVIOUS_TEXT,
            "repetition_penalty": settings.WHISPER_REPETITION_PENALTY,
            "compression_ratio_threshold": settings.WHISPER_COMPRESSION_RATIO_THRESHOLD,
            "log_prob_threshold": settings.WHISPER_LOG_PROB_THRESHOLD,
            "no_speech_threshold": settings.WHISPER_NO_SPEECH_THRESHOLD,
        }

        # no_repeat_ngram_size: 0より大きい場合のみ設定
        if settings.WHISPER_NO_REPEAT_NGRAM_SIZE > 0:
            transcribe_params["no_repeat_ngram_size"] = settings.WHISPER_NO_REPEAT_NGRAM_SIZE

        # Whisperで文字起こし
        segments, info = whisper_model.transcribe(converted_path, **transcribe_params)

        logger.info(f"✅️info出力: {info}")

        if not segments:
            raise ValueError("音声が認識されませんでした（無音またはノイズの可能性）")

        # セグメントからテキストを抽出（Phase 12: セグメント単位の品質フィルタリング）
        texts = []
        for s in segments:
            seg_text = s.text.strip()
            if seg_text and is_valid_text(seg_text):
                texts.append(s.text)
            elif seg_text:
                logger.debug(f"🚫 低品質セグメント除外: {seg_text}")
        text = "".join(texts).strip()

        # 数字間の不要なスペース（半角・全角）を削除
        text = re.sub(r"(?<=\d)[\s　]+(?=\d)", "", text)

        if not text:
            raise ValueError("音声解析結果が空でした")

        logger.info(f"🗣 Whisper出力: {text}")

        return text

    except subprocess.CalledProcessError:
        raise HTTPException(status_code=500, detail="音声変換に失敗しました。")

    finally:
        # 一時ファイル削除
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        if converted_path and os.path.exists(converted_path):
            os.remove(converted_path)
