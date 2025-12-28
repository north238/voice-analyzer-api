import json
import requests
import time
import re

from utils.logger import logger

OLLAMA_URL = "http://local-llm:11434/api/chat"
# MODEL_NAME = "qwen2.5:3b-instruct-q8_0" 軽量だが精度低い
# MODEL_NAME = "qwen2.5:7b-instruct-q4_0" 中国語に変換される問題あり
MODEL_NAME = "gemma2:2b-instruct-q8_0"

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

入力: むてんかのせっけん
出力: {"text": "無添加の石鹸", "confidence": 0.95}

入力: でんわばんごうはぜろいちにい
出力: {"text": "電話番号は012", "confidence": 0.9}

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
                "temperature": 0.3,  # Gemma2は少し高めが良い
                "top_k": 10,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
                "num_predict": 256,
            },
            "stream": False,
        }

        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
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
    max_chunk_size = 50

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


# 以前実装コード（日本語特化モデルに切り替えのため不要）
# def analyze_with_llm(text: str, max_chunk_size: int = 150) -> dict:
#     # テキストが短い場合は分割しない
#     if len(text) <= max_chunk_size:
#         logger.info(f"📝 Processing full text ({len(text)} chars)")
#         return process_single_chunk(text, 0)

#     # 長い場合は分割して処理
#     logger.info(f"📦 Text too long ({len(text)} chars), splitting into chunks")
#     return process_with_chunks(text, max_chunk_size)

# def process_single_chunk(text: str, chunk_index: int) -> dict:
#     start_time = time.perf_counter()

#     try:
#         logger.info(f"🔄 Processing: {text[:50]}...")

#         payload = {
#             "model": MODEL_NAME,
#             "messages": [
#                 {"role": "user", "content": f"{SYSTEM_PROMPT}\n\n入力: {text}\n出力:"}
#             ],
#             "options": {
#                 "temperature": 0.3,  # Gemma2は少し高めが良い
#                 "top_k": 10,
#                 "top_p": 0.9,
#                 "repeat_penalty": 1.1,
#                 "num_predict": 256,
#             },
#             "stream": False,
#         }

#         response = requests.post(OLLAMA_URL, json=payload, timeout=120)
#         response.raise_for_status()
#         data = response.json()

#         content = data.get("message", {}).get("content", "{}")
#         logger.info(f"content: {content}")

#         # JSONパース
#         clean_content = re.sub(r"```(?:json)?\s*|\s*```", "", content).strip()

#         # JSON以外のテキストを削除
#         json_match = re.search(r'\{[^{}]*"text"[^{}]*\}', clean_content)
#         if json_match:
#             clean_content = json_match.group(0)

#         parsed = json.loads(clean_content)
#         converted_text = parsed.get("text", text)
#         confidence = float(parsed.get("confidence", 0.0))

#         elapsed = time.perf_counter() - start_time
#         logger.info(
#             f"✓ Converted: {converted_text} (conf: {confidence}, {elapsed:.2f}s)"
#         )

#         return {
#             "normalized": text,
#             "converted_text": converted_text,
#             "confidence": round(confidence, 2),
#             "chunks_processed": 1,
#             "chunks_failed": 0,
#         }

#     except requests.exceptions.RequestException as e:
#         logger.error(f"❌ Network error: {e}")
#         return {
#             "normalized": text,
#             "converted_text": text,
#             "confidence": 0.0,
#             "error": f"Network error: {str(e)}",
#         }
#     except (json.JSONDecodeError, ValueError, KeyError) as e:
#         logger.error(f"❌ Parse error: {e}")
#         logger.error(f"   Raw response: {content}")
#         return {
#             "normalized": text,
#             "converted_text": text,
#             "confidence": 0.0,
#             "error": f"Parse error: {str(e)}",
#         }
#     except Exception as e:
#         logger.error(f"❌ Unexpected error: {e}", exc_info=True)
#         return {
#             "normalized": text,
#             "converted_text": text,
#             "confidence": 0.0,
#             "error": str(e),
#         }


# def process_with_chunks(text: str, chunk_size: int) -> dict:
#     """長いテキストを分割して処理"""

#     # 単純に文字数で分割(オーバーラップなし)
#     chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

#     logger.info(f"📦 Split into {len(chunks)} chunks")
#     for i, chunk in enumerate(chunks):
#         logger.info(f"  Chunk {i+1}: '{chunk[:40]}...' ({len(chunk)} chars)")

#     converted_segments = []
#     confidence_scores = []
#     failed_count = 0
#     start_time = time.perf_counter()

#     for i, chunk in enumerate(chunks):
#         result = process_single_chunk(chunk, i)

#         if "error" in result:
#             failed_count += 1
#             converted_segments.append(chunk)
#             confidence_scores.append(0.0)
#         else:
#             converted_segments.append(result["converted_text"])
#             confidence_scores.append(result["confidence"])

#     elapsed = time.perf_counter() - start_time
#     final_text = "".join(converted_segments)
#     avg_confidence = (
#         sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
#     )

#     logger.info(f"⏱️  Total time: {elapsed:.2f}s")
#     logger.info("=" * 60)
#     logger.info(f"✅ Final result: {final_text}")
#     logger.info(f"📊 Avg confidence: {avg_confidence:.2f}")

#     return {
#         "normalized": text,
#         "converted_text": final_text,
#         "confidence": round(avg_confidence, 2),
#         "chunks_processed": len(chunks),
#         "chunks_failed": failed_count,
#     }



# def split_with_overlap(text: str, chunk_size: int = 100, overlap: int = 20) -> list[dict]:
#     # 句読点がある場合は句読点で分割
#     if re.search(r'[。、]', text):
#         sentences = re.split(r'([。、])', text)
#         chunks = []
#         current_chunk = ""

#         for i in range(0, len(sentences), 2):
#             sentence = sentences[i]
#             delimiter = sentences[i + 1] if i + 1 < len(sentences) else ""
#             segment = sentence + delimiter

#             if len(current_chunk) + len(segment) <= chunk_size:
#                 current_chunk += segment
#             else:
#                 if current_chunk:
#                     chunks.append({"text": current_chunk, "trim_start": 0})
#                 current_chunk = segment

#         if current_chunk:
#             chunks.append({"text": current_chunk, "trim_start": 0})

#         return chunks

#     # 句読点がない場合: オーバーラップ戦略
#     chunks = []
#     i = 0

#     while i < len(text):
#         # チャンクの終了位置
#         end = min(i + chunk_size, len(text))
#         chunk_text = text[i:end]

#         # 次のチャンクの開始位置(オーバーラップを考慮)
#         # 最後のチャンク以外は、overlap分だけ戻る
#         next_start = end - overlap if end < len(text) else end

#         # このチャンクで削除すべき先頭文字数(最初のチャンク以外)
#         trim_start = overlap if i > 0 else 0

#         chunks.append({
#             "text": chunk_text,
#             "trim_start": trim_start
#         })

#         i = next_start

#     return chunks

# def analyze_with_llm(text: str) -> dict:
#     chunk_info_list = split_with_overlap(text, chunk_size=100, overlap=20)
#     logger.info(f"📦 Total chunks: {len(chunk_info_list)}")
#     for i, chunk_info in enumerate(chunk_info_list):
#         logger.info(f"  Chunk {i+1}: '{chunk_info['text'][:40]}...' (trim_start={chunk_info['trim_start']})")

#     converted_segments = []
#     confidence_scores = []
#     start_time = time.perf_counter()

#     try:
#         for i, chunk in enumerate(chunk_info_list):
#             chunk = chunk_info["text"]
#             trim_start = chunk_info["trim_start"]
#             logger.info(f"🔄 Processing chunk {i+1}/{len(chunk_info_list)}: {chunk[:30]}...")

#             payload = {
#                 "model": MODEL_NAME,
#                 "messages": [
#                     {"role": "system", "content": SYSTEM_PROMPT},
#                     {"role": "user", "content": chunk}
#                 ],
#                 "format": "json",
#                 "options": {
#                     "temperature": 0.1,        # 多様性を許容
#                     "top_k": 3,                # 最も確率の高いトークンだけを選ぶ
#                     "repeat_penalty": 1.2,     # 同じ内容や無関係なループを防ぐ
#                     "num_predict": 256         # 出力長を制限して暴走を防ぐ
#                 },
#                 "stream": False,
#             }

#             # --- HTTPリクエストの例外処理 ---
#             try:
#                 response = requests.post(OLLAMA_URL, json=payload, timeout=60)
#                 response.raise_for_status()
#                 data = response.json()
#             except requests.exceptions.RequestException as e:
#                 logger.error(f"❌ Network error on chunk {i+1}: {e}")
#                 converted_segments.append(chunk) # 失敗時はひらがなのまま保持
#                 confidence_scores.append(0.0)
#                 continue

#             # --- JSONパースとデータ抽出の例外処理 ---
#             content = data.get("message", {}).get("content", "{}")

#             try:
#                 # マークダウンタグが含まれる場合のクリーニング
#                 clean_content = re.sub(r"```json|```", "", content).strip()
#                 parsed = json.loads(clean_content)

#                 converted_text = parsed.get("text", chunk)
#                 confidence = float(parsed.get("confidence", 0.0))

#                 if trim_start > 0:
#                     converted_text = converted_text[trim_start:]

#                 converted_segments.append(converted_text)
#                 confidence_scores.append(confidence)

#                 logger.info(f"Chunk {1+i} converted: {converted_text}")

#             except (json.JSONDecodeError, ValueError) as e:
#                 logger.error(f"❌ Parse error on chunk {i+1}: {e} | Content: {content}")

#                 fallback_text = str(chunk[trim_start:])
#                 converted_segments.append(fallback_text)
#                 confidence_scores.append(0.0)

#         # 最終的な集計
#         end_time = time.perf_counter()
#         elapsed_time = end_time - start_time

#         final_text = "".join(converted_segments)
#         avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

#         logger.info(f"⏱️  Processing time: {elapsed_time:.2f}s")
#         logger.info("=" * 60)
#         logger.info(f"✅ Final: {final_text}")
#         logger.info(f"📊 Avg confidence: {avg_confidence:.2f}")

#         return {
#             "normalized": text,
#             "converted_text": final_text,
#             "confidence": round(avg_confidence, 2)
#         }

#     except Exception as e:
#         # 予期せぬ致命的なエラー
#         logger.error(f"❌ Critical error in analyze_with_llm: {e}")
#         return {
#             "normalized": text,
#             "converted_text": "unknown",
#             "confidence": 0.0,
#             "error": str(e)
#         }
