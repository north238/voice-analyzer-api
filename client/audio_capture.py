"""
リアルタイム音声キャプチャモジュール（Phase 3.1）

sounddeviceを使用してマイクから音声を取得し、チャンク単位でコールバックを呼び出す。
※ sounddeviceはPortAudioをバンドルしているため、pip installだけで動作する
"""

import sounddevice as sd
import numpy as np
import logging
import io
import wave
from typing import Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    """音声キャプチャ設定"""
    sample_rate: int = 16000      # Whisper推奨: 16kHz
    channels: int = 1             # モノラル
    chunk_duration: float = 3.0   # チャンク長（秒）
    dtype: str = 'int16'          # 16-bit PCM

    @property
    def frames_per_chunk(self) -> int:
        """1チャンクあたりのフレーム数"""
        return int(self.sample_rate * self.chunk_duration)

    @property
    def bytes_per_chunk(self) -> int:
        """1チャンクあたりのバイト数（16-bit = 2 bytes）"""
        return self.frames_per_chunk * self.channels * 2

    def pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """
        生のPCMデータをWAVフォーマットに変換

        Args:
            pcm_data: 生のPCMバイト列

        Returns:
            WAVフォーマットのバイト列
        """
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)  # 16-bit = 2 bytes
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_data)
        return buffer.getvalue()


class AudioCapture:
    """
    リアルタイム音声キャプチャクラス

    使用例:
        config = AudioConfig(chunk_duration=3.0)
        capture = AudioCapture(config)

        def on_chunk(audio_data: bytes):
            print(f"Received {len(audio_data)} bytes")

        capture.start(on_chunk)
        input("Press Enter to stop...")
        capture.stop()
    """

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

    def start(self, on_chunk: Callable[[bytes], None], device_index: Optional[int] = None):
        """
        音声キャプチャを開始

        Args:
            on_chunk: チャンクデータを受け取るコールバック関数
            device_index: 使用するデバイスのインデックス（Noneの場合はデフォルト）
        """
        if self.is_recording:
            logger.warning("既に録音中です")
            return

        self.on_chunk_callback = on_chunk
        self.is_recording = True
        self.buffer.clear()

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
                callback=self._audio_callback
            )

            self.stream.start()
            logger.info(f"音声キャプチャ開始（{self.config.chunk_duration}秒チャンク、{self.config.sample_rate}Hz）")

        except Exception as e:
            logger.error(f"音声キャプチャ開始エラー: {e}")
            self.is_recording = False
            raise

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """
        sounddeviceのストリームコールバック

        チャンクサイズに達したらon_chunkコールバックを呼び出す
        """
        if status:
            logger.warning(f"Audio callback status: {status}")

        # numpy配列をバイト列に変換してバッファに追加
        self.buffer.extend(indata.tobytes())

        # チャンクサイズに達したら処理
        if len(self.buffer) >= self.config.bytes_per_chunk:
            pcm_data = bytes(self.buffer[:self.config.bytes_per_chunk])
            self.buffer = self.buffer[self.config.bytes_per_chunk:]

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
                if self.on_chunk_callback:
                    pcm_data = bytes(self.buffer)
                    if self.output_wav:
                        chunk_data = self.config.pcm_to_wav(pcm_data)
                    else:
                        chunk_data = pcm_data
                    self.on_chunk_callback(chunk_data)
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
