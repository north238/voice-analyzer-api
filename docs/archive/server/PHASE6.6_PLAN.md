# Phase 6.6 実装計画: バッファトリミング時の文脈保持

## 概要

累積バッファのトリミング時に暫定テキストを確定テキストに強制移行することで、文脈喪失を防止する。

## 実装する機能

### 1. バッファトリミング時の強制確定機能（優先度：高）

#### 目的

- バッファトリミング前に暫定テキストを確定テキストに移行
- 音声データ削除による文脈喪失を完全に防止

#### 設計方針

**A. トリミング前コールバック方式**

`CumulativeBuffer`クラスにトリミング前のコールバック機能を追加。

```python
class CumulativeBuffer:
    def __init__(self, config: Optional[CumulativeBufferConfig] = None):
        ...
        # トリミング前コールバック
        self.on_before_trim_callback: Optional[Callable] = None

    def set_on_before_trim_callback(self, callback: Callable):
        """トリミング前に呼ばれるコールバックを設定"""
        self.on_before_trim_callback = callback

    def _trim_buffer_if_needed(self):
        """バッファが最大サイズを超えた場合、古いデータを削除"""
        if self.total_audio_bytes > self.max_audio_bytes and len(self.audio_chunks) > 1:
            # トリミング前に暫定テキストを確定に移行
            if self.on_before_trim_callback:
                self.on_before_trim_callback()

            # トリミング実行
            while (
                self.total_audio_bytes > self.max_audio_bytes
                and len(self.audio_chunks) > 1
            ):
                removed = self.audio_chunks.pop(0)
                self.total_audio_bytes -= len(removed)
                logger.debug(f"🗑️ 古いチャンク削除: 残り{self.current_audio_duration:.1f}秒")
```

**B. 強制確定メソッドの追加**

`CumulativeBuffer`に暫定テキストを確定に移行するメソッドを追加。

```python
def force_finalize_pending_text(self, hiragana_converter=None) -> bool:
    """
    暫定テキストを強制的に確定テキストに移行

    バッファトリミング時に呼ばれることを想定。
    Phase 6.5のfinalize()メソッドと同様のロジックを使用。

    Returns:
        bool: 確定テキストに移行したかどうか
    """
    if not self.last_transcription:
        return False

    # 確定済みテキストを除いた残り（暫定部分）
    remaining = self.last_transcription[len(self.confirmed_text):]

    if not remaining:
        return False

    # 暫定テキストを確定に追加
    self.confirmed_text += remaining

    # ひらがな変換も更新
    if hiragana_converter:
        self.confirmed_hiragana += hiragana_converter(remaining)

    logger.info(
        f"🔒 暫定テキストを強制確定（トリミング前）: "
        f"+{len(remaining)}文字, 合計{len(self.confirmed_text)}文字"
    )

    return True
```

**C. main.pyでのコールバック設定**

WebSocketエンドポイントでバッファ作成時にコールバックを設定。

```python
@app.websocket("/ws/transcribe-stream-cumulative")
async def websocket_transcribe_stream_cumulative(websocket: WebSocket):
    ...
    # 累積バッファを作成
    buffer_config = CumulativeBufferConfig(...)
    buffer = CumulativeBuffer(buffer_config)

    # 処理オプションを取得する関数
    def get_hiragana_converter():
        connection = ws_manager.connections.get(session_id)
        if connection and connection.processing_options.get("hiragana", False):
            return lambda t: normalizer.to_hiragana(t, keep_punctuation=False)
        return None

    # トリミング前コールバックを設定
    def on_before_trim():
        hiragana_conv = get_hiragana_converter()
        buffer.force_finalize_pending_text(hiragana_converter=hiragana_conv)

    buffer.set_on_before_trim_callback(on_before_trim)

    cumulative_buffers[session_id] = buffer
    ...
```

#### メリット

- 文脈喪失を完全に防止
- Phase 6.5の`finalize`メソッドのロジックを再利用
- 実装が明確でテストしやすい

#### デメリット

- まだ変わる可能性があるテキストを強制確定
- ただし、30秒経過時点では十分安定していると考えられる

#### 変更ファイル

- `app/services/cumulative_buffer.py`
  - `set_on_before_trim_callback()`メソッド追加
  - `force_finalize_pending_text()`メソッド追加
  - `_trim_buffer_if_needed()`メソッド修正
- `app/main.py`
  - `websocket_transcribe_stream_cumulative()`でコールバック設定

### 2. 確定しきい値の設定可能化（優先度：中）

#### 目的

- `stable_text_threshold`を設定ファイルで調整可能に
- より早く確定させることで文脈喪失リスクを減らす

#### 設計方針

**A. config.pyに設定追加**

```python
# 累積バッファ設定
CUMULATIVE_MAX_AUDIO_SECONDS: float = float(
    os.getenv("CUMULATIVE_MAX_AUDIO_SECONDS", "30.0")
)
CUMULATIVE_TRANSCRIPTION_INTERVAL: int = int(
    os.getenv("CUMULATIVE_TRANSCRIPTION_INTERVAL", "3")
)
CUMULATIVE_STABLE_THRESHOLD: int = int(
    os.getenv("CUMULATIVE_STABLE_THRESHOLD", "2")
)
```

**現状**: 既に設定は存在するが、`CumulativeBufferConfig`で使用されていない

**B. CumulativeBufferConfigで設定値を使用**

cumulative_buffer.py:

```python
@dataclass
class CumulativeBufferConfig:
    """累積バッファ設定"""

    max_audio_duration_seconds: float = 30.0
    transcription_interval_chunks: int = 3
    stable_text_threshold: int = 2  # ← この値をconfig.pyから取得
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2
```

main.py:

```python
buffer_config = CumulativeBufferConfig(
    max_audio_duration_seconds=settings.CUMULATIVE_MAX_AUDIO_SECONDS,
    transcription_interval_chunks=settings.CUMULATIVE_TRANSCRIPTION_INTERVAL,
    stable_text_threshold=settings.CUMULATIVE_STABLE_THRESHOLD,  # ← 追加
)
```

#### デフォルト値の検討

現在: `stable_text_threshold = 2`

**オプション1**: デフォルト値を1に変更

- メリット: より早く確定、文脈喪失リスク減少
- デメリット: 確定が早すぎると誤りが増える可能性

**オプション2**: デフォルト値を2のまま維持

- メリット: 既存の動作を維持、安定性重視
- デメリット: 文脈喪失リスクは変わらず

**推奨**: デフォルト値2のまま、環境変数で調整可能にする

#### 変更ファイル

- `app/config.py`: 設定追加（既存）
- `app/services/cumulative_buffer.py`: 既存の設定を使用するだけ（変更不要）
- `app/main.py`: バッファ作成時に設定を渡す

### 3. バッファサイズ動的調整（優先度：低、オプショナル）

#### 目的

- 発話速度や文脈の複雑さに応じてバッファサイズを調整
- より長い文脈を保持

#### 設計方針

**A. 動的調整アルゴリズム**

```python
@dataclass
class CumulativeBufferConfig:
    max_audio_duration_seconds: float = 30.0
    min_audio_duration_seconds: float = 30.0  # 最小バッファサイズ
    max_audio_duration_seconds_limit: float = 60.0  # 最大バッファサイズ
    dynamic_adjustment_enabled: bool = False  # 動的調整を有効化
```

動的調整ロジック:

1. 発話速度を計算（文字数/秒）
2. 発話速度が速い → バッファサイズを大きく
3. 発話速度が遅い → バッファサイズを小さく

**B. 問題点**

1. **Whisperの30秒制限**
   - Whisperは30秒を超えると幻覚（hallucination）のリスクが増加
   - 公式ドキュメントでも30秒を推奨
   - 60秒まで拡大すると精度低下の可能性

2. **メモリ使用量**
   - バッファサイズを大きくするとメモリ使用量が増加
   - Raspberry Piなどリソース制約環境での影響

3. **複雑性**
   - 発話速度の計算が不正確な場合、逆効果
   - テストケースが複雑になる

#### 結論

**この機能は実装を見送る**

理由:

- Phase 6.6の目的は「文脈喪失の防止」であり、バッファサイズ拡大は本質的な解決にならない
- Whisperの30秒制限を考慮すると、リスクが大きい
- 解決策1（強制確定）で文脈喪失は防止可能
- 必要性が出てきたら、Phase 7以降で検討

## 実装順序

### ステップ1: バッファトリミング時の強制確定機能（タスク3）

1. `cumulative_buffer.py`を修正
   - `set_on_before_trim_callback()`メソッド追加
   - `force_finalize_pending_text()`メソッド追加
   - `_trim_buffer_if_needed()`メソッド修正

2. `main.py`を修正
   - `websocket_transcribe_stream_cumulative()`でコールバック設定

### ステップ2: 確定しきい値の設定可能化（タスク4）

1. `main.py`を修正
   - バッファ作成時に`settings.CUMULATIVE_STABLE_THRESHOLD`を渡す

### ステップ3: テスト作成（タスク6）

1. 単体テスト
   - `tests/test_cumulative_buffer_trim.py`（新規）
     - トリミング時の強制確定動作確認
     - コールバックが正しく呼ばれるか
     - 確定テキストが正しく移行されるか

2. 統合テスト
   - `tests/integration/test_long_recording.py`（新規）
     - 30秒超過時の文脈保持確認
     - 60秒以上の長時間録音での動作確認

3. 既存テストの更新
   - `tests/test_session_manager.py`に追加テスト

### ステップ4: 実機テスト（タスク7）

1. Chrome拡張機能
   - YouTubeなどで60秒以上録音
   - 文脈が保持されることを確認

2. ブラウザUI
   - マイク入力で60秒以上録音
   - テキストファイル出力で全文確認

3. パフォーマンス測定
   - 処理時間の変化
   - メモリ使用量の確認

## 期待される効果

### Before（現在）

```text
0-30秒: 「皆さんおはようございます 今日は2月8日です 良い天気ですね」
30秒: トリミング → 「今日は2月8日です 良い天気ですね」（文脈消失）
```

### After（実装後）

```text
0-30秒:
  確定テキスト: （なし）
  暫定テキスト: 「皆さんおはようございます 今日は2月8日です 良い天気ですね」

30秒: トリミング前に強制確定
  確定テキスト: 「皆さんおはようございます 今日は2月8日です 良い天気ですね」
  暫定テキスト: （なし）

30-60秒:
  確定テキスト: 「皆さんおはようございます 今日は2月8日です 良い天気ですね」
  暫定テキスト: 「これから予定を説明します」

60秒: トリミング前に強制確定
  確定テキスト: 「皆さんおはようございます...これから予定を説明します」
  暫定テキスト: （なし）
```

文脈が完全に保持される。

## パフォーマンスへの影響

### 処理時間

**影響なし**

- 強制確定処理は文字列操作のみ
- トリミング時に1回だけ実行
- 処理時間への影響は無視できるレベル（< 1ms）

### メモリ使用量

**微増（許容範囲）**

- 確定テキストが増えるため、メモリ使用量が微増
- ただし、テキストデータは軽量（数KB程度）
- 音声データ（数百KB〜数MB）に比べて無視できる

### ログ出力

**増加**

- トリミング時のログが追加される
- デバッグ時に有用
- 本番環境ではログレベルで調整可能

## リスクと対策

### リスク1: 誤った確定

**リスク**: まだ変わる可能性があるテキストを強制確定

**対策**:

- 30秒経過時点では十分安定していると考えられる
- Whisperの特性上、前回の結果を含んで長くなる傾向
- 実機テストで確認

### リスク2: ひらがな変換の不一致

**リスク**: 強制確定時のひらがな変換が正しく行われない

**対策**:

- コールバックで`hiragana_converter`を渡す
- Phase 6.5の`finalize`メソッドと同じロジックを使用
- 単体テストで確認

### リスク3: 既存機能への影響

**リスク**: 既存の確定ロジックとの競合

**対策**:

- 既存の安定性ベースの確定ロジックはそのまま維持
- 強制確定は**追加**処理として実装
- 既存テストを全て実行して回帰テスト

## 成功基準

### 機能面

- [ ] 30秒超過時に文脈が保持される
- [ ] 60秒以上の録音でも文脈が保持される
- [ ] 確定テキストと暫定テキストが正しく分離される
- [ ] ひらがな変換が正しく動作する

### パフォーマンス面

- [ ] 処理時間の増加が1%以内
- [ ] メモリ使用量の増加が5%以内
- [ ] 既存のテストが全て通過

### ユーザー体験面

- [ ] Chrome拡張機能で長時間録音が正常動作
- [ ] テキストファイル出力で全文が保存される
- [ ] エラーやクラッシュが発生しない

## 次のステップ

1. ✅ 調査完了（PHASE6.6_INVESTIGATION.md）
2. ✅ 実装計画作成（このドキュメント）
3. ⬜ バッファトリミング時の強制確定機能実装（タスク3）
4. ⬜ 確定しきい値の設定可能化（タスク4）
5. ⬜ 単体テスト・統合テスト作成（タスク6）
6. ⬜ 実機テスト（タスク7）
7. ⬜ ドキュメント更新（タスク8）

## 参考資料

- `docs/PHASE6.6_INVESTIGATION.md`: 調査資料
- `docs/PHASE6.5_COMPLETION.md`: Phase 6.5の完了報告（`finalize`メソッド）
- `docs/WHISPER_SPECIFICATIONS.md`: Whisper仕様と制限
