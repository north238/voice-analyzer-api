import json
import requests
import time
import re

from utils.logger import logger

OLLAMA_URL = "http://local-llm:11434/api/chat"
# MODEL_NAME = "qwen2.5:3b"
MODEL_NAME = "qwen2.5:3b-instruct-q8_0"

SYSTEM_PROMPT = """You are a Japanese Hiragana-to-Kanji converter.
Convert the input Hiragana text into natural Japanese with appropriate Kanji.

Rules:
1. Output ONLY valid JSON
2. Use exact key names: "text" and "confidence"
3. No explanations or markdown
4. Maintain the original meaning and context

Output format:
{"text": "漢字混じりの文章", "confidence": 0.9}"""

def split_by_sentences(text: str, max_length: int = 45) -> list[str]:
    # 句読点がある場合
    if re.search(r'[。、]', text):
        sentences = re.split(r'([。、])', text)
        chunks = []
        current_chunk = ""

        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            delimiter = sentences[i + 1] if i + 1 < len(sentences) else ""
            segment = sentence + delimiter

            if len(current_chunk) + len(segment) <= max_length:
                current_chunk += segment
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = segment

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    # 句読点がない場合: 助詞・接続詞の後ろで分割
    # 「は」「が」「を」「に」「で」「と」「から」「まで」などで分割
    particles = r'(は|が|を|に|へ|で|と|から|まで|より|の|や|か)'

    # 助詞の後ろにマーカーを入れて分割しやすくする
    marked_text = re.sub(particles, r'\1|', text)
    potential_chunks = marked_text.split('|')

    chunks = []
    current_chunk = ""

    for segment in potential_chunks:
        if not segment:
            continue

        if len(current_chunk) + len(segment) <= max_length:
            current_chunk += segment
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = segment

    if current_chunk:
        chunks.append(current_chunk)

    # それでも空の場合は単純分割
    if not chunks:
        chunks = [text[i:i + max_length] for i in range(0, len(text), max_length)]

    return chunks

def analyze_with_llm(text: str) -> dict:
    chunks = split_by_sentences(text, max_length=45)

    converted_segments = []
    confidence_scores = []
    start_time = time.perf_counter()

    try:
        for i, chunk in enumerate(chunks):
            logger.info(f"🔄 Processing chunk {i+1}/{len(chunks)}...")

            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": chunk}
                ],
                "format": "json",
                "options": {
                    "temperature": 0.1,        # 多様性を許容
                    "top_k": 3,                # 最も確率の高いトークンだけを選ぶ
                    "repeat_penalty": 1.2,     # 同じ内容や無関係なループを防ぐ
                    "num_predict": 256         # 出力長を制限して暴走を防ぐ
                },
                "stream": False,
            }

            # --- HTTPリクエストの例外処理 ---
            try:
                response = requests.post(OLLAMA_URL, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Network error on chunk {i+1}: {e}")
                converted_segments.append(chunk) # 失敗時はひらがなのまま保持
                confidence_scores.append(0.0)
                continue

            # --- JSONパースとデータ抽出の例外処理 ---
            content = data.get("message", {}).get("content", "{}")

            try:
                # マークダウンタグが含まれる場合のクリーニング
                clean_content = re.sub(r"```json|```", "", content).strip()
                parsed = json.loads(clean_content)

                converted_text = parsed.get("text", chunk)
                confidence = float(parsed.get("confidence", 0.0))

                converted_segments.append(converted_text)
                confidence_scores.append(confidence)

                logger.info(f"Chunk {1+i} converted: {converted_text}")

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"❌ Parse error on chunk {i+1}: {e} | Content: {content}")
                converted_segments.append(chunk)
                confidence_scores.append(0.0)

        # 最終的な集計
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        final_text = "".join(converted_segments)
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

        logger.info(f"⏱️  Processing time: {elapsed_time:.2f}s")
        logger.info("=" * 60)
        logger.info(f"✅ Final: {final_text}")
        logger.info(f"📊 Avg confidence: {avg_confidence:.2f}")

        return {
            "normalized": text,
            "converted_text": final_text,
            "confidence": round(avg_confidence, 2)
        }

    except Exception as e:
        # 予期せぬ致命的なエラー
        logger.error(f"❌ Critical error in analyze_with_llm: {e}")
        return {
            "normalized": text,
            "converted_text": "unknown",
            "confidence": 0.0,
            "error": str(e)
        }
