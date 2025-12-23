from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from services.audio_processor import transcribe_audio
from services.inventory_parser import parse_inventory
from services.text_filter import is_valid_text
from utils.logger import logger

app = FastAPI()


@app.post("/transcribe")
async def transcribe(file: UploadFile, intent: str = Form("inventory"),):
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
                    "message": "無効な音声内容です",
                    "input": text,
                },
            )

        # 意図に応じた処理
        if intent == "inventory":
            result = parse_inventory(text)

        # elif intent == "raw":
        #     result = analyze_with_llm(text)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"unknown intent: {intent}",
            )

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "音声解析に成功しました",
                "intent": intent,
                "text": text,
                "result": result,
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
