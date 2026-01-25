"""累積バッファ管理モジュール

音声チャンクを蓄積し、定期的に全体を再文字起こしして
確定テキストと暫定テキストを区別する。
"""

import re
import io
import wave
from dataclasses import dataclass, field
from typing import Optional, Tuple, List
from datetime import datetime
from utils.logger import logger


@dataclass
class CumulativeBufferConfig:
    """累積バッファ設定"""
    max_audio_duration_seconds: float = 30.0  # 最大蓄積時間（Whisperの1セグメント上限）
    transcription_interval_chunks: int = 3    # 何チャンクごとに再文字起こしするか
    stable_text_threshold: int = 2            # 何回同じ結果が出たら確定とするか
    sample_rate: int = 16000                  # サンプルレート
    channels: int = 1                         # チャンネル数
    sample_width: int = 2                     # サンプル幅（16bit = 2bytes）


@dataclass
class TranscriptionResult:
    """文字起こし結果"""
    confirmed_text: str      # 確定テキスト（変更されない部分）
    tentative_text: str      # 暫定テキスト（まだ変わる可能性あり）
    full_text: str           # 全体テキスト
    confirmed_hiragana: str  # 確定テキストのひらがな
    tentative_hiragana: str  # 暫定テキストのひらがな
    is_final: bool           # セッション終了フラグ


def extract_diff(previous: str, current: str) -> Tuple[str, str]:
    """
    前回の結果と今回の結果を比較し、確定部分と暫定部分を抽出

    アルゴリズム:
    1. 両方のテキストを文単位（句点区切り）で分割
    2. 前回存在した句点終わりの文で、今回も同じ形で存在するものを確定
    3. 残りを暫定とする

    例:
    前回: "これはテストです。システムを"
    今回: "これはテストです。システムを構築しています。"

    結果:
    確定: "これはテストです。"
    暫定: "システムを構築しています。"
    """
    if not current:
        return "", ""

    if not previous:
        # 前回結果がない場合、句点で終わる文を確定とみなす
        sentence_pattern = r'(?<=[。！？])'
        sentences = re.split(sentence_pattern, current)

        # 最後の文以外は確定（句点で終わっている）
        if len(sentences) > 1:
            confirmed = ''.join(sentences[:-1])
            tentative = sentences[-1] if sentences[-1].strip() else ""
        else:
            confirmed = ""
            tentative = current
        return confirmed, tentative

    # 句点で分割（句点は保持）
    sentence_pattern = r'(?<=[。！？])'
    prev_sentences = [s for s in re.split(sentence_pattern, previous) if s.strip()]
    curr_sentences = [s for s in re.split(sentence_pattern, current) if s.strip()]

    # 前回と今回で一致する句点終わりの文を確定
    confirmed_sentences = []
    for i, (prev_s, curr_s) in enumerate(zip(prev_sentences, curr_sentences)):
        # 句点で終わる文が一致した場合のみ確定
        if prev_s.strip() == curr_s.strip() and prev_s.rstrip().endswith(('。', '！', '？')):
            confirmed_sentences.append(curr_s)
        else:
            break

    # さらに、今回のテキストで句点で終わり、確定済みでない文も確定候補に
    # （前回より文が増えた場合）
    if len(curr_sentences) > len(confirmed_sentences):
        # 確定済みの次の文から、句点で終わるものを確定
        for i in range(len(confirmed_sentences), len(curr_sentences) - 1):
            s = curr_sentences[i]
            if s.rstrip().endswith(('。', '！', '？')):
                confirmed_sentences.append(s)
            else:
                break

    # 確定テキストを結合
    confirmed = ''.join(confirmed_sentences)

    # 暫定テキストは確定部分を除いた残り
    if confirmed:
        tentative = current[len(confirmed):].lstrip()
    else:
        tentative = current

    return confirmed, tentative


class CumulativeBuffer:
    """累積バッファ管理クラス

    音声チャンクを蓄積し、定期的に全体を再文字起こしする。
    確定テキストと暫定テキストを区別して管理する。
    """

    def __init__(self, config: Optional[CumulativeBufferConfig] = None):
        self.config = config or CumulativeBufferConfig()

        # 音声バッファ（生PCMデータ）
        self.audio_chunks: List[bytes] = []
        self.total_audio_bytes: int = 0

        # チャンクカウント
        self.chunk_count: int = 0

        # 文字起こし結果
        self.last_transcription: str = ""           # 前回の文字起こし結果
        self.confirmed_text: str = ""               # 確定済みテキスト
        self.confirmed_hiragana: str = ""           # 確定済みひらがな

        # 安定性チェック用
        self.stable_count: int = 0                  # 同じ結果が続いた回数
        self.previous_full_text: str = ""           # 前回の全体テキスト

        # 作成時刻
        self.created_at: datetime = datetime.now()

        logger.info(
            f"📦 CumulativeBuffer初期化: "
            f"最大{self.config.max_audio_duration_seconds}秒, "
            f"{self.config.transcription_interval_chunks}チャンクごとに再処理"
        )

    @property
    def max_audio_bytes(self) -> int:
        """最大音声バイト数"""
        return int(
            self.config.max_audio_duration_seconds
            * self.config.sample_rate
            * self.config.channels
            * self.config.sample_width
        )

    @property
    def current_audio_duration(self) -> float:
        """現在の音声長（秒）"""
        return self.total_audio_bytes / (
            self.config.sample_rate
            * self.config.channels
            * self.config.sample_width
        )

    def add_audio_chunk(self, audio_data: bytes) -> bool:
        """音声チャンクを追加

        Args:
            audio_data: 生PCMデータまたはWAVデータ

        Returns:
            再文字起こしが必要ならTrue
        """
        # WAVヘッダーがある場合は除去してPCMデータを取得
        pcm_data = self._extract_pcm_from_wav(audio_data)

        self.audio_chunks.append(pcm_data)
        self.total_audio_bytes += len(pcm_data)
        self.chunk_count += 1

        logger.debug(
            f"📥 チャンク追加: {self.chunk_count}個目, "
            f"累積{self.current_audio_duration:.1f}秒"
        )

        # 最大バッファサイズを超えた場合、古いデータを削除
        self._trim_buffer_if_needed()

        # 再文字起こしが必要かどうか判定
        return self.chunk_count % self.config.transcription_interval_chunks == 0

    def _extract_pcm_from_wav(self, audio_data: bytes) -> bytes:
        """WAVデータからPCMデータを抽出"""
        # WAVヘッダーの確認（"RIFF"で始まる）
        if audio_data[:4] == b'RIFF':
            try:
                with io.BytesIO(audio_data) as wav_buffer:
                    with wave.open(wav_buffer, 'rb') as wav_file:
                        return wav_file.readframes(wav_file.getnframes())
            except Exception as e:
                logger.warning(f"WAV解析失敗、生データとして処理: {e}")
                return audio_data
        return audio_data

    def _trim_buffer_if_needed(self):
        """バッファが最大サイズを超えた場合、古いデータを削除"""
        while self.total_audio_bytes > self.max_audio_bytes and len(self.audio_chunks) > 1:
            removed = self.audio_chunks.pop(0)
            self.total_audio_bytes -= len(removed)
            logger.debug(
                f"🗑️ 古いチャンク削除: 残り{self.current_audio_duration:.1f}秒"
            )

    def get_accumulated_audio(self) -> bytes:
        """累積音声データをWAV形式で取得"""
        if not self.audio_chunks:
            return b''

        # 全PCMデータを結合
        all_pcm = b''.join(self.audio_chunks)

        # WAV形式に変換
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(self.config.channels)
            wav_file.setsampwidth(self.config.sample_width)
            wav_file.setframerate(self.config.sample_rate)
            wav_file.writeframes(all_pcm)

        return wav_buffer.getvalue()

    def get_initial_prompt(self) -> Optional[str]:
        """次回の文字起こし用initial_promptを取得

        確定済みテキストの末尾を返す（文脈として使用）
        """
        if not self.confirmed_text:
            return None

        # 最後の2文程度を返す
        sentences = re.split(r'(?<=[。！？])', self.confirmed_text)
        recent_sentences = [s for s in sentences[-2:] if s.strip()]
        return ''.join(recent_sentences) if recent_sentences else None

    def update_transcription(
        self,
        new_text: str,
        hiragana_converter=None
    ) -> TranscriptionResult:
        """文字起こし結果を更新し、差分を計算

        Args:
            new_text: 新しい文字起こし結果
            hiragana_converter: ひらがな変換関数（省略可）

        Returns:
            TranscriptionResult: 確定/暫定テキストを含む結果
        """
        # 差分抽出（今回のテキスト全体から確定部分と暫定部分を分離）
        current_confirmed, tentative = extract_diff(self.last_transcription, new_text)

        # 新しく確定された部分を計算（既存の確定テキストとの差分）
        newly_confirmed = ""
        if current_confirmed and len(current_confirmed) > len(self.confirmed_text):
            # 今回の確定部分が既存より長い場合、差分を追加
            newly_confirmed = current_confirmed[len(self.confirmed_text):]
            self.confirmed_text = current_confirmed
        elif current_confirmed and not self.confirmed_text:
            # 初回の確定
            newly_confirmed = current_confirmed
            self.confirmed_text = current_confirmed

        # ひらがな変換
        confirmed_hiragana = ""
        tentative_hiragana = ""
        if hiragana_converter:
            if newly_confirmed:
                confirmed_hiragana = hiragana_converter(newly_confirmed)
                self.confirmed_hiragana += confirmed_hiragana
            if tentative:
                tentative_hiragana = hiragana_converter(tentative)

        # 前回結果を更新
        self.last_transcription = new_text

        # 安定性チェック（同じ結果が続いたらより多くを確定）
        if new_text == self.previous_full_text:
            self.stable_count += 1
        else:
            self.stable_count = 0
        self.previous_full_text = new_text

        logger.info(
            f"📝 文字起こし更新: "
            f"確定={len(self.confirmed_text)}文字, "
            f"暫定={len(tentative)}文字"
        )

        return TranscriptionResult(
            confirmed_text=self.confirmed_text,
            tentative_text=tentative,
            full_text=new_text,
            confirmed_hiragana=self.confirmed_hiragana,
            tentative_hiragana=tentative_hiragana,
            is_final=False
        )

    def finalize(self, hiragana_converter=None) -> TranscriptionResult:
        """セッション終了時に全テキストを確定"""
        # 残りの暫定テキストを確定
        if self.last_transcription:
            remaining = self.last_transcription[len(self.confirmed_text):]
            if remaining:
                self.confirmed_text += remaining
                if hiragana_converter:
                    self.confirmed_hiragana += hiragana_converter(remaining)

        logger.info(f"✅ セッション終了: 最終テキスト={len(self.confirmed_text)}文字")

        return TranscriptionResult(
            confirmed_text=self.confirmed_text,
            tentative_text="",
            full_text=self.confirmed_text,
            confirmed_hiragana=self.confirmed_hiragana,
            tentative_hiragana="",
            is_final=True
        )

    def clear(self):
        """バッファをクリア"""
        self.audio_chunks.clear()
        self.total_audio_bytes = 0
        self.chunk_count = 0
        self.last_transcription = ""
        self.confirmed_text = ""
        self.confirmed_hiragana = ""
        self.stable_count = 0
        self.previous_full_text = ""
        logger.info("🧹 CumulativeBufferをクリア")

    def get_stats(self) -> dict:
        """統計情報を取得"""
        return {
            "chunk_count": self.chunk_count,
            "audio_duration_seconds": self.current_audio_duration,
            "confirmed_text_length": len(self.confirmed_text),
            "last_transcription_length": len(self.last_transcription),
            "stable_count": self.stable_count,
        }
