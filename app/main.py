from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from services.audio_processor import transcribe_audio
from services.inventory_parser import parse_inventory
from services.llm_analyzer import analyze_with_llm
from services.text_filter import is_valid_text
from services.translator import translate_text
from utils.normalizer import JapaneseNormalizer
from utils.logger import logger

app = FastAPI()

# 正規化インスタンスの初期化
normalizer = JapaneseNormalizer()

@app.post("/transcribe")
async def transcribe(
    file: UploadFile, intent: str = Form("inventory"), translate: bool = Form(False)
):
    try:
        # Whisperで文字起こし
        text = await transcribe_audio(file)

        # NGワードフィルタリング
        if not is_valid_text(text):
            logger.warning(f"⚠️ 無効な内容検出: {text}")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "無効な音声内容です",
                    "input": text,
                },
            )

        hiragana_text = normalizer.to_hiragana(text)
        logger.info(f"📝 正規化後（ひらがな）: {hiragana_text}")

        # 翻訳処理（オプション）
        translated_text = None
        if translate:
            logger.info("🌐 翻訳を実行します")
            translated_text = translate_text(text)
            logger.info(f"✅ 翻訳完了: {translated_text}")

        # 意図に応じた処理
        # if intent == "inventory":
        #     result = parse_inventory(hiragana_text)

        # elif intent == "raw":
        #     result = analyze_with_llm(hiragana_text)

        # else:
        #     raise HTTPException(
        #         status_code=400,
        #         detail=f"unknown intent: {intent}",
        #     )

        response_content = {
            "status": "success",
            "message": "音声解析に成功しました",
            "intent": intent,
            "text": text,
            "result": hiragana_text,
        }

        # 翻訳結果を追加
        if translated_text is not None:
            response_content["translated"] = translated_text

        return JSONResponse(status_code=200, content=response_content)

    except Exception as e:
        logger.exception("❌ 音声解析中にエラー発生")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "音声解析中にエラーが発生しました。再度お試しください。",
                "detail": str(e),
            },
        )

@app.post("/translate")
async def translate(file: UploadFile):
    """
    音声ファイルを文字起こし→翻訳する専用エンドポイント
    """
    try:
        # Whisperで文字起こし
        text = await transcribe_audio(file)
        logger.info(f"📝 文字起こし完了: {text}")

        # NGワードフィルタリング
        if not is_valid_text(text):
            logger.warning(f"⚠️ 無効な内容検出: {text}")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "無効な音声内容です",
                    "input": text,
                },
            )

        # ひらがな正規化
        hiragana_text = normalizer.to_hiragana(text)
        logger.info(f"📝 正規化後（ひらがな）: {hiragana_text}")

        # 翻訳実行
        logger.info("🌐 翻訳を実行します")
        translated_text = translate_text(text)
        logger.info(f"✅ 翻訳完了: {translated_text}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "音声翻訳に成功しました",
                "original_text": text,
                "hiragana_text": hiragana_text,
                "translated_text": translated_text,
            },
        )

    except Exception as e:
        logger.exception("❌ 音声翻訳中にエラー発生")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "音声翻訳中にエラーが発生しました。再度お試しください。",
                "detail": str(e),
            },
        )


@app.get("/health")
async def health_check():
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "Voice Analyzer API",
            "version": "1.0.0",
        },
    )
