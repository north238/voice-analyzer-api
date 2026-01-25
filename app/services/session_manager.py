from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import uuid
from utils.logger import logger


@dataclass
class ChunkData:
    """チャンクデータの構造"""

    chunk_id: int
    timestamp: float
    original_text: str
    hiragana_text: str
    translated_text: str
    processing_time: float


@dataclass
class Session:
    """セッションデータの構造"""

    session_id: str
    created_at: datetime
    last_updated: datetime
    chunks: List[ChunkData] = field(default_factory=list)
    total_chunks: int = 0

    def add_chunk(self, chunk_data: ChunkData):
        """チャンクを追加"""
        self.chunks.append(chunk_data)
        self.total_chunks += 1
        self.last_updated = datetime.now()

    def get_recent_chunks(self, limit: int = 10) -> List[ChunkData]:
        """最新のN件のチャンクを取得"""
        return self.chunks[-limit:] if len(self.chunks) > limit else self.chunks

    def get_context_text(self, limit: int = 3) -> str:
        """前のチャンクからの文脈テキストを取得（翻訳時の文脈として使用）"""
        recent = self.get_recent_chunks(limit)
        if not recent:
            return ""
        return " ".join([chunk.original_text for chunk in recent])

    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """セッションがタイムアウトしているか確認"""
        timeout_delta = timedelta(minutes=timeout_minutes)
        return datetime.now() - self.last_updated > timeout_delta


class SessionManager:
    """セッション管理クラス"""

    def __init__(self, timeout_minutes: int = 30, max_chunks_per_session: int = 100):
        self.sessions: Dict[str, Session] = {}
        self.timeout_minutes = timeout_minutes
        self.max_chunks_per_session = max_chunks_per_session
        logger.info(
            f"🔧 SessionManager初期化: タイムアウト={timeout_minutes}分, 最大チャンク数={max_chunks_per_session}"
        )

    def create_session(self, session_id: Optional[str] = None) -> str:
        """新規セッションを作成"""
        if session_id is None:
            session_id = str(uuid.uuid4())

        if session_id in self.sessions:
            logger.warning(f"⚠️ セッションID {session_id} は既に存在します")
            return session_id

        now = datetime.now()
        self.sessions[session_id] = Session(
            session_id=session_id,
            created_at=now,
            last_updated=now,
            chunks=[],
            total_chunks=0,
        )
        logger.info(f"✅ 新規セッション作成: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[Session]:
        """セッションを取得"""
        session = self.sessions.get(session_id)
        if session is None:
            logger.warning(f"⚠️ セッションID {session_id} が見つかりません")
            return None

        # 期限切れチェック
        if session.is_expired(self.timeout_minutes):
            logger.info(f"🗑️ セッション {session_id} は期限切れのため削除します")
            self.delete_session(session_id)
            return None

        return session

    def add_chunk_to_session(
        self,
        session_id: str,
        chunk_id: int,
        timestamp: float,
        original_text: str,
        hiragana_text: str,
        translated_text: str,
        processing_time: float,
    ) -> bool:
        """セッションにチャンクデータを追加"""
        session = self.get_session(session_id)
        if session is None:
            logger.error(
                f"❌ セッション {session_id} が見つからないためチャンク追加失敗"
            )
            return False

        # 最大チャンク数チェック
        if len(session.chunks) >= self.max_chunks_per_session:
            logger.warning(
                f"⚠️ セッション {session_id} が最大チャンク数に達しました。古いチャンクを削除します"
            )
            # 古いチャンクを削除（FIFOで半分削除）
            keep_count = self.max_chunks_per_session // 2
            session.chunks = session.chunks[-keep_count:]

        chunk_data = ChunkData(
            chunk_id=chunk_id,
            timestamp=timestamp,
            original_text=original_text,
            hiragana_text=hiragana_text,
            translated_text=translated_text,
            processing_time=processing_time,
        )
        session.add_chunk(chunk_data)
        logger.info(
            f"📝 セッション {session_id} にチャンク {chunk_id} を追加（合計: {session.total_chunks}チャンク）"
        )
        return True

    def delete_session(self, session_id: str) -> bool:
        """セッションを削除"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"🗑️ セッション {session_id} を削除しました")
            return True
        logger.warning(f"⚠️ セッション {session_id} が見つかりません")
        return False

    def cleanup_expired_sessions(self) -> int:
        """期限切れのセッションをクリーンアップ"""
        expired_sessions = [
            sid
            for sid, session in self.sessions.items()
            if session.is_expired(self.timeout_minutes)
        ]

        for session_id in expired_sessions:
            self.delete_session(session_id)

        if expired_sessions:
            logger.info(
                f"🧹 {len(expired_sessions)}個の期限切れセッションを削除しました"
            )

        return len(expired_sessions)

    def get_session_count(self) -> int:
        """現在のセッション数を取得"""
        return len(self.sessions)

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """セッション情報を取得"""
        session = self.get_session(session_id)
        if session is None:
            return None

        return {
            "session_id": session.session_id,
            "created_at": session.created_at.isoformat(),
            "last_updated": session.last_updated.isoformat(),
            "total_chunks": session.total_chunks,
            "chunks_in_memory": len(session.chunks),
        }


# シングルトンインスタンス
_session_manager_instance: Optional[SessionManager] = None


def get_session_manager(
    timeout_minutes: int = 30, max_chunks_per_session: int = 100
) -> SessionManager:
    """セッションマネージャーのシングルトンインスタンスを取得"""
    global _session_manager_instance
    if _session_manager_instance is None:
        _session_manager_instance = SessionManager(
            timeout_minutes=timeout_minutes,
            max_chunks_per_session=max_chunks_per_session,
        )
    return _session_manager_instance
