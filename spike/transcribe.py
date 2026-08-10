"""認識精度の検証用スパイク（使い捨て）

音声ファイルを文字起こしして標準出力に出すだけのスクリプト。
docs/01_cleaanup_and_spike.md のタスクB（技術的な固有名詞の誤認識がどの程度発生するか）
を確かめるために使う。

app/services/async_processor.py の transcribe_async() をそのまま呼ぶ。
ここで独自に Whisper を呼ぶと app/config.py の設定（VAD、ハルシネーション抑制の閾値など）が
反映されず、本番と異なる条件での検証になってしまうため。

使い方:
    venv/bin/python spike/transcribe.py <音声ファイル>
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from services.async_processor import get_whisper_model, transcribe_async  # noqa: E402


async def main(audio_path: Path) -> None:
    audio_data = audio_path.read_bytes()

    # モデルロードと文字起こしを分けて測る。
    # 合算すると、ロードにかかる時間を文字起こしの速度と誤読してしまうため
    started = time.monotonic()
    get_whisper_model()
    load_elapsed = time.monotonic() - started

    started = time.monotonic()
    text, segments = await transcribe_async(audio_data, suffix=audio_path.suffix)
    elapsed = time.monotonic() - started

    print(f"\n=== セグメント（{len(segments)}件） ===")
    previous_end = 0.0
    for seg in segments:
        # セグメント間の空きは沈黙にあたる。R-7 の検討材料として出しておく
        gap = seg["start"] - previous_end
        gap_note = f"  ← 前のセグメントから {gap:.1f}秒あき" if gap >= 1.0 else ""
        print(f"[{seg['start']:7.2f} - {seg['end']:7.2f}] {seg['text']}{gap_note}")
        previous_end = seg["end"]

    print("\n=== 全文（原文のまま） ===")
    print(text)

    audio_seconds = segments[-1]["end"] if segments else 0.0
    ratio = elapsed / audio_seconds if audio_seconds else 0.0
    print(
        f"\n=== 文字起こし: {elapsed:.2f}秒 "
        f"（音声 {audio_seconds:.1f}秒 / リアルタイム比 {ratio:.2f}）"
        f"｜モデルロード: {load_elapsed:.2f}秒 ==="
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        sys.exit(1)

    asyncio.run(main(path))
