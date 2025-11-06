import re

# NGワードリスト
NG_WORDS = [
    "こんにちは",
    "こんばんは",
    "おはよう",
    "視聴",
    "ご視聴",
    "ありがとう",
    "どうも",
    "よろしく",
    "さようなら",
    "また見てね",
    "終わり",
    "終了",
    "お疲れ様",
]


def is_valid_text(text: str) -> bool:

    # NGワードが含まれていないか確認
    for word in NG_WORDS:
        if word in text:
            return False

    # 日本語・数字・単位以外が極端に多い文字列を除外
    if not re.search(r"[ぁ-んァ-ン一-龥0-9]", text):
        return False

    # 一文字の単語はノイズの可能性が高い（例：「あ」など）
    if len(text.strip()) <= 1:
        return False

    return True
