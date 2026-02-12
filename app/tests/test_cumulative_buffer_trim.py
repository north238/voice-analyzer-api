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
        should_transcribe, should_trim = buffer.add_audio_chunk(audio)
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
        should_trim = False
        for i in range(3):
            audio = create_dummy_audio(0.5)  # 0.5秒 × 3 = 1.5秒
            should_transcribe, should_trim = buffer.add_audio_chunk(audio)

        # Phase 7.0: トリミングはupdate_transcription内で実行される
        # should_trimがTrueの場合、update_transcriptionを呼ぶ必要がある
        if should_trim:
            buffer.update_transcription("テストテキスト", should_trim=True)

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
        should_transcribe, should_trim = buffer.add_audio_chunk(audio)

        # Phase 7.0: should_trimがFalseなのでトリミング不要
        assert should_trim is False

        # update_transcriptionを呼んでもコールバックは呼ばれない
        buffer.update_transcription("テストテキスト", should_trim=False)

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
        should_trim = False
        for i in range(3):
            audio = create_dummy_audio(0.5)
            should_transcribe, should_trim = buffer.add_audio_chunk(audio)

        # Phase 7.0: トリミングはupdate_transcription内で実行される
        if should_trim:
            buffer.update_transcription("皆さんおはようございます", should_trim=True)

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
        should_trim1 = False
        for i in range(3):
            audio = create_dummy_audio(0.5)
            should_transcribe, should_trim1 = buffer.add_audio_chunk(audio)

        # Phase 7.0: トリミングはupdate_transcription内で実行される
        if should_trim1:
            buffer.update_transcription("最初のテキスト", should_trim=True)

        # 2回目のトリミング
        buffer.last_transcription = "最初のテキスト2回目のテキスト"
        should_trim2 = False
        for i in range(3):
            audio = create_dummy_audio(0.5)
            should_transcribe, should_trim2 = buffer.add_audio_chunk(audio)

        if should_trim2:
            buffer.update_transcription("最初のテキスト2回目のテキスト", should_trim=True)

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
        should_trim = False
        for i in range(3):
            audio = create_dummy_audio(0.5)
            should_transcribe, should_trim = buffer.add_audio_chunk(audio)

        # Phase 7.0: トリミングはupdate_transcription内で実行される
        if should_trim:
            buffer.update_transcription("テストテキスト", should_trim=True)

        stats = buffer.get_stats()

        # 確定テキストの長さが記録されている
        assert stats["confirmed_text_length"] > 0
        assert stats["chunk_count"] == 3


class TestConfirmedTextIndependence:
    """Phase 8: 確定テキストの独立管理テスト"""

    def test_full_text_is_confirmed_plus_tentative(self, buffer):
        """full_text = confirmed_text + tentative_text であることを確認"""
        # 初期文字起こし
        result1 = buffer.update_transcription("ようこそ", should_trim=False)

        # 初回は全て暫定
        assert result1.confirmed_text == ""
        assert result1.tentative_text == "ようこそ"
        assert result1.full_text == result1.confirmed_text + result1.tentative_text
        assert result1.full_text == "ようこそ"

    def test_confirmed_text_persists_after_trim(self, buffer):
        """トリミング後も確定テキストが保持されることを確認"""

        def on_before_trim_callback():
            buffer.force_finalize_pending_text()

        buffer.set_on_before_trim_callback(on_before_trim_callback)

        # 初期文字起こし
        buffer.update_transcription("ようこそ", should_trim=False)

        # 安定して確定
        buffer.update_transcription("ようこそ", should_trim=False)

        # トリミング発生
        should_trim = False
        for i in range(3):
            audio = create_dummy_audio(0.5)
            should_transcribe, should_trim = buffer.add_audio_chunk(audio)

        # 新しい文字起こし（バッファには "ようこそ" が含まれない想定）
        if should_trim:
            result = buffer.update_transcription("今日は", should_trim=True)

            # 確定テキストは保持されている
            assert "ようこそ" in result.confirmed_text
            # 全体テキストは連続している
            assert result.full_text == result.confirmed_text + result.tentative_text
            # 暫定テキストは新しいバッファの内容
            assert "今日は" in result.full_text

    def test_no_duplication_between_confirmed_and_tentative(self, buffer):
        """確定テキストと暫定テキストが重複しないことを確認"""

        def on_before_trim_callback():
            buffer.force_finalize_pending_text()

        buffer.set_on_before_trim_callback(on_before_trim_callback)

        # 文字起こし結果を段階的に更新
        result1 = buffer.update_transcription("こんにちは", should_trim=False)
        result2 = buffer.update_transcription("こんにちは今日は", should_trim=False)

        # トリミング発生
        should_trim = False
        for i in range(3):
            audio = create_dummy_audio(0.5)
            should_transcribe, should_trim = buffer.add_audio_chunk(audio)

        if should_trim:
            result3 = buffer.update_transcription("良い天気です", should_trim=True)

            # full_text = confirmed_text + tentative_text
            assert result3.full_text == result3.confirmed_text + result3.tentative_text

            # 確定と暫定が重複していないことを確認
            # （簡易チェック: 長さの合計がfull_textの長さと一致）
            combined_length = len(result3.confirmed_text) + len(result3.tentative_text)
            assert len(result3.full_text) == combined_length

    def test_force_finalize_after_trim(self, buffer):
        """トリミング後のforce_finalize_pending_textが正しく動作することを確認"""
        # 文字起こし結果を設定
        buffer.last_transcription = "こんにちは今日は良い天気です"
        buffer.confirmed_text = "こんにちは"

        # 強制確定実行（バッファに確定テキストが含まれる場合）
        result1 = buffer.force_finalize_pending_text()
        assert result1 is True
        assert buffer.confirmed_text == "こんにちは今日は良い天気です"

        # バッファがトリミングされた後（確定テキストが含まれない場合）
        buffer.last_transcription = "明日も晴れるでしょう"

        # 強制確定実行（バッファに確定テキストが含まれない）
        result2 = buffer.force_finalize_pending_text()
        assert result2 is True
        assert "明日も晴れるでしょう" in buffer.confirmed_text
        assert buffer.confirmed_text == "こんにちは今日は良い天気です明日も晴れるでしょう"

    def test_session_end_with_independent_confirmed_text(self, buffer):
        """セッション終了時、確定テキストが正しく保存されることを確認"""

        def on_before_trim_callback():
            buffer.force_finalize_pending_text()

        buffer.set_on_before_trim_callback(on_before_trim_callback)

        # 段階的に文字起こし
        buffer.update_transcription("第一部", should_trim=False)

        # トリミング発生
        should_trim = False
        for i in range(3):
            audio = create_dummy_audio(0.5)
            should_transcribe, should_trim = buffer.add_audio_chunk(audio)

        if should_trim:
            buffer.update_transcription("第二部", should_trim=True)

        # セッション終了
        final_result = buffer.finalize()

        # 全体が確定テキストに含まれている
        assert "第一部" in final_result.confirmed_text
        assert "第二部" in final_result.confirmed_text
        # 暫定テキストは空
        assert final_result.tentative_text == ""
        # full_textと確定テキストが一致
        assert final_result.full_text == final_result.confirmed_text
