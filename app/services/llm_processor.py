import os
import json
import logging

try:
    import openai
except Exception:
    openai = None

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if openai and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY


def enhance_parsed_items(text: str, parsed_items: list) -> list:
    """LLM (OpenAI) を使って parsed_items を正規化 / 補正する。

    - 環境変数 OPENAI_API_KEY が設定されていなければ何もしない（そのまま返す）。
    - LLM の応答は JSON 配列のみを期待し、失敗した場合は元の parsed_items を返す。
    """

    if not openai or not OPENAI_API_KEY:
        logger.info("OPENAI_API_KEY not set or OpenAI SDK not available: skipping LLM enhancement")
        return parsed_items

    try:
        system = (
            "あなたは短い買い物メモの品目抽出と正規化を行うアシスタントです。"
            "入力テキストと事前抽出された items を受け取り、JSON 配列のみを出力してください。"
        )

        user = (
            f"原文:\n{text}\n\n"
            f"事前抽出:{json.dumps(parsed_items, ensure_ascii=False)}\n\n"
            "出力フォーマット: JSON 配列。各要素は次のキーを持ちます:\n"
            "  - item: 正規化された品名（日本語）\n"
            "  - quantity: 数値または空文字\n"
            "  - unit: 単位または空文字\n"
            "  - original: 元の抽出文字列（可能なら）\n"
            "例: [{\"item\": \"卵\", \"quantity\": \"1\", \"unit\": \"個\", \"original\": \"卵1個\"}]"
        )

        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.0,
            max_tokens=500,
        )

        content = resp["choices"][0]["message"]["content"]

        # 応答から最初と最後の角括弧で囲まれた JSON 配列部分を取り出す
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1 and end > start:
            json_text = content[start : end + 1]
        else:
            json_text = content

        result = json.loads(json_text)

        # 簡易検査: リストでなければ元の parsed_items を返す
        if not isinstance(result, list):
            logger.warning("LLM の応答がリストではありません。元の解析結果を返します。")
            return parsed_items

        return result

    except Exception as e:
        logger.exception("LLM による補正に失敗しました。元の解析結果を返します。")
        return parsed_items
