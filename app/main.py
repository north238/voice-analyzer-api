from fastapi import FastAPI, UploadFile
from fastapi.responses import JSONResponse
from services.audio_processor import transcribe_audio
from services.text_parser import parse_text
from services.text_filter import is_valid_text
from utils.logger import logger

app = FastAPI()


@app.post("/transcribe")
async def transcribe(file: UploadFile):
    try:
        # Whisperで文字起こし
        text = await transcribe_audio(file)
        logger.info(f"📝 文字起こし結果: {text}")

        # NGワードフィルタリング
        if not is_valid_text(text):
            logger.warning(f"⚠️ 無効な内容検出: {text}")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "品名として認識できませんでした。再度お試しください。",
                    "input": text,
                },
            )

        # テキストを解析して構造化（例：「卵1個」→ {"item":"卵","quantity":"1","unit":"個"}）
        parsed_items = parse_text(text)
        logger.info(f"🔍 解析結果: {parsed_items}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "音声解析に成功しました。",
                "data": {
                    "input": text,
                    "items": parsed_items,
                },
            },
        )

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
