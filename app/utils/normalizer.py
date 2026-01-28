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
            keep_punctuation: 句読点を保持するかどうか

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

    def add_punctuation(self, text: str) -> str:
        """
        形態素解析を使って適切な位置に句読点を挿入

        Args:
            text: 句読点のない日本語テキスト

        Returns:
            句読点を挿入したテキスト

        Examples:
            >>> normalizer = JapaneseNormalizer()
            >>> normalizer.add_punctuation("無添加のシャボン玉石鹸ならもう安心天然の保湿成分が含まれるため")
            '無添加のシャボン玉石鹸なら、もう安心。天然の保湿成分が含まれるため、'
        """
        if not text or not text.strip():
            return ""

        # 形態素解析
        tokens = list(self.tokenizer.tokenize(text))
        result_parts = []

        for i, token in enumerate(tokens):
            surface = token.surface
            pos_parts = token.part_of_speech.split(",") if token.part_of_speech else []
            part_of_speech = pos_parts[0] if pos_parts else ""

            result_parts.append(surface)

            # 次のトークンがあるか確認
            if i < len(tokens) - 1:
                next_token = tokens[i + 1]
                next_pos_parts = (
                    next_token.part_of_speech.split(",")
                    if next_token.part_of_speech
                    else []
                )
                next_pos = next_pos_parts[0] if next_pos_parts else ""
                next_surface = next_token.surface

                # 句読点挿入のルール

                # 1. 接続助詞「ため」「ので」「から」「けれど」の後に読点
                if surface in ["ため", "ので", "から", "けれど", "けれども", "が"]:
                    # 「が」は接続助詞の場合のみ（「リンゴが」などの格助詞は除外）
                    if (
                        surface == "が"
                        and len(pos_parts) > 1
                        and pos_parts[1] == "接続助詞"
                    ):
                        result_parts.append("、")
                    elif surface != "が":
                        result_parts.append("、")

                # 2. 助詞「は」の後に読点（主題を明確化）
                elif part_of_speech == "助詞" and surface == "は":
                    # 次が名詞・動詞・形容詞の場合に読点
                    if next_pos in ["名詞", "動詞", "形容詞", "副詞"]:
                        result_parts.append("、")

                # 3. 動詞・形容詞の連用形や終止形の後に句点（文の区切り）
                elif part_of_speech in ["動詞", "形容詞"]:
                    conjugation = pos_parts[5] if len(pos_parts) > 5 else ""

                    # 「ます」「です」などの丁寧語の後
                    if surface in [
                        "ます",
                        "です",
                        "ました",
                        "でした",
                        "ません",
                        "ありません",
                    ]:
                        # 次が名詞・動詞・形容詞・接頭詞で始まる場合は新しい文なので句点
                        if next_pos in ["名詞", "動詞", "形容詞", "副詞", "接頭詞"]:
                            # 「お」で始まる名詞の場合も句点を入れる（「お肌」など）
                            result_parts.append("。")

                    # 終止形の後
                    elif conjugation in ["基本形", "終止形"]:
                        # 次が名詞で始まる、または接続詞の場合は句点
                        if next_pos in ["名詞", "接続詞", "副詞"]:
                            # ただし「お」「ご」などの接頭詞は除外
                            if next_surface not in ["お", "ご"]:
                                result_parts.append("。")

                # 4. 助動詞「ます」「です」「だ」「た」の後
                elif part_of_speech == "助動詞":
                    # 「ます」「です」「ました」「でした」の後に接頭詞や名詞が来る場合は句点
                    if surface in [
                        "ます",
                        "です",
                        "ました",
                        "でした",
                        "ません",
                        "ませんでした",
                        "だった",
                        "まし",
                        "でし",
                    ]:
                        if next_pos in [
                            "名詞",
                            "動詞",
                            "形容詞",
                            "接頭詞",
                            "副詞",
                            "代名詞",
                        ]:
                            # 指示代名詞（「それ」「これ」「あれ」など）の前は必ず句点
                            if next_surface in [
                                "それ",
                                "これ",
                                "あれ",
                                "その",
                                "この",
                                "あの",
                                "そこ",
                                "ここ",
                                "あそこ",
                            ]:
                                result_parts.append("。")
                            # その他の名詞・動詞・形容詞の前も句点
                            elif next_pos in [
                                "名詞",
                                "動詞",
                                "形容詞",
                                "接頭詞",
                                "副詞",
                            ]:
                                result_parts.append("。")
                            # 「まし」「でし」の後に「た」が来て、その先に指示代名詞がある場合
                            # 2トークン先をチェック
                            if surface in ["まし", "でし"] and i + 1 < len(tokens) - 1:
                                next_next_token = tokens[i + 2]
                                next_next_surface = next_next_token.surface
                                if next_surface == "た" and next_next_surface in [
                                    "それ",
                                    "これ",
                                    "あれ",
                                    "その",
                                    "この",
                                    "あの",
                                ]:
                                    # 「まし/でし」の後ではなく「た」の後に句点を入れるため、ここではスキップ
                                    pass
                    # 「た」の後（連体修飾を除外）
                    elif surface == "た":
                        # 前のトークンをチェック
                        prev_surface = tokens[i - 1].surface if i > 0 else ""

                        # 次が助詞「の」の場合は連体修飾なので句点を入れない
                        if next_surface == "の":
                            pass  # 句点を入れない
                        # 次が指示代名詞の場合は必ず句点（「ました。それは」など）
                        elif next_surface in [
                            "それ",
                            "これ",
                            "あれ",
                            "その",
                            "この",
                            "あの",
                        ]:
                            result_parts.append("。")
                        # 次が名詞の場合、前が「まし」「でし」でない限り連体修飾の可能性
                        elif next_pos == "名詞" and prev_surface not in [
                            "まし",
                            "でし",
                        ]:
                            pass  # 句点を入れない（連体修飾）
                        # それ以外（動詞、形容詞など）の前は句点
                        elif next_pos in ["動詞", "形容詞", "副詞", "接続詞"]:
                            result_parts.append("。")
                    # その他の助動詞「だ」の終止形の後
                    elif surface == "だ":
                        conjugation = pos_parts[5] if len(pos_parts) > 5 else ""
                        if conjugation in ["基本形", "終止形"]:
                            if next_pos in ["名詞", "動詞", "形容詞", "接続詞"]:
                                result_parts.append("。")

                # 5. 名詞の後で文の切れ目が明確な場合（名詞+名詞の連続）
                elif part_of_speech == "名詞" and next_pos == "名詞":
                    # カタカナ複合名詞は保護（固有名詞の可能性）
                    # 例: 「シャボン玉石鹸」のようなカタカナを含む複合名詞
                    is_katakana_compound = re.match(
                        r"^[ァ-ヴー]+$", surface
                    ) or re.match(r"^[ァ-ヴー]+$", next_surface)

                    # カタカナ複合名詞の場合は句点を入れない
                    if is_katakana_compound:
                        pass  # 固有名詞を保護
                    # 前の文脈を見て、動詞や形容詞の後の名詞なら句点を検討
                    elif i > 0:
                        prev_token = tokens[i - 1]
                        prev_pos = (
                            prev_token.part_of_speech.split(",")[0]
                            if prev_token.part_of_speech
                            else ""
                        )
                        # 直前が助詞でない場合（つまり文節の切れ目の可能性）
                        if prev_pos not in ["助詞", "助動詞"]:
                            # 意味的な切れ目を判断（例：「安心天然」→「安心。天然」）
                            # ただし両方とも漢字2文字以上の場合のみ
                            if (
                                len(surface) >= 2
                                and len(next_surface) >= 2
                                and re.match(r"^[一-龥]+$", surface)
                                and re.match(r"^[一-龥]+$", next_surface)
                            ):
                                result_parts.append("。")

        return "".join(result_parts)

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
