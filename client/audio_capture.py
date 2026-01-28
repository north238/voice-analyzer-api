"""
リアルタイム音声キャプチャモジュール（Phase 3.2）

sounddeviceを使用してマイクから音声を取得し、チャンク単位でコールバックを呼び出す。
Phase 3.2ではVAD（Voice Activity Detection）による動的チャンク分割と音量メーターを追加。

※ sounddeviceはPortAudioをバンドルしているため、pip installだけで動作する
"""

import sounddevice as sd
import numpy as np
import logging
import io
import wave
from typing import Callable, Optional
from dataclasses import dataclass

# VADライブラリ（オプション）
try:
    import webrtcvad

    VAD_AVAILABLE = True
except ImportError:
    VAD_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    """音声キャプチャ設定"""

    # 基本設定
    sample_rate: int = 16000  # Whisper推奨: 16kHz
    channels: int = 1  # モノラル
    chunk_duration: float = 3.0  # 固定チャンク長（秒）- VAD無効時に使用
    dtype: str = "int16"  # 16-bit PCM

    # VAD設定（Phase 3.2）
    enable_vad: bool = False  # VAD有効化フラグ
    vad_aggressiveness: int = 2  # VAD感度（0-3、3が最も厳密）
    silence_duration_ms: int = 500  # 無音判定時間（ミリ秒）
    min_chunk_duration_ms: int = 500  # 最小チャンク長（ミリ秒）
    max_chunk_duration_ms: int = 10000  # 最大チャンク長（ミリ秒）

    @property
    def frames_per_chunk(self) -> int:
        """1チャンクあたりのフレーム数（固定長モード用）"""
        return int(self.sample_rate * self.chunk_duration)

    @property
    def bytes_per_chunk(self) -> int:
        """1チャンクあたりのバイト数（16-bit = 2 bytes）"""
        return self.frames_per_chunk * self.channels * 2

    @property
    def min_chunk_bytes(self) -> int:
        """最小チャンクサイズ（バイト）"""
        return (
            int(self.sample_rate * self.min_chunk_duration_ms / 1000)
            * self.channels
            * 2
        )

    @property
    def max_chunk_bytes(self) -> int:
        """最大チャンクサイズ（バイト）"""
        return (
            int(self.sample_rate * self.max_chunk_duration_ms / 1000)
            * self.channels
            * 2
        )

    @property
    def silence_frames(self) -> int:
        """無音判定に必要なフレーム数"""
        return int(self.sample_rate * self.silence_duration_ms / 1000)

    def pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """
        生のPCMデータをWAVフォーマットに変換

        Args:
            pcm_data: 生のPCMバイト列

        Returns:
            WAVフォーマットのバイト列
        """
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)  # 16-bit = 2 bytes
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_data)
        return buffer.getvalue()


def calculate_volume_db(audio_data: np.ndarray) -> float:
    """
    PCM音声データから音量レベル（dB）を計算

    Args:
        audio_data: numpy配列の音声データ

    Returns:
        音量レベル（dB）。-60dB〜0dBの範囲に正規化
    """
    if len(audio_data) == 0:
        return -60.0

    # RMS（二乗平均平方根）を計算
    rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))

    # dBに変換（16-bit PCMの最大値は32767）
    if rms > 0:
        db = 20 * np.log10(rms / 32767.0)
        # -60dB〜0dBの範囲にクランプ
        return max(-60.0, min(0.0, db))
    else:
        return -60.0


class AudioCapture:
    """
    リアルタイム音声キャプチャクラス（Phase 3.2対応）

    使用例（固定長モード - Phase 3.1互換）:
        config = AudioConfig(chunk_duration=3.0)
        capture = AudioCapture(config)

        def on_chunk(audio_data: bytes):
            print(f"Received {len(audio_data)} bytes")

        capture.start(on_chunk)
        input("Press Enter to stop...")
        capture.stop()

    使用例（VADモード - Phase 3.2）:
        config = AudioConfig(
            enable_vad=True,
            vad_aggressiveness=2,
            silence_duration_ms=500,
            min_chunk_duration_ms=500,
            max_chunk_duration_ms=10000
        )
        capture = AudioCapture(config)

        def on_chunk(audio_data: bytes):
            print(f"Received {len(audio_data)} bytes")

        def on_volume(volume_db: float, is_speech: bool):
            print(f"Volume: {volume_db:.1f}dB, Speech: {is_speech}")

        capture.start(on_chunk, on_volume_level=on_volume)
    """

    # webrtcvadがサポートするフレームサイズ（ミリ秒）
    VAD_FRAME_DURATION_MS = 30  # 10, 20, 30のいずれか

    def __init__(self, config: AudioConfig = None, output_wav: bool = True):
        """
        Args:
            config: 音声キャプチャ設定
            output_wav: TrueならWAVフォーマット、FalseならPCM生データを出力
        """
        self.config = config or AudioConfig()
        self.output_wav = output_wav
        self.stream: Optional[sd.InputStream] = None
        self.is_recording = False
        self.buffer = bytearray()
        self.on_chunk_callback: Optional[Callable[[bytes], None]] = None
        self.on_volume_callback: Optional[Callable[[float, bool], None]] = None

        # VAD関連
        self.vad = None
        self.vad_buffer = bytearray()  # VAD判定用バッファ
        self.silence_frame_count = 0  # 連続無音フレーム数
        self.is_speaking = False  # 発話中フラグ
        self.speech_started = False  # 発話開始フラグ

        # VADフレームサイズ（バイト）
        self.vad_frame_bytes = (
            int(self.config.sample_rate * self.VAD_FRAME_DURATION_MS / 1000)
            * self.config.channels
            * 2
        )

        # 無音判定に必要なフレーム数
        self.silence_frames_threshold = int(
            self.config.silence_duration_ms / self.VAD_FRAME_DURATION_MS
        )

        # VAD初期化
        if self.config.enable_vad:
            if VAD_AVAILABLE:
                self.vad = webrtcvad.Vad(self.config.vad_aggressiveness)
                logger.info(f"VAD有効化（感度: {self.config.vad_aggressiveness}）")
            else:
                logger.warning(
                    "webrtcvadがインストールされていません。固定長モードで動作します。"
                )
                self.config.enable_vad = False

    def start(
        self,
        on_chunk: Callable[[bytes], None],
        device_index: Optional[int] = None,
        on_volume_level: Optional[Callable[[float, bool], None]] = None,
    ):
        """
        音声キャプチャを開始

        Args:
            on_chunk: チャンクデータを受け取るコールバック関数
            device_index: 使用するデバイスのインデックス（Noneの場合はデフォルト）
            on_volume_level: 音量レベルを受け取るコールバック関数（オプション）
                            引数: (volume_db: float, is_speech: bool)
        """
        if self.is_recording:
            logger.warning("既に録音中です")
            return

        self.on_chunk_callback = on_chunk
        self.on_volume_callback = on_volume_level
        self.is_recording = True
        self.buffer.clear()
        self.vad_buffer.clear()
        self.silence_frame_count = 0
        self.is_speaking = False
        self.speech_started = False

        try:
            # デバイス選択のログ
            if device_index is not None:
                device_info = sd.query_devices(device_index)
                logger.info(f"使用デバイス: [{device_index}] {device_info['name']}")
            else:
                logger.info("デフォルトデバイスを使用")

            # ストリーム開始
            self.stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype=self.config.dtype,
                device=device_index,
                blocksize=1024,  # 内部バッファサイズ（小さめで低遅延）
                callback=self._audio_callback,
            )

            self.stream.start()

            if self.config.enable_vad:
                logger.info(
                    f"音声キャプチャ開始（VADモード、無音閾値: {self.config.silence_duration_ms}ms、"
                    f"最小: {self.config.min_chunk_duration_ms}ms、"
                    f"最大: {self.config.max_chunk_duration_ms}ms）"
                )
            else:
                logger.info(
                    f"音声キャプチャ開始（固定長モード、{self.config.chunk_duration}秒チャンク、"
                    f"{self.config.sample_rate}Hz）"
                )

        except Exception as e:
            logger.error(f"音声キャプチャ開始エラー: {e}")
            self.is_recording = False
            raise

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """
        sounddeviceのストリームコールバック

        VADモード: 音声区間検出に基づいて動的にチャンクを区切る
        固定長モード: 設定されたチャンクサイズに達したら処理
        """
        if status:
            logger.warning(f"Audio callback status: {status}")

        # 音量レベル計算
        volume_db = calculate_volume_db(indata)

        # numpy配列をバイト列に変換
        audio_bytes = indata.tobytes()

        if self.config.enable_vad and self.vad:
            self._process_vad_mode(audio_bytes, volume_db)
        else:
            self._process_fixed_mode(audio_bytes, volume_db)

    def _process_vad_mode(self, audio_bytes: bytes, volume_db: float):
        """VADモードでの音声処理"""
        # VAD判定用バッファに追加
        self.vad_buffer.extend(audio_bytes)
        self.buffer.extend(audio_bytes)

        # VADフレームサイズ分のデータがあればVAD判定
        is_speech = False
        while len(self.vad_buffer) >= self.vad_frame_bytes:
            frame = bytes(self.vad_buffer[: self.vad_frame_bytes])
            self.vad_buffer = self.vad_buffer[self.vad_frame_bytes :]

            try:
                is_speech = self.vad.is_speech(frame, self.config.sample_rate)
            except Exception as e:
                logger.warning(f"VAD判定エラー: {e}")
                is_speech = False

            if is_speech:
                # 音声検出
                self.silence_frame_count = 0
                if not self.speech_started:
                    self.speech_started = True
                    logger.debug("発話開始検出")
                self.is_speaking = True
            else:
                # 無音検出
                self.silence_frame_count += 1
                if (
                    self.speech_started
                    and self.silence_frame_count >= self.silence_frames_threshold
                ):
                    # 無音が閾値を超えた→チャンク確定
                    self.is_speaking = False

        # 音量コールバック呼び出し
        if self.on_volume_callback:
            try:
                self.on_volume_callback(volume_db, self.is_speaking)
            except Exception as e:
                logger.error(f"音量コールバックエラー: {e}")

        # チャンク送信判定
        should_send = False
        buffer_len = len(self.buffer)

        # 最大チャンクサイズに達した場合は強制送信
        if buffer_len >= self.config.max_chunk_bytes:
            should_send = True
            logger.debug("最大チャンクサイズに達したため送信")

        # 発話終了＋最小チャンクサイズ以上の場合は送信
        elif (
            self.speech_started
            and not self.is_speaking
            and buffer_len >= self.config.min_chunk_bytes
        ):
            should_send = True
            logger.debug(f"発話終了を検出、チャンク送信（{buffer_len} bytes）")

        if should_send:
            self._send_chunk()
            self.speech_started = False

    def _process_fixed_mode(self, audio_bytes: bytes, volume_db: float):
        """固定長モードでの音声処理（Phase 3.1互換）"""
        self.buffer.extend(audio_bytes)

        # 音量コールバック呼び出し
        if self.on_volume_callback:
            try:
                self.on_volume_callback(volume_db, True)  # 固定長モードでは常にTrue
            except Exception as e:
                logger.error(f"音量コールバックエラー: {e}")

        # チャンクサイズに達したら処理
        if len(self.buffer) >= self.config.bytes_per_chunk:
            pcm_data = bytes(self.buffer[: self.config.bytes_per_chunk])
            self.buffer = self.buffer[self.config.bytes_per_chunk :]
            self._send_chunk_data(pcm_data)

    def _send_chunk(self):
        """現在のバッファをチャンクとして送信"""
        if len(self.buffer) == 0:
            return

        pcm_data = bytes(self.buffer)
        self.buffer.clear()
        self._send_chunk_data(pcm_data)

    def _send_chunk_data(self, pcm_data: bytes):
        """PCMデータをチャンクとして送信"""
        # WAVフォーマットに変換（オプション）
        if self.output_wav:
            chunk_data = self.config.pcm_to_wav(pcm_data)
        else:
            chunk_data = pcm_data

        # コールバック呼び出し
        try:
            if self.on_chunk_callback:
                self.on_chunk_callback(chunk_data)
        except Exception as e:
            logger.error(f"チャンク処理エラー: {e}")

    def stop(self):
        """音声キャプチャを停止"""
        if not self.is_recording:
            logger.warning("録音していません")
            return

        self.is_recording = False

        # 残りのバッファを処理
        if len(self.buffer) > 0:
            logger.info(f"残りバッファを処理: {len(self.buffer)} bytes")
            try:
                self._send_chunk()
            except Exception as e:
                logger.error(f"最終チャンク処理エラー: {e}")
            self.buffer.clear()

        # ストリーム停止
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        logger.info("音声キャプチャ停止")

    def close(self):
        """リソースの解放"""
        self.stop()
        logger.info("AudioCaptureクローズ")


def list_audio_devices():
    """
    利用可能な音声デバイスを列挙して表示

    コマンドラインからの確認用ユーティリティ
    """
    print("\n=== 利用可能な音声デバイス ===")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        print(f"[{i}] {device['name']}")
        print(f"    入力チャンネル: {device['max_input_channels']}")
        print(f"    出力チャンネル: {device['max_output_channels']}")
        print(f"    デフォルトサンプルレート: {device['default_samplerate']}")


if __name__ == "__main__":
    # デバイス一覧表示テスト
    logging.basicConfig(level=logging.INFO)
    list_audio_devices()

    # 簡易録音テスト
    print("\n=== 簡易録音テスト（3秒チャンク） ===")
    print("3秒間話してください...")

    chunk_count = 0

    def test_callback(audio_data: bytes):
        global chunk_count
        chunk_count += 1
        print(f"チャンク#{chunk_count}: {len(audio_data)} bytes受信")

    config = AudioConfig(chunk_duration=3.0)
    capture = AudioCapture(config)

    try:
        capture.start(test_callback)
        import time

        # ストリームが動作中は待機
        while capture.is_recording:
            try:
                time.sleep(0.1)
            except KeyboardInterrupt:
                print("\n停止中...")
                break
    finally:
        capture.close()

    print(f"\n合計 {chunk_count} チャンクを受信しました")
