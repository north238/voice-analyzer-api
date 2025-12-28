from pykakasi import kakasi
import jaconv
import re

def normalize_to_hiragana(text: str) -> str:

    # 全角英数 → 半角
    text = jaconv.z2h(text, ascii=True, digit=True, kana=False)

    # カタカナ → ひらがな
    kks = kakasi()
    kks.setMode("J", "H")  # 漢字 → ひらがな
    kks.setMode("K", "H")  # カタカナ → ひらがな
    kks.setMode("H", "H")  # ひらがな → ひらがな

    conv = kks.getConverter()
    text = conv.do(text)

    # 余計な記号を除去（音声ゴミ対策）
    text = re.sub(r"[^\wぁ-んー\s]", "", text)

    # 連続スペースを1つに
    text = re.sub(r"\s+", " ", text).strip()

    return text