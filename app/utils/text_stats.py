"""
日本語テキストの統計情報を取得するユーティリティ
"""

import re
from typing import Dict


class TextStatistics:
    """日本語テキストの統計情報を計算"""

    @staticmethod
    def count_characters(text: str, exclude_whitespace: bool = True) -> int:
        """
        文字数をカウント

        Args:
            text: 対象テキスト
            exclude_whitespace: 空白文字を除外するか（デフォルト: True）

        Returns:
            文字数

        Examples:
            >>> TextStatistics.count_characters("こんにちは")
            5
            >>> TextStatistics.count_characters("こんにちは 世界")
            6
            >>> TextStatistics.count_characters("こんにちは 世界", exclude_whitespace=False)
            7
        """
        if exclude_whitespace:
            text = re.sub(r"\s+", "", text)
        return len(text)

    @staticmethod
    def count_punctuation(text: str) -> Dict[str, int]:
        """
        句読点の数をカウント

        Args:
            text: 対象テキスト

        Returns:
            句読点の種類ごとのカウント辞書

        Examples:
            >>> TextStatistics.count_punctuation("今日は良い天気です。明日も晴れるでしょう。")
            {'。': 2, '、': 0, '！': 0, '？': 0}
        """
        punctuation_marks = ["。", "、", "！", "？"]
        counts = {mark: text.count(mark) for mark in punctuation_marks}
        return counts

    @staticmethod
    def count_by_script(text: str) -> Dict[str, int]:
        """
        文字種別ごとの文字数をカウント

        Args:
            text: 対象テキスト

        Returns:
            文字種別ごとのカウント辞書

        Examples:
            >>> TextStatistics.count_by_script("こんにちは世界Hello123")
            {'hiragana': 5, 'katakana': 0, 'kanji': 2, 'alphabet': 5, 'number': 3, 'other': 0}
        """
        counts = {
            "hiragana": 0,  # ひらがな
            "katakana": 0,  # カタカナ
            "kanji": 0,  # 漢字
            "alphabet": 0,  # アルファベット
            "number": 0,  # 数字
            "other": 0,  # その他
        }

        for char in text:
            if re.match(r"[ぁ-ん]", char):
                counts["hiragana"] += 1
            elif re.match(r"[ァ-ン]", char):
                counts["katakana"] += 1
            elif re.match(r"[一-龯]", char):
                counts["kanji"] += 1
            elif re.match(r"[a-zA-Z]", char):
                counts["alphabet"] += 1
            elif re.match(r"[0-9]", char):
                counts["number"] += 1
            elif not char.isspace():
                counts["other"] += 1

        return counts

    @staticmethod
    def analyze(text: str) -> Dict[str, any]:
        """
        テキストの総合的な統計情報を取得

        Args:
            text: 対象テキスト

        Returns:
            統計情報の辞書

        Examples:
            >>> stats = TextStatistics.analyze("こんにちは、世界！")
            >>> stats['total_characters']
            7
            >>> stats['script_counts']['hiragana']
            5
        """
        return {
            "total_characters": TextStatistics.count_characters(
                text, exclude_whitespace=False
            ),
            "characters_without_space": TextStatistics.count_characters(
                text, exclude_whitespace=True
            ),
            "punctuation_counts": TextStatistics.count_punctuation(text),
            "script_counts": TextStatistics.count_by_script(text),
        }
