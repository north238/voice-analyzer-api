"""
累積バッファのトリミング機能のテスト

Phase 6.6で追加された機能:
- バッファトリミング時の強制確定
- トリミング前コールバック
"""

import pytest
import wave
import io
from services.cumulative_buffer import (
    CumulativeBuffer,
    CumulativeBufferConfig,
    TranscriptionResult,
)


@pytest.fixture
def buffer_config():
    """テスト用のバッファ設定（短めの設定）"""
    return CumulativeBufferConfig(
        max_audio_duration_seconds=1.0,  # 1秒で簡単にトリミング発生
        transcription_interval_chunks=1,
        stable_text_threshold=2,
        sample_rate=16000,
        channels=1,
        sample_width=2,
    )


@pytest.fixture
def buffer(buffer_config):
    """テスト用の累積バッファ"""
    return CumulativeBuffer(buffer_config)


def create_dummy_audio(duration_seconds: float, sample_rate: int = 16000) -> bytes:
    """ダミー音声データ（WAV形式）を生成

    Args:
        duration_seconds: 音声の長さ（秒）
        sample_rate: サンプルレート

    Returns:
        WAV形式の音声データ
    """
    # PCMデータ生成（無音）
    num_samples = int(duration_seconds * sample_rate)
    pcm_data = b"\x00\x00" * num_samples  # 16bit無音データ

    # WAV形式に変換
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)

    return wav_buffer.getvalue()


class TestCallbackSetup:
    """コールバック設定のテスト"""

    def test_set_callback(self, buffer):
        """コールバックを設定できることを確認"""
        callback_called = []

        def test_callback():
            callback_called.append(True)

        buffer.set_on_before_trim_callback(test_callback)
        assert buffer.on_before_trim_callback is not None

    def test_callback_is_optional(self, buffer):
        """コールバックは省略可能"""
        # コールバックなしでもエラーにならない
        audio = create_dummy_audio(0.5)
        buffer.add_audio_chunk(audio)
        assert True  # エラーが発生しなければOK


class TestTrimWithCallback:
    """トリミング時のコールバック実行テスト"""

    def test_callback_called_on_trim(self, buffer):
        """トリミング時にコールバックが呼ばれることを確認"""
        callback_called = []

        def test_callback():
            callback_called.append(True)

        buffer.set_on_before_trim_callback(test_callback)

        # トリミングが発生するまで音声を追加（1秒を超える）
        for i in range(3):
            audio = create_dummy_audio(0.5)  # 0.5秒 × 3 = 1.5秒
            buffer.add_audio_chunk(audio)

        # コールバックが呼ばれたことを確認
        assert len(callback_called) > 0, "コールバックが呼ばれませんでした"

    def test_callback_not_called_before_trim(self, buffer):
        """トリミング前はコールバックが呼ばれないことを確認"""
        callback_called = []

        def test_callback():
            callback_called.append(True)

        buffer.set_on_before_trim_callback(test_callback)

        # トリミングが発生しない範囲で音声を追加
        audio = create_dummy_audio(0.5)  # 0.5秒 < 1秒（上限）
        buffer.add_audio_chunk(audio)

        # コールバックは呼ばれない
        assert len(callback_called) == 0


class TestForceFinalizePendingText:
    """強制確定メソッドのテスト"""

    def test_force_finalize_basic(self, buffer):
        """基本的な強制確定動作を確認"""
        # 文字起こし結果を設定
        buffer.last_transcription = "これはテストです"
        buffer.confirmed_text = ""

        # 強制確定実行
        result = buffer.force_finalize_pending_text()

        assert result is True
        assert buffer.confirmed_text == "これはテストです"

    def test_force_finalize_with_existing_confirmed(self, buffer):
        """既存の確定テキストがある場合の強制確定"""
        buffer.last_transcription = "これはテストですシステムを構築しています"
        buffer.confirmed_text = "これはテストです"

        # 強制確定実行
        result = buffer.force_finalize_pending_text()

        assert result is True
        assert buffer.confirmed_text == "これはテストですシステムを構築しています"

    def test_force_finalize_no_pending_text(self, buffer):
        """暫定テキストがない場合"""
        buffer.last_transcription = "これはテストです"
        buffer.confirmed_text = "これはテストです"  # 全て確定済み

        # 強制確定実行
        result = buffer.force_finalize_pending_text()

        assert result is False  # 確定するものがない
        assert buffer.confirmed_text == "これはテストです"

    def test_force_finalize_empty_transcription(self, buffer):
        """文字起こし結果が空の場合"""
        buffer.last_transcription = ""
        buffer.confirmed_text = ""

        # 強制確定実行
        result = buffer.force_finalize_pending_text()

        assert result is False
        assert buffer.confirmed_text == ""

    def test_force_finalize_with_hiragana_converter(self, buffer):
        """ひらがな変換付きの強制確定"""

        def hiragana_converter(text: str) -> str:
            """簡易ひらがな変換（テスト用）"""
            return text + "_ひらがな"

        buffer.last_transcription = "これはテストです"
        buffer.confirmed_text = ""
        buffer.confirmed_hiragana = ""

        # ひらがな変換付きで強制確定
        result = buffer.force_finalize_pending_text(
            hiragana_converter=hiragana_converter
        )

        assert result is True
        assert buffer.confirmed_text == "これはテストです"
        assert buffer.confirmed_hiragana == "これはテストです_ひらがな"


class TestTrimWithForceFinalize:
    """トリミングと強制確定の統合テスト"""

    def test_trim_preserves_context(self, buffer):
        """トリミング時に文脈が保持されることを確認"""
        finalized_texts = []

        def on_before_trim_callback():
            """トリミング前に暫定テキストを確定"""
            result = buffer.force_finalize_pending_text()
            if result:
                finalized_texts.append(buffer.confirmed_text)

        buffer.set_on_before_trim_callback(on_before_trim_callback)

        # 文字起こし結果を設定
        buffer.last_transcription = "皆さんおはようございます"

        # トリミングが発生するまで音声を追加
        for i in range(3):
            audio = create_dummy_audio(0.5)
            buffer.add_audio_chunk(audio)

        # 確定テキストが保存されていることを確認
        assert len(finalized_texts) > 0
        assert "皆さんおはようございます" in buffer.confirmed_text

    def test_multiple_trims_accumulate_text(self, buffer):
        """複数回のトリミングで確定テキストが蓄積されることを確認"""

        def on_before_trim_callback():
            buffer.force_finalize_pending_text()

        buffer.set_on_before_trim_callback(on_before_trim_callback)

        # 1回目のトリミング
        buffer.last_transcription = "最初のテキスト"
        for i in range(3):
            audio = create_dummy_audio(0.5)
            buffer.add_audio_chunk(audio)

        # 2回目のトリミング
        buffer.last_transcription = "最初のテキスト2回目のテキスト"
        for i in range(3):
            audio = create_dummy_audio(0.5)
            buffer.add_audio_chunk(audio)

        # 確定テキストが蓄積されていることを確認
        assert "最初のテキスト" in buffer.confirmed_text
        assert "2回目のテキスト" in buffer.confirmed_text


class TestBufferStats:
    """統計情報のテスト"""

    def test_stats_include_trim_info(self, buffer):
        """統計情報にトリミング関連の情報が含まれることを確認"""

        def on_before_trim_callback():
            buffer.force_finalize_pending_text()

        buffer.set_on_before_trim_callback(on_before_trim_callback)

        # 文字起こし結果を設定
        buffer.last_transcription = "テストテキスト"

        # トリミング発生まで音声追加
        for i in range(3):
            audio = create_dummy_audio(0.5)
            buffer.add_audio_chunk(audio)

        stats = buffer.get_stats()

        # 確定テキストの長さが記録されている
        assert stats["confirmed_text_length"] > 0
        assert stats["chunk_count"] == 3
