import os
from typing import Literal


class Settings:
    """アプリケーション設定"""

    # Whisper設定
    # Phase 12: base → small に変更（精度大幅向上）
    WHISPER_MODEL_SIZE: Literal["tiny", "base", "small", "medium"] = os.getenv(
        "WHISPER_MODEL_SIZE", "small"
    )
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    WHISPER_CPU_THREADS: int = int(os.getenv("WHISPER_CPU_THREADS", "4"))
    WHISPER_NUM_WORKERS: int = int(os.getenv("WHISPER_NUM_WORKERS", "1"))

    # 文字起こし設定
    # Phase 12: beam_size/best_of を 1 に変更（smallモデルの精度でgreedy decodingでも十分）
    WHISPER_BEAM_SIZE: int = int(os.getenv("WHISPER_BEAM_SIZE", "1"))
    WHISPER_BEST_OF: int = int(os.getenv("WHISPER_BEST_OF", "1"))
    WHISPER_TEMPERATURE: float = 0.0
    # 外部VAD（Silero VAD）へ渡す設定。Whisper内蔵VADは使わないため
    # vad_filter 関連の設定は持たない
    WHISPER_VAD_MIN_SILENCE_MS: int = int(
        os.getenv("WHISPER_VAD_MIN_SILENCE_MS", "500")
    )

    # ハルシネーション抑制設定（Phase 12追加）
    # condition_on_previous_text: 前の出力への依存を断ち、繰り返しの連鎖を防止
    WHISPER_CONDITION_ON_PREVIOUS_TEXT: bool = (
        os.getenv("WHISPER_CONDITION_ON_PREVIOUS_TEXT", "false").lower() == "true"
    )
    # repetition_penalty: 同じトークンの繰り返しにペナルティ
    WHISPER_REPETITION_PENALTY: float = float(
        os.getenv("WHISPER_REPETITION_PENALTY", "1.1")
    )
    # compression_ratio_threshold: 繰り返しが多いセグメントを自動除外
    WHISPER_COMPRESSION_RATIO_THRESHOLD: float = float(
        os.getenv("WHISPER_COMPRESSION_RATIO_THRESHOLD", "2.4")
    )
    # log_prob_threshold: 確信度が低いセグメントを除外
    WHISPER_LOG_PROB_THRESHOLD: float = float(
        os.getenv("WHISPER_LOG_PROB_THRESHOLD", "-1.0")
    )
    # no_speech_threshold: 無音セグメントの閾値
    WHISPER_NO_SPEECH_THRESHOLD: float = float(
        os.getenv("WHISPER_NO_SPEECH_THRESHOLD", "0.6")
    )
    # no_repeat_ngram_size: 0=無効（日本語は自然な繰り返しがあるため）
    WHISPER_NO_REPEAT_NGRAM_SIZE: int = int(
        os.getenv("WHISPER_NO_REPEAT_NGRAM_SIZE", "0")
    )



settings = Settings()
