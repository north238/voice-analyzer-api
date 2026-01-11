import json
import requests
import time
import re

from config import settings
from utils.logger import logger

OLLAMA_URL = "http://local-llm:11434/api/chat"
MODEL_NAME = settings.OLLAMA_MODEL

# SYSTEM_PROMPT = """You are a Japanese Hiragana-to-Kanji converter.
# Convert the input Hiragana text into natural Japanese with appropriate Kanji.

# Rules:
# 1. Output ONLY valid JSON
# 2. Use exact key names: "text" and "confidence"
# 3. No explanations or markdown
# 4. Maintain the original meaning and context

# Output format:
# {"text": "漢字混じりの文章", "confidence": 0.9}"""

SYSTEM_PROMPT = """あなたは日本語のひらがなを漢字かな混じり文に変換する専門家です。

【タスク】
入力されたひらがなのみの文章を、自然な日本語（漢字とひらがなが混ざった文）に変換してください。

【絶対に守ること】
1. 入力されたすべての文字を変換すること（省略・要約は禁止）
2. 文の長さを変えないこと
3. 単語を追加・削除しないこと
4. 日本語のみで出力すること（英語・中国語は使用禁止）
5. JSON形式のみで出力すること

【変換例】
入力: きょうはてんきがいいです
出力: {"text": "今日は天気が良いです", "confidence": 0.95}

【出力形式】
{"text": "変換後の日本語", "confidence": 0.0から1.0の数値}

重要: 入力文を要約せず、全ての文字を変換してください。JSONのみを出力してください。"""

def call_llm(text: str) -> dict:
    try:
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "user", "content": f"{SYSTEM_PROMPT}\n\n入力: {text}\n出力:"}
            ],
            "options": {
                "temperature": settings.OLLAMA_TEMPERATURE,  # Gemma2は少し高めが良い
                "top_k": settings.OLLAMA_TOP_K,
                "top_p": settings.OLLAMA_TOP_P,
                "repeat_penalty": settings.OLLAMA_REPEAT_PENALTY,
                "num_predict": settings.OLLAMA_NUM_PREDICT,
            },
            "stream": False,
        }

        response = requests.post(OLLAMA_URL, json=payload, timeout=settings.OLLAMA_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        content = data.get("message", {}).get("content", "{}")
        logger.debug(f"Raw LLM response: {content}")

        # JSONを抽出
        clean_content = re.sub(r"```(?:json)?\s*|\s*```", "", content).strip()
        json_match = re.search(r'\{[^{}]*"text"[^{}]*\}', clean_content)

        if json_match:
            clean_content = json_match.group(0)

        parsed = json.loads(clean_content)
        return {
            "text": parsed.get("text", text),
            "confidence": float(parsed.get("confidence", 0.0)),
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Network error: {e}")
        return {"text": text, "confidence": 0.0, "error": str(e)}
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error(f"❌ Parse error: {e}")
        logger.error(f"   Content: {content}")
        return {"text": text, "confidence": 0.0, "error": str(e)}
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        return {"text": text, "confidence": 0.0, "error": str(e)}


def smart_split(text: str, max_size: int = 50) -> list[str]:

    if len(text) <= max_size:
        return [text]

    # 助詞・接続詞のパターン (後ろで分割可能な位置)
    split_pattern = r"([。、]|(?<=[はがをにへでとからよりまで])(?=[ぁ-ん]))"

    # 分割候補を作成
    parts = re.split(split_pattern, text)

    chunks = []
    current = ""

    for part in parts:
        if not part:
            continue

        # 結合しても制限内なら結合
        if len(current) + len(part) <= max_size:
            current += part
        else:
            # 制限を超える場合
            if current:
                chunks.append(current)
            current = part

    # 残りを追加
    if current:
        chunks.append(current)

    # 分割できなかった場合は強制分割
    if len(chunks) == 1 and len(chunks[0]) > max_size:
        chunks = [text[i : i + max_size] for i in range(0, len(text), max_size)]

    return chunks


def analyze_with_llm(text: str) -> dict:
    start_time = time.perf_counter()

    # Gemma2は50文字程度に分割すると精度が上がる
    max_chunk_size = settings.MAX_TEXT_LENGTH

    # 短い場合は分割しない
    if len(text) <= max_chunk_size:
        logger.info(f"📝 Processing full text ({len(text)} chars)")
        result = call_llm(text)

        elapsed = time.perf_counter() - start_time
        logger.info(f"✅ Result: {result['text']}")
        logger.info(f"📊 Confidence: {result['confidence']:.2f}")
        logger.info(f"⏱️  Time: {elapsed:.2f}s")

        return {
            "normalized": text,
            "converted_text": result["text"],
            "confidence": result["confidence"],
            "chunks_processed": 1,
            "chunks_failed": 1 if "error" in result else 0,
        }

    # 長い場合は分割して処理
    chunks = smart_split(text, max_size=max_chunk_size)

    logger.info(f"📦 Split into {len(chunks)} chunks:")
    for i, chunk in enumerate(chunks):
        logger.info(f"  [{i+1}] '{chunk}' ({len(chunk)} chars)")

    results = []
    confidences = []
    failed = 0

    for i, chunk in enumerate(chunks):
        logger.info(f"🔄 Processing chunk {i+1}/{len(chunks)}...")
        result = call_llm(chunk)

        if "error" in result:
            failed += 1
            results.append(chunk)
            confidences.append(0.0)
        else:
            results.append(result["text"])
            confidences.append(result["confidence"])

        logger.info(
            f"  ✓ [{i+1}] {result['text'][:50]}... (conf: {result['confidence']:.2f})"
        )

    final_text = "".join(results)
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    elapsed = time.perf_counter() - start_time

    logger.info("=" * 60)
    logger.info(f"✅ Final result: {final_text}")
    logger.info(f"📊 Avg confidence: {avg_conf:.2f}")
    logger.info(f"⏱️  Total time: {elapsed:.2f}s")

    return {
        "normalized": text,
        "converted_text": final_text,
        "confidence": round(avg_conf, 2),
        "chunks_processed": len(chunks),
        "chunks_failed": failed,
    }
