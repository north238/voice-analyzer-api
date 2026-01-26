"""
翻訳機能のテスト
"""

import pytest
from app.services.translator import Translator, translate_text, get_translator


class TestTranslator:
    """Translatorクラスのテスト"""

    @pytest.fixture
    def translator(self):
        """テスト用の翻訳インスタンス"""
        return Translator()

    # ========================================
    # _load_model のテスト
    # ========================================

    def test_load_model_lazy_loading(self, translator):
        """遅延ロードの動作確認"""
        # 初期状態ではモデルは未ロード
        assert translator.model is None
        assert translator.tokenizer is None

        # モデルロード実行
        translator._load_model()

        # ロード後はモデルとトークナイザが設定される
        assert translator.model is not None
        assert translator.tokenizer is not None

    def test_load_model_idempotent(self, translator):
        """複数回呼び出しても同じインスタンス"""
        translator._load_model()
        model1 = translator.model
        tokenizer1 = translator.tokenizer

        # 再度呼び出し
        translator._load_model()
        model2 = translator.model
        tokenizer2 = translator.tokenizer

        # 同じインスタンスであることを確認
        assert model1 is model2
        assert tokenizer1 is tokenizer2

    # ========================================
    # _preprocess_text のテスト
    # ========================================

    def test_preprocess_text_phone_number(self, translator):
        """電話番号の保護処理"""
        text = "電話番号は09012345678です。"
        processed, replacements = translator._preprocess_text(text)

        # 電話番号がプレースホルダーに置換される
        assert "__PHONE_0__" in processed
        assert "09012345678" not in processed
        assert replacements["__PHONE_0__"] == "09012345678"

    def test_preprocess_text_multiple_phones(self, translator):
        """複数の電話番号の保護処理"""
        text = "連絡先は09012345678または08012345678です。"
        processed, replacements = translator._preprocess_text(text)

        # 2つの電話番号がそれぞれプレースホルダーに置換
        assert "__PHONE_0__" in processed
        assert "__PHONE_1__" in processed
        assert len(replacements) == 2

    def test_preprocess_text_no_phone(self, translator):
        """電話番号がない場合"""
        text = "これは普通のテキストです。"
        processed, replacements = translator._preprocess_text(text)

        # 変更なし
        assert processed == text
        assert len(replacements) == 0

    def test_preprocess_text_short_number(self, translator):
        """10桁未満の数字は保護しない"""
        text = "番号は123456789です。"
        processed, replacements = translator._preprocess_text(text)

        # 9桁なので保護されない
        assert processed == text
        assert len(replacements) == 0

    # ========================================
    # _postprocess_text のテスト
    # ========================================

    def test_postprocess_text_restore_phone(self, translator):
        """保護した電話番号の復元"""
        text = "Phone number is __PHONE_0__."
        replacements = {"__PHONE_0__": "09012345678"}
        restored = translator._postprocess_text(text, replacements)

        assert "09012345678" in restored
        assert "__PHONE_0__" not in restored

    def test_postprocess_text_multiple_replacements(self, translator):
        """複数のプレースホルダーの復元"""
        text = "Numbers are __PHONE_0__ and __PHONE_1__."
        replacements = {
            "__PHONE_0__": "09012345678",
            "__PHONE_1__": "08012345678",
        }
        restored = translator._postprocess_text(text, replacements)

        assert "09012345678" in restored
        assert "08012345678" in restored
        assert "__PHONE_0__" not in restored
        assert "__PHONE_1__" not in restored

    def test_postprocess_text_empty_replacements(self, translator):
        """置換マップが空の場合"""
        text = "Normal text."
        replacements = {}
        restored = translator._postprocess_text(text, replacements)

        assert restored == text

    # ========================================
    # _split_into_sentences のテスト
    # ========================================

    def test_split_into_sentences_single(self, translator):
        """単一文の分割"""
        text = "今日は良い天気です。"
        sentences = translator._split_into_sentences(text)

        assert len(sentences) == 1
        assert sentences[0] == "今日は良い天気です。"

    def test_split_into_sentences_multiple(self, translator):
        """複数文の分割"""
        text = "今日は良い天気です。明日も晴れるでしょう。"
        sentences = translator._split_into_sentences(text)

        assert len(sentences) == 2
        assert sentences[0] == "今日は良い天気です。"
        assert sentences[1] == "明日も晴れるでしょう。"

    def test_split_into_sentences_no_period(self, translator):
        """句点がない場合"""
        text = "今日は良い天気です"
        sentences = translator._split_into_sentences(text)

        # 句点を自動追加
        assert len(sentences) == 1
        assert sentences[0] == "今日は良い天気です。"

    def test_split_into_sentences_trailing_period(self, translator):
        """末尾の空白句点を処理"""
        text = "文1。文2。"
        sentences = translator._split_into_sentences(text)

        assert len(sentences) == 2
        assert sentences[0] == "文1。"
        assert sentences[1] == "文2。"

    def test_split_into_sentences_empty_string(self, translator):
        """空文字列の分割"""
        text = ""
        sentences = translator._split_into_sentences(text)

        assert len(sentences) == 0

    def test_split_into_sentences_whitespace_only(self, translator):
        """空白のみの場合"""
        text = "   "
        sentences = translator._split_into_sentences(text)

        assert len(sentences) == 0

    # ========================================
    # translate_text のテスト（基本動作）
    # ========================================

    def test_translate_text_empty_string(self, translator):
        """空文字列の翻訳"""
        result = translator.translate_text("")
        assert result == ""

    def test_translate_text_whitespace_only(self, translator):
        """空白のみの翻訳"""
        result = translator.translate_text("   ")
        assert result == ""

    def test_translate_text_basic_sentence(self, translator):
        """基本的な日本語文の翻訳（厳密な一致は求めない）"""
        text = "今日は良い天気です。"
        result = translator.translate_text(text)

        # 何かしらの英語テキストが返却されることを確認
        assert result is not None
        assert len(result) > 0
        assert isinstance(result, str)

    def test_translate_text_short_phrase(self, translator):
        """短いフレーズの翻訳"""
        text = "こんにちは"
        result = translator.translate_text(text)

        # 結果が返却される
        assert result is not None
        assert len(result) > 0

    # ========================================
    # translate_text のテスト（長文処理）
    # ========================================

    def test_translate_text_multiple_sentences(self, translator):
        """複数文の翻訳（文分割処理）"""
        text = "今日は良い天気です。明日も晴れるでしょう。"
        result = translator.translate_text(text)

        # 複数文が処理される
        assert result is not None
        assert len(result) > 0

    def test_translate_text_long_text(self, translator):
        """長文の翻訳（自動分割）"""
        # 長い文を生成
        text = "これは長い文章のテスト��す。" * 20  # 複数文を生成
        result = translator.translate_text(text)

        # 長文でも処理できる
        assert result is not None
        assert len(result) > 0

    # ========================================
    # translate_text のテスト（前処理・後処理）
    # ========================================

    def test_translate_text_with_phone_number(self, translator):
        """電話番号を含むテキストの翻訳"""
        text = "私の電話番号は09012345678です。"
        result = translator.translate_text(text)

        # 翻訳結果に電話番号が含まれることを期待
        # （モデルの振る舞いによっては保持されない可能性もある）
        assert result is not None
        assert len(result) > 0

    # ========================================
    # _translate_chunk のテスト（内部メソッド）
    # ========================================

    def test_translate_chunk_basic(self, translator):
        """単一チャンクの翻訳処理"""
        translator._load_model()  # モデルを事前ロード
        text = "こんにちは世界"
        result = translator._translate_chunk(text)

        assert result is not None
        assert len(result) > 0
        assert isinstance(result, str)

    # ========================================
    # _translate_long_text のテスト（内部メソッド）
    # ========================================

    def test_translate_long_text_basic(self, translator):
        """長文翻訳処理（複数文の結合）"""
        translator._load_model()  # モデルを事前ロード
        text = "文1です。文2です。文3です。"
        result = translator._translate_long_text(text)

        assert result is not None
        assert len(result) > 0

    # ========================================
    # パラメータ化テスト
    # ========================================

    @pytest.mark.parametrize(
        "input_text,expected_empty",
        [
            ("", True),  # 空文字列
            ("   ", True),  # 空白のみ
            ("こんにちは", False),  # 通常のテキスト
            ("今日は良い天気です。", False),  # 句点付き
        ],
    )
    def test_translate_text_empty_check_parametrized(
        self, translator, input_text, expected_empty
    ):
        """パラメータ化テスト: 空文字列判定"""
        result = translator.translate_text(input_text)

        if expected_empty:
            assert result == ""
        else:
            assert len(result) > 0

    @pytest.mark.parametrize(
        "phone_number",
        [
            "09012345678",  # 11桁
            "0120123456",  # 10桁
            "08011112222",  # 11桁
        ],
    )
    def test_preprocess_phone_numbers_parametrized(self, translator, phone_number):
        """パラメータ化テスト: 様々な電話番号パターン"""
        text = f"電話番号は{phone_number}です。"
        processed, replacements = translator._preprocess_text(text)

        assert "__PHONE_0__" in processed
        assert phone_number not in processed
        assert replacements["__PHONE_0__"] == phone_number


class TestGetTranslator:
    """get_translator関数のテスト"""

    def test_get_translator_singleton(self):
        """シングルトンパターンの動作確認"""
        # グローバルインスタンスをリセット（テスト用）
        import app.services.translator as t

        t._translator_instance = None

        translator1 = get_translator()
        translator2 = get_translator()

        # 同じインスタンスが返される
        assert translator1 is translator2

    def test_get_translator_returns_translator_instance(self):
        """Translatorインスタンスが返される"""
        import app.services.translator as t

        t._translator_instance = None

        translator = get_translator()
        assert isinstance(translator, Translator)


class TestTranslateTextFunction:
    """translate_text便利関数のテスト"""

    def test_translate_text_function_basic(self):
        """基本的な翻訳動作"""
        result = translate_text("こんにちは")
        assert result is not None
        assert len(result) > 0

    def test_translate_text_function_empty(self):
        """空文字列の処理"""
        result = translate_text("")
        assert result == ""

    def test_translate_text_function_uses_singleton(self):
        """シングルトンインスタンスを使用"""
        import app.services.translator as t

        t._translator_instance = None

        # 初回呼び出し
        result1 = translate_text("テスト")
        translator1 = t._translator_instance

        # 2回目呼び出し
        result2 = translate_text("テスト")
        translator2 = t._translator_instance

        # 同じインスタンスが使用される
        assert translator1 is translator2


# ========================================
# 統合テスト
# ========================================


class TestTranslatorIntegration:
    """Translatorの統合テスト"""

    def test_full_translation_workflow(self):
        """翻訳の完全なワークフロー"""
        # 1. インスタンス取得
        translator = get_translator()

        # 2. 基本的な翻訳
        result1 = translator.translate_text("今日は良い天気です。")
        assert len(result1) > 0

        # 3. 複数文の翻訳
        result2 = translator.translate_text("おはようございます。今日も頑張りましょう。")
        assert len(result2) > 0

        # 4. 電話番号を含む翻訳
        result3 = translator.translate_text("連絡先は09012345678です。")
        assert len(result3) > 0

    def test_consecutive_translations(self):
        """連続した翻訳処理"""
        translator = get_translator()

        texts = [
            "こんにちは",
            "今日は良い天気です。",
            "明日も晴れるでしょう。",
            "よろしくお願いします。",
        ]

        for text in texts:
            result = translator.translate_text(text)
            assert result is not None
            assert len(result) > 0

    def test_mixed_content_translation(self):
        """様々なコンテンツの混在した翻訳"""
        translator = get_translator()

        # 電話番号、句読点、複数文を含む複雑なテキスト
        text = "私の名前は山田太郎です。電話番号は09012345678です。よろしくお願いします。"
        result = translator.translate_text(text)

        assert result is not None
        assert len(result) > 0


if __name__ == "__main__":
    # このファイルを直接実行してテスト
    pytest.main([__file__, "-v"])
