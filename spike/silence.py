"""沈黙を記録する構成の検証用スパイク（使い捨て）

docs/02_slience_and_verification.md のタスクA。

第1段階で、音声認識エンジンの内蔵VADが無音区間を除去してから文字起こしするため、
沈黙の情報が処理に到達する前に失われることが判明した。
そこで、無音の情報を認識処理の外側で保持する構成に変える。

    音声ファイル
      ↓ ffmpeg で 16kHz/モノラルへ変換
      ↓ Silero VAD で発話区間を取得        ← 沈黙の情報をここで保持する
      ↓ 短い間で隔てられた区間は結合
      ↓ ブロックごとに Whisper へ渡す（内蔵VADは無効）
      ↓ ブロック間に沈黙マーカーを挿入
    テキスト

内蔵VADを無効にしたうえで無音をそのまま認識処理へ渡す方法は採らない。
無音を与えると同じフレーズを繰り返す既知の挙動があり、R-1（発話に忠実であること）に
違反する出力が生じるため。発話区間だけを切り出して渡すことで回避する。

使い方:
    venv/bin/python spike/silence.py <音声ファイル>
"""

import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from config import settings  # noqa: E402
from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: E402
from services.async_processor import get_whisper_model  # noqa: E402

SAMPLE_RATE = 16000

# --- 暫定値: 記法・閾値とも第2段階では確定させない（指示書3章） ---

# 沈黙マーカー。R-7 が求めるのは「沈黙があったと分かること」のみで長短の区別は不要。
# そのため秒数は本文に埋め込まない
SILENCE_MARKER = "..."

# この秒数以上あいた場合のみ沈黙として扱う。
# Silero VAD は息継ぎ程度（0.6秒前後）でも区間を分けるため、すべてを沈黙とすると
# 息継ぎのたびにマーカーが入る。また区間が細切れになるほど Whisper に渡る文脈が減り
# 認識精度が落ちるため、閾値未満の間で隔てられた区間は結合する
SILENCE_THRESHOLD_SEC = 1.5

# --- ここまで暫定値 ---


def load_audio(path: Path) -> np.ndarray:
    """音声ファイルを 16kHz/モノラルの float32 波形として読み込む

    変換手順は app/services/async_processor.py と同じ
    """
    converted = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-ar", str(SAMPLE_RATE), "-ac", "1", converted],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with wave.open(converted) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0
    except subprocess.CalledProcessError:
        raise ValueError("音声変換に失敗しました")
    finally:
        if os.path.exists(converted):
            os.remove(converted)


def detect_speech_blocks(audio: np.ndarray) -> list:
    """発話区間を検出し、短い間で隔てられたものを結合する

    Returns:
        [{"start": 秒, "end": 秒}, ...]
    """
    timestamps = get_speech_timestamps(
        audio,
        VadOptions(min_silence_duration_ms=settings.WHISPER_VAD_MIN_SILENCE_MS),
        sampling_rate=SAMPLE_RATE,
    )
    regions = [
        {"start": t["start"] / SAMPLE_RATE, "end": t["end"] / SAMPLE_RATE}
        for t in timestamps
    ]

    blocks = []
    for region in regions:
        if blocks and region["start"] - blocks[-1]["end"] < SILENCE_THRESHOLD_SEC:
            blocks[-1]["end"] = region["end"]
        else:
            blocks.append(dict(region))
    return blocks


def transcribe_block(audio: np.ndarray, block: dict) -> str:
    """発話ブロックを文字起こしする

    設定は app/config.py をそのまま使う（本体と同じ条件で検証するため）。
    ただし vad_filter は False 固定。無音の判定は外部VADが済ませているため
    """
    model = get_whisper_model()
    chunk = audio[int(block["start"] * SAMPLE_RATE) : int(block["end"] * SAMPLE_RATE)]

    params = {
        "language": "ja",
        "beam_size": settings.WHISPER_BEAM_SIZE,
        "best_of": settings.WHISPER_BEST_OF,
        "temperature": settings.WHISPER_TEMPERATURE,
        "vad_filter": False,
        "condition_on_previous_text": settings.WHISPER_CONDITION_ON_PREVIOUS_TEXT,
        "repetition_penalty": settings.WHISPER_REPETITION_PENALTY,
        "compression_ratio_threshold": settings.WHISPER_COMPRESSION_RATIO_THRESHOLD,
        "log_prob_threshold": settings.WHISPER_LOG_PROB_THRESHOLD,
        "no_speech_threshold": settings.WHISPER_NO_SPEECH_THRESHOLD,
    }
    if settings.WHISPER_NO_REPEAT_NGRAM_SIZE > 0:
        params["no_repeat_ngram_size"] = settings.WHISPER_NO_REPEAT_NGRAM_SIZE

    segments, _ = model.transcribe(chunk, **params)
    # R-1, R-2: Whisper の出力を加工しない
    return "".join(s.text for s in segments).strip()


def main(audio_path: Path) -> None:
    audio = load_audio(audio_path)
    duration = len(audio) / SAMPLE_RATE

    started = time.monotonic()
    get_whisper_model()
    load_elapsed = time.monotonic() - started

    started = time.monotonic()
    blocks = detect_speech_blocks(audio)
    vad_elapsed = time.monotonic() - started

    started = time.monotonic()
    results = [(block, transcribe_block(audio, block)) for block in blocks]
    transcribe_elapsed = time.monotonic() - started

    print(f"\n=== 発話ブロック（{len(blocks)}件） / 音声 {duration:.2f}秒 ===")
    previous_end = 0.0
    parts = []
    for block, text in results:
        gap = block["start"] - previous_end
        if gap >= SILENCE_THRESHOLD_SEC:
            print(f"{'':>21}{SILENCE_MARKER}  ← 沈黙 {gap:.2f}秒")
            parts.append(SILENCE_MARKER)
        print(f"[{block['start']:7.2f} - {block['end']:7.2f}] {text}")
        parts.append(text)
        previous_end = block["end"]

    trailing = duration - previous_end
    if trailing >= SILENCE_THRESHOLD_SEC:
        print(f"{'':>21}{SILENCE_MARKER}  ← 沈黙 {trailing:.2f}秒（末尾）")
        parts.append(SILENCE_MARKER)

    print("\n=== 全文（原文のまま） ===")
    print("".join(parts))

    total = vad_elapsed + transcribe_elapsed
    print(
        f"\n=== VAD: {vad_elapsed:.2f}秒 ｜ 文字起こし: {transcribe_elapsed:.2f}秒 "
        f"｜ 合計 {total:.2f}秒（リアルタイム比 {total / duration:.2f}）"
        f"｜ モデルロード: {load_elapsed:.2f}秒 ==="
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        sys.exit(1)

    main(path)
