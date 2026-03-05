"""
WebSocket接続マネージャー
WebSocket接続のライフサイクル管理と進捗通知を担当
"""

from fastapi import WebSocket
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import json

from utils.performance_monitor import PerformanceMonitor
from utils.logger import logger


@dataclass
class WebSocketConnection:
    """WebSocket接続の情報を保持するクラス"""

    websocket: WebSocket
    session_id: str
    monitor: PerformanceMonitor = field(default_factory=PerformanceMonitor)
    chunk_count: int = 0
    connected_at: datetime = field(default_factory=datetime.now)
    processing_options: dict = field(
        default_factory=lambda: {
            "hiragana": False,
            "translation": False,
            "summary": False,
        }
    )

    def increment_chunk(self) -> int:
        """チャンクカウントを増加させ、現在のカウントを返す"""
        current = self.chunk_count
        self.chunk_count += 1
        return current


class WebSocketManager:
    """WebSocket接続を管理するクラス"""

    def __init__(self):
        # session_id -> WebSocketConnection のマッピング
        self.connections: Dict[str, WebSocketConnection] = {}

    async def connect(
        self, websocket: WebSocket, session_id: Optional[str] = None
    ) -> WebSocketConnection:
        """
        WebSocket接続を受け付けて管理下に置く

        Args:
            websocket: FastAPIのWebSocketオブジェクト
            session_id: 既存のセッションID（省略時は新規生成）

        Returns:
            WebSocketConnection: 接続情報
        """
        await websocket.accept()

        # セッションIDがない場合は新規生成
        if session_id is None or session_id not in self.connections:
            session_id = str(uuid.uuid4())

        connection = WebSocketConnection(
            websocket=websocket,
            session_id=session_id,
        )
        self.connections[session_id] = connection

        logger.info(f"🔌 WebSocket接続確立: session_id={session_id}")

        # 接続確認メッセージを送信
        await self.send_json(
            session_id,
            {
                "type": "connected",
                "session_id": session_id,
                "message": "WebSocket接続が確立されました",
            },
        )

        return connection

    async def disconnect(self, session_id: str) -> None:
        """
        WebSocket接続を切断してクリーンアップ

        Args:
            session_id: 切断するセッションID
        """
        if session_id in self.connections:
            connection = self.connections[session_id]
            try:
                await connection.websocket.close()
            except Exception:
                pass  # 既に閉じている場合は無視
            del self.connections[session_id]
            logger.info(
                f"🔌 WebSocket接続切断: session_id={session_id}, "
                f"処理チャンク数={connection.chunk_count}"
            )

    def get_connection(self, session_id: str) -> Optional[WebSocketConnection]:
        """
        セッションIDから接続を取得

        Args:
            session_id: セッションID

        Returns:
            WebSocketConnection or None
        """
        return self.connections.get(session_id)

    async def send_json(self, session_id: str, data: dict) -> bool:
        """
        JSONデータを送信

        Args:
            session_id: 送信先のセッションID
            data: 送信するデータ

        Returns:
            bool: 送信成功かどうか
        """
        connection = self.get_connection(session_id)
        if connection is None:
            logger.warning(f"⚠️ [WS] send_json: セッション接続なし (session_id={session_id}, type={data.get('type')})")
            return False

        try:
            if connection.websocket.client_state.name != "CONNECTED":
                return False
            await connection.websocket.send_json(data)
            return True
        except Exception:
            # 切断済みの場合は静かに失敗
            return False

    async def send_progress(
        self, session_id: str, step: str, message: str, chunk_id: Optional[int] = None
    ) -> bool:
        """
        進捗通知を送信

        Args:
            session_id: 送信先のセッションID
            step: 処理ステップ名（transcribing, normalizing, translating, summarizing）
            message: 進捗メッセージ
            chunk_id: 処理中のチャンクID（オプション）

        Returns:
            bool: 送信成功かどうか
        """
        data = {
            "type": "progress",
            "step": step,
            "message": message,
        }
        if chunk_id is not None:
            data["chunk_id"] = chunk_id

        return await self.send_json(session_id, data)

    async def send_result(
        self,
        session_id: str,
        chunk_id: int,
        original_text: str,
        hiragana_text: str,
        translated_text: str,
        performance: dict,
    ) -> bool:
        """
        処理結果を送信

        Args:
            session_id: 送信先のセッションID
            chunk_id: チャンクID
            original_text: 元のテキスト
            hiragana_text: ひらがな変換後のテキスト
            translated_text: 翻訳後のテキスト
            performance: パフォーマンス情報

        Returns:
            bool: 送信成功かどうか
        """
        data = {
            "type": "result",
            "chunk_id": chunk_id,
            "results": {
                "original_text": original_text,
                "hiragana_text": hiragana_text,
                "translated_text": translated_text,
            },
            "performance": performance,
        }
        return await self.send_json(session_id, data)

    async def send_error(self, session_id: str, error_message: str) -> bool:
        """
        エラーメッセージを送信

        Args:
            session_id: 送信先のセッションID
            error_message: エラーメッセージ

        Returns:
            bool: 送信成功かどうか
        """
        data = {
            "type": "error",
            "message": error_message,
        }
        return await self.send_json(session_id, data)

    async def send_session_end(
        self, session_id: str, total_chunks: int, statistics: dict
    ) -> bool:
        """
        セッション終了通知を送信

        Args:
            session_id: 送信先のセッションID
            total_chunks: 処理した総チャンク数
            statistics: 統計情報

        Returns:
            bool: 送信成功かどうか
        """
        data = {
            "type": "session_end",
            "total_chunks": total_chunks,
            "statistics": statistics,
        }
        return await self.send_json(session_id, data)

    def get_active_connections_count(self) -> int:
        """アクティブな接続数を取得"""
        return len(self.connections)


# シングルトンインスタンス
_websocket_manager_instance: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """WebSocketマネージャーのシングルトンインスタンスを取得"""
    global _websocket_manager_instance
    if _websocket_manager_instance is None:
        _websocket_manager_instance = WebSocketManager()
    return _websocket_manager_instance
