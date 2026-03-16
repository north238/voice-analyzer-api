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
    WHISPER_VAD_ENABLED: bool = (
        os.getenv("WHISPER_VAD_ENABLED", "true").lower() == "true"
    )
    WHISPER_VAD_MIN_SILENCE_MS: int = int(
        os.getenv("WHISPER_VAD_MIN_SILENCE_MS", "500")
    )
    WHISPER_VAD_SPEECH_PAD_MS: int = int(os.getenv("WHISPER_VAD_SPEECH_PAD_MS", "400"))

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
    # Phase 8修正: 30秒 → 15秒（精度優先、表記揺れを最小化）
    CUMULATIVE_MAX_AUDIO_SECONDS: float = float(
        os.getenv("CUMULATIVE_MAX_AUDIO_SECONDS", "12.0")
    )
    CUMULATIVE_TRANSCRIPTION_INTERVAL: int = int(
        os.getenv("CUMULATIVE_TRANSCRIPTION_INTERVAL", "3")
    )
    CUMULATIVE_STABLE_THRESHOLD: int = int(
        os.getenv("CUMULATIVE_STABLE_THRESHOLD", "3")
    )

    # テキスト処理設定
    MAX_TEXT_LENGTH: int = int(os.getenv("MAX_TEXT_LENGTH", "50"))

    #################################################################################
    # ブラウザ版で使用（ラズパイは不使用）
    # Ollama設定（API）
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://local-llm:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))
    OLLAMA_TEMPERATURE: float = 0.2
    OLLAMA_NUM_PREDICT: int = 256
    OLLAMA_TOP_K: int = 10
    OLLAMA_TOP_P: float = 0.9
    OLLAMA_REPEAT_PENALTY: float = 1.1

    # 要約設定（Phase 13追加）
    SUMMARY_PROVIDER: str = os.getenv(
        "SUMMARY_PROVIDER", "ollama"
    )  # "ollama" or "gemini"

    # Ollama要約用（デフォルトプロバイダー）
    OLLAMA_SUMMARY_MODEL: str = os.getenv("OLLAMA_SUMMARY_MODEL", "gemma3:4b")
    OLLAMA_SUMMARY_NUM_PREDICT: int = int(
        os.getenv("OLLAMA_SUMMARY_NUM_PREDICT", "1024")
    )
    # Gemini要約用
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_MAX_OUTPUT_TOKENS: int = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "512"))
    GEMINI_TEMPERATURE: float = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
    #################################################################################

    # API設定
    API_TITLE: str = "Voice Analyzer API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "Whisper音声認識 + 日本語処理API for Raspberry Pi"


settings = Settings()
