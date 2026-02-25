"""
要約サービス（Phase 13）
プロバイダー切り替え対応: Ollama / Gemini
"""

import requests
from typing import Optional
from urllib.parse import urljoin

from config import settings
from utils.logger import logger

# システムプロンプト（共通）
SUMMARY_SYSTEM_PROMPT = """あなたは日本語の文字起こしテキストを要約する専門家です。

【タスク】
音声の文字起こし結果を簡潔に要約してください。

【ルール】
1. 日本語で出力すること
2. 要点を箇条書きで整理すること
3. 元のテキストの意味を損なわないこと
4. 要約は元のテキストの1/3程度の長さにすること
5. フィラー（えー、あのー等）は除去すること
6. 箇条書きの前に見出しや前置きは不要。要点のみ出力すること"""


async def summarize_text(text: str, api_key: Optional[str] = None) -> str:
    """
    テキストを要約する（プロバイダーは設定で切り替え）

    Args:
        text: 要約対象のテキスト
        api_key: Gemini APIキー（クライアントから直接指定する場合）

    Returns:
        str: 要約結果
    """
    if not text or not text.strip():
        return ""

    provider = settings.SUMMARY_PROVIDER
    logger.info(f"📋 要約開始: プロバイダー={provider}, テキスト={len(text)}文字")

    if provider == "ollama":
        return await _summarize_with_ollama(text)
    elif provider == "gemini":
        return await _summarize_with_gemini(text, api_key)
    else:
        raise ValueError(f"未対応の要約プロバイダー: {provider}")


async def _summarize_with_ollama(text: str) -> str:
    """Ollamaで要約を実行"""
    try:
        ollama_url = urljoin(
            settings.OLLAMA_BASE_URL.rstrip("/") + "/", "api/chat"
        )

        payload = {
            "model": settings.OLLAMA_SUMMARY_MODEL,
            "messages": [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"以下の文字起こしテキストを要約してください:\n\n{text}",
                },
            ],
            "options": {
                "temperature": settings.OLLAMA_TEMPERATURE,
                "num_predict": settings.OLLAMA_SUMMARY_NUM_PREDICT,
                "top_p": settings.OLLAMA_TOP_P,
            },
            "stream": False,
        }

        response = requests.post(
            ollama_url, json=payload, timeout=settings.OLLAMA_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()

        summary = data.get("message", {}).get("content", "").strip()
        logger.info(f"📋 Ollama要約完了: {len(summary)}文字")
        return summary

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ollama要約エラー（ネットワーク）: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Ollama要約エラー: {e}")
        raise


async def _summarize_with_gemini(text: str, api_key: Optional[str] = None) -> str:
    """Gemini APIで要約を実行"""
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError(
            "google-generativeaiパッケージが必要です: pip install google-generativeai"
        )

    key = api_key or settings.GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_API_KEYが設定されていません")

    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel(
            settings.GEMINI_MODEL,
            generation_config=genai.GenerationConfig(
                max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
                temperature=settings.GEMINI_TEMPERATURE,
            ),
            system_instruction=SUMMARY_SYSTEM_PROMPT,
        )

        response = await model.generate_content_async(
            f"以下の文字起こしテキストを要約してください:\n\n{text}"
        )
        summary = response.text.strip()
        logger.info(f"📋 Gemini要約完了: {len(summary)}文字")
        return summary

    except Exception as e:
        logger.error(f"❌ Gemini要約エラー: {e}")
        raise
