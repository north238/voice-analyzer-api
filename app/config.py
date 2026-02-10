import os
from typing import Literal


class Settings:
    """アプリケーション設定"""

    # Whisper設定
    # Phase 4最適化: small → base に変更（処理時間50%削減）
    WHISPER_MODEL_SIZE: Literal["tiny", "base", "small", "medium"] = os.getenv(
        "WHISPER_MODEL_SIZE", "base"
    )
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_CPU_THREADS: int = 4
    WHISPER_NUM_WORKERS: int = 1

    # 文字起こし設定
    # Phase 4最適化: beam_size/best_of を 5 → 3 に変更（処理時間15-20%削減）
    WHISPER_BEAM_SIZE: int = int(os.getenv("WHISPER_BEAM_SIZE", "3"))
    WHISPER_BEST_OF: int = int(os.getenv("WHISPER_BEST_OF", "3"))
    WHISPER_TEMPERATURE: float = 0.0
    WHISPER_VAD_ENABLED: bool = True
    WHISPER_VAD_MIN_SILENCE_MS: int = 500
    WHISPER_VAD_SPEECH_PAD_MS: int = 400

    # Ollama設定
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    OLLAMA_MODEL: str = "gemma2:2b-instruct-q8_0"
    OLLAMA_TIMEOUT: int = 120
    OLLAMA_TEMPERATURE: float = 0.3
    OLLAMA_NUM_PREDICT: int = 256
    OLLAMA_TOP_K: int = 10
    OLLAMA_TOP_P: float = 0.9
    OLLAMA_REPEAT_PENALTY: float = 1.1

    # 翻訳設定
    TRANSLATION_MODEL: str = os.getenv(
        "TRANSLATION_MODEL", "Helsinki-NLP/opus-mt-ja-en"
    )
    MAX_TRANSLATION_LENGTH: int = int(os.getenv("MAX_TRANSLATION_LENGTH", "512"))
    TRANSLATION_DEVICE: str = "cpu"  # CPU推奨（Raspberry Pi対応）

    # セッション管理設定
    SESSION_TIMEOUT_MINUTES: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
    MAX_CHUNKS_PER_SESSION: int = int(os.getenv("MAX_CHUNKS_PER_SESSION", "100"))

    # 累積バッファ設定
    # Phase 8修正: 30秒 → 25秒（処理遅延を考慮してWhisperの30秒制限を超えないように）
    CUMULATIVE_MAX_AUDIO_SECONDS: float = float(
        os.getenv("CUMULATIVE_MAX_AUDIO_SECONDS", "25.0")
    )
    CUMULATIVE_TRANSCRIPTION_INTERVAL: int = int(
        os.getenv("CUMULATIVE_TRANSCRIPTION_INTERVAL", "3")
    )
    CUMULATIVE_STABLE_THRESHOLD: int = int(
        os.getenv("CUMULATIVE_STABLE_THRESHOLD", "2")
    )

    # テキスト処理設定
    MAX_TEXT_LENGTH: int = 50

    # API設定
    API_TITLE: str = "Voice Analyzer API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "Whisper音声認識 + 日本語処理API for Raspberry Pi"


settings = Settings()
