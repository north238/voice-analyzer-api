#!/usr/bin/env python3
"""
音声ファイルをチャンク分割してサーバーに送信するクライアント
"""

import argparse
import requests
import time
import uuid
from typing import Dict, List
from audio_input import split_audio_file


class ChunkTranslationClient:
    """チャンクベース翻訳クライアント"""

    def __init__(self, base_url: str = "http://localhost:5001"):
        self.base_url = base_url
        self.session_id = None
        self.chunk_results = []
        self.performance_data = []

    def send_chunk(
        self, audio_data: bytes, filename: str, chunk_id: int, is_final: bool = False
    ) -> Dict:
        """
        音声チャンクをサーバーに送信

        Args:
            audio_data: 音声データのバイト列
            filename: ファイル名
            chunk_id: チャンクID
            is_final: 最終チャンクかどうか

        Returns:
            Dict: サーバーからのレスポンス
        """
        url = f"{self.base_url}/translate-chunk"

        # マルチパートフォームデータの準備
        files = {"file": (filename, audio_data, "audio/wav")}
        data = {
            "chunk_id": chunk_id,
            "is_final": str(is_final).lower(),
        }

        # セッションIDがあれば追加
        if self.session_id:
            data["session_id"] = self.session_id

        # リクエスト送信
        start_time = time.time()
        response = requests.post(url, files=files, data=data)
        elapsed_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            # 初回レスポンスからセッションIDを取得
            if not self.session_id:
                self.session_id = result.get("session_id")
                print(f"\n🆔 セッションID: {self.session_id}\n")

            # パフォーマンスデータを記録
            self.performance_data.append(
                {
                    "chunk_id": chunk_id,
                    "request_time": elapsed_time,
                    "server_performance": result.get("performance", {}),
                }
            )

            return result
        else:
            print(f"❌ エラー: {response.status_code}")
            print(f"   レスポンス: {response.text}")
            raise Exception(f"チャンク送信失敗: {response.status_code}")

    def process_audio_file(
        self, file_path: str, chunk_duration: int = 3, show_details: bool = True
    ):
        """
        音声ファイルを処理

        Args:
            file_path: 音声ファイルのパス
            chunk_duration: チャンクの長さ（秒）
            show_details: 詳細情報を表示するか
        """
        print("=" * 70)
        print("🎤 チャンクベース音声翻訳クライアント")
        print("=" * 70)
        print(f"📁 音声ファイル: {file_path}")
        print(f"⏱️  チャンク長: {chunk_duration}秒")
        print(f"🌐 サーバーURL: {self.base_url}")
        print("=" * 70 + "\n")

        # 音声ファイルを分割
        chunks = split_audio_file(file_path, chunk_duration_seconds=chunk_duration)
        total_chunks = len(chunks)

        print(f"📤 {total_chunks}個のチャンクをサーバーに送信します...\n")

        # 各チャンクを送信
        for i, (audio_data, filename, chunk_id) in enumerate(chunks):
            is_final = i == total_chunks - 1

            print(f"📦 チャンク {chunk_id + 1}/{total_chunks} を送信中...")

            try:
                result = self.send_chunk(audio_data, filename, chunk_id, is_final)
                self.chunk_results.append(result)

                if show_details:
                    self._print_chunk_result(result)
                else:
                    print(f"   ✅ 処理完了\n")

            except Exception as e:
                print(f"   ❌ エラー: {e}\n")
                break

        # 最終統計を表示
        self._print_summary()

    def _print_chunk_result(self, result: Dict):
        """チャンク処理結果を表示"""
        status = result.get("status")
        chunk_id = result.get("chunk_id")
        results = result.get("results", {})
        performance = result.get("performance", {})
        context = result.get("context", {})

        if status == "success":
            print(f"   ✅ ステータス: {status}")
            print(f"   📝 元テキスト: {results.get('original_text', '')[:50]}...")
            print(f"   🔤 ひらがな: {results.get('hiragana_text', '')[:50]}...")
            print(f"   🌐 翻訳: {results.get('translated_text', '')[:50]}...")
            print(f"   ⏱️  処理時間: {performance.get('total_time', 0):.3f}秒")
            print(
                f"   📊 累計チャンク: {context.get('total_chunks', 0)}個"
            )
            print()
        else:
            print(f"   ❌ エラー: {result.get('message', 'Unknown error')}")
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
        print(f"総処理時間: {total_request_time:.3f}秒")
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
                        if step != "total_time":
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


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="音声ファイルをチャンク分割して翻訳")
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
        default="http://localhost:5001",
        help="サーバーURL デフォルト: http://localhost:5001",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="詳細情報を非表示",
    )

    args = parser.parse_args()

    # クライアント実行
    client = ChunkTranslationClient(base_url=args.url)
    client.process_audio_file(
        file_path=args.file,
        chunk_duration=args.chunk_duration,
        show_details=not args.no_details,
    )


if __name__ == "__main__":
    main()
