# Phase 4.1: 累積バッファ方式リアルタイム文字起こし 完了報告

## 概要

チャンク境界での文脈分断問題を解決し、リアルタイム文字起こしを実現した。

### 課題と解決策

**課題:**

- 3秒チャンク独立処理では文脈が分断される（「システムを構築して」→「います」）
- 前後の文脈なしでWhisperの認識精度が低下

**解決策:**

- 音声を累積し、定期的に全体を再文字起こし
- `initial_prompt`で前回結果を渡して文脈維持
- 確定テキスト（変更されない部分）と暫定テキスト（まだ変わる可能性）を区別

## 実装内容

### 1. 新規ファイル

**`app/services/cumulative_buffer.py`**

- `CumulativeBufferConfig`: バッファ設定（最大蓄積時間、処理間隔等）
- `TranscriptionResult`: 文字起こし結果（確定/暫定テキスト）
- `CumulativeBuffer`: 音声バッファ管理クラス
- `extract_diff()`: 差分抽出アルゴリズム

### 2. 修正ファイル

**`app/services/async_processor.py`**

- `_transcribe_sync()`に`initial_prompt`パラメータ追加
- `transcribe_async()`も同様に拡張

**`app/config.py`**

- `CUMULATIVE_MAX_AUDIO_SECONDS`: 最大蓄積時間（デフォルト30秒）
- `CUMULATIVE_TRANSCRIPTION_INTERVAL`: 再処理間隔（デフォルト3チャンク）
- `CUMULATIVE_STABLE_THRESHOLD`: 安定判定閾値（デフォルト2回）

**`app/main.py`**

- 新エンドポイント `WebSocket /ws/transcribe-stream-cumulative`
- `process_cumulative_chunk()`: 累積チャンク処理
- `perform_cumulative_transcription()`: 累積文字起こし実行
- `finalize_cumulative_session()`: セッション終了処理

**`client/realtime_client.py`**

- `--cumulative`フラグ追加
- 確定テキスト（白色）と暫定テキスト（グレー）の区別表示
- `accumulating`/`transcription_update`メッセージ対応

## 処理フロー

```text
マイク入力（3秒チャンク）
  ↓
CumulativeBufferに蓄積
  ↓
3チャンクごとに累積音声を全体文字起こし
  ↓
差分抽出（句点で分割、一致部分を確定）
  ↓
確定/暫定テキストをクライアントに配信
  ↓
確定テキストをひらがな正規化
```

## 差分抽出アルゴリズム

```text
前回: "これはテストです。システムを"
今回: "これはテストです。システムを構築しています。"

結果:
  確定: "これはテストです。"（句点で終わり、前回と一致）
  暫定: "システムを構築しています。"（まだ変わる可能性）
```

## WebSocketメッセージ仕様

### 蓄積中通知

```json
{
  "type": "accumulating",
  "chunk_id": 1,
  "accumulated_seconds": 3.0,
  "chunks_until_transcription": 2
}
```

### 文字起こし結果

```json
{
  "type": "transcription_update",
  "chunk_id": 3,
  "transcription": {
    "confirmed": "これはテストです。",
    "tentative": "システムを構築しています",
    "full_text": "これはテストです。システムを構築しています"
  },
  "hiragana": {
    "confirmed": "これはてすとです。",
    "tentative": "しすてむをこうちくしています"
  },
  "performance": {
    "transcription_time": 2.5,
    "total_time": 2.8,
    "accumulated_audio_seconds": 9.0
  },
  "is_final": false
}
```

### セッション終了

```json
{
  "type": "session_end",
  "transcription": {
    "confirmed": "最終確定テキスト",
    "tentative": "",
    "full_text": "最終確定テキスト"
  },
  "hiragana": {
    "confirmed": "さいしゅうかくていてきすと",
    "tentative": ""
  },
  "statistics": {
    "chunk_count": 10,
    "audio_duration_seconds": 30.0
  },
  "is_final": true
}
```

## テスト方法

```bash
# サーバー起動
docker compose up -d

# 累積バッファモードでクライアント起動
python client/realtime_client.py --cumulative

# 通常モード（従来の翻訳付き）
python client/realtime_client.py
```

## 処理負荷

| 項目     | 従来方式            | 累積バッファ方式           |
| -------- | ------------------- | -------------------------- |
| 処理対象 | 3秒                 | 9秒（3チャンク分）         |
| 処理時間 | 1.7〜2.2秒          | 2〜3秒（翻訳なしで軽量化） |
| 処理頻度 | 毎チャンク          | 3チャンクに1回             |
| 実効時間 | 1.7〜2.2秒/チャンク | 0.7〜1秒/チャンク          |

メモリ使用量: 約1MB/セッション（Raspberry Piでも動作可能）

## 成功基準（達成済み）

- ✅ 累積バッファへの音声蓄積が正常動作
- ✅ 確定/暫定テキストが正しく区別される
- ✅ 処理時間が累積音声長の1.5倍以内
- ✅ 既存エンドポイントとの互換性維持
- ✅ ひらがな正規化が適用される

## 機能スコープ

- **文字起こし**: 日本語音声→テキスト（累積バッファ方式）✅
- **ひらがな正規化**: 維持 ✅
- **翻訳**: 今回は対象外（処理軽量化のため）

## 完了日

2026-01-25
