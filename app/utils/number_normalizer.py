import re

# 基本数字
NUMBER_MAP = {
    "ぜろ": "0",
    "れい": "0",
    "いち": "1",
    "に": "2",
    "さん": "3",
    "よん": "4",
    "し": "4",
    "ご": "5",
    "ろく": "6",
    "なな": "7",
    "しち": "7",
    "はち": "8",
    "きゅう": "9",
    "く": "9",
}

# 位取り
UNIT_MAP = {
    "じゅう": 10,
    "ひゃく": 100,
    "せん": 1000,
}


def normalize_numbers(text: str) -> str:
    # 単純な連続数字（ぜろいちに 等）
    for k, v in NUMBER_MAP.items():
        text = text.replace(k, v)

    # 位取り処理（簡易）
    def replace_units(match):
        num = match.group(1)
        unit = match.group(2)

        base = int(NUMBER_MAP.get(num, "1"))
        return str(base * UNIT_MAP[unit])

    pattern = (
        r"(いち|に|さん|よん|し|ご|ろく|なな|しち|はち|きゅう|く)?(じゅう|ひゃく|せん)"
    )
    text = re.sub(pattern, replace_units, text)

    return text
