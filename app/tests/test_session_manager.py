"""
セッション管理機能のテスト
"""

import pytest
import time
from datetime import datetime, timedelta
from app.services.session_manager import (
    SessionManager,
    Session,
    ChunkData,
    get_session_manager,
)


class TestChunkData:
    """ChunkDataクラスのテスト"""

    def test_chunk_data_creation(self):
        """ChunkDataの基本的な作成"""
        chunk = ChunkData(
            chunk_id=0,
            timestamp=1234567890.0,
            original_text="こんにちは",
            hiragana_text="こんにちは",
            translated_text="Hello",
            processing_time=1.5,
        )
        assert chunk.chunk_id == 0
        assert chunk.timestamp == 1234567890.0
        assert chunk.original_text == "こんにちは"
        assert chunk.hiragana_text == "こんにちは"
        assert chunk.translated_text == "Hello"
        assert chunk.processing_time == 1.5


class TestSession:
    """Sessionクラスのテスト"""

    @pytest.fixture
    def session(self):
        """テスト用セッションインスタンス"""
        return Session(
            session_id="test-session-123",
            created_at=datetime.now(),
            last_updated=datetime.now(),
            chunks=[],
            total_chunks=0,
        )

    @pytest.fixture
    def sample_chunk(self):
        """テスト用チャンクデータ"""
        return ChunkData(
            chunk_id=0,
            timestamp=time.time(),
            original_text="今日は良い天気です",
            hiragana_text="きょうはよいてんきです",
            translated_text="It's a nice weather today",
            processing_time=2.0,
        )

    # ========================================
    # add_chunk のテスト
    # ========================================

    def test_add_chunk_basic(self, session, sample_chunk):
        """基本的なチャンク追加"""
        session.add_chunk(sample_chunk)
        assert len(session.chunks) == 1
        assert session.total_chunks == 1
        assert session.chunks[0] == sample_chunk

    def test_add_chunk_multiple(self, session):
        """複数チャンクの追加"""
        for i in range(5):
            chunk = ChunkData(
                chunk_id=i,
                timestamp=time.time(),
                original_text=f"テキスト{i}",
                hiragana_text=f"てきすと{i}",
                translated_text=f"Text{i}",
                processing_time=1.0,
            )
            session.add_chunk(chunk)

        assert len(session.chunks) == 5
        assert session.total_chunks == 5

    def test_add_chunk_updates_last_updated(self, session, sample_chunk):
        """チャンク追加時にlast_updatedが更新される"""
        old_updated = session.last_updated
        time.sleep(0.01)  # 時間差を作る
        session.add_chunk(sample_chunk)
        assert session.last_updated > old_updated

    # ========================================
    # get_recent_chunks のテスト
    # ========================================

    def test_get_recent_chunks_less_than_limit(self, session):
        """limit以下のチャンク数の場合"""
        for i in range(3):
            chunk = ChunkData(
                chunk_id=i,
                timestamp=time.time(),
                original_text=f"テキスト{i}",
                hiragana_text=f"てきすと{i}",
                translated_text=f"Text{i}",
                processing_time=1.0,
            )
            session.add_chunk(chunk)

        recent = session.get_recent_chunks(limit=10)
        assert len(recent) == 3

    def test_get_recent_chunks_more_than_limit(self, session):
        """limitを超えるチャンク数の場合"""
        for i in range(15):
            chunk = ChunkData(
                chunk_id=i,
                timestamp=time.time(),
                original_text=f"テキスト{i}",
                hiragana_text=f"てきすと{i}",
                translated_text=f"Text{i}",
                processing_time=1.0,
            )
            session.add_chunk(chunk)

        recent = session.get_recent_chunks(limit=10)
        assert len(recent) == 10
        # 最新のチャンク（ID: 5-14）が取得されることを確認
        assert recent[0].chunk_id == 5
        assert recent[-1].chunk_id == 14

    def test_get_recent_chunks_empty(self, session):
        """チャンクが空の場合"""
        recent = session.get_recent_chunks(limit=10)
        assert len(recent) == 0

    # ========================================
    # get_context_text のテスト
    # ========================================

    def test_get_context_text_basic(self, session):
        """基本的な文脈テキスト取得"""
        for i in range(5):
            chunk = ChunkData(
                chunk_id=i,
                timestamp=time.time(),
                original_text=f"テキスト{i}",
                hiragana_text=f"てきすと{i}",
                translated_text=f"Text{i}",
                processing_time=1.0,
            )
            session.add_chunk(chunk)

        context = session.get_context_text(limit=3)
        assert context == "テキスト2 テキスト3 テキスト4"

    def test_get_context_text_less_than_limit(self, session):
        """limit以下のチャンク数の場合"""
        for i in range(2):
            chunk = ChunkData(
                chunk_id=i,
                timestamp=time.time(),
                original_text=f"テキスト{i}",
                hiragana_text=f"てきすと{i}",
                translated_text=f"Text{i}",
                processing_time=1.0,
            )
            session.add_chunk(chunk)

        context = session.get_context_text(limit=5)
        assert context == "テキスト0 テキスト1"

    def test_get_context_text_empty(self, session):
        """チャンクが空の場合"""
        context = session.get_context_text()
        assert context == ""

    # ========================================
    # is_expired のテスト
    # ========================================

    def test_is_expired_not_expired(self, session):
        """期限切れでない場合"""
        session.last_updated = datetime.now()
        assert session.is_expired(timeout_minutes=30) is False

    def test_is_expired_just_expired(self):
        """ちょうど期限切れの場合"""
        session = Session(
            session_id="test-session",
            created_at=datetime.now(),
            last_updated=datetime.now() - timedelta(minutes=30, seconds=1),
            chunks=[],
            total_chunks=0,
        )
        assert session.is_expired(timeout_minutes=30) is True

    def test_is_expired_old_session(self):
        """古いセッションの場合"""
        session = Session(
            session_id="test-session",
            created_at=datetime.now(),
            last_updated=datetime.now() - timedelta(hours=2),
            chunks=[],
            total_chunks=0,
        )
        assert session.is_expired(timeout_minutes=30) is True

    def test_is_expired_custom_timeout(self, session):
        """カスタムタイムアウト値"""
        session.last_updated = datetime.now() - timedelta(minutes=5)
        assert session.is_expired(timeout_minutes=10) is False
        assert session.is_expired(timeout_minutes=3) is True


class TestSessionManager:
    """SessionManagerクラスのテスト"""

    @pytest.fixture
    def manager(self):
        """テスト用SessionManagerインスタンス（各テストで独立）"""
        return SessionManager(timeout_minutes=30, max_chunks_per_session=100)

    # ========================================
    # create_session のテスト
    # ========================================

    def test_create_session_auto_uuid(self, manager):
        """自動UUID生成でのセッション作成"""
        session_id = manager.create_session()
        assert session_id is not None
        assert len(session_id) == 36  # UUID形式
        assert session_id in manager.sessions

    def test_create_session_with_custom_id(self, manager):
        """カスタムIDでのセッション作成"""
        custom_id = "my-custom-session-id"
        session_id = manager.create_session(session_id=custom_id)
        assert session_id == custom_id
        assert custom_id in manager.sessions

    def test_create_session_duplicate_id(self, manager):
        """既存のセッションIDで再作成"""
        session_id = manager.create_session(session_id="duplicate-id")
        session_id2 = manager.create_session(session_id="duplicate-id")
        assert session_id == session_id2
        assert manager.get_session_count() == 1

    def test_create_session_initializes_fields(self, manager):
        """セッション作成時のフィールド初期化確認"""
        session_id = manager.create_session()
        session = manager.sessions[session_id]
        assert session.session_id == session_id
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_updated, datetime)
        assert session.chunks == []
        assert session.total_chunks == 0

    # ========================================
    # get_session のテスト
    # ========================================

    def test_get_session_exists(self, manager):
        """存在するセッションの取得"""
        session_id = manager.create_session()
        session = manager.get_session(session_id)
        assert session is not None
        assert session.session_id == session_id

    def test_get_session_not_exists(self, manager):
        """存在しないセッションの取得"""
        session = manager.get_session("non-existent-id")
        assert session is None

    def test_get_session_expired_auto_delete(self):
        """期限切れセッションの自動削除"""
        manager = SessionManager(timeout_minutes=0)  # タイムアウト0分
        session_id = manager.create_session()

        # last_updatedを過去に設定
        manager.sessions[session_id].last_updated = datetime.now() - timedelta(
            minutes=1
        )

        # 取得時に自動削除される
        session = manager.get_session(session_id)
        assert session is None
        assert session_id not in manager.sessions

    # ========================================
    # add_chunk_to_session のテスト
    # ========================================

    def test_add_chunk_to_session_success(self, manager):
        """正常なチャンク追加"""
        session_id = manager.create_session()
        result = manager.add_chunk_to_session(
            session_id=session_id,
            chunk_id=0,
            timestamp=time.time(),
            original_text="こんにちは",
            hiragana_text="こんにちは",
            translated_text="Hello",
            processing_time=1.5,
        )
        assert result is True
        session = manager.get_session(session_id)
        assert len(session.chunks) == 1
        assert session.total_chunks == 1

    def test_add_chunk_to_session_not_found(self, manager):
        """存在しないセッションへのチャンク追加"""
        result = manager.add_chunk_to_session(
            session_id="non-existent",
            chunk_id=0,
            timestamp=time.time(),
            original_text="テスト",
            hiragana_text="てすと",
            translated_text="Test",
            processing_time=1.0,
        )
        assert result is False

    def test_add_chunk_exceeds_max_chunks(self):
        """最大チャンク数を超えた場合のFIFO削除"""
        manager = SessionManager(timeout_minutes=30, max_chunks_per_session=10)
        session_id = manager.create_session()

        # 15個のチャンクを追加
        for i in range(15):
            manager.add_chunk_to_session(
                session_id=session_id,
                chunk_id=i,
                timestamp=time.time(),
                original_text=f"テキスト{i}",
                hiragana_text=f"てきすと{i}",
                translated_text=f"Text{i}",
                processing_time=1.0,
            )

        session = manager.get_session(session_id)
        # 最大10個を超えたら半分（5個）削除される
        # 11個目追加時: 10個 → 5個に削除 → 11個目追加 = 6個
        # 12個目追加時: 6個 → そのまま → 7個
        # 13個目追加時: 7個 → そのまま → 8個
        # 14個目追加時: 8個 → そのまま → 9個
        # 15個目追加時: 9個 → そのまま → 10個
        # 最終的に10個のチャンク（ID: 5-14）が保持される
        assert len(session.chunks) == 10
        # 古いチャンク（ID: 0-4）が削除されていることを確認
        assert session.chunks[0].chunk_id == 5
        assert session.chunks[-1].chunk_id == 14

    def test_add_chunk_updates_total_chunks(self, manager):
        """total_chunksは削除されても累積カウント"""
        manager = SessionManager(timeout_minutes=30, max_chunks_per_session=5)
        session_id = manager.create_session()

        for i in range(10):
            manager.add_chunk_to_session(
                session_id=session_id,
                chunk_id=i,
                timestamp=time.time(),
                original_text=f"テキスト{i}",
                hiragana_text=f"てきすと{i}",
                translated_text=f"Text{i}",
                processing_time=1.0,
            )

        session = manager.get_session(session_id)
        # chunksは制限されるが、total_chunksは累積
        assert len(session.chunks) <= 5
        assert session.total_chunks == 10

    # ========================================
    # delete_session のテスト
    # ========================================

    def test_delete_session_exists(self, manager):
        """存在するセッションの削除"""
        session_id = manager.create_session()
        result = manager.delete_session(session_id)
        assert result is True
        assert session_id not in manager.sessions

    def test_delete_session_not_exists(self, manager):
        """存在しないセッションの削除"""
        result = manager.delete_session("non-existent")
        assert result is False

    # ========================================
    # cleanup_expired_sessions のテスト
    # ========================================

    def test_cleanup_expired_sessions_none_expired(self, manager):
        """期限切れセッションがない場合"""
        manager.create_session()
        manager.create_session()
        count = manager.cleanup_expired_sessions()
        assert count == 0
        assert manager.get_session_count() == 2

    def test_cleanup_expired_sessions_some_expired(self):
        """一部のセッションが期限切れ"""
        manager = SessionManager(timeout_minutes=1)
        # 新しいセッション
        new_id = manager.create_session()
        # 古いセッション
        old_id = manager.create_session()
        manager.sessions[old_id].last_updated = datetime.now() - timedelta(minutes=2)

        count = manager.cleanup_expired_sessions()
        assert count == 1
        assert new_id in manager.sessions
        assert old_id not in manager.sessions

    def test_cleanup_expired_sessions_all_expired(self):
        """全セッションが期限切れ"""
        manager = SessionManager(timeout_minutes=1)
        id1 = manager.create_session()
        id2 = manager.create_session()
        id3 = manager.create_session()

        # すべて期限切れに設定
        for sid in [id1, id2, id3]:
            manager.sessions[sid].last_updated = datetime.now() - timedelta(minutes=2)

        count = manager.cleanup_expired_sessions()
        assert count == 3
        assert manager.get_session_count() == 0

    # ========================================
    # get_session_count のテスト
    # ========================================

    def test_get_session_count_zero(self, manager):
        """セッションが0個の場合"""
        assert manager.get_session_count() == 0

    def test_get_session_count_multiple(self, manager):
        """複数セッションの場合"""
        manager.create_session()
        manager.create_session()
        manager.create_session()
        assert manager.get_session_count() == 3

    def test_get_session_count_after_delete(self, manager):
        """削除後のカウント"""
        id1 = manager.create_session()
        id2 = manager.create_session()
        manager.delete_session(id1)
        assert manager.get_session_count() == 1

    # ========================================
    # get_session_info のテスト
    # ========================================

    def test_get_session_info_exists(self, manager):
        """存在するセッションの情報取得"""
        session_id = manager.create_session()
        manager.add_chunk_to_session(
            session_id=session_id,
            chunk_id=0,
            timestamp=time.time(),
            original_text="テスト",
            hiragana_text="てすと",
            translated_text="Test",
            processing_time=1.0,
        )

        info = manager.get_session_info(session_id)
        assert info is not None
        assert info["session_id"] == session_id
        assert "created_at" in info
        assert "last_updated" in info
        assert info["total_chunks"] == 1
        assert info["chunks_in_memory"] == 1

    def test_get_session_info_not_exists(self, manager):
        """存在しないセッションの情報取得"""
        info = manager.get_session_info("non-existent")
        assert info is None

    def test_get_session_info_format(self, manager):
        """情報のフォーマット確認"""
        session_id = manager.create_session()
        info = manager.get_session_info(session_id)

        # ISO形式の日時文字列であることを確認
        assert isinstance(info["created_at"], str)
        assert isinstance(info["last_updated"], str)
        # ISO形式パース可能
        datetime.fromisoformat(info["created_at"])
        datetime.fromisoformat(info["last_updated"])

    # ========================================
    # パラメータ化テスト
    # ========================================

    @pytest.mark.parametrize(
        "timeout_minutes,max_chunks",
        [
            (10, 50),
            (30, 100),
            (60, 200),
            (5, 10),
        ],
    )
    def test_manager_initialization_params(self, timeout_minutes, max_chunks):
        """SessionManagerの初期化パラメータテスト"""
        manager = SessionManager(
            timeout_minutes=timeout_minutes, max_chunks_per_session=max_chunks
        )
        assert manager.timeout_minutes == timeout_minutes
        assert manager.max_chunks_per_session == max_chunks

    @pytest.mark.parametrize(
        "chunk_count,expected_in_memory",
        [
            (3, 3),  # 最大値以下
            (10, 10),  # ちょうど最大値
            (15, 10),  # 超過（11個目で半分削除 → 6個、その後4個追加して10個に到達）
        ],
    )
    def test_chunk_limit_behavior(self, chunk_count, expected_in_memory):
        """チャンク数制限の動作パラメータ化テスト"""
        manager = SessionManager(timeout_minutes=30, max_chunks_per_session=10)
        session_id = manager.create_session()

        for i in range(chunk_count):
            manager.add_chunk_to_session(
                session_id=session_id,
                chunk_id=i,
                timestamp=time.time(),
                original_text=f"テキスト{i}",
                hiragana_text=f"てきすと{i}",
                translated_text=f"Text{i}",
                processing_time=1.0,
            )

        session = manager.get_session(session_id)
        assert len(session.chunks) == expected_in_memory
        assert session.total_chunks == chunk_count


class TestGetSessionManager:
    """get_session_manager関数のテスト"""

    def test_get_session_manager_singleton(self):
        """シングルトンパターンの動作確認"""
        # グローバルインスタンスをリセット（テスト用）
        import app.services.session_manager as sm

        sm._session_manager_instance = None

        manager1 = get_session_manager()
        manager2 = get_session_manager()
        assert manager1 is manager2

    def test_get_session_manager_with_params(self):
        """パラメータ付きでの取得（初回のみ反映）"""
        import app.services.session_manager as sm

        sm._session_manager_instance = None

        manager = get_session_manager(timeout_minutes=60, max_chunks_per_session=200)
        assert manager.timeout_minutes == 60
        assert manager.max_chunks_per_session == 200


# ========================================
# 統合テスト
# ========================================


class TestSessionManagerIntegration:
    """SessionManagerの統合テスト"""

    def test_full_workflow(self):
        """セッション管理の完全なワークフロー"""
        manager = SessionManager(timeout_minutes=30, max_chunks_per_session=100)

        # 1. セッション作成
        session_id = manager.create_session()
        assert manager.get_session_count() == 1

        # 2. チャンク追加
        for i in range(5):
            manager.add_chunk_to_session(
                session_id=session_id,
                chunk_id=i,
                timestamp=time.time(),
                original_text=f"今日は良い天気です{i}",
                hiragana_text=f"きょうはよいてんきです{i}",
                translated_text=f"It's a nice weather today {i}",
                processing_time=1.5,
            )

        # 3. セッション情報取得
        info = manager.get_session_info(session_id)
        assert info["total_chunks"] == 5
        assert info["chunks_in_memory"] == 5

        # 4. セッション取得と文脈確認
        session = manager.get_session(session_id)
        context = session.get_context_text(limit=3)
        assert "今日は良い天気です" in context

        # 5. セッション削除
        manager.delete_session(session_id)
        assert manager.get_session_count() == 0

    def test_multiple_sessions_concurrent(self):
        """複数セッションの同時管理"""
        manager = SessionManager()

        # 3つのセッションを作成
        session_ids = [manager.create_session() for _ in range(3)]

        # 各セッションにチャンク追加
        for i, session_id in enumerate(session_ids):
            for j in range(i + 1):  # セッションごとに異なるチャンク数
                manager.add_chunk_to_session(
                    session_id=session_id,
                    chunk_id=j,
                    timestamp=time.time(),
                    original_text=f"セッション{i}-チャンク{j}",
                    hiragana_text=f"せっしょん{i}-ちゃんく{j}",
                    translated_text=f"Session{i}-Chunk{j}",
                    processing_time=1.0,
                )

        # セッション数確認
        assert manager.get_session_count() == 3

        # 各セッションのチャンク数確認
        for i, session_id in enumerate(session_ids):
            session = manager.get_session(session_id)
            assert len(session.chunks) == i + 1


if __name__ == "__main__":
    # このファイルを直接実行してテスト
    pytest.main([__file__, "-v"])
