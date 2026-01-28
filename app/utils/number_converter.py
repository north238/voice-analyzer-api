import re
from typing import Optional


class NumberConverter:
    """数字を漢数字およびひらがなに変換"""

    # 基本的な数字マッピング
    KANJI_MAP = {
        "0": "〇",
        "1": "一",
        "2": "二",
        "3": "三",
        "4": "四",
        "5": "五",
        "6": "六",
        "7": "七",
        "8": "八",
        "9": "九",
    }

    # 位のマッピング
    UNITS = ["", "十", "百", "千"]
    BIG_UNITS = ["", "万", "億", "兆"]

    # 数え言葉（1-10）
    COUNTERS = {
        1: "ひとつ",
        2: "ふたつ",
        3: "みっつ",
        4: "よっつ",
        5: "いつつ",
        6: "むっつ",
        7: "ななつ",
        8: "やっつ",
        9: "ここのつ",
        10: "とお",
    }

    # 漢数字の読み（後でjanomeを通さない場合用）
    KANJI_READINGS = {
        "〇": "ぜろ",
        "一": "いち",
        "二": "に",
        "三": "さん",
        "四": "よん",
        "五": "ご",
        "六": "ろく",
        "七": "なな",
        "八": "はち",
        "九": "きゅう",
        "十": "じゅう",
        "百": "ひゃく",
        "千": "せん",
        "万": "まん",
        "億": "おく",
        "兆": "ちょう",
    }

    @staticmethod
    def to_kanji(num_str: str) -> str:
        """
        数字文字列を漢数字に変換

        Args:
            num_str: 数字文字列（例: "1974"）

        Returns:
            漢数字文字列（例: "千九百七十四"）

        Examples:
            >>> NumberConverter.to_kanji("1974")
            '千九百七十四'
            >>> NumberConverter.to_kanji("2024")
            '二千二十四'
            >>> NumberConverter.to_kanji("0")
            '〇'
        """
        try:
            num = int(num_str)
        except ValueError:
            return num_str

        # 0の特別処理
        if num == 0:
            return "〇"

        # 負の数は未対応
        if num < 0:
            return num_str

        result = []

        # 4桁ごとに分割して処理
        for big_unit_idx, chunk in enumerate(NumberConverter._split_by_10000(num)):
            if chunk == 0:
                continue

            chunk_kanji = NumberConverter._convert_chunk(chunk)

            # 大きな単位を追加（万、億など）
            if big_unit_idx > 0:
                chunk_kanji += NumberConverter.BIG_UNITS[big_unit_idx]

            result.insert(0, chunk_kanji)

        return "".join(result)

    @staticmethod
    def _split_by_10000(num: int) -> list:
        """数字を10000ごとに分割"""
        chunks = []
        while num > 0:
            chunks.append(num % 10000)
            num //= 10000
        return chunks if chunks else [0]

    @staticmethod
    def _convert_chunk(chunk: int) -> str:
        """
        4桁の数字を漢数字に変換

        ルール:
        - 「一十」「一百」「一千」は「十」「百」「千」にする
        - 「三百」「六百」「八百」は例外処理なし（janomeが処理）
        """
        if chunk == 0:
            return ""

        result = []
        digits = str(chunk).zfill(4)

        for i, digit in enumerate(digits):
            d = int(digit)
            if d == 0:
                continue

            unit_idx = 3 - i  # 千=3, 百=2, 十=1, 一=0

            # 「一十」「一百」「一千」は「十」「百」「千」にする
            if d == 1 and unit_idx > 0:
                result.append(NumberConverter.UNITS[unit_idx])
            else:
                result.append(NumberConverter.KANJI_MAP[digit])
                if unit_idx > 0:
                    result.append(NumberConverter.UNITS[unit_idx])

        return "".join(result)

    @staticmethod
    def preprocess_text(text: str) -> str:
        """
        テキスト内の数字を文脈に応じて変換

        変換ルール:
        1. 年号: 西暦形式（1000-2999年）→ 漢数字
        2. 月日: 1-12月、1-31日 → 漢数字
        3. 単位付き数字: 個、本、枚など → 漢数字
        4. 電話番号: ハイフン付きはそのまま
        5. その他の数字: 漢数字（1-4桁）

        Args:
            text: 変換対象のテキスト

        Returns:
            数字が漢数字に変換されたテキスト

        Examples:
            >>> NumberConverter.preprocess_text("1974年3月")
            '千九百七十四年三月'
            >>> NumberConverter.preprocess_text("卵3個")
            '卵三個'
        """

        # 1. 電話番号を一時的に保護（日本語括弧とアルファベットを使用してjanomeの誤変換を回避）
        phone_patterns = re.findall(r"\d{2,4}-\d{3,4}-\d{4}", text)
        phone_placeholders = {}
        for i, phone in enumerate(phone_patterns):
            # 数字の代わりにアルファベット（a, b, c...）を使用
            placeholder = f"【PHONE{chr(97+i)}】"  # chr(97) = 'a'
            phone_placeholders[placeholder] = phone
            text = text.replace(phone, placeholder, 1)

        # 2. 年号の処理（1000-2999年）
        text = re.sub(
            r"([12]\d{3})年",
            lambda m: f"{NumberConverter.to_kanji(m.group(1))}年",
            text,
        )

        # 3. 月の処理（1-12月）
        text = re.sub(
            r"(\d{1,2})月", lambda m: f"{NumberConverter.to_kanji(m.group(1))}月", text
        )

        # 4. 日の処理（1-31日）
        text = re.sub(
            r"(\d{1,2})日", lambda m: f"{NumberConverter.to_kanji(m.group(1))}日", text
        )

        # 5. 時刻の処理（1-24時、0-59分）
        text = re.sub(
            r"(\d{1,2})時", lambda m: f"{NumberConverter.to_kanji(m.group(1))}時", text
        )
        text = re.sub(
            r"(\d{1,2})分", lambda m: f"{NumberConverter.to_kanji(m.group(1))}分", text
        )

        # 6. 単位付き数字（個、本、枚、台、人など）
        common_units = [
            "個",
            "本",
            "枚",
            "台",
            "人",
            "匹",
            "杯",
            "冊",
            "回",
            "歳",
            "才",
            "階",
            "番",
            "号",
            "円",
            "ドル",
            "メートル",
            "キロ",
            "グラム",
            "リットル",
            "センチ",
            "ミリ",
        ]

        for unit in common_units:
            text = re.sub(
                rf"(\d+){unit}",
                lambda m: f"{NumberConverter.to_kanji(m.group(1))}{unit}",
                text,
            )

        # 7. その他の独立した数字（1-4桁）を漢数字に変換
        text = re.sub(
            r"(?<!\d)(\d{1,4})(?!\d)",
            lambda m: NumberConverter.to_kanji(m.group(1)),
            text,
        )

        # 8. 電話番号を復元
        for placeholder, phone in phone_placeholders.items():
            text = text.replace(placeholder, phone)

        return text

    @staticmethod
    def to_counter_word(num: int) -> Optional[str]:
        """
        数字を数え言葉に変換

        Args:
            num: 数字（1-10）

        Returns:
            数え言葉（例: 1 → "ひとつ"）、範囲外ならNone

        Examples:
            >>> NumberConverter.to_counter_word(1)
            'ひとつ'
            >>> NumberConverter.to_counter_word(5)
            'いつつ'
        """
        return NumberConverter.COUNTERS.get(num)
