import re
from pykakasi import kakasi
import jaconv


class HiraganaConverter:
    """Whisper出力をひらがなに変換するクラス

    Phase 1: kakasi の精度向上
    Phase 2: 数字のひらがな化
    Phase 3: 複雑な漢字への対応
    """

    def __init__(self):
        # kakasi の初期化（複合語対応）
        self.kks = kakasi()
        self.kks.setMode("J", "H")  # 漢字 → ひらがな
        self.kks.setMode("K", "H")  # カタカナ → ひらがな
        self.kks.setMode("H", "H")  # ひらがな → ひらがな
        self.conv = self.kks.getConverter()

        # 数字ひらがな化マップ
        self.number_to_hiragana = {
            "0": "ぜろ",
            "1": "いち",
            "2": "に",
            "3": "さん",
            "4": "よん",
            "5": "ご",
            "6": "ろく",
            "7": "なな",
            "8": "はち",
            "9": "きゅう",
        }

        # 位取りマップ
        self.place_values = {
            "10": "じゅう",
            "100": "ひゃく",
            "1000": "せん",
            "10000": "まん",
        }

    def normalize_to_hiragana(self, text: str) -> str:
        """Whisper出力をひらがなに変換する（複数ステップ）"""

        # 全角英数を半角に
        text = jaconv.z2h(text, ascii=True, digit=True, kana=False)

        # kakasi で基本変換
        text = self.conv.do(text)

        # 数字をひらがなに変換
        text = self._convert_numbers_to_hiragana(text)

        # 余計な記号を除去
        text = re.sub(r"[^\wぁ-んー\s]", "", text)

        # 連続スペースを1つに
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _convert_numbers_to_hiragana(self, text: str) -> str:
        """数字をひらがなに変換する

        例:
        - 「卵1個」→ 「たまごひとつ」
        - 「砂糖100g」→ 「さとうひゃくぐらむ」
        - 「0120」→ 「ぜろいちにぜろ」
        """

        def replace_number(match):
            num_str = match.group(0)

            # 電話番号のような連続数字
            if len(num_str) >= 4 and num_str.isdigit():
                return "".join(self.number_to_hiragana[d] for d in num_str)

            # 通常の数字（個数・グラム等）
            num = int(num_str)

            # 1-9: 個別の数字
            if 1 <= num <= 9:
                return self._get_counter_word(num)

            # 10以上: 位を考慮
            return self._convert_large_number(num)

        # 数字パターンをマッチして変換
        text = re.sub(r"\d+", replace_number, text)

        return text

    def _get_counter_word(self, num: int) -> str:
        """1-9の数字を数え言葉に変換（文脈を考慮した自然な表現）

        例: 1→いち or ひと, 2→に or ふた, etc
        """
        counter_words = {
            1: "ひとつ",
            2: "ふたつ",
            3: "みっつ",
            4: "よっつ",
            5: "いつつ",
            6: "むっつ",
            7: "ななつ",
            8: "やっつ",
            9: "ここのつ",
        }
        return counter_words.get(num, self.number_to_hiragana.get(str(num), str(num)))

    def _convert_large_number(self, num: int) -> str:
        """10以上の数字を位付き表現に変換

        例:
        - 100 → ひゃく
        - 120 → ひゃくにじゅう
        - 1000 → せん
        """
        if num == 0:
            return "ぜろ"

        result = []

        # 万の位
        if num >= 10000:
            man = num // 10000
            result.append(
                self.number_to_hiragana.get(str(man), str(man))
                + self.place_values["10000"]
            )
            num %= 10000

        # 千の位
        if num >= 1000:
            sen = num // 1000
            if sen == 1:
                result.append(self.place_values["1000"])
            else:
                result.append(
                    self.number_to_hiragana.get(str(sen), str(sen))
                    + self.place_values["1000"]
                )
            num %= 1000

        # 百の位
        if num >= 100:
            hyaku = num // 100
            if hyaku == 1:
                result.append(self.place_values["100"])
            elif hyaku == 3:
                result.append("さんびゃく")  # 三百の例外
            elif hyaku == 6:
                result.append("ろっぴゃく")  # 六百の例外
            elif hyaku == 8:
                result.append("はっぴゃく")  # 八百の例外
            else:
                result.append(
                    self.number_to_hiragana.get(str(hyaku), str(hyaku))
                    + self.place_values["100"]
                )
            num %= 100

        # 十の位
        if num >= 10:
            ju = num // 10
            if ju == 1:
                result.append(self.place_values["10"])
            else:
                result.append(
                    self.number_to_hiragana.get(str(ju), str(ju))
                    + self.place_values["10"]
                )
            num %= 10

        # 一の位
        if num > 0:
            result.append(self.number_to_hiragana.get(str(num), str(num)))

        return "".join(result)


# グローバルインスタンス
_converter = HiraganaConverter()


def normalize_to_hiragana(text: str) -> str:
    """Whisper出力をひらがなに変換する（公開API）"""
    return _converter.normalize_to_hiragana(text)
