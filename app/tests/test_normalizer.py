"""
JapaneseNormalizer の基本的なテスト

test_normalizer_comprehensive.py との棲み分け:
- test_normalizer.py (本ファイル): 基本的な機能の単体テスト
- test_normalizer_comprehensive.py: 実際のユースケースを含む包括的なテスト
"""

import pytest
from app.utils.normalizer import JapaneseNormalizer


class TestJapaneseNormalizer:
    """JapaneseNormalizerクラスの基本テスト"""

    @pytest.fixture
    def normalizer(self):
        """テスト用の正規化インスタンス"""
        return JapaneseNormalizer()

    # ========================================
    # to_hiragana のテスト: 基本動作
    # ========================================

    def test_to_hiragana_basic_kanji(self, normalizer):
        """基本的な漢字→ひらがな変換"""
        assert normalizer.to_hiragana("今日") == "きょう"
        assert normalizer.to_hiragana("明日") == "あした"
        assert normalizer.to_hiragana("世界") == "せかい"

    def test_to_hiragana_basic_katakana(self, normalizer):
        """基本的なカタカナ→ひらがな変換"""
        assert normalizer.to_hiragana("リンゴ") == "りんご"
        assert normalizer.to_hiragana("バナナ") == "ばなな"
        assert normalizer.to_hiragana("カタカナ") == "かたかな"

    def test_to_hiragana_already_hiragana(self, normalizer):
        """既にひらがなのテキスト（変換なし）"""
        assert normalizer.to_hiragana("ひらがな") == "ひらがな"
        assert normalizer.to_hiragana("こんにちは") == "こんにちは"

    def test_to_hiragana_mixed_text(self, normalizer):
        """混在テキスト（漢字・カタカナ・ひらがな）"""
        result = normalizer.to_hiragana("今日はリンゴを食べました")
        assert result == "きょうはりんごをたべました"

    # ========================================
    # to_hiragana のテスト: 数字変換
    # ========================================

    def test_to_hiragana_number_with_counter(self, normalizer):
        """数字+助数詞の変換"""
        assert normalizer.to_hiragana("3個") == "さんこ"
        assert normalizer.to_hiragana("2本") == "にほん"
        assert normalizer.to_hiragana("5枚") == "ごまい"

    def test_to_hiragana_year_date(self, normalizer):
        """年号・日付の変換"""
        result = normalizer.to_hiragana("1974年3月")
        assert result == "せんきゅうひゃくななじゅうよねんさんがつ"

    def test_to_hiragana_age(self, normalizer):
        """年齢の変換（音便処理を含む）"""
        assert normalizer.to_hiragana("50歳") == "ごじゅっさい"
        assert normalizer.to_hiragana("20歳") == "にじゅっさい"

    # ========================================
    # to_hiragana のテスト: エッジケース
    # ========================================

    def test_to_hiragana_empty_string(self, normalizer):
        """空文字列の処理"""
        assert normalizer.to_hiragana("") == ""

    def test_to_hiragana_whitespace_only(self, normalizer):
        """空白のみの処理"""
        assert normalizer.to_hiragana("   ") == ""
        assert normalizer.to_hiragana("　　") == ""

    def test_to_hiragana_with_punctuation_default(self, normalizer):
        """句読点の処理（デフォルト: 削除）"""
        result = normalizer.to_hiragana("今日は良い天気です。")
        assert "。" not in result
        assert result == "きょうはよいてんきです"

    def test_to_hiragana_with_alphabet(self, normalizer):
        """アルファベット混在"""
        result = normalizer.to_hiragana("Hello世界")
        # アルファベットはそのまま、漢字はひらがなに
        assert "Hello" in result
        assert "せかい" in result

    def test_to_hiragana_with_hyphenated_numbers(self, normalizer):
        """ハイフン付き数字（電話番号など）"""
        result = normalizer.to_hiragana("電話番号は090-1234-5678です")
        # ハイフン付き数字はそのまま保持される
        assert "090-1234-5678" in result

    # ========================================
    # keep_punctuation パラメータのテスト
    # ========================================

    def test_to_hiragana_keep_punctuation_true(self, normalizer):
        """句読点保持モード（True）"""
        result = normalizer.to_hiragana("今日は、良い天気です。", keep_punctuation=True)
        assert "、" in result
        assert "。" in result
        assert result == "きょうは、よいてんきです。"

    def test_to_hiragana_keep_punctuation_false(self, normalizer):
        """句読点削除モード（False）"""
        result = normalizer.to_hiragana("今日は、良い天気です。", keep_punctuation=False)
        assert "、" not in result
        assert "。" not in result

    def test_to_hiragana_keep_whitespace(self, normalizer):
        """keep_punctuation=Trueで空白も保持"""
        result = normalizer.to_hiragana("今日 は 良い 天気", keep_punctuation=True)
        # 空白は単一スペースに正規化される
        assert " " in result

    # ========================================
    # to_hiragana_readable のテスト
    # ========================================

    def test_to_hiragana_readable_basic(self, normalizer):
        """読みやすさモードの基本動作"""
        result = normalizer.to_hiragana_readable("今日は良い天気です。")
        assert result == "きょうはよいてんきです。"
        assert "。" in result

    def test_to_hiragana_readable_with_comma(self, normalizer):
        """読みやすさモードで読点も保持"""
        result = normalizer.to_hiragana_readable("りんご、みかん、バナナ")
        assert "、" in result
        assert result == "りんご、みかん、ばなな"

    # ========================================
    # to_hiragana_with_counters のテスト
    # ========================================

    def test_to_hiragana_with_counters_basic(self, normalizer):
        """数え言葉モードの基本動作"""
        assert normalizer.to_hiragana_with_counters("りんご1") == "りんごひとつ"
        assert normalizer.to_hiragana_with_counters("みかん2") == "みかんふたつ"
        assert normalizer.to_hiragana_with_counters("バナナ3") == "ばななみっつ"

    def test_to_hiragana_with_counters_with_unit(self, normalizer):
        """助数詞がある場合は数え言葉に変換しない"""
        # 助数詞「個」があるため「さんこ」のまま
        assert normalizer.to_hiragana_with_counters("卵3個") == "たまごさんこ"
        assert normalizer.to_hiragana_with_counters("牛乳2本") == "ぎゅうにゅうにほん"

    # ========================================
    # add_punctuation のテスト
    # ========================================

    def test_add_punctuation_basic(self, normalizer):
        """句読点挿入の基本動作"""
        result = normalizer.add_punctuation("今日は良い天気です")
        # 句読点が適切に挿入される
        assert "。" in result or "、" in result

    def test_add_punctuation_empty_string(self, normalizer):
        """空文字列の句読点挿入"""
        assert normalizer.add_punctuation("") == ""

    # ========================================
    # normalize_with_mode のテスト
    # ========================================

    def test_normalize_with_mode_standard(self, normalizer):
        """モード指定: standard"""
        result = normalizer.normalize_with_mode("今日は良い天気です。", mode="standard")
        assert "。" not in result  # 句読点削除

    def test_normalize_with_mode_readable(self, normalizer):
        """モード指定: readable"""
        result = normalizer.normalize_with_mode("今日は良い天気です。", mode="readable")
        assert "。" in result  # 句読点保持

    def test_normalize_with_mode_counter(self, normalizer):
        """モード指定: counter"""
        result = normalizer.normalize_with_mode("りんご3", mode="counter")
        assert result == "りんごみっつ"  # 数え言葉に変換

    # ========================================
    # パラメータ化テスト
    # ========================================

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("今日", "きょう"),
            ("明日", "あした"),
            ("リンゴ", "りんご"),
            ("カタカナ", "かたかな"),
            ("3個", "さんこ"),
            ("", ""),
        ],
    )
    def test_to_hiragana_parametrized(self, normalizer, input_text, expected):
        """パラメータ化テスト: 基本的なひらがな変換"""
        assert normalizer.to_hiragana(input_text) == expected

    @pytest.mark.parametrize(
        "input_text,keep_punctuation,expected_has_punctuation",
        [
            ("今日は良い天気です。", True, True),
            ("今日は良い天気です。", False, False),
            ("りんご、みかん", True, True),
            ("りんご、みかん", False, False),
        ],
    )
    def test_keep_punctuation_parametrized(
        self, normalizer, input_text, keep_punctuation, expected_has_punctuation
    ):
        """パラメータ化テスト: keep_punctuationパラメータ"""
        result = normalizer.to_hiragana(input_text, keep_punctuation=keep_punctuation)
        has_punctuation = "。" in result or "、" in result
        assert has_punctuation == expected_has_punctuation

    @pytest.mark.parametrize(
        "number_text,expected",
        [
            ("1", "ひとつ"),
            ("2", "ふたつ"),
            ("3", "みっつ"),
            ("5", "いつつ"),
            ("10", "とお"),
        ],
    )
    def test_counter_conversion_parametrized(self, normalizer, number_text, expected):
        """パラメータ化テスト: 数え言葉変換"""
        result = normalizer.to_hiragana_with_counters(number_text)
        assert expected in result


if __name__ == "__main__":
    # このファイルを直接実行してテスト
    pytest.main([__file__, "-v"])
