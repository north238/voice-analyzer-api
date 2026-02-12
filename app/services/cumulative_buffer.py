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
from services.text_filter import is_valid_text


@dataclass
class CumulativeBufferConfig:
    """累積バッファ設定"""

    max_audio_duration_seconds: float = 25.0  # 最大蓄積時間（Whisperの30秒制限を考慮し余裕を持たせる）
    transcription_interval_chunks: int = 3  # 何チャンクごとに再文字起こしするか
    stable_text_threshold: int = 2  # 何回同じ結果が出たら確定とするか
    sample_rate: int = 16000  # サンプルレート
    channels: int = 1  # チャンネル数
    sample_width: int = 2  # サンプル幅（16bit = 2bytes）


@dataclass
class TranscriptionResult:
    """文字起こし結果"""

    confirmed_text: str  # 確定テキスト（変更されない部分）
    tentative_text: str  # 暫定テキスト（まだ変わる可能性あり）
    full_text: str  # 全体テキスト
    confirmed_hiragana: str  # 確定テキストのひらがな
    tentative_hiragana: str  # 暫定テキストのひらがな
    is_final: bool  # セッション終了フラグ


def extract_diff(previous: str, current: str) -> Tuple[str, str]:
    """
    前回の結果と今回の結果を比較し、確定部分と暫定部分を抽出

    アルゴリズム（句点に依存しない新しいロジック）:
    1. 前回と今回で一致する先頭部分を確定とする
    2. Whisperは通常、前回の結果を含んで長くなる性質を利用
    3. 単語の途中で切れないように配慮

    例:
    前回: "これはテストですシステムを"
    今回: "これはテストですシステムを構築しています"

    結果:
    確定: "これはテストですシステムを"
    暫定: "構築しています"
    """
    if not current:
        return "", ""

    if not previous:
        # 前回結果がない場合、全て暫定
        logger.debug(f"🔍 extract_diff: 前回なし → 全て暫定")
        return "", current

    # 前回と今回の共通接頭辞を探す
    min_len = min(len(previous), len(current))
    match_len = 0

    for i in range(min_len):
        if previous[i] == current[i]:
            match_len = i + 1
        else:
            break

    logger.debug(f"🔍 extract_diff: 一致長={match_len}, 前回長={len(previous)}, 今回長={len(current)}")

    # 完全一致の場合は前回のテキスト全体を確定
    if match_len == len(previous) and len(current) >= len(previous):
        confirmed = previous
        tentative = current[len(previous):]
    elif match_len > 0:
        # 一部一致の場合、一致した部分を確定
        # ただし、単語の途中で切れないように、句読点か空白まで戻る
        confirmed = current[:match_len]

        # 句読点で終わっていない場合、最後の句読点または空白まで戻る
        if match_len < len(current) and not confirmed.endswith(("。", "！", "？", " ", "　")):
            # 最後の句読点または空白を探す
            last_break = max(
                confirmed.rfind("。"),
                confirmed.rfind("！"),
                confirmed.rfind("？"),
                confirmed.rfind(" "),
                confirmed.rfind("　")
            )
            if last_break > 0:
                confirmed = confirmed[:last_break + 1]
            else:
                # 区切りが見つからない場合は確定なし
                confirmed = ""

        tentative = current[len(confirmed):] if confirmed else current
    else:
        # 一致なし（文字起こし結果が大きく変わった）
        confirmed = ""
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
        self.last_transcription: str = ""  # 前回の文字起こし結果
        self.confirmed_text: str = ""  # 確定済みテキスト
        self.confirmed_hiragana: str = ""  # 確定済みひらがな

        # 安定性チェック用
        self.stable_count: int = 0  # 同じ結果が続いた回数
        self.previous_full_text: str = ""  # 前回の全体テキスト

        # トリミング前コールバック
        self.on_before_trim_callback: Optional[callable] = None

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
            self.config.sample_rate * self.config.channels * self.config.sample_width
        )

    @property
    def session_elapsed_seconds(self) -> float:
        """セッション開始からの実際の経過時間（秒）"""
        return (datetime.now() - self.created_at).total_seconds()

    def add_audio_chunk(self, audio_data: bytes) -> tuple[bool, bool]:
        """音声チャンクを追加

        Args:
            audio_data: 生PCMデータまたはWAVデータ

        Returns:
            (should_transcribe, should_trim): 再文字起こしが必要ならTrue, トリミングが必要ならTrue
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

        # トリミングが必要かチェック（実行はしない）
        should_trim = (
            self.total_audio_bytes > self.max_audio_bytes and len(self.audio_chunks) > 1
        )

        # 再文字起こしが必要かどうか判定
        should_transcribe = (
            self.chunk_count % self.config.transcription_interval_chunks == 0
        )

        return should_transcribe, should_trim

    def _extract_pcm_from_wav(self, audio_data: bytes) -> bytes:
        """WAVデータからPCMデータを抽出"""
        # WAVヘッダーの確認（"RIFF"で始まる）
        if audio_data[:4] == b"RIFF":
            try:
                with io.BytesIO(audio_data) as wav_buffer:
                    with wave.open(wav_buffer, "rb") as wav_file:
                        return wav_file.readframes(wav_file.getnframes())
            except Exception as e:
                logger.warning(f"WAV解析失敗、生データとして処理: {e}")
                return audio_data
        return audio_data

    def _trim_buffer_before_update(self):
        """トリミング前コールバックを実行（update_transcription内で呼ばれる）"""
        if self.on_before_trim_callback:
            logger.debug("🔔 トリミング前コールバック実行")
            self.on_before_trim_callback()

    def _trim_buffer_if_needed(self):
        """バッファが最大サイズを超えた場合、古いデータを削除（update_transcription内で呼ばれる）"""
        # トリミング実行
        while (
            self.total_audio_bytes > self.max_audio_bytes and len(self.audio_chunks) > 1
        ):
            removed = self.audio_chunks.pop(0)
            self.total_audio_bytes -= len(removed)
            logger.debug(f"🗑️ 古いチャンク削除: 残り{self.current_audio_duration:.1f}秒")

    def get_accumulated_audio(self) -> bytes:
        """累積音声データをWAV形式で取得"""
        if not self.audio_chunks:
            return b""

        # 全PCMデータを結合
        all_pcm = b"".join(self.audio_chunks)

        # WAV形式に変換
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(self.config.channels)
            wav_file.setsampwidth(self.config.sample_width)
            wav_file.setframerate(self.config.sample_rate)
            wav_file.writeframes(all_pcm)

        return wav_buffer.getvalue()

    def set_on_before_trim_callback(self, callback: callable):
        """トリミング前に呼ばれるコールバックを設定

        Args:
            callback: トリミング前に実行される関数
        """
        self.on_before_trim_callback = callback
        logger.info("🔔 トリミング前コールバックを設定しました")

    def _remove_confirmed_overlap(self, confirmed: str, new: str) -> str:
        """confirmed_textとnew_textの重複部分を除外してtentativeを返す（類似度ベース対応）"""
        if not confirmed:
            return new

        # 方法1: 最長一致（完全一致）
        overlap_len = 0
        max_overlap = min(len(confirmed), len(new))

        # 最長一致を探す（後ろから前へ）
        for i in range(max_overlap, 0, -1):
            if confirmed[-i:] == new[:i]:
                overlap_len = i
                break

        if overlap_len > 0:
            result = new[overlap_len:]
            logger.debug(f"   重複除外（完全一致）: {overlap_len}文字一致, 残り={len(result)}文字")
            return result

        # 方法2: 類似度ベースの重複検出（Whisperの表記揺れ対応）
        from difflib import SequenceMatcher

        # confirmed_textの末尾とnew_textの先頭を比較
        # 比較範囲: 50〜150文字
        compare_len = min(150, len(confirmed), len(new))
        if compare_len >= 50:
            confirmed_tail = confirmed[-compare_len:]
            new_head = new[:compare_len]

            # 類似度を計算（0.0〜1.0）
            similarity = SequenceMatcher(None, confirmed_tail, new_head).ratio()

            # 類似度が75%以上の場合、重複と判定
            if similarity >= 0.75:
                # 重複部分の長さを推定（類似度に基づく）
                estimated_overlap = int(compare_len * similarity)
                result = new[estimated_overlap:]
                logger.debug(f"   重複除外（類似度{similarity:.2%}）: {estimated_overlap}文字スキップ, 残り={len(result)}文字")
                logger.info(f"   💡 表記揺れを検出しました（類似度: {similarity:.2%}）")
                return result

        # 方法3: 文字数ベース推定（上記が失敗した場合）
        if len(new) > len(confirmed):
            # new_textがconfirmed_textより長い場合、confirmed_textの長さ分スキップ
            estimated_skip = len(confirmed)
            result = new[estimated_skip:]
            logger.debug(f"   重複除外（文字数推定）: {estimated_skip}文字スキップ, 残り={len(result)}文字")
            logger.warning(f"   ⚠️ 完全一致・類似度検出失敗、文字数ベースで推定しました")
            return result
        else:
            # new_textがconfirmed_text以下の場合、トリミング後の新しいバッファと判断
            # new_text全体を返す（独立した新しい内容）
            logger.debug(f"   重複除外: new_textが短い（{len(new)} <= {len(confirmed)}）→ 新しいバッファと判断")
            return new

    def force_finalize_pending_text(self, hiragana_converter=None) -> bool:
        """暫定テキストを強制的に確定テキストに移行

        バッファトリミング時に呼ばれることを想定。
        Phase 6.5のfinalize()メソッドと同様のロジックを使用。

        Args:
            hiragana_converter: ひらがな変換関数（省略可）

        Returns:
            bool: 確定テキストに移行したかどうか
        """
        if not self.last_transcription:
            return False

        # ✅ 確定済みテキストを除いた残り（重複除外ロジックを使用）
        remaining = self._remove_confirmed_overlap(self.confirmed_text, self.last_transcription)

        if not remaining:
            logger.debug("   強制確定: 残りなし（スキップ）")
            return False

        # 暫定テキストを確定に追加（追記のみ）
        self.confirmed_text += remaining

        # ひらがな変換も更新
        if hiragana_converter:
            self.confirmed_hiragana += hiragana_converter(remaining)

        logger.info(
            f"🔒 暫定テキストを強制確定（トリミング前）: "
            f"+{len(remaining)}文字, 合計{len(self.confirmed_text)}文字"
        )

        return True

    def get_initial_prompt(self) -> Optional[str]:
        """次回の文字起こし用initial_promptを取得

        確定済みテキストの末尾を返す（文脈として使用）
        ハルシネーション対策: 無効なテキストは除外
        """
        if not self.confirmed_text:
            return None

        # 最後の10文程度を返す（文脈強化）
        sentences = re.split(r"(?<=[。！？])", self.confirmed_text)
        recent_sentences = [s for s in sentences[-10:] if s.strip()]
        prompt = "".join(recent_sentences)

        # 長さ制限（Whisperのトークン制限を考慮: 224トークン ≈ 200文字）
        max_length = 200
        if len(prompt) > max_length:
            # 末尾から切り取る
            prompt = prompt[-max_length:]

        # ハルシネーション対策: 無効なテキスト（繰り返しパターン等）は除外
        if prompt and not is_valid_text(prompt):
            logger.warning("⚠️ initial_promptに無効なテキストを検出、除外します")
            return None

        return prompt if prompt else None

    def update_transcription(
        self, new_text: str, hiragana_converter=None, should_trim: bool = False
    ) -> TranscriptionResult:
        """文字起こし結果を更新し、差分を計算

        Args:
            new_text: 新しい文字起こし結果
            hiragana_converter: ひらがな変換関数（省略可）
            should_trim: トリミングが必要かどうか（デフォルトFalse）

        Returns:
            TranscriptionResult: 確定/暫定テキストを含む結果
        """
        # デバッグログ
        logger.debug(f"🔍 update_transcription呼び出し (should_trim={should_trim})")
        logger.debug(f"   前回: {self.last_transcription[:50] if self.last_transcription else '(なし)'}...")
        logger.debug(f"   今回: {new_text[:50] if new_text else '(なし)'}...")
        logger.debug(f"   既存確定: {self.confirmed_text[:50] if self.confirmed_text else '(なし)'}...")

        # 新しいアプローチ: 安定性ベースの確定
        newly_confirmed = ""
        tentative = new_text

        # ✅ confirmed_textとnew_textの重複を検出（クラスメソッドを使用）
        def remove_confirmed_overlap(confirmed: str, new: str) -> str:
            """confirmed_textとnew_textの重複部分を除外してtentativeを返す（ラッパー）"""
            return self._remove_confirmed_overlap(confirmed, new)

        # 安定性チェック（同じ結果が連続して出現したら確定）
        if new_text == self.previous_full_text:
            self.stable_count += 1
            logger.debug(f"   安定カウント: {self.stable_count}")

            # 閾値を超えたら、前回のテキストを確定に追加
            if self.stable_count >= self.config.stable_text_threshold:
                # 前回のテキストから既に確定済みの部分を除く
                if self.confirmed_text:
                    # ✅ 重複除外ロジックを使用
                    remaining = remove_confirmed_overlap(self.confirmed_text, new_text)

                    if remaining:
                        # 残りの部分から、適切な区切りまでを確定に追加
                        # 句読点・空白で区切る
                        break_points = []
                        for char in ["。", "！", "？", " ", "　"]:
                            pos = remaining.find(char)
                            if pos > 0:
                                break_points.append(pos + 1)

                        if break_points:
                            # 最初の区切りまでを確定
                            cut_pos = min(break_points)
                            newly_confirmed = remaining[:cut_pos]
                            self.confirmed_text += newly_confirmed
                            tentative = remaining[cut_pos:]
                            logger.debug(f"   新規確定: {newly_confirmed[:30]}...")
                        else:
                            # 区切りがない場合、残り全体を暫定のまま
                            tentative = remaining
                    else:
                        # 重複除外後に残りがない場合
                        tentative = ""
                        logger.debug(f"   重複除外後、残りなし")
                else:
                    # 初回の確定: 適切な区切りまでを確定
                    break_points = []
                    for char in ["。", "！", "？"]:
                        pos = new_text.find(char)
                        if pos > 0:
                            break_points.append(pos + 1)

                    if break_points:
                        cut_pos = min(break_points)
                        newly_confirmed = new_text[:cut_pos]
                        self.confirmed_text = newly_confirmed
                        tentative = new_text[cut_pos:]
                        logger.debug(f"   初回確定: {newly_confirmed[:30]}...")
                    else:
                        # 句読点がない場合、全て暫定のまま
                        tentative = new_text
        else:
            # テキストが変わった場合
            self.stable_count = 0
            logger.debug(f"   テキスト変更 → 安定カウントリセット")

            # ✅ 重複除外ロジックを使用
            if self.confirmed_text:
                tentative = remove_confirmed_overlap(self.confirmed_text, new_text)
            else:
                # 確定テキストがまだない場合、全て暫定
                tentative = new_text

        # ✅ トリミング前コールバックを実行（この時点でlast_transcriptionは古い値）
        if should_trim:
            self._trim_buffer_before_update()

        # 前回結果を更新（トリミング後に更新）
        self.previous_full_text = new_text
        self.last_transcription = new_text

        # ✅ 強制確定後に暫定テキストを再計算（重複除外ロジックを再利用）
        if should_trim:
            tentative = remove_confirmed_overlap(self.confirmed_text, new_text)
            logger.debug(f"   トリミング後の暫定テキスト: {len(tentative)}文字")

        # ひらがな変換
        confirmed_hiragana = ""
        tentative_hiragana = ""
        if hiragana_converter:
            if newly_confirmed:
                confirmed_hiragana = hiragana_converter(newly_confirmed)
                self.confirmed_hiragana += confirmed_hiragana
            if tentative:
                tentative_hiragana = hiragana_converter(tentative)

        # ✅ トリミングを実行（強制確定後にチャンク削除）
        if should_trim:
            self._trim_buffer_if_needed()

        # 全体テキスト = 確定 + 暫定（常に連続）
        full_text = self.confirmed_text + tentative

        # デバッグログ: 先頭50文字を出力
        logger.debug(f"   確定テキスト（先頭50文字）: {self.confirmed_text[:50] if self.confirmed_text else '(なし)'}...")
        logger.debug(f"   暫定テキスト（先頭50文字）: {tentative[:50] if tentative else '(なし)'}...")
        logger.debug(f"   全体テキスト（先頭50文字）: {full_text[:50] if full_text else '(なし)'}...")

        logger.info(
            f"📝 文字起こし更新: "
            f"確定={len(self.confirmed_text)}文字, "
            f"暫定={len(tentative)}文字, "
            f"全体={len(full_text)}文字, "
            f"安定={self.stable_count}"
        )

        # デバッグログ: 返却する確定テキストの詳細
        logger.info(f"=" * 80)
        logger.info(f"📤 サーバー→クライアント送信データ:")
        logger.info(f"   confirmed_text.length: {len(self.confirmed_text)}")
        logger.info(f"   confirmed_text (全文):")
        logger.info(f"   「{self.confirmed_text}」")
        logger.info(f"   tentative_text.length: {len(tentative)}")
        logger.info(f"   tentative_text (先頭100文字): {tentative[:100] if tentative else '(なし)'}")
        logger.info(f"   full_text.length: {len(full_text)}")
        logger.info(f"=" * 80)

        return TranscriptionResult(
            confirmed_text=self.confirmed_text,
            tentative_text=tentative,
            full_text=full_text,
            confirmed_hiragana=self.confirmed_hiragana,
            tentative_hiragana=tentative_hiragana,
            is_final=False,
        )

    def finalize(self, hiragana_converter=None) -> TranscriptionResult:
        """セッション終了時に全テキストを確定"""
        # 残りの暫定テキストを確定
        if self.last_transcription:
            # 確定済みテキストを除いた残り（暫定部分）
            if self.confirmed_text in self.last_transcription:
                remaining = self.last_transcription[len(self.confirmed_text) :]
            else:
                # バッファがトリミングされた場合、全体を確定に追加
                remaining = self.last_transcription

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
            is_final=True,
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
