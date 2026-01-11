import tempfile
import subprocess
import os

from faster_whisper import WhisperModel
from faster_whisper.vad import VadOptions
from fastapi import UploadFile, HTTPException

from config import settings
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

        # Whisperで文字起こし
        segments, info = whisper_model.transcribe(
            converted_path,
            language="ja",
            beam_size=settings.WHISPER_BEAM_SIZE,
            best_of=settings.WHISPER_BEST_OF,
            temperature=settings.WHISPER_TEMPERATURE,
            vad_filter=settings.WHISPER_VAD_ENABLED,
            vad_parameters=vad_options,
        )

        logger.info(f"✅️info出力: {info}")

        texts = []
        has_speech = False

        for segment in segments:
            texts.append(segment.text)
            has_speech = True

        if not has_speech:
            raise ValueError("音声が認識されませんでした（無音またはノイズの可能性）")

        text = "".join(texts).strip()

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
