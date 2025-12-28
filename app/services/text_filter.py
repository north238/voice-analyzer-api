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

    return True
