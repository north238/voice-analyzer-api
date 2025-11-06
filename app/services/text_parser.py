import re

def parse_text(text: str):

    pattern = r"([^\d\s]+)\s*(\d+)?\s*(個|本|枚|g|ml|少々|適量|パック)?"
    items = []

    for match in re.finditer(pattern, text):
        item, quantity, unit = match.groups()
        if item:
            items.append(
                {"item": item.strip(), "quantity": quantity or "", "unit": unit or ""}
            )

    return items
