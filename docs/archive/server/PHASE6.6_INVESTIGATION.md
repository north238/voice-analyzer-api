# Phase 6.6 調査資料: バッファトリミング時の文脈喪失問題

## 調査日時

2026-02-08

## 問題の概要

累積バッファが30秒の上限に達すると、古い音声チャンクが自動削除される。この時、削除された部分のテキストが確定テキストに移行していない場合、完全に失われる。

### 具体例

```text
初期: 「皆さんおはようございます 今日は2月8日です」
 ↓
30秒経過でバッファトリミング
 ↓
結果: 「今日は2月8日です」（最初の部分が消失）
```

## コード分析

### 1. バッファトリミングのロジック

**ファイル**: `app/services/cumulative_buffer.py:208-216`

```python
def _trim_buffer_if_needed(self):
    """バッファが最大サイズを超えた場合、古いデータを削除"""
    while (
        self.total_audio_bytes > self.max_audio_bytes and len(self.audio_chunks) > 1
    ):
        removed = self.audio_chunks.pop(0)
        self.total_audio_bytes -= len(removed)
        logger.debug(f"🗑️ 古いチャンク削除: 残り{self.current_audio_duration:.1f}秒")
```

**問題点**:

- 古い音声チャンクを削除するだけ
- 削除されるチャンクに対応するテキストの処理が一切ない
- 暫定テキストが確定テキストに移行しないまま音声データだけが消える

### 2. 確定テキストへの移行条件

**ファイル**: `app/services/cumulative_buffer.py:256-379`

現在の確定ロジック（安定性ベース）:

```python
# 安定性チェック（同じ結果が連続して出現したら確定）
if new_text == self.previous_full_text:
    self.stable_count += 1

    # 閾値を超えたら、前回のテキストを確定に追加
    if self.stable_count >= self.config.stable_text_threshold:
        # 句読点・空白で区切って確定に追加
        ...
```

**確定条件**:

1. 同じテキストが`stable_text_threshold`回連続（デフォルト2回）
2. 句読点（。！？）または空白で区切られる位置まで

**問題点**:

- バッファトリミング時に強制確定する処理がない
- トリミング前に暫定テキストを確定に移行する仕組みがない
- 句読点がない場合、長時間暫定のままで確定されない可能性

### 3. トリミングが発生するタイミング

**ファイル**: `app/services/cumulative_buffer.py:168-194`

```python
def add_audio_chunk(self, audio_data: bytes) -> bool:
    """音声チャンクを追加"""
    pcm_data = self._extract_pcm_from_wav(audio_data)

    self.audio_chunks.append(pcm_data)
    self.total_audio_bytes += len(pcm_data)
    self.chunk_count += 1

    # 最大バッファサイズを超えた場合、古いデータを削除
    self._trim_buffer_if_needed()  # ← ここでトリミング

    # 再文字起こしが必要かどうか判定
    return self.chunk_count % self.config.transcription_interval_chunks == 0
```

**タイミング**:

- チャンク追加時に毎回チェック
- `max_audio_duration_seconds`（デフォルト30秒）を超えたら削除

### 4. WebSocketでの処理フロー

**ファイル**: `app/main.py:602-659`

```python
async def process_cumulative_chunk(session_id, chunk_id, audio_data, connection):
    buffer = cumulative_buffers.get(session_id)

    # 音声をバッファに追加（ここでトリミングが発生する可能性）
    should_transcribe = buffer.add_audio_chunk(audio_data)

    # 再文字起こしが必要な場合
    if should_transcribe:
        await perform_cumulative_transcription(...)
```

**問題点**:

- `add_audio_chunk`でトリミングが発生
- トリミング後に文字起こしが実行される場合、既に音声データは削除済み
- 削除された部分のテキストは次回の文字起こしに含まれない

## 文脈喪失が発生する具体的なシナリオ

### シナリオ1: 句読点なし長文

```text
0-10秒: 「皆さんおはようございます」（暫定）
10-20秒: 「皆さんおはようございます 今日は2月8日です」（暫定）
20-30秒: 「皆さんおはようございます 今日は2月8日です 良い天気ですね」（暫定）
30秒: トリミング発生
  → 0-10秒の音声チャンク削除
  → 「皆さんおはようございます」が確定に移行していない場合、消失
```

### シナリオ2: 確定しきい値に達しない場合

```text
0-10秒: 「こんにちは」（暫定）
10-20秒: 「こんにちは 今日は」（暫定、テキスト変更）
20-30秒: 「こんにちは 今日は良い天気ですね」（暫定、テキスト変更）
  → stable_countが0のままでリセットされ続ける
  → 確定テキストに移行しない
30秒: トリミング発生
  → 「こんにちは」の音声データが削除
  → 「こんにちは」が暫定のまま消失
```

### シナリオ3: 句読点が後半にある場合

```text
0-10秒: 「これは非常に重要な話なのですが」（暫定）
10-20秒: 「これは非常に重要な話なのですが まず最初に」（暫定）
20-30秒: 「これは非常に重要な話なのですが まず最初に説明します」（暫定）
  → 句読点がないため確定に移行しない
30秒: トリミング発生
  → 「これは非常に重要な話なのですが」が消失
```

## 設定値の確認

**ファイル**: `app/config.py:48-58`

```python
# 累積バッファ設定
CUMULATIVE_MAX_AUDIO_SECONDS: float = 30.0  # 最大30秒
CUMULATIVE_TRANSCRIPTION_INTERVAL: int = 3  # 3チャンクごとに再処理
CUMULATIVE_STABLE_THRESHOLD: int = 2  # 2回同じ結果で確定
```

**影響**:

- 30秒でトリミングは妥当（Whisperの制限）
- 3チャンクごとの再処理は妥当
- **stable_threshold=2**は厳しすぎる可能性
  - テキストが少しでも変わるとリセットされる
  - 長文の場合、確定に時間がかかる

## 既存の関連実装

### Phase 6.4での改善

**ファイル**: `docs/PHASE6.4_COMPLETION.md`

Phase 6.4で以下の改善を実施:

1. 録音時間の表示を実際の経過時間に分離（`session_elapsed_seconds`）
2. 確定テキストロジックを句点依存から安定性ベースに変更
3. 句点なしでも動作するように改善

**しかし**:

- バッファトリミング時の文脈保持は未実装
- トリミング時の強制確定処理がない

### Phase 6.5での改善

**ファイル**: `docs/PHASE6.5_COMPLETION.md`

Phase 6.5で以下の改善を実施:

1. タイムアウト延長（10秒→20秒）
2. セッション終了時の強制確定処理（`finalize`メソッド）

**セッション終了時の処理**:

```python
def finalize(self, hiragana_converter=None) -> TranscriptionResult:
    """セッション終了時に全テキストを確定"""
    # 残りの暫定テキストを確定
    if self.last_transcription:
        remaining = self.last_transcription[len(self.confirmed_text):]
        if remaining:
            self.confirmed_text += remaining
            ...
```

**しかし**:

- これは**セッション終了時**のみの処理
- **バッファトリミング時**には適用されない
- トリミング時に同様の処理が必要

## 解決策の候補

### 解決策1: バッファトリミング時の強制確定（推奨）

**実装内容**:

1. `_trim_buffer_if_needed()`でトリミング前にコールバックを呼ぶ
2. コールバックで現在の暫定テキストを確定テキストに強制移行
3. トリミング後は新しい音声データのみを処理

**メリット**:

- 文脈喪失を完全に防止
- 実装が明確でテストしやすい

**デメリット**:

- 確定テキストに誤りが含まれる可能性（まだ変わる可能性があるテキストを強制確定）
- ただし、30秒経過時点では十分安定していると考えられる

### 解決策2: 確定しきい値の調整

**実装内容**:

1. `stable_text_threshold`を設定可能に（config.py経由）
2. デフォルト値を2から1に変更（1回の出現で確定）
3. より早く確定させることで文脈喪失リスクを減らす

**メリット**:

- トリミング前に確定される可能性が高まる
- 設定で調整可能

**デメリット**:

- 確定が早すぎると誤りが増える可能性
- 根本解決にはならない（トリミング時に暫定が残る可能性）

### 解決策3: バッファサイズ動的調整

**実装内容**:

1. 発話速度や文脈の複雑さに応じてバッファサイズを調整
2. 最小30秒、最大60秒の範囲で動的調整

**メリット**:

- より長い文脈を保持可能

**デメリット**:

- Whisperは30秒を超えると幻覚（hallucination）のリスクが増加
- メモリ使用量が増加
- 複雑で効果が限定的

## 推奨アプローチ

**優先度1: 解決策1（バッファトリミング時の強制確定）**

- 文脈喪失を確実に防止
- Phase 6.5の`finalize`メソッドと同様のロジックを流用

**優先度2: 解決策2（確定しきい値の調整）**

- 設定可能化により柔軟性向上
- デフォルト値の最適化

**優先度3: 解決策3（バッファサイズ動的調整）**

- 効果が限定的なため、必要性を検討してから実装

## 次のステップ

1. ✅ 調査完了（このドキュメント）
2. ⬜ 解決策の設計と実装計画作成（PHASE6.6_PLAN.md）
3. ⬜ バッファトリミング時の強制確定機能実装
4. ⬜ 確定しきい値の設定可能化
5. ⬜ テスト作成と実機テスト
6. ⬜ ドキュメント更新（PHASE6.6_COMPLETION.md）

## 参考ファイル

- `app/services/cumulative_buffer.py`: 累積バッファ管理
- `app/services/session_manager.py`: セッション管理
- `app/config.py`: 設定管理
- `app/main.py`: WebSocketエンドポイント
- `docs/PHASE6.4_COMPLETION.md`: Phase 6.4の完了報告
- `docs/PHASE6.5_COMPLETION.md`: Phase 6.5の完了報告
- `docs/WHISPER_SPECIFICATIONS.md`: Whisper仕様と制限
