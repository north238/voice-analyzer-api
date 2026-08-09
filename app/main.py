from fastapi import FastAPI, UploadFile, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from services.audio_processor import transcribe_audio
from services.text_filter import is_valid_text
from services.session_manager import get_session_manager
from services.websocket_manager import get_websocket_manager
from services.async_processor import transcribe_async
from services.cumulative_buffer import (
    CumulativeBuffer,
    CumulativeBufferConfig,
)
from utils.performance_monitor import PerformanceMonitor
from utils.logger import logger
from config import settings
import asyncio
import time
import json
import os
from typing import Optional, Dict
from pydantic import BaseModel

app = FastAPI()

# セッションマネージャーの初期化
session_manager = get_session_manager(
    timeout_minutes=settings.SESSION_TIMEOUT_MINUTES,
    max_chunks_per_session=settings.MAX_CHUNKS_PER_SESSION,
)

# WebSocketマネージャーの初期化
ws_manager = get_websocket_manager()

# 累積バッファの管理（セッションIDをキーにした辞書）
cumulative_buffers: Dict[str, CumulativeBuffer] = {}


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

                    if msg_type == "end":
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
            text, segments = await transcribe_async(
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
                {
                    "type": "buffer_trim_start",
                    "chunk_id": chunk_id,
                    "message": "バッファ整理中...",
                },
            )

        # 差分抽出（ひらがな・翻訳はセッション終了時に一括処理）
        result = buffer.update_transcription(
            text, should_trim=should_trim, segments=segments
        )
        logger.info(
            f"📝 差分抽出完了: 確定={len(result.confirmed_text)}文字, 暫定={len(result.tentative_text)}文字"
        )

        if should_trim:
            await ws_manager.send_json(
                session_id,
                {
                    "type": "buffer_trim_complete",
                    "chunk_id": chunk_id,
                    "message": "バッファ整理完了",
                },
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
                "confirmed_timestamp": result.confirmed_timestamp,
                "new_confirmed_segments": result.new_confirmed_segments,  # Phase 12.2
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

        # セッション終了、全テキストを確定
        final_result = buffer.finalize()

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

        await ws_manager.send_json(session_id, response_data)

        logger.info(
            f"🏁 累積バッファセッション終了: session={session_id}, "
            f"最終テキスト={len(final_result.confirmed_text)}文字"
        )

    except Exception as e:
        logger.exception(f"❌ セッション終了処理エラー: {e}")
        await ws_manager.send_error(session_id, f"セッション終了処理エラー: {str(e)}")


# サンプルファイル配信の設定
sample_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample")
if os.path.exists(sample_dir):
    app.mount("/sample", StaticFiles(directory=sample_dir), name="sample")
    logger.info(f"📁 サンプルファイル配信を有効化: {sample_dir}")
