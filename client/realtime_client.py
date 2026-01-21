"""
リアルタイム音声翻訳クライアント（Phase 3.1）

マイク入力 → WebSocket送信 → リアルタイム翻訳結果受信
"""

import asyncio
import websockets
import json
import logging
import argparse
import sys
from typing import Optional
from datetime import datetime
from audio_capture import AudioCapture, AudioConfig, list_audio_devices

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class RealtimeTranslationClient:
    """
    リアルタイム音声翻訳クライアント

    使用例:
        client = RealtimeTranslationClient("ws://localhost:5001/ws/translate-stream")
        await client.run(chunk_duration=3.0)
    """

    def __init__(self, url: str, device_index: Optional[int] = None):
        self.url = url
        self.device_index = device_index
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.session_id: Optional[str] = None
        self.chunk_count = 0
        self.is_running = False

        # パフォーマンス統計
        self.total_processing_time = 0.0
        self.chunk_times = []

    async def run(self, chunk_duration: float = 3.0):
        """
        リアルタイム翻訳セッションを開始

        Args:
            chunk_duration: チャンク長（秒）
        """
        logger.info("=== リアルタイム音声翻訳クライアント起動 ===")
        logger.info(f"接続先: {self.url}")
        logger.info(f"チャンク長: {chunk_duration}秒")

        try:
            # WebSocket接続
            async with websockets.connect(self.url) as websocket:
                self.websocket = websocket
                logger.info("WebSocket接続成功")

                # 接続確認メッセージ受信
                message = await websocket.recv()
                data = json.loads(message)
                if data["type"] == "connected":
                    self.session_id = data["session_id"]
                    logger.info(f"セッション開始: {self.session_id}")

                # 音声キャプチャ設定
                config = AudioConfig(chunk_duration=chunk_duration)
                capture = AudioCapture(config)

                # 受信タスクと送信タスクを並列実行
                self.is_running = True

                receive_task = asyncio.create_task(self._receive_loop())
                capture_task = asyncio.create_task(
                    self._capture_loop(capture)
                )

                # Ctrl+Cで停止
                try:
                    print("\n🎤 録音開始！話してください...")
                    print("Ctrl+C で停止\n")
                    await asyncio.gather(receive_task, capture_task)
                except KeyboardInterrupt:
                    logger.info("ユーザーによる停止")
                finally:
                    self.is_running = False
                    capture.close()

                    # 終了メッセージ送信
                    await websocket.send(json.dumps({"type": "end"}))

                    # 統計情報表示
                    self._print_statistics()

        except Exception as e:
            logger.error(f"エラー: {e}", exc_info=True)

    async def _capture_loop(self, capture: AudioCapture):
        """音声キャプチャループ（別スレッドで実行）"""
        loop = asyncio.get_event_loop()

        def on_chunk(audio_data: bytes):
            """チャンク受信時のコールバック"""
            if self.is_running:
                asyncio.run_coroutine_threadsafe(
                    self._send_chunk(audio_data),
                    loop
                )

        # ブロッキング処理を別スレッドで実行
        await loop.run_in_executor(
            None,
            lambda: self._start_capture(capture, on_chunk)
        )

    def _start_capture(self, capture: AudioCapture, on_chunk):
        """音声キャプチャを開始（ブロッキング）"""
        try:
            capture.start(on_chunk, device_index=self.device_index)
            # is_runningがFalseになるまで待機
            while self.is_running:
                import time
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"キャプチャエラー: {e}")
        finally:
            capture.stop()

    async def _send_chunk(self, audio_data: bytes):
        """音声チャンクをWebSocketで送信"""
        if not self.websocket:
            return

        try:
            self.chunk_count += 1
            chunk_start = datetime.now()

            logger.info(f"チャンク#{self.chunk_count} 送信中... ({len(audio_data)} bytes)")
            await self.websocket.send(audio_data)

            # 送信時刻を記録（レスポンス時間計測用）
            self.chunk_times.append({
                "chunk_id": self.chunk_count,
                "sent_at": chunk_start
            })

        except Exception as e:
            logger.error(f"送信エラー: {e}")

    async def _receive_loop(self):
        """WebSocketメッセージ受信ループ"""
        try:
            while self.is_running:
                message = await self.websocket.recv()
                data = json.loads(message)

                await self._handle_message(data)

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket接続終了")
        except Exception as e:
            logger.error(f"受信エラー: {e}")

    async def _handle_message(self, data: dict):
        """受信メッセージの処理"""
        msg_type = data.get("type")

        if msg_type == "progress":
            # 進捗通知
            step = data.get("step")
            message = data.get("message", "")
            logger.info(f"  [{step}] {message}")

        elif msg_type == "result":
            # 翻訳結果
            chunk_id = data.get("chunk_id")
            results = data.get("results", {})
            performance = data.get("performance", {})

            # 処理時間計算
            chunk_info = next(
                (c for c in self.chunk_times if c["chunk_id"] == chunk_id),
                None
            )
            if chunk_info:
                elapsed = (datetime.now() - chunk_info["sent_at"]).total_seconds()
                self.total_processing_time += elapsed

            print(f"\n{'='*60}")
            print(f"チャンク#{chunk_id} 結果")
            print(f"{'='*60}")
            print(f"📝 文字起こし: {results.get('original_text', '')}")
            print(f"🔤 ひらがな  : {results.get('hiragana_text', '')}")
            print(f"🌍 翻訳      : {results.get('translated_text', '')}")
            print(f"\n⏱️  処理時間:")
            print(f"  - 文字起こし: {performance.get('transcription_time', 0):.2f}秒")
            print(f"  - 正規化    : {performance.get('normalization_time', 0):.2f}秒")
            print(f"  - 翻訳      : {performance.get('translation_time', 0):.2f}秒")
            print(f"  - 合計      : {performance.get('total_time', 0):.2f}秒")
            if chunk_info:
                print(f"  - レイテンシ: {elapsed:.2f}秒（送信〜受信）")
            print(f"{'='*60}\n")

        elif msg_type == "error":
            # エラー
            error_msg = data.get("message", "不明なエラー")
            logger.error(f"❌ サーバーエラー: {error_msg}")

        elif msg_type == "session_end":
            # セッション終了
            total_chunks = data.get("total_chunks", 0)
            logger.info(f"セッション終了（合計 {total_chunks} チャンク）")

    def _print_statistics(self):
        """統計情報を表示"""
        if self.chunk_count == 0:
            return

        avg_time = self.total_processing_time / self.chunk_count

        print("\n" + "="*60)
        print("📊 処理統計")
        print("="*60)
        print(f"合計チャンク数  : {self.chunk_count}")
        print(f"平均処理時間    : {avg_time:.2f}秒/チャンク")
        print(f"合計処理時間    : {self.total_processing_time:.2f}秒")
        print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="リアルタイム音声翻訳クライアント（Phase 3.1）"
    )
    parser.add_argument(
        "--url",
        default="ws://localhost:5001/ws/translate-stream",
        help="WebSocketサーバーURL（デフォルト: ws://localhost:5001/ws/translate-stream）"
    )
    parser.add_argument(
        "--chunk-duration",
        type=float,
        default=3.0,
        help="チャンク長（秒）（デフォルト: 3.0）"
    )
    parser.add_argument(
        "--device",
        type=int,
        default=None,
        help="使用する音声デバイスのインデックス（デフォルト: システムデフォルト）"
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="利用可能な音声デバイスを表示して終了"
    )

    args = parser.parse_args()

    # デバイス一覧表示
    if args.list_devices:
        list_audio_devices()
        sys.exit(0)

    # クライアント起動
    client = RealtimeTranslationClient(args.url, device_index=args.device)

    try:
        asyncio.run(client.run(chunk_duration=args.chunk_duration))
    except KeyboardInterrupt:
        logger.info("終了します")


if __name__ == "__main__":
    main()
