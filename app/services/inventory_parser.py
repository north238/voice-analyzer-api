import re
from utils.logger import logger
from typing import List, Dict

# 認識対象の単位
UNITS = [
    "個",
    "本",
    "枚",
    "袋",
    "パック",
    "g",
    "kg",
    "ml",
    "l",
    "少々",
    "適量",
]

UNIT_PATTERN = "|".join(UNITS)

ITEM_PATTERN = re.compile(
    rf"""
    (?P<item>[ぁ-ん一-龥ー]{2,})
    \s*
    (?P<quantity>\d+)?
    \s*
    (?P<unit>{UNIT_PATTERN})?
    """,
    re.VERBOSE,
)


def parse_inventory(text: str) -> Dict[str, List[Dict]]:
    items = []

    for match in ITEM_PATTERN.finditer(text):
        item = match.group("item")
        quantity = match.group("quantity")
        unit = match.group("unit")

        # 品名ノイズ除去（数字混じり・短すぎ防止）
        if not _is_valid_item_name(item):
            continue

        items.append(
            {
                "name": item,
                "quantity": int(quantity) if quantity else 1,
                "unit": unit or "個",
            }
        )

    logger.info(f"🔍 解析結果: {items}")

    return {"items": items}


def _is_valid_item_name(item: str) -> bool:
    # 2文字未満は不可
    if len(item) < 2:
        return False

    # 同一文字の連続（雑音対策）
    if len(set(item)) == 1:
        return False

    return True
