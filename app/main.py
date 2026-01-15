from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from services.audio_processor import transcribe_audio
from services.inventory_parser import parse_inventory
from services.llm_analyzer import analyze_with_llm
from services.text_filter import is_valid_text
from services.translator import translate_text
from services.session_manager import get_session_manager
from utils.normalizer import JapaneseNormalizer
from utils.performance_monitor import PerformanceMonitor
from utils.logger import logger
from config import settings
import time
from typing import Optional

app = FastAPI()

# 正規化インスタンスの初期化
normalizer = JapaneseNormalizer()

# セッションマネージャーの初期化
session_manager = get_session_manager(
    timeout_minutes=settings.SESSION_TIMEOUT_MINUTES,
    max_chunks_per_session=settings.MAX_CHUNKS_PER_SESSION,
)

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


@app.post("/translate-chunk")
async def translate_chunk(
    file: UploadFile,
    session_id: Optional[str] = Form(None),
    chunk_id: int = Form(0),
    is_final: bool = Form(False),
):
    """
    音声チャンクを受け取り、文字起こし→正規化→翻訳を行う
    セッションIDでチャンク間の状態を管理
    """
    monitor = PerformanceMonitor()
    request_start_time = time.time()

    try:
        # セッション管理
        if session_id is None:
            session_id = session_manager.create_session()
            logger.info(f"🆕 新規セッション作成: {session_id}")
        else:
            # 既存セッション確認
            session = session_manager.get_session(session_id)
            if session is None:
                # セッションが見つからない場合は新規作成
                session_id = session_manager.create_session(session_id)
                logger.info(f"🆕 セッションが見つからないため新規作成: {session_id}")

        logger.info(
            f"📦 チャンク処理開始: session={session_id}, chunk={chunk_id}, final={is_final}"
        )

        # 1. Whisper文字起こし
        with monitor.measure("transcription"):
            text = await transcribe_audio(file)
            logger.info(f"📝 文字起こし完了: {text}")

        # 2. NGワードフィルタリング
        with monitor.measure("filtering"):
            if not is_valid_text(text):
                logger.warning(f"⚠️ 無効な内容検出: {text}")
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "無効な音声内容です",
                        "session_id": session_id,
                        "chunk_id": chunk_id,
                        "input": text,
                    },
                )

        # 3. ひらがな正規化
        with monitor.measure("normalization"):
            hiragana_text = normalizer.to_hiragana(text)
            logger.info(f"📝 正規化完了: {hiragana_text}")

        # 4. 翻訳
        with monitor.measure("translation"):
            translated_text = translate_text(text)
            logger.info(f"✅ 翻訳完了: {translated_text}")

        # 処理時間の計算
        total_time = time.time() - request_start_time

        # セッションにチャンクデータを保存
        session_manager.add_chunk_to_session(
            session_id=session_id,
            chunk_id=chunk_id,
            timestamp=request_start_time,
            original_text=text,
            hiragana_text=hiragana_text,
            translated_text=translated_text,
            processing_time=total_time,
        )

        # セッション情報を取得
        session_info = session_manager.get_session_info(session_id)

        # 最終チャンクの場合はクリーンアップ
        if is_final:
            logger.info(f"🏁 最終チャンク処理完了: session={session_id}")
            # 必要に応じてセッション削除（後で統計を見られるように残す場合はコメントアウト）
            # session_manager.delete_session(session_id)

        # レスポンス構築
        response_content = {
            "status": "success",
            "session_id": session_id,
            "chunk_id": chunk_id,
            "is_final": is_final,
            "results": {
                "original_text": text,
                "hiragana_text": hiragana_text,
                "translated_text": translated_text,
            },
            "performance": monitor.get_summary(),
            "context": {
                "previous_chunks": session_info["total_chunks"] - 1,
                "total_chunks": session_info["total_chunks"],
            },
        }

        logger.info(
            f"✅ チャンク処理完了: session={session_id}, chunk={chunk_id}, time={total_time:.3f}秒"
        )

        return JSONResponse(status_code=200, content=response_content)

    except Exception as e:
        logger.exception(f"❌ チャンク処理中にエラー発生: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "チャンク処理中にエラーが発生しました",
                "session_id": session_id if session_id else None,
                "chunk_id": chunk_id,
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
