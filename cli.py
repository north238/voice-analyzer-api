"""開発中の思考を音声で吐き出し、LLM に渡すための忠実なテキストとして残すツール。

使い方:
    python cli.py                 マイクから入力する（Ctrl+C で終了）
    python cli.py <音声ファイル>   音声ファイルを処理する

結果は標準出力に表示しつつ、同時に Markdown ファイルへ追記する。
ログは標準エラー出力に出るため、`2>/dev/null` で結果だけを取り出せる。

構造について:
    発話区間が確定するたびに、表示と書き出しの両方へ流す。セッション終了を待たない。
    これは R-8（話している間に確認できること）と
    R-12（異常時に取得済みの発話が失われないこと）を同時に満たすため。
    処理が完了してからまとめて出力する構造では、どちらも満たせない。
"""

import argparse
import os
import queue
import subprocess
import sys
import tempfile
import threading
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

from config import settings  # noqa: E402
from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: E402
from services.async_processor import get_whisper_model  # noqa: E402

SAMPLE_RATE = 16000

# --- 暫定値: 記法・閾値とも確定させない（docs/03_usable_state.md 4章） ---

# 沈黙マーカー。R-7 が求めるのは「沈黙があったと分かること」のみで長短の区別は不要
SILENCE_MARKER = "..."

# この秒数以上あいた場合のみ沈黙として扱う。
# 閾値未満の間で隔てられた区間は結合する。
# 注: これは要求由来の制約ではない。息継ぎにマーカーを入れること自体は R-1 に反しない
#     （実際にあった間の記録であり、推測でも修正でもない）。
#     マーカーが多すぎると下流の LLM にとってノイズになるという実用上の判断であり、
#     暫定の設計判断として後から自由に変えてよい
SILENCE_THRESHOLD_SEC = 1.5

# --- ここまで暫定値 ---

# マイク入力で、直近の音声に対して VAD をかける間隔
VAD_INTERVAL_SEC = 1.0

# 発話が途切れたと判断してから文字起こしに回すまでの余裕。
# VAD が区間の終わりを確定するには、後続に無音が続く必要があるため
TAIL_MARGIN_SEC = SILENCE_THRESHOLD_SEC + 0.5

# 1コールバックあたりの取得サンプル数（100ms分）。
# 未指定にすると 1ms 単位の細切れで届き（実測で毎秒約1068回）、
# ループが空転して処理が進まなくなる
BLOCK_SIZE = 1600

# キューの待ち時間。無音でもこの間隔でループを回して Ctrl+C を受け取れるようにする。
# タイムアウトなしのブロッキング取得にすると、音声が来るまで割り込みが処理されない
QUEUE_TIMEOUT_SEC = 0.5


class Recorder:
    """セッションの記録係。

    発話が確定するたびに追記して即座に flush + fsync する。
    finally での一括書き出しに頼らないのは、強制終了時に実行されないため（R-12）。
    """

    def __init__(self, output_dir: Path):
        started = datetime.now()
        output_dir.mkdir(parents=True, exist_ok=True)
        self.path = output_dir / f"{started:%Y-%m-%d_%H%M%S}.md"

        # セッション開始時点でファイルを作る。異常終了しても記録が残るようにするため
        self._file = self.path.open("w", encoding="utf-8")
        self._write(f"# {started:%Y-%m-%d %H:%M:%S}\n\n")

    def _write(self, text: str) -> None:
        self._file.write(text)
        self._file.flush()
        os.fsync(self._file.fileno())

    def append(self, text: str) -> None:
        self._write(text)

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()


def to_waveform(pcm: np.ndarray) -> np.ndarray:
    """int16 PCM を Whisper が扱う float32 波形にする"""
    return pcm.astype(np.float32) / 32768.0


def load_file(path: Path) -> np.ndarray:
    """音声ファイルを 16kHz/モノラルの float32 波形として読み込む"""
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
        return to_waveform(pcm)
    except subprocess.CalledProcessError:
        raise SystemExit(f"音声の読み込みに失敗しました: {path}")
    finally:
        if os.path.exists(converted):
            os.remove(converted)


def find_speech_regions(audio: np.ndarray) -> list:
    """Silero VAD で発話区間を求め、短い間で隔てられたものを結合する"""
    timestamps = get_speech_timestamps(
        audio,
        VadOptions(min_silence_duration_ms=settings.WHISPER_VAD_MIN_SILENCE_MS),
        sampling_rate=SAMPLE_RATE,
    )
    regions = []
    for t in timestamps:
        region = {"start": t["start"] / SAMPLE_RATE, "end": t["end"] / SAMPLE_RATE}
        if regions and region["start"] - regions[-1]["end"] < SILENCE_THRESHOLD_SEC:
            regions[-1]["end"] = region["end"]
        else:
            regions.append(region)
    return regions


def transcribe(audio: np.ndarray) -> str:
    """発話区間を文字起こしする。

    vad_filter は False 固定。無音の判定は外部 VAD が済ませている。
    内蔵 VAD に任せると無音区間が除去され、沈黙の情報が失われる（R-7）。
    """
    model = get_whisper_model()
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

    segments, _ = model.transcribe(audio, **params)
    # R-1, R-2: Whisper の出力を加工せずそのまま返す
    return "".join(s.text for s in segments).strip()


class Session:
    """確定した発話を、表示と記録の両方へ流す"""

    def __init__(self, recorder: Recorder):
        self.recorder = recorder
        self.previous_end = 0.0
        self.has_output = False

    def emit(self, text: str, start: float, end: float) -> None:
        if not text:
            self.previous_end = end
            return

        gap = start - self.previous_end
        if self.has_output and gap >= SILENCE_THRESHOLD_SEC:
            print(SILENCE_MARKER, flush=True)
            self.recorder.append(f"{SILENCE_MARKER}\n\n")

        print(text, flush=True)
        self.recorder.append(f"{text}\n\n")
        self.previous_end = end
        self.has_output = True


def run_file(path: Path, session: Session) -> None:
    """音声ファイルを処理する。区間ごとに確定させ、逐次出力する"""
    audio = load_file(path)
    for region in find_speech_regions(audio):
        chunk = audio[int(region["start"] * SAMPLE_RATE) : int(region["end"] * SAMPLE_RATE)]
        session.emit(transcribe(chunk), region["start"], region["end"])


def run_microphone(session: Session, device: int = None) -> None:
    """マイクから入力する。

    R-6（冒頭が失われないこと）のため、録音を先に開始してから
    モデルをロードする。ロードには実測で約1.3秒かかるが、
    その間の音声もバッファに溜まるため冒頭は失われない。
    """
    import sounddevice as sd

    frames = queue.Queue()

    def on_audio(indata, _frames, _time, status):
        # sounddevice のコールバックは別スレッドから呼ばれる。
        # ここで重い処理をすると音声のドロップアウトを招くため、キューに積むだけにする
        frames.put(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=device,
        blocksize=BLOCK_SIZE,
        callback=on_audio,
    )
    stream.start()
    print("録音を開始しました。Ctrl+C で終了します。", file=sys.stderr)

    # 録音を止めずにモデルを読み込む（R-6）
    loader = threading.Thread(target=get_whisper_model, daemon=True)
    loader.start()

    buffer = np.empty(0, dtype=np.float32)
    consumed = 0.0  # バッファ先頭が、セッション開始から何秒地点にあたるか

    def drop_front(samples: int) -> None:
        """バッファ先頭を捨て、捨てた分だけ経過時間を進める"""
        nonlocal buffer, consumed
        if samples <= 0:
            return
        buffer = buffer[samples:]
        consumed += samples / SAMPLE_RATE

    try:
        while True:
            # 溜まった音声を取り出す。
            # タイムアウト付きにして、無音でもループを回して Ctrl+C を受け取れるようにする
            chunks = []
            try:
                chunks.append(frames.get(timeout=QUEUE_TIMEOUT_SEC))
            except queue.Empty:
                pass
            while not frames.empty():
                chunks.append(frames.get())

            if chunks:
                buffer = np.concatenate(
                    [buffer] + [to_waveform(c.flatten()) for c in chunks]
                )

            if len(buffer) < VAD_INTERVAL_SEC * SAMPLE_RATE:
                continue

            loader.join()  # 初回のみ待つ。2回目以降はロード済みで即座に返る

            regions = find_speech_regions(buffer)
            if not regions:
                # 発話が無いので、末尾の余裕分だけ残して捨てる。
                # 捨てないと沈黙が続くほどバッファが伸び、VAD の所要時間も増え続ける
                # （実測: 10分の無音でバッファ36MB、VAD 1.42秒/周回）
                drop_front(len(buffer) - int(TAIL_MARGIN_SEC * SAMPLE_RATE))
                continue

            # 末尾の区間は、まだ発話が続いている可能性があるため確定させない。
            # 十分な無音が後続していれば確定とみなす
            buffer_end = len(buffer) / SAMPLE_RATE
            settled = [r for r in regions if buffer_end - r["end"] >= TAIL_MARGIN_SEC]
            if not settled:
                # 発話の途中。捨てると欠落するため、バッファはそのまま保持する（R-5）
                continue

            for region in settled:
                chunk = buffer[
                    int(region["start"] * SAMPLE_RATE) : int(region["end"] * SAMPLE_RATE)
                ]
                session.emit(
                    transcribe(chunk), consumed + region["start"], consumed + region["end"]
                )

            # 確定させた分をバッファから捨てる
            drop_front(int(settled[-1]["end"] * SAMPLE_RATE))

    except KeyboardInterrupt:
        print("", file=sys.stderr)
    finally:
        stream.stop()
        stream.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("audio", nargs="?", help="音声ファイル（省略時はマイク入力）")
    parser.add_argument("--device", type=int, default=None, help="入力デバイスの番号")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "notes", help="記録の保存先"
    )
    args = parser.parse_args()

    recorder = Recorder(args.output_dir)
    session = Session(recorder)
    print(f"記録先: {recorder.path}", file=sys.stderr)

    try:
        if args.audio:
            path = Path(args.audio)
            if not path.exists():
                raise SystemExit(f"ファイルが見つかりません: {path}")
            run_file(path, session)
        else:
            run_microphone(session, args.device)
    finally:
        recorder.close()


if __name__ == "__main__":
    main()
