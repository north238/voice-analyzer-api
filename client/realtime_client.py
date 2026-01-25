"""
リアルタイム音声翻訳クライアント（Phase 3.2 + 累積バッファ対応）

マイク入力 → WebSocket送信 → リアルタイム翻訳結果受信
Phase 3.2ではVAD（Voice Activity Detection）による動的チャンク分割と音量メーターを追加。
Phase 5では累積バッファ方式によるリアルタイム文字起こしを追加。
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


def create_volume_meter(volume_db: float, is_speech: bool, width: int = 30) -> str:
    """
    音量メーターを生成

    Args:
        volume_db: 音量レベル（dB）-60〜0
        is_speech: 発話中かどうか
        width: メーターの幅

    Returns:
        音量メーター文字列
    """
    # -60dB〜0dBを0〜1に正規化
    normalized = (volume_db + 60) / 60
    normalized = max(0.0, min(1.0, normalized))

    # メーターの長さ
    filled = int(normalized * width)

    # 発話状態に応じた色/記号
    if is_speech:
        bar = '█' * filled + '░' * (width - filled)
        status = '🎤'
    else:
        bar = '▓' * filled + '░' * (width - filled)
        status = '🔇'

    return f"{status} [{bar}] {volume_db:5.1f}dB"


class RealtimeTranslationClient:
    """
    リアルタイム音声翻訳クライアント（Phase 3.2 + 累積バッファ対応）

    使用例:
        client = RealtimeTranslationClient("ws://localhost:5001/ws/translate-stream")
        await client.run(chunk_duration=3.0)

    使用例（VADモード）:
        client = RealtimeTranslationClient("ws://localhost:5001/ws/translate-stream")
        await client.run(enable_vad=True, silence_duration_ms=500)

    使用例（累積バッファモード）:
        client = RealtimeTranslationClient("ws://localhost:5001/ws/transcribe-stream-cumulative")
        await client.run(cumulative_mode=True)
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

        # 音量メーター表示用
        self.show_volume_meter = True
        self.last_volume_db = -60.0
        self.last_is_speech = False

        # 累積バッファモード用
        self.cumulative_mode = False
        self.confirmed_text = ""      # 確定テキスト
        self.tentative_text = ""      # 暫定テキスト
        self.confirmed_hiragana = ""  # 確定ひらがな
        self.tentative_hiragana = ""  # 暫定ひらがな

    async def run(
        self,
        chunk_duration: float = 3.0,
        enable_vad: bool = False,
        vad_aggressiveness: int = 2,
        silence_duration_ms: int = 500,
        min_chunk_duration_ms: int = 500,
        max_chunk_duration_ms: int = 10000,
        show_volume_meter: bool = True,
        cumulative_mode: bool = False
    ):
        """
        リアルタイム翻訳セッションを開始

        Args:
            chunk_duration: 固定チャンク長（秒）- VAD無効時に使用
            enable_vad: VAD有効化フラグ
            vad_aggressiveness: VAD感度（0-3、3が最も厳密）
            silence_duration_ms: 無音判定時間（ミリ秒）
            min_chunk_duration_ms: 最小チャンク長（ミリ秒）
            max_chunk_duration_ms: 最大チャンク長（ミリ秒）
            show_volume_meter: 音量メーター表示フラグ
            cumulative_mode: 累積バッファモード有効化フラグ
        """
        self.show_volume_meter = show_volume_meter
        self.cumulative_mode = cumulative_mode

        logger.info("=== リアルタイム音声翻訳クライアント起動 ===")
        logger.info(f"接続先: {self.url}")

        if cumulative_mode:
            logger.info("モード: 累積バッファ（リアルタイム文字起こし）")
        elif enable_vad:
            logger.info(f"モード: VAD（感度: {vad_aggressiveness}、無音閾値: {silence_duration_ms}ms）")
            logger.info(f"チャンク長: {min_chunk_duration_ms}ms〜{max_chunk_duration_ms}ms")
        else:
            logger.info(f"モード: 固定長（{chunk_duration}秒チャンク）")

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
                config = AudioConfig(
                    chunk_duration=chunk_duration,
                    enable_vad=enable_vad,
                    vad_aggressiveness=vad_aggressiveness,
                    silence_duration_ms=silence_duration_ms,
                    min_chunk_duration_ms=min_chunk_duration_ms,
                    max_chunk_duration_ms=max_chunk_duration_ms
                )
                capture = AudioCapture(config)

                # 受信タスクと送信タスクを並列実行
                self.is_running = True

                receive_task = asyncio.create_task(self._receive_loop())
                capture_task = asyncio.create_task(
                    self._capture_loop(capture)
                )

                # 音量メーター表示タスク（VADモード時のみ）
                volume_task = None
                if show_volume_meter:
                    volume_task = asyncio.create_task(self._volume_display_loop())

                # Ctrl+Cで停止
                try:
                    print("\n🎤 録音開始！話してください...")
                    if enable_vad:
                        print("（VADモード: 発話終了を検出して自動送信）")
                    print("Ctrl+C で停止\n")

                    tasks = [receive_task, capture_task]
                    if volume_task:
                        tasks.append(volume_task)
                    await asyncio.gather(*tasks)
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

        def on_volume_level(volume_db: float, is_speech: bool):
            """音量レベル受信時のコールバック"""
            self.last_volume_db = volume_db
            self.last_is_speech = is_speech

        # ブロッキング処理を別スレッドで実行
        await loop.run_in_executor(
            None,
            lambda: self._start_capture(capture, on_chunk, on_volume_level)
        )

    def _start_capture(self, capture: AudioCapture, on_chunk, on_volume_level):
        """音声キャプチャを開始（ブロッキング）"""
        try:
            capture.start(
                on_chunk,
                device_index=self.device_index,
                on_volume_level=on_volume_level
            )
            # is_runningがFalseになるまで待機
            while self.is_running:
                import time
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"キャプチャエラー: {e}")
        finally:
            capture.stop()

    async def _volume_display_loop(self):
        """音量メーター表示ループ"""
        try:
            while self.is_running:
                if self.show_volume_meter:
                    meter = create_volume_meter(
                        self.last_volume_db,
                        self.last_is_speech
                    )
                    # カーソルを行頭に戻して上書き
                    print(f"\r{meter}", end='', flush=True)
                await asyncio.sleep(0.05)  # 20fps
        except asyncio.CancelledError:
            pass
        finally:
            # 改行して次の出力に備える
            print()

    async def _send_chunk(self, audio_data: bytes):
        """音声チャンクをWebSocketで送信"""
        if not self.websocket:
            return

        try:
            self.chunk_count += 1
            chunk_start = datetime.now()

            # 音量メーター表示中は改行してからログ出力
            if self.show_volume_meter:
                print()  # 音量メーターの行を改行

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
            # 翻訳結果（従来モード）
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

        elif msg_type == "accumulating":
            # 累積中の通知（累積バッファモード）
            accumulated = data.get("accumulated_seconds", 0)
            until_transcription = data.get("chunks_until_transcription", 0)
            if until_transcription > 0:
                logger.info(f"📦 音声蓄積中... {accumulated:.1f}秒（残り{until_transcription}チャンクで処理）")

        elif msg_type == "transcription_update":
            # 累積バッファモードの文字起こし結果
            chunk_id = data.get("chunk_id")
            transcription = data.get("transcription", {})
            hiragana = data.get("hiragana", {})
            performance = data.get("performance", {})
            is_silent = data.get("is_silent", False)

            # 確定/暫定テキストを更新
            self.confirmed_text = transcription.get("confirmed", "")
            self.tentative_text = transcription.get("tentative", "")
            self.confirmed_hiragana = hiragana.get("confirmed", "")
            self.tentative_hiragana = hiragana.get("tentative", "")

            if is_silent:
                logger.info("🔇 無音区間")
                return

            # 処理時間計算
            chunk_info = next(
                (c for c in self.chunk_times if c["chunk_id"] == chunk_id),
                None
            )
            if chunk_info:
                elapsed = (datetime.now() - chunk_info["sent_at"]).total_seconds()
                self.total_processing_time += elapsed

            # リアルタイム文字起こし表示
            self._display_cumulative_result(performance)

        elif msg_type == "skipped":
            # 無音チャンクスキップ
            chunk_id = data.get("chunk_id")
            logger.info(f"チャンク#{chunk_id}: 無音のためスキップ")

        elif msg_type == "error":
            # エラー
            error_msg = data.get("message", "不明なエラー")
            logger.error(f"❌ サーバーエラー: {error_msg}")

        elif msg_type == "session_end":
            # セッション終了
            if self.cumulative_mode:
                # 累積バッファモードの最終結果
                transcription = data.get("transcription", {})
                hiragana = data.get("hiragana", {})
                statistics = data.get("statistics", {})

                self.confirmed_text = transcription.get("confirmed", "")
                self.confirmed_hiragana = hiragana.get("confirmed", "")

                print(f"\n{'='*60}")
                print("🏁 セッション終了 - 最終結果")
                print(f"{'='*60}")
                print(f"📝 確定テキスト:")
                print(f"   {self.confirmed_text}")
                print(f"\n🔤 ひらがな:")
                print(f"   {self.confirmed_hiragana}")
                print(f"\n📊 統計:")
                print(f"   - 処理チャンク数: {statistics.get('chunk_count', 0)}")
                print(f"   - 累積音声: {statistics.get('audio_duration_seconds', 0):.1f}秒")
                print(f"{'='*60}\n")
            else:
                total_chunks = data.get("total_chunks", 0)
                logger.info(f"セッション終了（合計 {total_chunks} チャンク）")

    def _display_cumulative_result(self, performance: dict):
        """累積バッファモードの結果を表示"""
        # 画面をクリアして最新の状態を表示
        print(f"\n{'='*60}")
        print("📝 リアルタイム文字起こし")
        print(f"{'='*60}")

        # 確定テキスト（白/通常色）
        if self.confirmed_text:
            print(f"✅ 確定: {self.confirmed_text}")

        # 暫定テキスト（グレー表示をシミュレート）
        if self.tentative_text:
            # ANSI エスケープコードでグレー表示
            print(f"⏳ 暫定: \033[90m{self.tentative_text}\033[0m")

        print(f"\n🔤 ひらがな:")
        if self.confirmed_hiragana:
            print(f"   確定: {self.confirmed_hiragana}")
        if self.tentative_hiragana:
            print(f"   暫定: \033[90m{self.tentative_hiragana}\033[0m")

        # パフォーマンス情報
        print(f"\n⏱️  処理時間:")
        print(f"   - 文字起こし: {performance.get('transcription_time', 0):.2f}秒")
        print(f"   - 累積音声: {performance.get('accumulated_audio_seconds', 0):.1f}秒")
        print(f"   - 合計: {performance.get('total_time', 0):.2f}秒")
        print(f"{'='*60}\n")

    def _print_statistics(self):
        """統計情報を表示"""
        if self.chunk_count == 0:
            return

        avg_time = self.total_processing_time / self.chunk_count if self.chunk_count > 0 else 0

        print("\n" + "="*60)
        print("📊 処理統計")
        print("="*60)
        print(f"合計チャンク数  : {self.chunk_count}")
        print(f"平均処理時間    : {avg_time:.2f}秒/チャンク")
        print(f"合計処理時間    : {self.total_processing_time:.2f}秒")
        print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="リアルタイム音声翻訳クライアント（Phase 3.2 + 累積バッファ対応）"
    )
    parser.add_argument(
        "--url",
        default=None,
        help="WebSocketサーバーURL（--cumulativeで自動設定）"
    )
    parser.add_argument(
        "--cumulative",
        action="store_true",
        help="累積バッファモード（リアルタイム文字起こし）を有効化"
    )
    parser.add_argument(
        "--chunk-duration",
        type=float,
        default=3.0,
        help="固定チャンク長（秒）- VAD無効時に使用（デフォルト: 3.0）"
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

    # VAD設定（Phase 3.2）
    parser.add_argument(
        "--enable-vad",
        action="store_true",
        help="VAD（Voice Activity Detection）を有効化"
    )
    parser.add_argument(
        "--vad-aggressiveness",
        type=int,
        default=2,
        choices=[0, 1, 2, 3],
        help="VAD感度（0-3、3が最も厳密、デフォルト: 2）"
    )
    parser.add_argument(
        "--silence-duration-ms",
        type=int,
        default=500,
        help="無音判定時間（ミリ秒、デフォルト: 500）"
    )
    parser.add_argument(
        "--min-chunk-duration-ms",
        type=int,
        default=500,
        help="最小チャンク長（ミリ秒、デフォルト: 500）"
    )
    parser.add_argument(
        "--max-chunk-duration-ms",
        type=int,
        default=10000,
        help="最大チャンク長（ミリ秒、デフォルト: 10000）"
    )
    parser.add_argument(
        "--no-volume-meter",
        action="store_true",
        help="音量メーター表示を無効化"
    )

    args = parser.parse_args()

    # デバイス一覧表示
    if args.list_devices:
        list_audio_devices()
        sys.exit(0)

    # URL設定（累積モードか通常モードかで自動設定）
    if args.url:
        url = args.url
    elif args.cumulative:
        url = "ws://localhost:5001/ws/transcribe-stream-cumulative"
    else:
        url = "ws://localhost:5001/ws/translate-stream"

    # クライアント起動
    client = RealtimeTranslationClient(url, device_index=args.device)

    try:
        asyncio.run(client.run(
            chunk_duration=args.chunk_duration,
            enable_vad=args.enable_vad,
            vad_aggressiveness=args.vad_aggressiveness,
            silence_duration_ms=args.silence_duration_ms,
            min_chunk_duration_ms=args.min_chunk_duration_ms,
            max_chunk_duration_ms=args.max_chunk_duration_ms,
            show_volume_meter=not args.no_volume_meter,
            cumulative_mode=args.cumulative
        ))
    except KeyboardInterrupt:
        logger.info("終了します")


if __name__ == "__main__":
    main()
