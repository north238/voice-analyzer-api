"""開発中の思考を音声で吐き出し、LLM に渡すための忠実なテキストとして残すツール。

使い方:
    python cli.py                 マイクから入力する（Ctrl+C で終了）
    python cli.py <音声ファイル>   音声ファイルを処理する

結果は標準出力に表示しつつ、同時に Markdown ファイルへ追記する。
ログは標準エラー出力に出るため、`2>/dev/null` で結果だけを取り出せる。
画面に出るのは異常時だけで、動作の記録は `logs/` にのみ残る。

構造について:
    発話区間が確定するたびに、表示と書き出しの両方へ流す。セッション終了を待たない。
    これは R-8（話している間に確認できること）と
    R-12（異常時に取得済みの発話が失われないこと）を同時に満たすため。
    処理が完了してからまとめて出力する構造では、どちらも満たせない。
"""

import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

from config import settings  # noqa: E402
from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: E402
from services.whisper_model import get_whisper_model  # noqa: E402
from utils.logger import logger  # noqa: E402

SAMPLE_RATE = 16000

# 設定ファイル。無くても動く（R-9）。利用者が直接編集できる形式（R-21）
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

# 沈黙マーカー（第4段階で確定）。
# R-7 が求めるのは「沈黙があったと分かること」のみで、長短の区別は不要。
# 出力の読み手は LLM であり、沈黙と発話内容を混同しないことを基準に選んだ。
# 以前は "..." を使っていたが、三点リーダとして発話本文にも現れうるため区別できない
# （実際に過去の出力にも本文中の "..." があった）。角括弧は発話に現れず、
# 注釈であることが読み手から明確に判別できる
SILENCE_MARKER = "[沈黙]"

# この秒数以上あいた場合のみ沈黙として扱う（第4段階で確定。値は据え置き）。
# 閾値未満の間で隔てられた区間は結合する。
# 実使用で、息継ぎがマーカー化せず思考の間だけが記録されることを確認済み。
# 注: これは要求由来の制約ではない。息継ぎにマーカーを入れること自体は R-1 に反しない
#     （実際にあった間の記録であり、推測でも修正でもない）。
#     マーカーが多すぎると下流の LLM にとってノイズになるという実用上の判断
SILENCE_THRESHOLD_SEC = 1.5

# マイク入力で、直近の音声に対して VAD をかける間隔
VAD_INTERVAL_SEC = 1.0

# 発話が途切れたと判断してから文字起こしに回すまでの余裕（第4段階で確定。値は据え置き）。
# VAD が区間の終わりを確定するには、後続に無音が続く必要がある。
# この値は表示までの待ち時間に直結する（実測 3.1〜7.1秒のうち 2.0秒がこれ）。
# 短縮すると待ちは減るが、発話が途中で切られて区間が細切れになり精度が落ちる
# （第2段階で、短い区間ほど精度が落ちることを実測済み）
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
        logger.error(f"音声の読み込みに失敗: {path}")
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


def log_transcription(audio: np.ndarray, start: float, end: float) -> str:
    """文字起こしして、どの区間をどれだけの時間で処理したかを記録に残す"""
    started = time.perf_counter()
    text = transcribe(audio)
    logger.debug(
        f"区間確定: {start:.1f}〜{end:.1f}秒（{end - start:.1f}秒）"
        f" 処理{time.perf_counter() - started:.2f}秒 {len(text)}文字"
    )
    return text


class StatusLine:
    """動作していることを示す表示（R-22）。

    長い沈黙を挟んで使うツールのため、何も出ない状態が「正常な待機」なのか
    「処理の停止」なのかを利用者が区別できる必要がある。

    標準エラーへ出し、同じ行を上書きする。標準出力は文字起こし結果だけに保つため
    （混ぜると R-8 の確認を妨げ、`2>/dev/null` で結果だけを取り出せなくなる）。
    リダイレクト時やパイプ時は表示しない。
    """

    # 動いていることが分かる最小限の表示にとどめる。
    # 経過時間や処理件数は R-22 の充足に不要なため出さない
    FRAMES = "|/-\\"

    def __init__(self, stream=sys.stderr):
        self.stream = stream
        self.enabled = stream.isatty()
        self.index = 0
        self.shown = False

    def tick(self, label: str) -> None:
        if not self.enabled:
            return
        frame = self.FRAMES[self.index % len(self.FRAMES)]
        self.index += 1
        self.stream.write(f"\r{frame} {label}    ")
        self.stream.flush()
        self.shown = True

    def clear(self) -> None:
        """結果を表示する前に、状態表示の行を消す"""
        if not self.enabled or not self.shown:
            return
        self.stream.write("\r\033[K")
        self.stream.flush()
        self.shown = False


class Session:
    """確定した発話を、表示と記録の両方へ流す"""

    def __init__(self, recorder: Recorder, status: "StatusLine" = None):
        self.recorder = recorder
        self.status = status
        self.previous_end = 0.0
        self.has_output = False
        self.count = 0

    def emit(self, text: str, start: float, end: float) -> None:
        if not text:
            # 発話区間として検出されたのにテキストが得られなかった。
            # 出力からは欠落したことが分からないため記録に残す（requirements.md 5.7）
            logger.info(f"空の結果: {start:.1f}〜{end:.1f}秒（{end - start:.1f}秒）")
            self.previous_end = end
            return

        # 状態表示の行を消してから結果を出す（表示が結果を押し流さないようにする）
        if self.status:
            self.status.clear()

        gap = start - self.previous_end
        if self.has_output and gap >= SILENCE_THRESHOLD_SEC:
            logger.info(f"沈黙マーカー: {gap:.1f}秒")
            print(SILENCE_MARKER, flush=True)
            self.recorder.append(f"{SILENCE_MARKER}\n\n")

        print(text, flush=True)
        self.recorder.append(f"{text}\n\n")
        self.previous_end = end
        self.has_output = True
        self.count += 1


def load_config() -> dict:
    """設定ファイルを読む。無ければ既定値で動く（R-9）。

    設定できる項目は、利用者が実際に変更したくなるものに絞っている（R-20, R-21）。
    項目を増やすほど「単純な操作で開始できること」から遠ざかるため、
    沈黙の閾値などの動作を左右する値は意図的に含めていない。
    """
    defaults = {
        "output_dir": "notes",
        "model_size": "",  # 空なら app/config.py の既定（small）に従う
    }

    if not CONFIG_PATH.exists():
        return defaults

    try:
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        # 壊れた設定で起動できなくなるより、既定値で動くほうがよい
        logger.warning(f"設定を読めませんでした（既定値で続行）: {e}")
        return defaults

    unknown = set(loaded) - set(defaults)
    if unknown:
        logger.warning(f"設定に未知の項目があります（無視）: {', '.join(sorted(unknown))}")

    defaults.update({k: v for k, v in loaded.items() if k in defaults})
    return defaults


def run_file(path: Path, session: Session, status: "StatusLine" = None) -> None:
    """音声ファイルを処理する。区間ごとに確定させ、逐次出力する"""
    audio = load_file(path)
    regions = find_speech_regions(audio)
    logger.debug(f"発話区間: {len(regions)}件 / 全体{len(audio) / SAMPLE_RATE:.1f}秒")
    for region in regions:
        chunk = audio[int(region["start"] * SAMPLE_RATE) : int(region["end"] * SAMPLE_RATE)]
        if status:
            status.tick("文字起こし中")
        text = log_transcription(chunk, region["start"], region["end"])
        session.emit(text, region["start"], region["end"])


def run_microphone(session: Session, device: int = None, status: "StatusLine" = None) -> None:
    """マイクから入力する。

    R-6（冒頭が失われないこと）のため、録音を先に開始してから
    モデルをロードする。ロードには実測で約1.3秒かかるが、
    その間の音声もバッファに溜まるため冒頭は失われない。
    """
    import sounddevice as sd

    frames = queue.Queue()

    # 入力の取りこぼし回数。発話が欠落する経路のひとつだが（R-5）、
    # 出力からは欠落したことが分からないため記録に残す
    overflows = 0
    reported_overflows = 0

    def on_audio(indata, _frames, _time, callback_status):
        # sounddevice のコールバックは別スレッドから呼ばれる。
        # ここで重い処理をすると音声のドロップアウトを招くため、
        # キューに積むことと、取りこぼしを数えることだけに留める
        nonlocal overflows
        if callback_status:
            overflows += 1
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
    was_speaking = False  # 直前の周回で発話を検出していたか（変化した時だけ記録する）

    def drop_front(samples: int) -> None:
        """バッファ先頭を捨て、捨てた分だけ経過時間を進める"""
        nonlocal buffer, consumed
        if samples <= 0:
            return
        buffer = buffer[samples:]
        consumed += samples / SAMPLE_RATE

    try:
        while True:
            # 取りこぼしは画面にも出す。状態表示と混ざらないよう行を消してから出す
            if overflows != reported_overflows:
                if status:
                    status.clear()
                logger.warning(f"音声の取りこぼしを検出（累計 {overflows} 回）")
                reported_overflows = overflows

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
            if status:
                status.tick("待機中" if not regions else "発話を検出中")

            # VAD は1秒ごとに回るため、毎周回記録すると待機中だけでログが埋まる。
            # 状態が変わった時にだけ残す
            if bool(regions) != was_speaking:
                was_speaking = bool(regions)
                logger.debug(
                    f"{'発話を検出' if was_speaking else '待機'}"
                    f"（バッファ{len(buffer) / SAMPLE_RATE:.1f}秒）"
                )

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
                if status:
                    status.tick("文字起こし中")
                start = consumed + region["start"]
                end = consumed + region["end"]
                session.emit(log_transcription(chunk, start, end), start, end)

            # 確定させた分をバッファから捨てる
            drop_front(int(settled[-1]["end"] * SAMPLE_RATE))

    except KeyboardInterrupt:
        if status:
            status.clear()
        print("", file=sys.stderr)
    finally:
        stream.stop()
        stream.close()


def main() -> None:
    config = load_config()

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("audio", nargs="?", help="音声ファイル（省略時はマイク入力）")
    parser.add_argument("--device", type=int, default=None, help="入力デバイスの番号")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"記録の保存先（既定: {config['output_dir']}）",
    )
    args = parser.parse_args()

    # コマンドラインの指定が設定ファイルより優先される
    output_dir = args.output_dir or Path(config["output_dir"]).expanduser()

    # settings は import 時（このファイルの先頭）に環境変数を読み終えているため、
    # ここで os.environ を書き換えても間に合わない。属性へ直接代入する。
    # 環境変数での指定があればそちらを優先する（従来の setdefault と同じ扱い）
    if config["model_size"] and not os.getenv("WHISPER_MODEL_SIZE"):
        settings.WHISPER_MODEL_SIZE = config["model_size"]

    status = StatusLine()
    recorder = Recorder(output_dir)
    session = Session(recorder, status)
    print(f"記録先: {recorder.path.resolve()}", file=sys.stderr)

    # 記録と突き合わせるための1行。実際に使われた設定を残す
    logger.info(
        f"セッション開始: 記録先={recorder.path.resolve()}"
        f" 入力={args.audio or 'マイク'}"
        f" モデル={settings.WHISPER_MODEL_SIZE}"
    )

    try:
        if args.audio:
            path = Path(args.audio)
            if not path.exists():
                logger.error(f"ファイルが見つかりません: {path}")
                raise SystemExit(f"ファイルが見つかりません: {path}")
            run_file(path, session, status)
        else:
            run_microphone(session, args.device, status)
    except Exception:
        # 画面に出て消えるだけでは後から原因を追えない。
        # ここでトレースバックを出したうえで SystemExit に変える。
        # そのまま再送出すると同じトレースバックが画面に二重に出る。
        # SystemExit / KeyboardInterrupt は正常な終了経路なので対象外（Exception を継承しない）
        status.clear()
        logger.exception("異常終了")
        raise SystemExit(1)
    finally:
        status.clear()
        recorder.close()
        logger.info(f"セッション終了: 発話{session.count}件")


if __name__ == "__main__":
    main()
