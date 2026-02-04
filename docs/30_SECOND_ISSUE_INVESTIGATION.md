# 30秒問題の調査と実装方法

## 📋 概要

このドキュメントは、録音時間が30秒を超えた際に発生する問題の調査結果と、複数の解決策の実装方法をまとめたものです。実装前の壁打ち（設計レビュー）や、実装時の参考資料として使用してください。

**作成日**: 2026-02-03
**ステータス**: 調査完了、実装待ち

## 🐛 問題の詳細

### 発生する問題

1. **録音時間のカウントが30秒で止まる**
   - UIに表示される累積時間が30秒で固定される
   - 実際は録音が継続しているが、表示が更新されない

2. **音声解析の精度が著しく低下する**
   - 30秒を超えると、文字起こしの精度が急激に悪化
   - 誤認識が増加
   - 文脈を考慮した認識ができなくなる

### 再現手順

1. Chrome拡張機能またはブラウザUIで文字起こしを開始
2. 30秒以上録音を継続
3. UI上の「累積音声」の秒数が30秒前後で止まる
4. 文字起こし結果の精度が低下する

## 🔍 根本原因の分析

### 原因1: 累積バッファの30秒制限

#### コード箇所

**app/services/cumulative_buffer.py**
```python
@dataclass
class CumulativeBufferConfig:
    """累積バッファ設定"""
    max_audio_duration_seconds: float = 30.0  # 最大蓄積時間（Whisperの1セグメント上限）
    ...

def _trim_buffer_if_needed(self):
    """バッファが最大サイズを超えた場合、古いデータを削除"""
    while (
        self.total_audio_bytes > self.max_audio_bytes and len(self.audio_chunks) > 1
    ):
        removed = self.audio_chunks.pop(0)  # ← 古いチャンクを削除
        self.total_audio_bytes -= len(removed)
```

#### 問題の詳細

- 30秒を超えると、古い音声チャンクが自動的に削除される
- `buffer.current_audio_duration`は、バッファ内の音声長を返す
- 削除後のバッファ長は30秒付近で固定される

### 原因2: クライアントへの秒数送信

#### コード箇所

**app/main.py:636-644**
```python
await ws_manager.send_json(
    session_id,
    {
        "type": "accumulating",
        "chunk_id": chunk_id,
        "accumulated_seconds": buffer.current_audio_duration,  # ← 30秒で固定
        "chunks_until_transcription": chunks_until_transcription,
    },
)
```

#### 問題の詳細

- クライアントに送信される`accumulated_seconds`は、バッファ内の音声長
- 30秒を超えると、この値が固定される
- クライアント側のUIは、この値をそのまま表示

### 原因3: 文脈の喪失

#### コード箇所

**app/services/cumulative_buffer.py:232-243**
```python
def get_initial_prompt(self) -> Optional[str]:
    """次回の文字起こし用initial_promptを取得

    確定済みテキストの末尾を返す（文脈として使用）
    """
    if not self.confirmed_text:
        return None

    # 最後の2文程度を返す
    sentences = re.split(r"(?<=[。！？])", self.confirmed_text)
    recent_sentences = [s for s in sentences[-2:] if s.strip()]
    return "".join(recent_sentences) if recent_sentences else None
```

#### 問題の詳細

- 音声データが削除されると、その部分の情報が完全に失われる
- `initial_prompt`として確定テキストの末尾2文のみを渡している
- テキストのみでは、音声の文脈（イントネーション、話し方など）が失われる
- 精度が低下する

### Whisperモデルの30秒制限との関係

- Whisperモデルは30秒のセグメントをネイティブサポート
- 30秒を超えると、幻覚（hallucination）や切り詰めが発生する可能性
- **現在の実装は、この制限を回避するために30秒で古いデータを削除している**
- ただし、削除方法が適切でないため、精度が低下している

## 💡 解決策の提案

### 解決策A: 実際の経過時間を追跡（シンプル、推奨）

#### 概要

- 音声バッファは30秒に制限（現状維持）
- セッション開始からの実際の経過時間を別途記録
- クライアントに正確な録音時間を表示
- 確定テキストを保持して文脈を維持

#### メリット

- **実装が比較的簡単**
- メモリ使用量が増加しない
- Whisperの30秒制限に準拠
- 既存のアーキテクチャを大きく変更しない

#### デメリット

- 音声データは依然として30秒で削除される
- 精度の改善は限定的

#### 実装方針

##### 1. CumulativeBufferにセッション開始時刻を追加

```python
# app/services/cumulative_buffer.py
@dataclass
class CumulativeBuffer:
    """累積バッファ管理クラス"""

    def __init__(self, config: Optional[CumulativeBufferConfig] = None):
        # ... 既存の初期化

        # セッション時刻を追加
        self.session_start_time: datetime = datetime.now()  # ← 追加

    @property
    def session_elapsed_seconds(self) -> float:
        """セッション開始からの経過時間（秒）"""
        return (datetime.now() - self.session_start_time).total_seconds()
```

##### 2. WebSocketレスポンスに実際の経過時間を追加

```python
# app/main.py:636-644
await ws_manager.send_json(
    session_id,
    {
        "type": "accumulating",
        "chunk_id": chunk_id,
        "accumulated_seconds": buffer.current_audio_duration,  # バッファ内の音声長
        "session_elapsed_seconds": buffer.session_elapsed_seconds,  # ← 追加: 実際の経過時間
        "chunks_until_transcription": chunks_until_transcription,
    },
)
```

##### 3. クライアント側のUI更新

```javascript
// extension/sidepanel/js/ui-controller.js
// または app/static/js/ui-controller.js

// accumulatingメッセージ受信時
if (data.type === "accumulating") {
    // 実際の経過時間を表示
    const elapsedTime = data.session_elapsed_seconds || data.accumulated_seconds;
    // UIを更新
    updateElapsedTimeDisplay(elapsedTime);
}
```

##### 4. パフォーマンス情報の更新

```python
# app/main.py:793-797
"performance": {
    "transcription_time": transcription_time,
    "total_time": total_time,
    "accumulated_audio_seconds": buffer.current_audio_duration,  # バッファ内の音声長
    "session_elapsed_seconds": buffer.session_elapsed_seconds,  # ← 追加: 実際の経過時間
},
```

#### 実装の影響範囲

- ✅ `app/services/cumulative_buffer.py`: CumulativeBufferクラス
- ✅ `app/main.py`: WebSocketエンドポイント
- ✅ `extension/sidepanel/js/ui-controller.js`: UI表示
- ✅ `app/static/js/ui-controller.js`: UI表示（従来版）

### 解決策B: バッファサイズの拡張（中程度）

#### 概要

- 30秒 → 45秒または60秒に拡張
- オーバーラップを持たせて文脈を保持
- セッション開始からの実際の経過時間も追跡

#### メリット

- より長い文脈を保持できる
- 精度の改善が期待できる
- 実装は比較的簡単

#### デメリット

- メモリ使用量が増加（1.5倍〜2倍）
- Whisperの30秒推奨制限を超える
- 60秒を超えるとまた同じ問題が発生

#### 実装方針

##### 1. バッファサイズの設定変更

```python
# app/config.py
CUMULATIVE_MAX_AUDIO_SECONDS: float = float(
    os.getenv("CUMULATIVE_MAX_AUDIO_SECONDS", "45.0")  # 30.0 → 45.0
)
```

##### 2. オーバーラップの実装

```python
# app/services/cumulative_buffer.py
def _trim_buffer_if_needed(self):
    """バッファが最大サイズを超えた場合、古いデータを削除"""
    # オーバーラップを持たせる
    overlap_seconds = 5.0  # 5秒のオーバーラップ
    overlap_bytes = int(
        overlap_seconds * self.config.sample_rate *
        self.config.channels * self.config.sample_width
    )

    while (
        self.total_audio_bytes > self.max_audio_bytes and
        len(self.audio_chunks) > 1
    ):
        # 完全に削除せず、一部を残す
        removed = self.audio_chunks.pop(0)
        self.total_audio_bytes -= len(removed)

        # オーバーラップ分を保持
        if self.total_audio_bytes < overlap_bytes:
            # 削除しすぎた場合は、一部を戻す
            # （実装の詳細は要検討）
            pass
```

#### 実装の影響範囲

- ✅ `app/config.py`: 設定値の変更
- ✅ `app/services/cumulative_buffer.py`: バッファ削除ロジック
- ⚠️ メモリ使用量の監視が必要

### 解決策C: スライディングウィンドウ方式（長期的、高度）

#### 概要

- 30秒のウィンドウをスライドさせながら処理
- 各ウィンドウの結果を結合
- faster-whisperの長時間音声処理機能を活用

#### メリット

- Whisperの仕様に完全準拠
- 高精度な長時間文字起こし
- 無制限の録音時間に対応

#### デメリット

- **実装が複雑**
- 既存のアーキテクチャを大幅に変更
- 処理負荷が増加（複数回の文字起こし）

#### 実装方針（概要のみ）

##### 1. セグメント管理クラスの作成

```python
# app/services/segment_manager.py (新規作成)

class AudioSegment:
    """音声セグメント"""
    start_time: float
    end_time: float
    audio_data: bytes
    transcription: str
    is_confirmed: bool

class SegmentManager:
    """セグメント管理クラス"""

    def __init__(self, window_size: float = 30.0, overlap: float = 5.0):
        self.window_size = window_size
        self.overlap = overlap
        self.segments: List[AudioSegment] = []

    def add_audio(self, audio_data: bytes, timestamp: float):
        """音声データを追加してセグメントを作成"""
        pass

    def get_next_segment(self) -> Optional[AudioSegment]:
        """次に処理すべきセグメントを取得"""
        pass

    def merge_transcriptions(self) -> str:
        """全セグメントの文字起こし結果を結合"""
        pass
```

##### 2. WebSocketエンドポイントの変更

```python
# app/main.py

async def process_cumulative_chunk_with_segments(
    session_id: str,
    chunk_id: int,
    audio_data: bytes,
    connection,
):
    """
    セグメント方式でチャンクを処理
    """
    segment_manager = segment_managers.get(session_id)

    # セグメントに追加
    segment_manager.add_audio(audio_data, timestamp=time.time())

    # 処理すべきセグメントを取得
    segment = segment_manager.get_next_segment()
    if segment:
        # セグメントを文字起こし
        text = await transcribe_async(segment.audio_data)
        segment.transcription = text

        # 全セグメントを結合
        full_text = segment_manager.merge_transcriptions()

        # クライアントに送信
        await ws_manager.send_json(session_id, {
            "type": "transcription_update",
            "transcription": {
                "confirmed": full_text,
                "tentative": "",
            }
        })
```

#### 実装の影響範囲

- 🆕 `app/services/segment_manager.py`: 新規作成
- ✅ `app/main.py`: WebSocketエンドポイントの大幅変更
- ✅ `app/services/cumulative_buffer.py`: 廃止または大幅変更
- ⚠️ 既存のテストコードの修正が必要

### 解決策D: 確定テキストの強化（補助的）

#### 概要

- `initial_prompt`に渡すテキストを増やす
- 確定テキストの末尾2文 → 10文程度に拡張
- 解決策A〜Cと組み合わせて使用

#### メリット

- 実装が簡単
- 文脈の保持が改善
- 他の解決策と併用可能

#### デメリット

- `initial_prompt`が長すぎると処理が遅くなる可能性
- 効果は限定的（音声データは依然として削除される）

#### 実装方針

```python
# app/services/cumulative_buffer.py

def get_initial_prompt(self) -> Optional[str]:
    """次回の文字起こし用initial_promptを取得"""
    if not self.confirmed_text:
        return None

    # 最後の10文程度を返す（2文 → 10文に拡張）
    sentences = re.split(r"(?<=[。！？])", self.confirmed_text)
    recent_sentences = [s for s in sentences[-10:] if s.strip()]  # ← 変更
    prompt = "".join(recent_sentences)

    # 長さ制限（Whisperの制限を考慮）
    max_length = 224  # Whisperのトークン制限
    if len(prompt) > max_length:
        prompt = prompt[-max_length:]

    return prompt if prompt else None
```

#### 実装の影響範囲

- ✅ `app/services/cumulative_buffer.py`: get_initial_promptメソッド

## 📊 解決策の比較

| 解決策 | 実装難易度 | 効果 | メモリ増加 | 処理負荷 | 推奨度 |
|--------|-----------|------|-----------|---------|--------|
| A: 経過時間追跡 | ★☆☆☆☆ | ★★☆☆☆ | なし | なし | ⭐⭐⭐⭐⭐ |
| B: バッファ拡張 | ★★☆☆☆ | ★★★☆☆ | 1.5〜2倍 | わずか | ⭐⭐⭐⭐☆ |
| C: スライディング | ★★★★★ | ★★★★★ | 可変 | 大 | ⭐⭐☆☆☆ |
| D: 文脈強化 | ★☆☆☆☆ | ★☆☆☆☆ | なし | わずか | ⭐⭐⭐☆☆ |

## 🎯 推奨実装プラン

### フェーズ1: 即座の対応（解決策A + D）

**目的**: ユーザー体験の改善（表示の修正）

**実装内容**:
1. 解決策A: 実際の経過時間を追跡・表示
2. 解決策D: `initial_prompt`の文数を増やす

**期待効果**:
- ✅ 録音時間が正しく表示される
- ✅ わずかに精度が改善
- ✅ 実装が簡単（1〜2時間）

**実装優先度**: **最高**

### フェーズ2: 中期的改善（解決策B）

**目的**: 精度の改善

**実装内容**:
1. バッファサイズを45秒に拡張
2. オーバーラップの実装（オプション）

**期待効果**:
- ✅ より長い文脈を保持
- ✅ 精度の改善
- ⚠️ メモリ使用量が増加

**実装優先度**: **中**

### フェーズ3: 長期的改善（解決策C）

**目的**: 根本的な解決

**実装内容**:
1. セグメント管理クラスの実装
2. スライディングウィンドウ方式の実装
3. 既存のアーキテクチャの見直し

**期待効果**:
- ✅ 無制限の録音時間に対応
- ✅ 高精度な長時間文字起こし
- ⚠️ 実装が複雑

**実装優先度**: **低**（将来的な検討）

## 🔧 実装時の注意事項

### 1. 後方互換性

- 既存のクライアント（ブラウザUI）も動作するように
- `session_elapsed_seconds`がない場合は`accumulated_seconds`を使用

### 2. エラーハンドリング

- セッション開始時刻が記録されていない場合の処理
- タイムスタンプの精度（ミリ秒 vs 秒）

### 3. テスト

- 30秒以下の録音で動作確認
- 30秒〜60秒の録音で動作確認
- 60秒以上の録音で動作確認
- メモリ使用量の監視

### 4. ドキュメント

- CLAUDE.mdの更新
- APIドキュメントの更新（WebSocketレスポンスの変更）

## 📝 実装チェックリスト

### 解決策A: 経過時間追跡

- [ ] `cumulative_buffer.py`にセッション開始時刻を追加
- [ ] `session_elapsed_seconds`プロパティを実装
- [ ] `main.py`のWebSocketレスポンスに追加
- [ ] UI側の表示を更新（サイドパネル）
- [ ] UI側の表示を更新（従来版ブラウザUI）
- [ ] テスト: 30秒以下の録音
- [ ] テスト: 30秒〜60秒の録音
- [ ] テスト: 60秒以上の録音
- [ ] ドキュメント更新

### 解決策D: 文脈強化

- [ ] `get_initial_prompt`メソッドを修正
- [ ] 文数を2文 → 10文に拡張
- [ ] 長さ制限を実装
- [ ] テスト: 精度の改善を確認

## 🔗 関連ドキュメント

- `docs/WHISPER_SPECIFICATIONS.md`: Whisperの仕様と制限
- `docs/PHASE4.1_COMPLETION.md`: 累積バッファ方式の実装
- `app/services/cumulative_buffer.py`: 累積バッファの実装
- `app/main.py`: WebSocketエンドポイント

## 📅 実装履歴

- **2026-02-03**: 問題調査完了、ドキュメント作成
- （実装後に追記）

## 💬 壁打ち用メモ

### 検討すべき点

1. **バッファサイズは45秒が適切か？60秒が良いか？**
   - Whisperの30秒推奨を考慮
   - メモリ使用量とのトレードオフ
   - ユースケース（通常の会話 vs プレゼンテーション）

2. **オーバーラップは必要か？**
   - 実装の複雑さ vs 精度の改善
   - 5秒のオーバーラップが適切か？

3. **initial_promptの長さ制限**
   - 10文が適切か？
   - Whisperのトークン制限（224トークン）を考慮
   - 処理速度への影響

4. **長期的にはスライディングウィンドウ方式が必要か？**
   - ユーザーの典型的な使用時間は？
   - 1時間を超える録音は想定するか？

5. **メモリ使用量の監視**
   - Raspberry Piでの動作を考慮
   - メモリ制限のアラート機能は必要か？

### 代替案

- **解決策E: ハイブリッド方式**
  - 30秒まで: 現在の累積バッファ方式
  - 30秒以降: セグメント方式に切り替え
  - 複雑さは増すが、柔軟性が高い

- **解決策F: クライアント側バッファリング**
  - サーバー側は30秒に制限
  - クライアント側で全音声を保持
  - 終了時に全音声を再処理
  - リアルタイム性は犠牲になる

## 🎓 学んだこと

- Whisperの30秒制限はアーキテクチャ上の制約
- 30秒を超えると幻覚が発生する可能性が高い
- faster-whisperは長時間音声を自動的にチャンキング
- リアルタイム処理では文脈の保持が重要
- 実際の経過時間とバッファ内の音声長は別物

## 🔮 将来の拡張

- より高度なセグメント管理
- 話者分離（diarization）
- リアルタイム翻訳の改善
- 複数言語対応
- クラウドベースのWhisper API（OpenAI/Azure）の統合
