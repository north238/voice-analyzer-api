import re
from collections import Counter

# よくある相槌・フィラー（意味を持たない）
FILLER_PATTERNS = [
    r"^(あ+|え+|う+|ん+)$",
    r"(えー+|あの+|その+)",
]

# 日本語として最低限意味を持ちそうな品詞的特徴
MEANINGFUL_PATTERN = re.compile(r"[ぁ-ん一-龥]")


def is_valid_text(text: str) -> bool:
    text = text.strip()

    # 日本語要素がほぼ無い
    if not MEANINGFUL_PATTERN.search(text):
        return False

    # フィラーのみ
    for pattern in FILLER_PATTERNS:
        if re.fullmatch(pattern, text):
            return False

    # 同一文字の異常な繰り返し（雑音）
    counts = Counter(text)
    most_common_char, freq = counts.most_common(1)[0]
    if freq / len(text) > 0.7:
        return False

    # 繰り返し単語・フレーズの検出（ハルシネーション対策）
    if _has_repeated_phrases(text):
        return False

    return True


def _has_repeated_phrases(text: str, min_phrase_len: int = 3, max_phrase_len: int = 15) -> bool:
    """繰り返し単語・フレーズが異常に多いかチェック

    Args:
        text: チェック対象のテキスト
        min_phrase_len: 最小フレーズ長（文字数）
        max_phrase_len: 最大フレーズ長（文字数）

    Returns:
        bool: 異常な繰り返しがある場合True
    """
    text_len = len(text)
    if text_len < min_phrase_len:
        return False

    # 様々な長さのN-gramで繰り返しをチェック
    for phrase_len in range(min_phrase_len, min(max_phrase_len + 1, text_len // 2 + 1)):
        # N-gramを生成
        ngrams = []
        for i in range(text_len - phrase_len + 1):
            ngrams.append(text[i:i + phrase_len])

        if not ngrams:
            continue

        # 最も頻出するN-gramをカウント
        ngram_counts = Counter(ngrams)
        most_common_ngram, freq = ngram_counts.most_common(1)[0]

        # そのN-gramが占める文字数の割合
        coverage = (freq * phrase_len) / text_len

        # 60%以上を同一のN-gramが占める場合は異常
        if coverage > 0.6:
            return True

    return False
