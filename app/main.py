from fastapi import FastAPI, UploadFile, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from services.audio_processor import transcribe_audio
from services.text_filter import is_valid_text
from services.translator import translate_text
from services.session_manager import get_session_manager
from services.websocket_manager import get_websocket_manager
from services.async_processor import (
    transcribe_async,
    normalize_async,
    translate_async,
)
from services.cumulative_buffer import (
    CumulativeBuffer,
    CumulativeBufferConfig,
)
from utils.normalizer import JapaneseNormalizer
from utils.performance_monitor import PerformanceMonitor
from utils.logger import logger
from config import settings
import time
import json
import os
from typing import Optional, Dict
from pydantic import BaseModel

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

# 累積バッファの管理（セッションIDをキーにした辞書）
cumulative_buffers: Dict[str, CumulativeBuffer] = {}


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
        hiragana_text = normalizer.to_hiragana(text, keep_punctuation=False)
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
            hiragana_text = normalizer.to_hiragana(text, keep_punctuation=False)
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


class ProcessTextRequest(BaseModel):
    text: str
    hiragana: bool = False
    translation: bool = False


@app.post("/process-text")
async def process_text(request: ProcessTextRequest):
    """テキストのひらがな変換・翻訳を行うエンドポイント（タイムアウト時などの補完用）"""
    result = {}
    if request.hiragana and request.text:
        result["hiragana"] = normalizer.to_hiragana(request.text, keep_punctuation=False)
    if request.translation and request.text:
        result["translation"] = await translate_async(request.text)
    return JSONResponse(status_code=200, content=result)


class SummarizeRequest(BaseModel):
    text: str
    api_key: Optional[str] = None


@app.post("/summarize")
async def summarize(request: SummarizeRequest):
    """テキストを要約するエンドポイント（Phase 13）"""
    try:
        if not request.text or not request.text.strip():
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "テキストが空です"},
            )

        from services.summarizer import summarize_text

        summary = await summarize_text(request.text, api_key=request.api_key)

        return JSONResponse(
            status_code=200,
            content={"status": "success", "summary": summary},
        )

    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)},
        )
    except Exception as e:
        logger.exception("❌ 要約処理中にエラー発生")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "要約処理中にエラーが発生しました",
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
            await ws_manager.send_json(
                session_id,
                {
                    "type": "skipped",
                    "chunk_id": chunk_id,
                    "reason": "silent",
                    "message": "無音チャンク",
                },
            )
            return

        transcription_time = monitor.get_last_measurement("transcription")
        logger.info(f"📝 文字起こし完了 ({transcription_time:.2f}秒): {text}")

        # 2. NGワードフィルタリング
        if not is_valid_text(text):
            logger.warning(f"⚠️ 無効な内容検出: {text}")
            await ws_manager.send_error(session_id, f"無効な音声内容です: {text}")
            return

        # 3. ひらがな正規化
        await ws_manager.send_progress(
            session_id, "normalizing", "ひらがな変換中...", chunk_id
        )
        with monitor.measure("normalization"):
            hiragana_text = await normalize_async(text, keep_punctuation=False)
        normalization_time = monitor.get_last_measurement("normalization")
        logger.info(f"📝 正規化完了 ({normalization_time:.2f}秒): {hiragana_text}")

        # 4. 翻訳
        await ws_manager.send_progress(session_id, "translating", "翻訳中...", chunk_id)
        with monitor.measure("translation"):
            translated_text = await translate_async(text)
        translation_time = monitor.get_last_measurement("translation")
        logger.info(f"✅ 翻訳完了 ({translation_time:.2f}秒): {translated_text}")

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


@app.websocket("/ws/transcribe-stream-cumulative")
async def websocket_transcribe_stream_cumulative(websocket: WebSocket):
    """
    累積バッファ方式によるリアルタイム文字起こし

    プロトコル:
    1. クライアントが接続
    2. サーバーが {"type": "connected", "session_id": "..."} を送信
    3. クライアントが音声チャンク（バイナリ）を送信
    4. サーバーが音声を累積し、一定間隔で全体を再文字起こし
    5. サーバーが確定/暫定テキストを送信
    6. 3-5を繰り返し
    7. クライアントが {"type": "end"} を送信してセッション終了
    """
    connection = None
    session_id = None

    try:
        # 接続を受け付け
        connection = await ws_manager.connect(websocket)
        session_id = connection.session_id

        # セッションマネージャーに登録
        session_manager.create_session(session_id)

        # 累積バッファを作成
        buffer_config = CumulativeBufferConfig(
            max_audio_duration_seconds=settings.CUMULATIVE_MAX_AUDIO_SECONDS,
            transcription_interval_chunks=settings.CUMULATIVE_TRANSCRIPTION_INTERVAL,
            stable_text_threshold=settings.CUMULATIVE_STABLE_THRESHOLD,
        )
        buffer = CumulativeBuffer(buffer_config)

        # トリミング前コールバックを設定
        def on_before_trim():
            """バッファトリミング前に暫定テキストを確定に移行（ひらがな変換はセッション終了時に一括処理）"""
            buffer.force_finalize_pending_text()

        buffer.set_on_before_trim_callback(on_before_trim)
        cumulative_buffers[session_id] = buffer

        logger.info(f"🚀 累積バッファセッション開始: {session_id}")

        while True:
            try:
                # メッセージを受信
                message = await websocket.receive()

                if message["type"] == "websocket.disconnect":
                    break

                # テキストメッセージ（制御コマンド）
                if "text" in message:
                    data = json.loads(message["text"])
                    msg_type = data.get("type", "")

                    if msg_type == "options":
                        # 処理オプションを設定
                        connection.processing_options = {
                            "hiragana": data.get("hiragana", False),
                            "translation": data.get("translation", False),
                            "summary": data.get("summary", False),
                        }
                        logger.info(
                            f"📝 処理オプション設定: session={session_id}, "
                            f"options={connection.processing_options}"
                        )
                        await ws_manager.send_json(
                            session_id, {"type": "options_received"}
                        )

                    elif msg_type == "end":
                        # セッション終了処理
                        await finalize_cumulative_session(session_id, connection)
                        break

                    elif msg_type == "ping":
                        await ws_manager.send_json(session_id, {"type": "pong"})

                # バイナリメッセージ（音声データ）
                elif "bytes" in message:
                    audio_data = message["bytes"]
                    chunk_id = connection.increment_chunk()

                    logger.info(
                        f"📦 累積チャンク受信: session={session_id}, "
                        f"chunk={chunk_id}, size={len(audio_data)}bytes"
                    )

                    # 累積バッファで処理
                    await process_cumulative_chunk(
                        session_id=session_id,
                        chunk_id=chunk_id,
                        audio_data=audio_data,
                        connection=connection,
                    )

            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket切断: session={session_id}")
                break

    except Exception as e:
        logger.exception(f"❌ 累積バッファWebSocketエラー: {e}")
        if session_id:
            await ws_manager.send_error(session_id, str(e))

    finally:
        # クリーンアップ
        if session_id:
            await ws_manager.disconnect(session_id)
            # 累積バッファを削除
            if session_id in cumulative_buffers:
                del cumulative_buffers[session_id]
                logger.info(f"🧹 累積バッファ削除: {session_id}")


async def process_cumulative_chunk(
    session_id: str,
    chunk_id: int,
    audio_data: bytes,
    connection,
):
    """
    累積バッファ方式でチャンクを処理

    Args:
        session_id: セッションID
        chunk_id: チャンクID
        audio_data: 音声データ
        connection: WebSocket接続情報
    """
    monitor = connection.monitor
    buffer = cumulative_buffers.get(session_id)

    if not buffer:
        logger.error(f"❌ 累積バッファが見つかりません: {session_id}")
        await ws_manager.send_error(session_id, "累積バッファが見つかりません")
        return

    try:
        # 音声をバッファに追加（トリミング判定のみ）
        should_transcribe, should_trim = buffer.add_audio_chunk(audio_data)

        # 蓄積中の通知
        chunks_until_transcription = buffer.config.transcription_interval_chunks - (
            buffer.chunk_count % buffer.config.transcription_interval_chunks
        )
        if chunks_until_transcription == buffer.config.transcription_interval_chunks:
            chunks_until_transcription = 0

        await ws_manager.send_json(
            session_id,
            {
                "type": "accumulating",
                "chunk_id": chunk_id,
                "accumulated_seconds": buffer.current_audio_duration,
                "session_elapsed_seconds": buffer.session_elapsed_seconds,
                "chunks_until_transcription": chunks_until_transcription,
            },
        )

        # 再文字起こしが必要な場合
        if should_transcribe:
            await perform_cumulative_transcription(
                session_id=session_id,
                chunk_id=chunk_id,
                buffer=buffer,
                monitor=monitor,
                should_trim=should_trim,
            )

    except Exception as e:
        logger.exception(f"❌ 累積チャンク処理エラー: {e}")
        await ws_manager.send_error(session_id, f"累積チャンク処理エラー: {str(e)}")


async def perform_cumulative_transcription(
    session_id: str,
    chunk_id: int,
    buffer: CumulativeBuffer,
    monitor: PerformanceMonitor,
    should_trim: bool = False,
):
    """
    累積音声の全体文字起こしを実行

    Args:
        session_id: セッションID
        chunk_id: チャンクID
        buffer: 累積バッファ
        monitor: パフォーマンスモニター
        should_trim: トリミングが必要かどうか（デフォルトFalse）
    """
    request_start_time = time.time()

    try:
        # 進捗通知
        await ws_manager.send_progress(
            session_id, "transcribing", "累積音声を文字起こし中...", chunk_id
        )

        # 累積音声を取得
        accumulated_audio = buffer.get_accumulated_audio()
        if not accumulated_audio:
            logger.warning(f"⚠️ 累積音声が空です: {session_id}")
            return

        # initial_promptを取得（前回の確定テキスト）
        initial_prompt = buffer.get_initial_prompt()

        # 文字起こし実行
        with monitor.measure("transcription"):
            text = await transcribe_async(
                accumulated_audio, suffix=".wav", initial_prompt=initial_prompt
            )

        transcription_time = monitor.get_last_measurement("transcription")
        logger.info(
            f"📝 累積文字起こし完了 ({transcription_time:.2f}秒, "
            f"{buffer.current_audio_duration:.1f}秒分): {text}"
        )

        # 無音の場合
        if not text:
            await ws_manager.send_json(
                session_id,
                {
                    "type": "transcription_update",
                    "chunk_id": chunk_id,
                    "transcription": {
                        "confirmed": buffer.confirmed_text,
                        "tentative": "",
                        "full_text": buffer.confirmed_text,
                    },
                    "hiragana": {
                        "confirmed": buffer.confirmed_hiragana,
                        "tentative": "",
                    },
                    "is_silent": True,
                },
            )
            return

        # NGワードフィルタリング
        if not is_valid_text(text):
            logger.warning(f"⚠️ 無効な内容検出: {text}")
            return

        # トリミング通知
        if should_trim:
            await ws_manager.send_json(
                session_id,
                {"type": "buffer_trim_start", "chunk_id": chunk_id, "message": "バッファ整理中..."}
            )

        # 差分抽出（ひらがな・翻訳はセッション終了時に一括処理）
        result = buffer.update_transcription(text, should_trim=should_trim)
        logger.info(
            f"📝 差分抽出完了: 確定={len(result.confirmed_text)}文字, 暫定={len(result.tentative_text)}文字"
        )

        if should_trim:
            await ws_manager.send_json(
                session_id,
                {"type": "buffer_trim_complete", "chunk_id": chunk_id, "message": "バッファ整理完了"}
            )

        # 処理時間
        total_time = time.time() - request_start_time

        # 結果を構築（文字起こしのみ）
        response_data = {
            "type": "transcription_update",
            "chunk_id": chunk_id,
            "transcription": {
                "confirmed": result.confirmed_text,
                "tentative": result.tentative_text,
                "full_text": result.full_text,
            },
            "performance": {
                "transcription_time": transcription_time,
                "normalization_time": 0.0,
                "translation_time": 0.0,
                "total_time": total_time,
                "accumulated_audio_seconds": buffer.current_audio_duration,
                "session_elapsed_seconds": buffer.session_elapsed_seconds,
            },
            "is_final": False,
        }

        # 結果を送信
        await ws_manager.send_json(session_id, response_data)

        logger.info(
            f"✅ 累積文字起こし送信完了: session={session_id}, "
            f"chunk={chunk_id}, time={total_time:.3f}秒"
        )

    except Exception as e:
        logger.exception(f"❌ 累積文字起こしエラー: {e}")
        await ws_manager.send_error(session_id, f"累積文字起こしエラー: {str(e)}")


async def finalize_cumulative_session(session_id: str, connection):
    """
    累積バッファセッションを終了し、最終結果を送信

    Args:
        session_id: セッションID
        connection: WebSocket接続情報
    """
    buffer = cumulative_buffers.get(session_id)
    if not buffer:
        logger.warning(f"⚠️ 累積バッファが見つかりません: {session_id}")
        return

    try:
        # 残りのチャンクがあれば最終処理
        if buffer.chunk_count % buffer.config.transcription_interval_chunks != 0:
            # 最後の文字起こしを実行
            await perform_cumulative_transcription(
                session_id=session_id,
                chunk_id=buffer.chunk_count,
                buffer=buffer,
                monitor=connection.monitor,
            )

        # 処理オプションを取得
        options = connection.processing_options

        # セッション終了、全テキストを確定
        final_result = buffer.finalize()

        # ひらがな正規化（オプション）: 確定テキスト全体を一括変換
        hiragana_confirmed = ""
        if options.get("hiragana", False) and final_result.confirmed_text:
            await ws_manager.send_progress(session_id, "normalizing", "ひらがな変換中...", 0)
            hiragana_confirmed = normalizer.to_hiragana(
                final_result.confirmed_text, keep_punctuation=False
            )
            logger.info(f"📝 ひらがな一括変換完了: {len(hiragana_confirmed)}文字")

        # 翻訳（オプション）: 確定テキスト全体を一括翻訳
        translated_confirmed = ""
        if options.get("translation", False) and final_result.confirmed_text:
            await ws_manager.send_progress(session_id, "translating", "翻訳中...", 0)
            translated_confirmed = await translate_async(final_result.confirmed_text)
            logger.info(f"🌐 最終翻訳完了: {len(translated_confirmed)}文字")

        # 要約（オプション）: 確定テキスト全体を一括要約
        summary_text = ""
        if options.get("summary", False) and final_result.confirmed_text:
            try:
                await ws_manager.send_progress(session_id, "summarizing", "要約中...", 0)
                from services.summarizer import summarize_text

                summary_text = await summarize_text(final_result.confirmed_text)
                logger.info(f"📋 要約完了: {len(summary_text)}文字")
            except Exception as e:
                logger.error(f"❌ 要約エラー（スキップ）: {e}")
                summary_text = ""

        # 最終結果を構築
        response_data = {
            "type": "session_end",
            "transcription": {
                "confirmed": final_result.confirmed_text,
                "tentative": "",
                "full_text": final_result.full_text,
            },
            "statistics": buffer.get_stats(),
            "session_elapsed_seconds": buffer.session_elapsed_seconds,
            "is_final": True,
        }

        # オプション処理結果を条件付きで追加
        if options.get("hiragana", False):
            response_data["hiragana"] = {
                "confirmed": hiragana_confirmed,
                "tentative": "",
            }

        if options.get("translation", False):
            response_data["translation"] = {
                "confirmed": translated_confirmed,
                "tentative": "",
            }

        if options.get("summary", False):
            response_data["summary"] = summary_text

        # 最終結果を送信
        await ws_manager.send_json(session_id, response_data)

        logger.info(
            f"🏁 累積バッファセッション終了: session={session_id}, "
            f"最終テキスト={len(final_result.confirmed_text)}文字"
        )

    except Exception as e:
        logger.exception(f"❌ セッション終了処理エラー: {e}")
        await ws_manager.send_error(session_id, f"セッション終了処理エラー: {str(e)}")


# 静的ファイル配信の設定
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"📁 静的ファイル配信を有効化: {static_dir}")

# サンプルファイル配信の設定
sample_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample")
if os.path.exists(sample_dir):
    app.mount("/sample", StaticFiles(directory=sample_dir), name="sample")
    logger.info(f"📁 サンプルファイル配信を有効化: {sample_dir}")


@app.get("/")
async def serve_web_ui():
    """Web UIのHTMLを返す"""
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return JSONResponse(
        status_code=200,
        content={
            "message": "Voice Analyzer API",
            "version": "1.0.0",
            "web_ui": "Web UIは /static/index.html を配置してください",
        },
    )
