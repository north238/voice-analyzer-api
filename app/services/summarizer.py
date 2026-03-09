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
SUMMARY_SYSTEM_PROMPT = """あなたは日本語テキストの要約AIです。
入力は音声の文字起こしのため、誤字・脱字・フィラーが含まれます。

出力ルール：
- 最初に見出しを1行出力する
- 見出しはタイトルの引用ではなく「聞いた人へのメリット・示唆」を一言で表す
- 見出しは体言止めではなく「〜できる」「〜がわかる」などの表現を使う
- 見出しの後に「・」で始まる箇条書き3点を出力する
- 各項目は30字以内で完結させる
- フィラー（ですね、えー、あのー、まあ等）は除去する
- 誤字・誤変換は文脈から推測して正しい言葉に直す
- 重複している内容は1点にまとめる
- 見出しと箇条書き以外の文章は一切出力しない

出力フォーマット：
[聞いた人へのメリット・示唆を表す一言]
・[要点1]
・[要点2]
・[要点3]"""


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
        ollama_url = urljoin(settings.OLLAMA_BASE_URL.rstrip("/") + "/", "api/chat")

        payload = {
            "model": settings.OLLAMA_SUMMARY_MODEL,
            "messages": [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                # 例示（Whisperノイズの典型例）
                {
                    "role": "user",
                    "content": "以下の文字起こしテキストを要約してください:\n\nゴーランゴーですねこれはですね軽量でですね高速なプログラミング言語となっていてですね学習コストがですね低くなっていますで収得がですね比較的良いとなっていますで実効速度がですね早くてですねパフォーマンスがですね高くなっています",
                },
                {
                    "role": "assistant",
                    "content": "## 今注目のGo言語、学ぶ価値は高い\n・Goは軽量で高速なプログラミング言語\n・学習コストが低く習得しやすい\n・実行速度が速くパフォーマンスが高い",
                },
                # 本番入力
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
