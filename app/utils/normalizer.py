"""
日本語テキストをひらがなに正規化するモジュール

機能:
- 漢字・カタカナをひらがなに変換
- 数字を適切にひらがな化（数え言葉対応）
- janome形態素解析による高精度な変換
"""

from janome.tokenizer import Tokenizer
import jaconv
import re
from typing import Optional
from .number_converter import NumberConverter


class JapaneseNormalizer:
    """
    日本語テキストをひらがなに正規化

    処理フロー:
    1. 数字を漢数字に前処理（NumberConverter）
    2. janomeで形態素解析
    3. reading属性でひらがな化
    4. カタカナ→ひらがな変換
    5. 音便処理
    """

    def __init__(self):
        """初期化"""
        self.tokenizer = Tokenizer()
        self.converter = NumberConverter()

    def to_hiragana(self, text: str, keep_punctuation: bool = False) -> str:
        """
        テキストを完全なひらがなに変換

        Args:
            text: 変換対象のテキスト
            keep_punctuation: 句読点を残すかどうか

        Returns:
            ひらがな化されたテキスト

        Examples:
            >>> normalizer = JapaneseNormalizer()
            >>> normalizer.to_hiragana("1974年3月")
            'せんきゅうひゃくななじゅうよねんさんがつ'
            >>> normalizer.to_hiragana("卵3個")
            'たまごさんこ'
        """

        if not text or not text.strip():
            return ""

        # Step 1: 数字を漢数字に前処理
        preprocessed = self.converter.preprocess_text(text)

        # Step 2: janomeで形態素解析してひらがな化
        hiragana_parts = []

        for token in self.tokenizer.tokenize(preprocessed):
            surface = token.surface
            reading = token.reading

            # 句読点の処理
            if surface in ["。", "、", "！", "？", "…", "・"]:
                if keep_punctuation:
                    hiragana_parts.append(surface)
                continue

            # その他の記号・空白
            if surface in [" ", "　", "\n", "\t"]:
                if keep_punctuation:
                    hiragana_parts.append(surface)
                continue

            # reading属性の処理
            if reading == "*" or reading is None:
                # readingが取得できない場合
                # 数字は前処理で変換済みなので、ここには記号や特殊文字が来る
                if re.match(r"^[a-zA-Z0-9\-]+$", surface):
                    # アルファベット・数字・ハイフンはそのまま
                    hiragana_parts.append(surface)
                elif re.match(r"^[\u4e00-\u9fff]+$", surface):
                    # 漢字なのにreadingがない場合（稀）
                    # 表層形をそのまま使うか、エラーログを出す
                    hiragana_parts.append(surface)
                else:
                    # その他の記号
                    if keep_punctuation:
                        hiragana_parts.append(surface)
            else:
                # カタカナ読みをひらがなに変換
                hiragana = jaconv.kata2hira(reading)
                hiragana_parts.append(hiragana)

        result = "".join(hiragana_parts)

        # Step 3: 音便処理（促音化）
        result = self._apply_onbin(result)

        # 連続する空白を1つにまとめる
        if keep_punctuation:
            result = re.sub(r"\s+", " ", result)

        return result.strip()

    def _apply_onbin(self, text: str) -> str:
        """
        音便（促音化）を適用

        日本語の自然な発音に合わせて促音化する
        例: 「ななじゅうよん」→「ななじゅうよ」
            「ごじゅうさい」→「ごじゅっさい」

        Args:
            text: ひらがなテキスト

        Returns:
            音便処理後のテキスト
        """

        # 1. 十の位 + 「よん」→「よ」（文末または特定の助詞の前）
        # 例: にじゅうよん → にじゅうよ、ななじゅうよねん → ななじゅうよねん
        text = re.sub(r"じゅうよん($|[^かきくけこがぎぐげご])", r"じゅうよ\1", text)

        # 2. 「さい」の前の促音化
        # 例: ごじゅうさい → ごじゅっさい
        text = re.sub(r"じゅうさい", r"じゅっさい", text)

        return text

    def to_hiragana_readable(self, text: str) -> str:
        """
        読みやすさを重視したひらがな化

        - 句読点を保持
        - 適度な空白を維持

        Args:
            text: 変換対象のテキスト

        Returns:
            読みやすいひらがなテキスト

        Examples:
            >>> normalizer = JapaneseNormalizer()
            >>> normalizer.to_hiragana_readable("今日は良い天気です。")
            'きょうは よい てんきです。'
        """
        return self.to_hiragana(text, keep_punctuation=True)

    def to_hiragana_with_counters(
        self, text: str, keep_punctuation: bool = False
    ) -> str:
        """
        数え言葉（ひとつ、ふたつ）を使ったひらがな化

        用途: 子ども向けコンテンツなど

        Args:
            text: 変換対象のテキスト
            keep_punctuation: 句読点を残すかどうか

        Returns:
            数え言葉を含むひらがなテキスト

        Examples:
            >>> normalizer = JapaneseNormalizer()
            >>> normalizer.to_hiragana_with_counters("りんご3")
            'りんごみっつ'
        """

        if not text or not text.strip():
            return ""

        # Step 1: 数字のみの場合は先に漢数字に変換
        preprocessed = self.converter.preprocess_text(text)

        # Step 2: janomeで形態素解析
        hiragana_parts = []

        for token in self.tokenizer.tokenize(preprocessed):
            surface = token.surface
            reading = token.reading

            # 句読点の処理
            if surface in ["。", "、", "！", "？", "…", "・"]:
                if keep_punctuation:
                    hiragana_parts.append(surface)
                continue

            # 空白
            if surface in [" ", "　", "\n", "\t"]:
                if keep_punctuation:
                    hiragana_parts.append(surface)
                continue

            # reading属性の処理
            if reading == "*" or reading is None:
                if re.match(r"^[a-zA-Z0-9\-]+$", surface):
                    hiragana_parts.append(surface)
                elif re.match(r"^[\u4e00-\u9fff]+$", surface):
                    hiragana_parts.append(surface)
                else:
                    if keep_punctuation:
                        hiragana_parts.append(surface)
            else:
                hiragana = jaconv.kata2hira(reading)
                hiragana_parts.append(hiragana)

        result = "".join(hiragana_parts)

        # Step 3: 音便処理
        result = self._apply_onbin(result)

        # Step 4: 数字の読みを数え言葉に置換
        counter_map = {
            "いち": "ひとつ",
            "に": "ふたつ",
            "さん": "みっつ",
            "よん": "よっつ",
            "し": "よっつ",
            "ご": "いつつ",
            "ろく": "むっつ",
            "なな": "ななつ",
            "しち": "ななつ",
            "はち": "やっつ",
            "きゅう": "ここのつ",
            "く": "ここのつ",
            "じゅう": "とお",
        }

        # 助数詞のパターン（これらの後ろでは変換しない）
        unit_suffixes = [
            "こ",
            "ほん",
            "ぽん",
            "ぼん",
            "まい",
            "だい",
            "にん",
            "ひき",
            "ぴき",
            "びき",
            "はい",
            "ぱい",
            "ばい",
            "さつ",
            "かい",
            "がい",
            "さい",
            "じ",
            "ふん",
            "ぷん",
            "がつ",
            "にち",
            "ねん",
            "えん",
            "ど",
            "どる",
        ]

        unit_pattern = "|".join(unit_suffixes)

        # 数え言葉への変換（最長一致優先で、単語の一部にマッチしないように）
        # 例: 「りんご」の「ご」は変換しない
        for num_reading, counter_word in sorted(
            counter_map.items(), key=lambda x: len(x[0]), reverse=True
        ):
            # 前後が母音（ひらがな）でない場合のみ置換
            # または単独で存在する場合のみ置換
            pattern = rf"(?<![あ-ん])({num_reading})(?!{unit_pattern}|[あ-ん])"
            result = re.sub(pattern, counter_word, result)

        return result

    def normalize_with_mode(self, text: str, mode: str = "standard") -> str:
        """
        モード指定でひらがな化

        Args:
            text: 変換対象のテキスト
            mode: 変換モード
                - "standard": 通常のひらがな化
                - "readable": 句読点・空白を保持
                - "counter": 数え言葉を使用

        Returns:
            モードに応じたひらがなテキスト
        """

        if mode == "readable":
            return self.to_hiragana_readable(text)
        elif mode == "counter":
            return self.to_hiragana_with_counters(text)
        else:  # standard
            return self.to_hiragana(text)
