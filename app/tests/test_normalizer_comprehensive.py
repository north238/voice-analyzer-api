"""
JapaneseNormalizer の包括的なテストスクリプト

実行方法:
    python tests/test_normalizer_comprehensive.py

テスト項目:
- 数字変換（年号、単位付き、独立数字）
- 活用形処理
- カタカナ→ひらがな
- 複合語処理
- 特殊ケース（電話番号など）
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.normalizer import JapaneseNormalizer
from utils.number_converter import NumberConverter


class TestResult:
    """テスト結果を管理"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []

    def add_result(self, test_name: str, input_text: str, expected: str, actual: str):
        """テスト結果を追加"""
        if expected == actual:
            self.passed += 1
            print(f"✓ {test_name}")
        else:
            self.failed += 1
            print(f"✗ {test_name}")
            print(f"  Input:    {input_text}")
            print(f"  Expected: {expected}")
            print(f"  Got:      {actual}")
            self.failures.append(
                {
                    "name": test_name,
                    "input": input_text,
                    "expected": expected,
                    "actual": actual,
                }
            )

    def print_summary(self):
        """テスト結果サマリーを表示"""
        total = self.passed + self.failed
        print("\n" + "=" * 60)
        print(f"テスト結果: {self.passed}/{total} passed")
        print(f"成功率: {self.passed/total*100:.1f}%")

        if self.failures:
            print(f"\n失敗したテスト ({len(self.failures)}件):")
            for f in self.failures:
                print(f"\n  [{f['name']}]")
                print(f"  Input:    {f['input']}")
                print(f"  Expected: {f['expected']}")
                print(f"  Got:      {f['actual']}")


def test_number_converter():
    """NumberConverter のテスト"""
    print("\n" + "=" * 60)
    print("NumberConverter テスト")
    print("=" * 60 + "\n")

    result = TestResult()
    converter = NumberConverter()

    # 基本的な数字変換
    test_cases = [
        ("基本: 1桁", "3", "三"),
        ("基本: 2桁", "24", "二十四"),
        ("基本: 3桁", "123", "百二十三"),
        ("基本: 4桁", "1974", "千九百七十四"),
        ("基本: 0", "0", "〇"),
        ("基本: 10", "10", "十"),
        ("基本: 100", "100", "百"),
        ("基本: 1000", "1000", "千"),
    ]

    for name, input_str, expected in test_cases:
        actual = converter.to_kanji(input_str)
        result.add_result(name, input_str, expected, actual)

    # 前処理テスト
    preprocess_cases = [
        ("前処理: 年号", "1974年", "千九百七十四年"),
        ("前処理: 月", "3月", "三月"),
        ("前処理: 日", "15日", "十五日"),
        ("前処理: 時刻", "3時15分", "三時十五分"),
        ("前処理: 単位(個)", "卵3個", "卵三個"),
        ("前処理: 単位(本)", "牛乳2本", "牛乳二本"),
        ("前処理: 単位(歳)", "50歳", "五十歳"),
        ("前処理: 複合", "1974年3月15日", "千九百七十四年三月十五日"),
        ("前処理: 電話番号", "090-1234-5678", "090-1234-5678"),  # そのまま
    ]

    for name, input_str, expected in preprocess_cases:
        actual = converter.preprocess_text(input_str)
        result.add_result(name, input_str, expected, actual)

    result.print_summary()
    return result


def test_hiragana_conversion():
    """ひらがな変換のテスト"""
    print("\n" + "=" * 60)
    print("ひらがな変換テスト (standard mode)")
    print("=" * 60 + "\n")

    result = TestResult()
    normalizer = JapaneseNormalizer()

    test_cases = [
        # 数字変換
        ("数字: 年号", "1974年3月", "せんきゅうひゃくななじゅうよねんさんがつ"),
        ("数字: 単位(個)", "卵3個", "たまごさんこ"),
        ("数字: 単位(本)", "牛乳2本", "ぎゅうにゅうにほん"),
        ("数字: 年齢", "50歳", "ごじゅっさい"),
        # 活用形
        ("活用形: 過去形", "出てきた", "でてきた"),
        ("活用形: 受動形", "つけられた", "つけられた"),
        ("活用形: 進行形", "埋まっていた", "うまっていた"),
        # カタカナ
        ("カタカナ: 単純", "カタカナ", "かたかな"),
        ("カタカナ: 複合語", "シャボン玉", "しゃぼんだま"),
        # 複雑な文
        (
            "複合: 年齢付き自己紹介",
            "1974年3月に生まれて、今年で50歳になります",
            "せんきゅうひゃくななじゅうよねんさんがつにうまれてことしでごじゅっさいになります",
        ),
        (
            "複合: 買い物リスト",
            "卵3個と牛乳2本を買いました",
            "たまごさんことぎゅうにゅうにほんをかいました",
        ),
        # 特殊ケース
        (
            "特殊: 電話番号混在",
            "電話番号は090-1234-5678です",
            "でんわばんごうは090-1234-5678です",
        ),
        ("特殊: 空文字列", "", ""),
        ("特殊: 空白のみ", "   ", ""),
    ]

    for name, input_text, expected in test_cases:
        actual = normalizer.to_hiragana(input_text)
        result.add_result(name, input_text, expected, actual)

    result.print_summary()
    return result


def test_counter_words():
    """数え言葉変換のテスト"""
    print("\n" + "=" * 60)
    print("数え言葉変換テスト (counter mode)")
    print("=" * 60 + "\n")

    result = TestResult()
    normalizer = JapaneseNormalizer()

    test_cases = [
        # 助数詞なし → 数え言葉に変換
        ("数え言葉: 1", "りんご1", "りんごひとつ"),
        ("数え言葉: 2", "みかん2", "みかんふたつ"),
        ("数え言葉: 3", "バナナ3", "ばななみっつ"),
        ("数え言葉: 5", "いちご5", "いちごいつつ"),
        # 助数詞あり → そのまま
        ("助数詞あり: 個", "卵3個", "たまごさんこ"),
        ("助数詞あり: 本", "牛乳2本", "ぎゅうにゅうにほん"),
        ("助数詞あり: 枚", "紙5枚", "かみごまい"),
    ]

    for name, input_text, expected in test_cases:
        actual = normalizer.to_hiragana_with_counters(input_text)
        result.add_result(name, input_text, expected, actual)

    result.print_summary()
    return result


def test_readable_mode():
    """読みやすさモードのテスト"""
    print("\n" + "=" * 60)
    print("読みやすさモードテスト (readable mode)")
    print("=" * 60 + "\n")

    result = TestResult()
    normalizer = JapaneseNormalizer()

    # 句読点が保持されることを確認
    test_cases = [
        ("句読点: 句点", "今日は晴れです。", "きょうははれです。"),
        ("句読点: 読点", "りんご、みかん、バナナ", "りんご、みかん、ばなな"),
        (
            "句読点: 複合",
            "今日は良い天気です。散歩に行きましょう。",
            "きょうはよいてんきです。さんぽにいきましょう。",
        ),
    ]

    for name, input_text, expected in test_cases:
        actual = normalizer.to_hiragana_readable(input_text)
        result.add_result(name, input_text, expected, actual)

    result.print_summary()
    return result


def main():
    """メインテスト実行"""
    print("\n" + "=" * 60)
    print("音声解析API - ひらがな化処理 包括テスト")
    print("=" * 60)

    # 各テストを実行
    results = []
    results.append(test_number_converter())
    results.append(test_hiragana_conversion())
    results.append(test_counter_words())
    results.append(test_readable_mode())

    # 総合結果
    print("\n" + "=" * 60)
    print("総合テスト結果")
    print("=" * 60)

    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total = total_passed + total_failed

    print(f"\n全体: {total_passed}/{total} passed")
    print(f"成功率: {total_passed/total*100:.1f}%")

    if total_failed > 0:
        print(f"\n⚠ {total_failed}件のテストが失敗しました")
        return 1
    else:
        print("\n✓ すべてのテストが成功しました")
        return 0


if __name__ == "__main__":
    sys.exit(main())
