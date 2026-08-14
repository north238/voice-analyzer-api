"""R-2（言い直しの消失）の原因を切り分ける比較スクリプト（使い捨て）

第2段階の検証で、内蔵VAD構成では言い直しの「いや」が消え、
外部VAD構成では残るという差が出た。この差が何に由来するのかを確定させる。

当初「condition_on_previous_text による文脈の引き継ぎが原因では」という仮説があったが、
app/config.py で既に False であり、両構成とも同じ値を渡している。この経路は成立しない。

ただし condition_on_previous_text が制御するのは窓「間」の引き継ぎであり、
窓「内」の文脈は常に効く。両構成では Whisper に渡る音声の形が違う。

    内蔵VAD構成: 81秒 → 無音除去後57.1秒を30秒窓に詰める（約1.9窓）
    外部VAD構成: 5ブロックを独立に渡す（「いや」を含むブロック3は12.28秒）

そこで「音声の渡し方」と「vad_filter」を独立に変えて切り分ける。

    A: 全体      / vad_filter=True   現状の内蔵VAD構成
    B: 全体      / vad_filter=False  vad_filter単体の効果を見る
    C: ブロックのみ / vad_filter=False  現状の外部VAD構成の該当部分
    D: ブロックのみ / vad_filter=True   音声長を揃えてvad_filterだけ変える

読み取り方:
    C と D で差       → vad_filter そのものが原因
    C=D かつ A と D で差 → 窓に入る発話量が原因
    どれも同じ         → モデル固有の揺らぎ（n=1の偶然）

使い方:
    venv/bin/python spike/compare_r2.py <音声ファイル>
"""

import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from config import settings  # noqa: E402
from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: E402
from services.async_processor import get_whisper_model  # noqa: E402

SAMPLE_RATE = 16000
SILENCE_THRESHOLD_SEC = 1.5  # spike/silence.py と同じ暫定値

# 検証したい語。出力に残っているかを判定するために使う
TARGET_WORD = "いや"

# 各条件を何回実行するか（temperature=0 なので決定的なはずだが実測で確認する）
RUNS = 2


def load_audio(path: Path) -> np.ndarray:
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
    finally:
        if os.path.exists(converted):
            os.remove(converted)


def detect_blocks(audio: np.ndarray) -> list:
    """spike/silence.py と同じロジックで発話ブロックを求める"""
    timestamps = get_speech_timestamps(
        audio,
        VadOptions(min_silence_duration_ms=settings.WHISPER_VAD_MIN_SILENCE_MS),
        sampling_rate=SAMPLE_RATE,
    )
    regions = [
        {"start": t["start"] / SAMPLE_RATE, "end": t["end"] / SAMPLE_RATE} for t in timestamps
    ]
    blocks = []
    for region in regions:
        if blocks and region["start"] - blocks[-1]["end"] < SILENCE_THRESHOLD_SEC:
            blocks[-1]["end"] = region["end"]
        else:
            blocks.append(dict(region))
    return blocks


def transcribe(audio: np.ndarray, vad_filter: bool) -> str:
    """設定は本体と揃える。vad_filter だけを引数で変える"""
    model = get_whisper_model()
    params = {
        "language": "ja",
        "beam_size": settings.WHISPER_BEAM_SIZE,
        "best_of": settings.WHISPER_BEST_OF,
        "temperature": settings.WHISPER_TEMPERATURE,
        "vad_filter": vad_filter,
        "condition_on_previous_text": settings.WHISPER_CONDITION_ON_PREVIOUS_TEXT,
        "repetition_penalty": settings.WHISPER_REPETITION_PENALTY,
        "compression_ratio_threshold": settings.WHISPER_COMPRESSION_RATIO_THRESHOLD,
        "log_prob_threshold": settings.WHISPER_LOG_PROB_THRESHOLD,
        "no_speech_threshold": settings.WHISPER_NO_SPEECH_THRESHOLD,
    }
    if settings.WHISPER_NO_REPEAT_NGRAM_SIZE > 0:
        params["no_repeat_ngram_size"] = settings.WHISPER_NO_REPEAT_NGRAM_SIZE

    if vad_filter:
        params["vad_parameters"] = VadOptions(
            min_silence_duration_ms=settings.WHISPER_VAD_MIN_SILENCE_MS,
            speech_pad_ms=settings.WHISPER_VAD_SPEECH_PAD_MS,
        )

    segments, _ = model.transcribe(audio, **params)
    return "".join(s.text for s in segments).strip()


def main(audio_path: Path) -> None:
    audio = load_audio(audio_path)
    get_whisper_model()

    blocks = detect_blocks(audio)
    # 検証対象の語を含むブロックを探す（外部VAD構成での出力を再現して特定する）
    target_idx = None
    for i, block in enumerate(blocks):
        chunk = audio[int(block["start"] * SAMPLE_RATE) : int(block["end"] * SAMPLE_RATE)]
        if TARGET_WORD in transcribe(chunk, vad_filter=False):
            target_idx = i
            break

    if target_idx is None:
        print(f"「{TARGET_WORD}」を含むブロックが見つかりませんでした")
        return

    block = blocks[target_idx]
    chunk = audio[int(block["start"] * SAMPLE_RATE) : int(block["end"] * SAMPLE_RATE)]
    print(
        f"\n対象ブロック: #{target_idx + 1} "
        f"[{block['start']:.2f} - {block['end']:.2f}] {block['end'] - block['start']:.2f}秒"
    )
    print(f"音声全体: {len(audio) / SAMPLE_RATE:.2f}秒\n")

    conditions = [
        ("A", "全体", audio, True),
        ("B", "全体", audio, False),
        ("C", "ブロックのみ", chunk, False),
        ("D", "ブロックのみ", chunk, True),
    ]

    for label, scope, data, vad in conditions:
        print(f"{'=' * 70}")
        print(f"条件{label}: {scope} / vad_filter={vad}")
        outputs = [transcribe(data, vad) for _ in range(RUNS)]
        stable = len(set(outputs)) == 1
        found = TARGET_WORD in outputs[0]
        print(f"  「{TARGET_WORD}」: {'あり' if found else 'なし'}"
              f" ／ {RUNS}回の出力: {'一致' if stable else '不一致'}")
        for i, out in enumerate(outputs if not stable else outputs[:1], 1):
            prefix = f"  [{i}回目] " if not stable else "  "
            print(f"{prefix}{out}")
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        sys.exit(1)
    main(path)
