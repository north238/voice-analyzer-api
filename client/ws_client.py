#!/usr/bin/env python3
"""
WebSocketを使用した音声チャンクのストリーミング翻訳クライアント
"""

import argparse
import asyncio
import json
import time
from typing import Dict, List, Optional
from audio_input import split_audio_file

try:
    import websockets
except ImportError:
    print("❌ websocketsがインストールされていません")
    print("   pip install websockets>=12.0")
    exit(1)


class WebSocketTranslationClient:
    """WebSocketベースの翻訳クライアント"""

    def __init__(self, base_url: str = "ws://localhost:5001"):
        self.base_url = base_url
        self.session_id: Optional[str] = None
        self.chunk_results: List[Dict] = []
        self.performance_data: List[Dict] = []
        self.websocket = None

    async def connect(self) -> bool:
        """WebSocket接続を確立"""
        ws_url = f"{self.base_url}/ws/translate-stream"
        try:
            self.websocket = await websockets.connect(ws_url)
            # 接続確認メッセージを受信
            response = await self.websocket.recv()
            data = json.loads(response)

            if data.get("type") == "connected":
                self.session_id = data.get("session_id")
                print(f"\n🔌 WebSocket接続確立")
                print(f"🆔 セッションID: {self.session_id}\n")
                return True
            else:
                print(f"❌ 接続エラー: {data}")
                return False

        except Exception as e:
            print(f"❌ WebSocket接続失敗: {e}")
            return False

    async def disconnect(self):
        """WebSocket接続を切断"""
        if self.websocket:
            try:
                # 終了メッセージを送信
                await self.websocket.send(json.dumps({"type": "end"}))
                # 終了応答を待つ
                response = await asyncio.wait_for(
                    self.websocket.recv(), timeout=5.0
                )
                data = json.loads(response)
                if data.get("type") == "session_end":
                    print(f"\n🏁 セッション終了: 総チャンク数={data.get('total_chunks')}")

                await self.websocket.close()
            except Exception:
                pass
            finally:
                self.websocket = None

    async def send_chunk(
        self, audio_data: bytes, chunk_id: int, show_progress: bool = True
    ) -> Optional[Dict]:
        """
        音声チャンクをサーバーに送信

        Args:
            audio_data: 音声データのバイト列
            chunk_id: チャンクID
            show_progress: 進捗を表示するか

        Returns:
            Dict: サーバーからの結果（エラー時はNone）
        """
        if not self.websocket:
            print("❌ WebSocket未接続")
            return None

        start_time = time.time()

        try:
            # バイナリデータとして音声を送信
            await self.websocket.send(audio_data)

            # 進捗通知と結果を受信
            result = None
            while True:
                response = await asyncio.wait_for(
                    self.websocket.recv(), timeout=60.0
                )
                data = json.loads(response)
                msg_type = data.get("type")

                if msg_type == "progress":
                    if show_progress:
                        step = data.get("step", "")
                        message = data.get("message", "")
                        print(f"   ⏳ {step}: {message}")

                elif msg_type == "result":
                    elapsed_time = time.time() - start_time
                    result = data
                    result["_client_time"] = elapsed_time

                    # パフォーマンスデータを記録
                    self.performance_data.append({
                        "chunk_id": chunk_id,
                        "request_time": elapsed_time,
                        "server_performance": data.get("performance", {}),
                    })
                    self.chunk_results.append(result)
                    break

                elif msg_type == "error":
                    print(f"   ❌ エラー: {data.get('message')}")
                    break

            return result

        except asyncio.TimeoutError:
            print(f"   ❌ タイムアウト: チャンク {chunk_id}")
            return None
        except Exception as e:
            print(f"   ❌ 送信エラー: {e}")
            return None

    async def process_audio_file(
        self,
        file_path: str,
        chunk_duration: int = 3,
        show_details: bool = True,
    ):
        """
        音声ファイルを処理

        Args:
            file_path: 音声ファイルのパス
            chunk_duration: チャンクの長さ（秒）
            show_details: 詳細情報を表示するか
        """
        print("=" * 70)
        print("🎤 WebSocketストリーミング音声翻訳クライアント")
        print("=" * 70)
        print(f"📁 音声ファイル: {file_path}")
        print(f"⏱️  チャンク長: {chunk_duration}秒")
        print(f"🌐 サーバーURL: {self.base_url}")
        print("=" * 70)

        # WebSocket接続
        if not await self.connect():
            return

        try:
            # 音声ファイルを分割
            chunks = split_audio_file(file_path, chunk_duration_seconds=chunk_duration)
            total_chunks = len(chunks)

            print(f"\n📤 {total_chunks}個のチャンクをストリーミング送信します...\n")

            # 各チャンクを送信
            for i, (audio_data, filename, chunk_id) in enumerate(chunks):
                print(f"📦 チャンク {chunk_id + 1}/{total_chunks} を送信中...")

                result = await self.send_chunk(
                    audio_data, chunk_id, show_progress=show_details
                )

                if result and show_details:
                    self._print_chunk_result(result)
                elif result:
                    print(f"   ✅ 処理完了\n")

        finally:
            # 接続を切断
            await self.disconnect()

        # 最終統計を表示
        self._print_summary()

    def _print_chunk_result(self, result: Dict):
        """チャンク処理結果を表示"""
        results = result.get("results", {})
        performance = result.get("performance", {})
        client_time = result.get("_client_time", 0)

        print(f"   ✅ 処理完了")
        print(f"   📝 元テキスト: {results.get('original_text', '')[:50]}...")
        print(f"   🔤 ひらがな: {results.get('hiragana_text', '')[:50]}...")
        print(f"   🌐 翻訳: {results.get('translated_text', '')[:50]}...")
        print(f"   ⏱️  サーバー処理時間: {performance.get('total_time', 0):.3f}秒")
        print(f"   ⏱️  クライアント総時間: {client_time:.3f}秒")
        print()

    def _print_summary(self):
        """処理サマリーを表示"""
        if not self.performance_data:
            return

        print("\n" + "=" * 70)
        print("📊 処理サマリー")
        print("=" * 70)

        total_chunks = len(self.performance_data)
        total_request_time = sum(p["request_time"] for p in self.performance_data)
        avg_request_time = total_request_time / total_chunks if total_chunks > 0 else 0

        # サーバー側の処理時間集計
        total_server_time = sum(
            p["server_performance"].get("total_time", 0)
            for p in self.performance_data
        )
        avg_server_time = total_server_time / total_chunks if total_chunks > 0 else 0

        print(f"総チャンク数: {total_chunks}個")
        print(f"総処理時間（クライアント）: {total_request_time:.3f}秒")
        print(f"総処理時間（サーバー）: {total_server_time:.3f}秒")
        print(f"平均リクエスト時間: {avg_request_time:.3f}秒/チャンク")
        print(f"平均サーバー処理時間: {avg_server_time:.3f}秒/チャンク")
        print()

        # 各ステップの平均処理時間
        if self.performance_data:
            first_perf = self.performance_data[0]["server_performance"]
            if first_perf:
                print("各ステップの平均処理時間:")
                step_totals = {}
                for perf_data in self.performance_data:
                    server_perf = perf_data["server_performance"]
                    for step, duration in server_perf.items():
                        if step != "total_time" and isinstance(duration, (int, float)):
                            step_totals[step] = step_totals.get(step, 0) + duration

                for step, total in step_totals.items():
                    avg = total / total_chunks
                    print(f"  - {step}: {avg:.3f}秒")

        print("=" * 70 + "\n")

        # 全チャンクの翻訳結果を表示
        print("=" * 70)
        print("📄 全翻訳結果")
        print("=" * 70)
        for i, result in enumerate(self.chunk_results):
            results = result.get("results", {})
            print(f"\nチャンク {i}:")
            print(f"  日本語: {results.get('original_text', '')}")
            print(f"  英語: {results.get('translated_text', '')}")
        print("\n" + "=" * 70)


async def main_async():
    """非同期メイン関数"""
    parser = argparse.ArgumentParser(
        description="WebSocketで音声ファイルをストリーミング翻訳"
    )
    parser.add_argument("--file", "-f", required=True, help="音声ファイルのパス")
    parser.add_argument(
        "--chunk-duration",
        "-d",
        type=int,
        default=3,
        help="チャンクの長さ（秒）デフォルト: 3",
    )
    parser.add_argument(
        "--url",
        "-u",
        default="ws://localhost:5001",
        help="WebSocketサーバーURL デフォルト: ws://localhost:5001",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="詳細情報を非表示",
    )

    args = parser.parse_args()

    # クライアント実行
    client = WebSocketTranslationClient(base_url=args.url)
    await client.process_audio_file(
        file_path=args.file,
        chunk_duration=args.chunk_duration,
        show_details=not args.no_details,
    )


def main():
    """メイン関数"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()