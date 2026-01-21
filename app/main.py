from fastapi import FastAPI, UploadFile, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from services.audio_processor import transcribe_audio
from services.inventory_parser import parse_inventory
from services.llm_analyzer import analyze_with_llm
from services.text_filter import is_valid_text
from services.translator import translate_text
from services.session_manager import get_session_manager
from services.websocket_manager import get_websocket_manager
from services.async_processor import (
    transcribe_async,
    normalize_async,
    translate_async,
    add_punctuation_async,
)
from utils.normalizer import JapaneseNormalizer
from utils.performance_monitor import PerformanceMonitor
from utils.logger import logger
from config import settings
import time
import json
from typing import Optional

app = FastAPI()

# 正規化インスタンスの初期化
normalizer = JapaneseNormalizer()

# セッションマネージャーの初期化
session_manager = get_session_manager(
    timeout_minutes=settings.SESSION_TIMEOUT_MINUTES,
    max_chunks_per_session=settings.MAX_CHUNKS_PER_SESSION,
)

# WebSocketマネージャーの初期化
ws_manager = get_websocket_manager()

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

        # 句読点を挿入（翻訳精度向上のため）
        text_with_punctuation = normalizer.add_punctuation(text)
        logger.info(f"📝 句読点挿入後: {text_with_punctuation}")

        # ひらがな正規化（句読点付きテキストから）
        hiragana_text = normalizer.to_hiragana(text_with_punctuation, keep_punctuation=True)
        logger.info(f"📝 正規化後（ひらがな）: {hiragana_text}")

        # 翻訳実行（句読点付きテキストを使用）
        logger.info("🌐 翻訳を実行します")
        translated_text = translate_text(text_with_punctuation)
        logger.info(f"✅ 翻訳完了: {translated_text}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "音声翻訳に成功しました",
                "original_text": text,
                "text_with_punctuation": text_with_punctuation,
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

        # 3. 句読点挿入
        with monitor.measure("punctuation"):
            text_with_punctuation = normalizer.add_punctuation(text)
            logger.info(f"📝 句読点挿入完了: {text_with_punctuation}")

        # 4. ひらがな正規化
        with monitor.measure("normalization"):
            hiragana_text = normalizer.to_hiragana(text_with_punctuation, keep_punctuation=True)
            logger.info(f"📝 正規化完了: {hiragana_text}")

        # 5. 翻訳
        with monitor.measure("translation"):
            translated_text = translate_text(text_with_punctuation)
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
            "websocket_connections": ws_manager.get_active_connections_count(),
        },
    )


@app.websocket("/ws/translate-stream")
async def websocket_translate_stream(websocket: WebSocket):
    """
    WebSocketによる音声チャンクのストリーミング翻訳

    プロトコル:
    1. クライアントが接続
    2. サーバーが {"type": "connected", "session_id": "..."} を送信
    3. クライアントが音声チャンク（バイナリ）を送信
    4. サーバーが進捗通知を送信しながら処理
    5. サーバーが結果を送信
    6. 3-5を繰り返し
    7. クライアントが {"type": "end"} を送信してセッション終了
    """
    connection = None
    session_id = None

    try:
        # 接続を受け付け
        connection = await ws_manager.connect(websocket)
        session_id = connection.session_id

        # セッションマネージャーにも登録
        session_manager.create_session(session_id)
        logger.info(f"🚀 WebSocketセッション開始: {session_id}")

        while True:
            try:
                # メッセージを受信（テキストまたはバイナリ）
                message = await websocket.receive()

                if message["type"] == "websocket.disconnect":
                    break

                # テキストメッセージ（制御コマンド）
                if "text" in message:
                    data = json.loads(message["text"])
                    msg_type = data.get("type", "")

                    if msg_type == "end":
                        # セッション終了
                        session_info = session_manager.get_session_info(session_id)
                        statistics = {}
                        if session_info:
                            statistics = {
                                "total_chunks": session_info.get("total_chunks", 0),
                                "duration": session_info.get("last_updated", ""),
                            }

                        await ws_manager.send_session_end(
                            session_id,
                            connection.chunk_count,
                            statistics,
                        )
                        logger.info(f"🏁 WebSocketセッション終了: {session_id}")
                        break

                    elif msg_type == "ping":
                        # Ping応答
                        await ws_manager.send_json(session_id, {"type": "pong"})

                # バイナリメッセージ（音声データ）
                elif "bytes" in message:
                    audio_data = message["bytes"]
                    chunk_id = connection.increment_chunk()

                    logger.info(
                        f"📦 WebSocketチャンク受信: session={session_id}, chunk={chunk_id}, size={len(audio_data)}bytes"
                    )

                    # チャンク処理を実行
                    await process_websocket_chunk(
                        session_id=session_id,
                        chunk_id=chunk_id,
                        audio_data=audio_data,
                        connection=connection,
                    )

            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket切断: session={session_id}")
                break

    except Exception as e:
        logger.exception(f"❌ WebSocketエラー: {e}")
        if session_id:
            await ws_manager.send_error(session_id, str(e))

    finally:
        # クリーンアップ
        if session_id:
            await ws_manager.disconnect(session_id)
            # セッションは残す（統計確認用）


async def process_websocket_chunk(
    session_id: str,
    chunk_id: int,
    audio_data: bytes,
    connection,
):
    """
    WebSocket経由で受信した音声チャンクを処理

    Args:
        session_id: セッションID
        chunk_id: チャンクID
        audio_data: 音声データ
        connection: WebSocket接続情報
    """
    monitor = connection.monitor
    request_start_time = time.time()

    try:
        # 1. 文字起こし
        await ws_manager.send_progress(
            session_id, "transcribing", "音声認識中...", chunk_id
        )
        with monitor.measure("transcription"):
            text = await transcribe_async(audio_data)

        # 無音チャンクはスキップ（エラーではなく正常終了）
        if not text:
            await ws_manager.send_json(session_id, {
                "type": "skipped",
                "chunk_id": chunk_id,
                "reason": "silent",
                "message": "無音チャンク"
            })
            return

        logger.info(f"📝 文字起こし完了: {text}")

        # 2. NGワードフィルタリング
        if not is_valid_text(text):
            logger.warning(f"⚠️ 無効な内容検出: {text}")
            await ws_manager.send_error(session_id, f"無効な音声内容です: {text}")
            return

        # 3. 句読点挿入
        await ws_manager.send_progress(
            session_id, "punctuation", "句読点挿入中...", chunk_id
        )
        with monitor.measure("punctuation"):
            text_with_punctuation = await add_punctuation_async(text)
            logger.info(f"📝 句読点挿入完了: {text_with_punctuation}")

        # 4. ひらがな正規化
        await ws_manager.send_progress(
            session_id, "normalizing", "ひらがな変換中...", chunk_id
        )
        with monitor.measure("normalization"):
            hiragana_text = await normalize_async(text_with_punctuation)
            logger.info(f"📝 正規化完了: {hiragana_text}")

        # 5. 翻訳
        await ws_manager.send_progress(
            session_id, "translating", "翻訳中...", chunk_id
        )
        with monitor.measure("translation"):
            translated_text = await translate_async(text_with_punctuation)
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

        # 結果を送信
        await ws_manager.send_result(
            session_id=session_id,
            chunk_id=chunk_id,
            original_text=text,
            hiragana_text=hiragana_text,
            translated_text=translated_text,
            performance=monitor.get_summary(),
        )

        logger.info(
            f"✅ WebSocketチャンク処理完了: session={session_id}, chunk={chunk_id}, time={total_time:.3f}秒"
        )

    except Exception as e:
        logger.exception(f"❌ チャンク処理エラー: {e}")
        await ws_manager.send_error(session_id, f"チャンク処理エラー: {str(e)}")
