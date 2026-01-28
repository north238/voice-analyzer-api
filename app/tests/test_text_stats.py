"""
テキスト統計情報取得機能のテスト
"""

import pytest
from app.utils.text_stats import TextStatistics


class TestTextStatistics:
    """TextStatisticsクラスのテスト"""

    # ========================================
    # count_characters のテスト
    # ========================================

    def test_count_characters_basic(self):
        """基本的な文字数カウント"""
        assert TextStatistics.count_characters("こんにちは") == 5
        assert TextStatistics.count_characters("世界") == 2

    def test_count_characters_with_space_excluded(self):
        """空白を除外した文字数カウント"""
        assert TextStatistics.count_characters("こんにちは 世界") == 7
        assert TextStatistics.count_characters("今日は　良い　天気") == 7

    def test_count_characters_with_space_included(self):
        """空白を含めた文字数カウント"""
        assert (
            TextStatistics.count_characters("こんにちは 世界", exclude_whitespace=False)
            == 8
        )
        assert (
            TextStatistics.count_characters(
                "今日は　良い　天気", exclude_whitespace=False
            )
            == 9
        )

    def test_count_characters_empty_string(self):
        """空文字列の文字数カウント"""
        assert TextStatistics.count_characters("") == 0

    def test_count_characters_whitespace_only(self):
        """空白のみの文字数カウント"""
        assert TextStatistics.count_characters("   ") == 0
        assert TextStatistics.count_characters("   ", exclude_whitespace=False) == 3

    # ========================================
    # count_punctuation のテスト
    # ========================================

    def test_count_punctuation_basic(self):
        """基本的な句読点カウント"""
        result = TextStatistics.count_punctuation("今日は良い天気です。")
        assert result["。"] == 1
        assert result["、"] == 0
        assert result["！"] == 0
        assert result["？"] == 0

    def test_count_punctuation_multiple(self):
        """複数の句読点カウント"""
        result = TextStatistics.count_punctuation("こんにちは、世界！今日は良い天気ですか？")
        assert result["。"] == 0
        assert result["、"] == 1
        assert result["！"] == 1
        assert result["？"] == 1

    def test_count_punctuation_none(self):
        """句読点なしのテキスト"""
        result = TextStatistics.count_punctuation("こんにちは")
        assert result["。"] == 0
        assert result["、"] == 0
        assert result["！"] == 0
        assert result["？"] == 0

    def test_count_punctuation_empty_string(self):
        """空文字列の句読点カウント"""
        result = TextStatistics.count_punctuation("")
        assert result["。"] == 0
        assert result["、"] == 0

    # ========================================
    # count_by_script のテスト
    # ========================================

    def test_count_by_script_hiragana_only(self):
        """ひらがなのみのテキスト"""
        result = TextStatistics.count_by_script("こんにちは")
        assert result["hiragana"] == 5
        assert result["katakana"] == 0
        assert result["kanji"] == 0
        assert result["alphabet"] == 0
        assert result["number"] == 0

    def test_count_by_script_katakana_only(self):
        """カタカナのみのテキスト"""
        result = TextStatistics.count_by_script("コンニチハ")
        assert result["hiragana"] == 0
        assert result["katakana"] == 5
        assert result["kanji"] == 0

    def test_count_by_script_kanji_only(self):
        """漢字のみのテキスト"""
        result = TextStatistics.count_by_script("世界平和")
        assert result["hiragana"] == 0
        assert result["katakana"] == 0
        assert result["kanji"] == 4

    def test_count_by_script_mixed_japanese(self):
        """混在テキスト（ひらがな、カタカナ、漢字）"""
        result = TextStatistics.count_by_script("こんにちは世界コンニチハ")
        assert result["hiragana"] == 5
        assert result["katakana"] == 5
        assert result["kanji"] == 2

    def test_count_by_script_alphabet(self):
        """アルファベットを含むテキスト"""
        result = TextStatistics.count_by_script("Hello")
        assert result["alphabet"] == 5
        assert result["hiragana"] == 0

    def test_count_by_script_number(self):
        """数字を含むテキスト"""
        result = TextStatistics.count_by_script("123")
        assert result["number"] == 3
        assert result["hiragana"] == 0

    def test_count_by_script_all_mixed(self):
        """すべての文字種が混在"""
        result = TextStatistics.count_by_script("こんにちは世界Hello123")
        assert result["hiragana"] == 5
        assert result["katakana"] == 0
        assert result["kanji"] == 2
        assert result["alphabet"] == 5
        assert result["number"] == 3

    def test_count_by_script_with_whitespace(self):
        """空白を含むテキスト"""
        result = TextStatistics.count_by_script("こんにちは 世界")
        # 空白はカウントされない
        assert result["hiragana"] == 5
        assert result["kanji"] == 2
        assert result["other"] == 0

    def test_count_by_script_with_punctuation(self):
        """句読点を含むテキスト"""
        result = TextStatistics.count_by_script("こんにちは。")
        assert result["hiragana"] == 5
        assert result["other"] == 1  # 句読点は other にカウント

    def test_count_by_script_empty_string(self):
        """空文字列"""
        result = TextStatistics.count_by_script("")
        assert result["hiragana"] == 0
        assert result["katakana"] == 0
        assert result["kanji"] == 0

    # ========================================
    # analyze のテスト
    # ========================================

    def test_analyze_basic(self):
        """基本的な総合分析"""
        result = TextStatistics.analyze("こんにちは、世界！")
        assert result["total_characters"] == 9
        assert result["characters_without_space"] == 9
        assert result["punctuation_counts"]["、"] == 1
        assert result["punctuation_counts"]["！"] == 1
        assert result["script_counts"]["hiragana"] == 5
        assert result["script_counts"]["kanji"] == 2

    def test_analyze_with_space(self):
        """空白を含むテキストの総合分析"""
        result = TextStatistics.analyze("こんにちは 世界")
        assert result["total_characters"] == 8
        assert result["characters_without_space"] == 7

    def test_analyze_mixed_content(self):
        """混在コンテンツの総合分析"""
        result = TextStatistics.analyze("Hello世界123")
        assert result["script_counts"]["alphabet"] == 5
        assert result["script_counts"]["kanji"] == 2
        assert result["script_counts"]["number"] == 3

    def test_analyze_empty_string(self):
        """空文字列の総合分析"""
        result = TextStatistics.analyze("")
        assert result["total_characters"] == 0
        assert result["characters_without_space"] == 0
        assert all(count == 0 for count in result["punctuation_counts"].values())
        assert all(count == 0 for count in result["script_counts"].values())

    # ========================================
    # パラメータ化テスト
    # ========================================

    @pytest.mark.parametrize(
        "text,expected_hiragana,expected_kanji",
        [
            ("あいうえお", 5, 0),
            ("世界", 0, 2),
            ("こんにちは世界", 5, 2),
            ("", 0, 0),
        ],
    )
    def test_count_by_script_parametrized(
        self, text, expected_hiragana, expected_kanji
    ):
        """パラメータ化テスト: 文字種別カウント"""
        result = TextStatistics.count_by_script(text)
        assert result["hiragana"] == expected_hiragana
        assert result["kanji"] == expected_kanji


if __name__ == "__main__":
    # このファイルを直接実行してテスト
    pytest.main([__file__, "-v"])
