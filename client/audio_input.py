"""
音声ファイルの分割処理を行うユーティリティ
"""

from pydub import AudioSegment
from typing import List, Tuple
import io
import os


class AudioSplitter:
    """音声ファイルを指定秒数で分割するクラス"""

    def __init__(self, chunk_duration_ms: int = 3000):
        """
        Args:
            chunk_duration_ms: チャンクの長さ（ミリ秒）デフォルト3秒
        """
        self.chunk_duration_ms = chunk_duration_ms

    def load_audio(self, file_path: str) -> AudioSegment:
        """
        音声ファイルを読み込む

        Args:
            file_path: 音声ファイルのパス

        Returns:
            AudioSegment: 読み込んだ音声データ
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"音声ファイルが見つかりません: {file_path}")

        # ファイル拡張子から形式を判定
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".mp3":
            audio = AudioSegment.from_mp3(file_path)
        elif ext == ".wav":
            audio = AudioSegment.from_wav(file_path)
        elif ext == ".ogg":
            audio = AudioSegment.from_ogg(file_path)
        elif ext == ".webm":
            audio = AudioSegment.from_file(file_path, format="webm")
        else:
            # 未知の形式は自動判定
            audio = AudioSegment.from_file(file_path)

        print(f"✅ 音声ファイル読み込み完了: {file_path}")
        print(f"   - 長さ: {len(audio) / 1000:.2f}秒")
        print(f"   - サンプルレート: {audio.frame_rate}Hz")
        print(f"   - チャンネル数: {audio.channels}")

        return audio

    def split_audio(self, audio: AudioSegment) -> List[AudioSegment]:
        """
        音声を指定秒数ごとに分割

        Args:
            audio: 分割する音声データ

        Returns:
            List[AudioSegment]: 分割された音声チャンクのリスト
        """
        chunks = []
        audio_length_ms = len(audio)
        num_chunks = (audio_length_ms + self.chunk_duration_ms - 1) // self.chunk_duration_ms

        print(f"\n📦 音声を{self.chunk_duration_ms / 1000}秒ごとに分割します...")
        print(f"   - 総チャンク数: {num_chunks}個")

        for i in range(num_chunks):
            start_ms = i * self.chunk_duration_ms
            end_ms = min((i + 1) * self.chunk_duration_ms, audio_length_ms)
            chunk = audio[start_ms:end_ms]
            chunks.append(chunk)
            print(f"   - チャンク {i}: {start_ms / 1000:.2f}秒 ~ {end_ms / 1000:.2f}秒")

        return chunks

    def chunk_to_bytes(
        self, chunk: AudioSegment, format: str = "wav"
    ) -> Tuple[bytes, str]:
        """
        AudioSegmentをバイトストリームに変換

        Args:
            chunk: 変換する音声チャンク
            format: 出力フォーマット（wav, mp3など）

        Returns:
            Tuple[bytes, str]: (音声データのバイト列, ファイル名)
        """
        buffer = io.BytesIO()
        chunk.export(buffer, format=format)
        buffer.seek(0)
        audio_bytes = buffer.read()

        filename = f"chunk.{format}"
        return audio_bytes, filename

    def split_audio_file(
        self, file_path: str, output_format: str = "wav"
    ) -> List[Tuple[bytes, str, int]]:
        """
        音声ファイルを読み込み、分割してバイト列のリストとして返す

        Args:
            file_path: 音声ファイルのパス
            output_format: 出力フォーマット

        Returns:
            List[Tuple[bytes, str, int]]: [(音声データ, ファイル名, チャンクID), ...]
        """
        # 音声読み込み
        audio = self.load_audio(file_path)

        # 分割
        chunks = self.split_audio(audio)

        # バイト列に変換
        result = []
        for i, chunk in enumerate(chunks):
            audio_bytes, filename = self.chunk_to_bytes(chunk, format=output_format)
            result.append((audio_bytes, filename, i))

        print(f"\n✅ {len(result)}個のチャンクを生成しました\n")
        return result


def split_audio_file(
    file_path: str, chunk_duration_seconds: int = 3, output_format: str = "wav"
) -> List[Tuple[bytes, str, int]]:
    """
    音声ファイルを分割する便利関数

    Args:
        file_path: 音声ファイルのパス
        chunk_duration_seconds: チャンクの長さ（秒）
        output_format: 出力フォーマット

    Returns:
        List[Tuple[bytes, str, int]]: [(音声データ, ファイル名, チャンクID), ...]
    """
    splitter = AudioSplitter(chunk_duration_ms=chunk_duration_seconds * 1000)
    return splitter.split_audio_file(file_path, output_format=output_format)
