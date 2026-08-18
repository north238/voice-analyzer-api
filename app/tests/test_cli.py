"""cli.py のテスト

音声認識そのものは対象にしない。モデルのロードに時間がかかり、
結果も録音条件に左右されるため、テストで固定できない。

ここで守るのは要求に直結する挙動に絞る:
沈黙マーカーの挿入条件（R-7）、記録の即時書き出し（R-12）、
設定の反映（R-20）、そして欠落や異常が記録に残ること。
"""

import sys
import types

import numpy as np
import pytest

import cli
from config import settings


# --- 波形の変換 ---------------------------------------------------------


def test_to_waveform():
    """int16 PCM を ±1.0 の float32 に正規化する"""
    waveform = cli.to_waveform(np.array([0, 32767, -32768], dtype=np.int16))

    assert waveform.dtype == np.float32
    assert waveform[0] == 0.0
    assert 0.99 < waveform[1] < 1.0
    assert waveform[2] == -1.0


# --- 発話区間の結合 -----------------------------------------------------


def fake_timestamps(*gaps_and_lengths):
    """秒指定から VAD の返り値（サンプル単位）を作る"""

    def build(_audio, _options, sampling_rate=None):
        return [
            {"start": int(start * cli.SAMPLE_RATE), "end": int(end * cli.SAMPLE_RATE)}
            for start, end in gaps_and_lengths
        ]

    return build


def test_find_speech_regions_merges_short_gaps(monkeypatch):
    """閾値未満の間で隔てられた区間は結合し、閾値以上なら分ける"""
    monkeypatch.setattr(
        cli,
        "get_speech_timestamps",
        # 0.5秒の間（閾値未満）で結合、その後 2.0秒の間（閾値以上）で分離
        fake_timestamps((0.0, 1.0), (1.5, 2.0), (4.0, 5.0)),
    )

    regions = cli.find_speech_regions(np.zeros(10, dtype=np.float32))

    assert regions == [{"start": 0.0, "end": 2.0}, {"start": 4.0, "end": 5.0}]


# --- 記録 ---------------------------------------------------------------


def test_recorder_creates_file_before_any_speech(tmp_path):
    """発話がなくてもセッション開始時点でファイルができる（R-12）"""
    recorder = cli.Recorder(tmp_path)
    try:
        assert recorder.path.exists()
    finally:
        recorder.close()


def test_recorder_writes_without_close(tmp_path):
    """追記のたびに書き出す。close を待たない（R-12）

    強制終了では finally が実行されないため、close 時にまとめて
    書き出す構造では取得済みの発話が失われる。
    """
    recorder = cli.Recorder(tmp_path)
    try:
        recorder.append("途中まで\n")
        assert "途中まで" in recorder.path.read_text(encoding="utf-8")
    finally:
        recorder.close()


# --- 沈黙マーカー -------------------------------------------------------


def emit_all(tmp_path, utterances):
    """発話の並びを流し込み、書き出された記録を返す"""
    recorder = cli.Recorder(tmp_path)
    session = cli.Session(recorder)
    try:
        for text, start, end in utterances:
            session.emit(text, start, end)
    finally:
        recorder.close()
    return recorder.path.read_text(encoding="utf-8"), session


def test_silence_marker_inserted(tmp_path):
    """閾値以上あいたら沈黙が分かるようにする（R-7）"""
    gap = cli.SILENCE_THRESHOLD_SEC + 0.1
    recorded, _ = emit_all(
        tmp_path, [("前半", 0.0, 1.0), ("後半", 1.0 + gap, 3.0)]
    )

    assert cli.SILENCE_MARKER in recorded


def test_silence_marker_not_inserted_below_threshold(tmp_path):
    """息継ぎ程度の間ではマーカーを入れない"""
    gap = cli.SILENCE_THRESHOLD_SEC - 0.1
    recorded, _ = emit_all(
        tmp_path, [("前半", 0.0, 1.0), ("後半", 1.0 + gap, 3.0)]
    )

    assert cli.SILENCE_MARKER not in recorded


def test_silence_marker_not_inserted_before_first_utterance(tmp_path):
    """開始から発話までの間はマーカーにしない（発話の前は沈黙ではない）"""
    recorded, _ = emit_all(tmp_path, [("最初の発話", 60.0, 61.0)])

    assert cli.SILENCE_MARKER not in recorded


def test_transcription_is_not_modified(tmp_path):
    """言い直しや口ごもりをそのまま残す（R-1, R-2, R-3）"""
    spoken = "えーっと、キャッシュの、いや、ログの設計を"
    recorded, _ = emit_all(tmp_path, [(spoken, 0.0, 3.0)])

    assert spoken in recorded


# --- 欠落の記録 ---------------------------------------------------------


def test_empty_result_is_logged(tmp_path, logs):
    """区間はあるのにテキストが空なら記録に残す

    出力からは欠落したことが分からないため（requirements.md 5.7）。
    """
    recorded, session = emit_all(tmp_path, [("", 1.0, 2.5)])

    assert "空の結果" in logs.text
    assert session.count == 0


def test_empty_result_keeps_position(tmp_path):
    """空の結果でも位置は進める。次の発話の間が過大にならないようにする"""
    recorded, _ = emit_all(
        tmp_path,
        [
            ("最初", 0.0, 1.0),
            ("", 1.0, 5.0),  # 空。ここで位置が進まないと次が沈黙扱いになる
            ("続き", 5.2, 6.0),
        ],
    )

    assert cli.SILENCE_MARKER not in recorded


def test_stdout_has_only_transcription(tmp_path, capsys):
    """標準出力は文字起こし結果だけに保つ（`2>/dev/null` で取り出せること）"""
    gap = cli.SILENCE_THRESHOLD_SEC + 0.1
    emit_all(tmp_path, [("前半", 0.0, 1.0), ("", 1.0, 1.5), ("後半", 1.5 + gap, 5.0)])

    assert capsys.readouterr().out == f"前半\n{cli.SILENCE_MARKER}\n後半\n"


# --- 設定 ---------------------------------------------------------------


def test_load_config_without_file(monkeypatch, tmp_path):
    """設定ファイルが無くても既定値で動く（R-9）"""
    monkeypatch.setattr(cli, "CONFIG_PATH", tmp_path / "none.json")

    assert cli.load_config() == {"output_dir": "notes", "model_size": ""}


def test_load_config_broken_file(monkeypatch, tmp_path, logs):
    """壊れた設定でも起動できる。読めなかったことは記録に残す"""
    path = tmp_path / "config.json"
    path.write_text("{ こわれている", encoding="utf-8")
    monkeypatch.setattr(cli, "CONFIG_PATH", path)

    config = cli.load_config()

    assert config["output_dir"] == "notes"
    assert "設定を読めませんでした" in logs.text


def test_load_config_unknown_key(monkeypatch, tmp_path, logs):
    """未知の項目は無視する。無視したことは記録に残す"""
    path = tmp_path / "config.json"
    path.write_text('{"output_dir": "書き出し先", "謎": 1}', encoding="utf-8")
    monkeypatch.setattr(cli, "CONFIG_PATH", path)

    config = cli.load_config()

    assert config["output_dir"] == "書き出し先"
    assert "謎" not in config
    assert "未知の項目" in logs.text


def run_main_until_exit(monkeypatch, tmp_path, config_text=None, env=None):
    """main() を設定の反映だけ確かめて抜ける

    存在しないファイルを渡して SystemExit で止める。
    モデルのロードまで進めないため、実行は一瞬で終わる。
    """
    config_path = tmp_path / "config.json"
    if config_text is not None:
        config_path.write_text(config_text, encoding="utf-8")
    monkeypatch.setattr(cli, "CONFIG_PATH", config_path)

    monkeypatch.delenv("WHISPER_MODEL_SIZE", raising=False)
    initial = "small"
    if env:
        monkeypatch.setenv("WHISPER_MODEL_SIZE", env)
        # 環境変数は import の時点で settings に取り込まれている。その状態を再現する
        initial = env

    # monkeypatch 経由で書き換え、テスト後に元の値へ戻す
    monkeypatch.setattr(settings, "WHISPER_MODEL_SIZE", initial)
    monkeypatch.setattr(
        sys,
        "argv",
        ["cli.py", str(tmp_path / "missing.wav"), "--output-dir", str(tmp_path)],
    )

    with pytest.raises(SystemExit):
        cli.main()


def test_model_size_from_config_is_applied(monkeypatch, tmp_path):
    """設定ファイルのモデル指定が実際に使われる（R-20）

    settings は import 時に環境変数を読み終えているため、
    main() で os.environ を書き換えても間に合わない。
    """
    run_main_until_exit(monkeypatch, tmp_path, config_text='{"model_size": "base"}')

    assert settings.WHISPER_MODEL_SIZE == "base"


def test_env_takes_precedence_over_config(monkeypatch, tmp_path):
    """環境変数での指定は設定ファイルより優先される

    環境変数は import の時点で settings に取り込まれているため、
    設定ファイルの値で上書きしない。
    """
    run_main_until_exit(
        monkeypatch, tmp_path, config_text='{"model_size": "base"}', env="tiny"
    )

    assert settings.WHISPER_MODEL_SIZE == "tiny"


def test_model_size_unset_keeps_default(monkeypatch, tmp_path):
    """モデルを指定しなければ既定のまま"""
    run_main_until_exit(monkeypatch, tmp_path, config_text='{"output_dir": "notes"}')

    assert settings.WHISPER_MODEL_SIZE == "small"


def test_missing_audio_file_is_logged(monkeypatch, tmp_path, logs):
    """入力が見つからないことは記録に残す"""
    run_main_until_exit(monkeypatch, tmp_path)

    assert "ファイルが見つかりません" in logs.text


def test_unexpected_error_is_logged(monkeypatch, tmp_path, logs):
    """異常終了はトレースバックごと記録に残す

    画面に出て消えるだけでは、後から原因を追えない。
    """
    monkeypatch.setattr(cli, "CONFIG_PATH", tmp_path / "none.json")
    monkeypatch.setattr(
        sys, "argv", ["cli.py", "--output-dir", str(tmp_path)]
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("マイクが壊れた")

    monkeypatch.setattr(cli, "run_microphone", boom)

    with pytest.raises(SystemExit):
        cli.main()

    assert "異常終了" in logs.text
    assert "マイクが壊れた" in logs.text
    assert "RuntimeError" in logs.text


# --- マイク入力 ---------------------------------------------------------


class OverflowFlags:
    """sounddevice が取りこぼしを知らせるときのフラグ相当"""

    def __bool__(self):
        return True

    def __str__(self):
        return "input overflow"


def use_fake_microphone(monkeypatch, blocks):
    """sounddevice を差し替えて、指定したブロックを流し込む

    blocks は (サンプル数, 取りこぼしの有無) の並び。
    """

    class FakeStream:
        def __init__(self, callback=None, **_kwargs):
            self.callback = callback

        def start(self):
            for samples, overflowed in blocks:
                self.callback(
                    np.zeros((samples, 1), dtype="int16"),
                    samples,
                    None,
                    OverflowFlags() if overflowed else None,
                )

        def stop(self):
            pass

        def close(self):
            pass

    fake = types.ModuleType("sounddevice")
    fake.InputStream = FakeStream
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    # モデルのロードはこのテストの対象外
    monkeypatch.setattr(cli, "get_whisper_model", lambda: None)


def test_microphone_reports_overflow(monkeypatch, tmp_path, logs):
    """入力の取りこぼしを記録に残す

    取りこぼしは発話が欠落する経路のひとつだが（R-5）、
    出力を見ても欠落したことが分からない。
    """
    one_interval = int(cli.VAD_INTERVAL_SEC * cli.SAMPLE_RATE) + 1
    use_fake_microphone(monkeypatch, [(one_interval, True)])

    def stop(_audio):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "find_speech_regions", stop)

    recorder = cli.Recorder(tmp_path)
    try:
        cli.run_microphone(cli.Session(recorder))
    finally:
        recorder.close()

    assert "音声の取りこぼしを検出" in logs.text


def test_microphone_logs_only_on_state_change(monkeypatch, tmp_path, logs):
    """待機や発話が続く間は記録を増やさない

    VAD は1秒ごとに回るため、毎周回記録すると待機中のログで埋まる。
    """
    one_interval = int(cli.VAD_INTERVAL_SEC * cli.SAMPLE_RATE) + 1
    use_fake_microphone(monkeypatch, [(one_interval, False)])

    # 発話が2周続き、そのあと待機が2周続く。区間はバッファ末尾から遠いため
    # 確定待ちのまま文字起こしには進まない
    speaking = [{"start": 0.0, "end": 0.1}]
    responses = [speaking, speaking, [], []]

    def sequence(_audio):
        if not responses:
            raise KeyboardInterrupt
        return responses.pop(0)

    monkeypatch.setattr(cli, "find_speech_regions", sequence)

    recorder = cli.Recorder(tmp_path)
    try:
        cli.run_microphone(cli.Session(recorder))
    finally:
        recorder.close()

    messages = [record.getMessage() for record in logs.records]
    assert len([m for m in messages if m.startswith("発話を検出")]) == 1
    assert len([m for m in messages if m.startswith("待機")]) == 1
