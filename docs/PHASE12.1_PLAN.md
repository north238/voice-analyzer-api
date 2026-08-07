# Phase 12.1: Whisperタイムスタンプの導入

## 概要

Phase 12でタイムスタンプ付き文字起こし表示を実装済み（クライアント側のみ）。
現状はクライアント側の `Date.now() - sessionStartTime` で経過時間を算出しているが、これは「テキストが確定された時刻」であり「音声内でその発話が行われた時刻」ではない。

faster-whisperはセグメントごとに `s.start` / `s.end`（秒単位）を返すため、これを活用すれば音声ストリーム内の正確な発話位置を表示できる。

## 課題：累積バッファとの組み合わせ

累積バッファ方式では音声が最大25秒まで蓄積され、閾値超過時にトリミング（古いチャンク削除）される。
Whisperのタイムスタンプはバッファ内の相対位置（0〜25秒）のため、トリミングされた分のオフセットを加算して絶対時刻に変換する必要がある。

```text
絶対タイムスタンプ = trimmed_audio_seconds + segment.start
```

## 変更方針

サーバー側でWhisperセグメントのタイムスタンプを取得・伝搬し、クライアントはサーバーから受け取ったタイムスタンプを使用する。

## 変更ファイルと内容

### 1. `app/services/async_processor.py`

- `_transcribe_sync()` の戻り値を `str` → `(str, list[dict])` に変更
  - `list[dict]`: `[{"text": "...", "start": 0.0, "end": 1.5}, ...]`
- `transcribe_async()` も同様に戻り値変更
- セグメントごとにテキスト・開始時間・終了時間を収集

### 2. `app/services/cumulative_buffer.py`

- `CumulativeBuffer` に `trimmed_audio_seconds: float = 0.0` 追加
- `CumulativeBuffer` に `last_segments: list = []` 追加
- `_trim_buffer_if_needed()`: 削除したチャンクの秒数を `trimmed_audio_seconds` に加算
- `_find_timestamp_for_text_position()`: テキスト内の文字位置に対応するセグメントのタイムスタンプを探索
- `update_transcription()`: `segments` 引数を追加、新規確定テキストのタイムスタンプを計算
- `TranscriptionResult` に `confirmed_timestamp: float = 0.0` 追加
- `clear()`: 新フィールドのリセット追加

### 3. `app/main.py`

- `perform_cumulative_transcription()`: `transcribe_async()` の戻り値を `(text, segments)` で受け取り
- `buffer.update_transcription()` に `segments` を渡す
- WebSocketレスポンスの `transcription` オブジェクトに `confirmed_timestamp` フィールドを追加
- 非累積WebSocket (`process_websocket_chunk`) も戻り値変更に対応

### 4. クライアント側（両UI）

- `extension/sidepanel/js/ui-controller.js`
- `app/static/js/ui-controller.js`
- `updateTranscription()`: サーバーから `confirmed_timestamp` を受け取り、`_appendConfirmedBlock()` と `transcriptionHistory` に使用
- `Date.now() - sessionStartTime` のフォールバックは維持（サーバーがタイムスタンプを返さない場合用）

## タイムスタンプ計算ロジック

### _find_timestamp_for_text_position

```python
def _find_timestamp_for_text_position(self, position: int, segments: list) -> float:
    """テキスト内の文字位置に対応するセグメントのタイムスタンプを見つける"""
    current_pos = 0
    for seg in segments:
        seg_end_pos = current_pos + len(seg["text"])
        if position < seg_end_pos:
            return self.trimmed_audio_seconds + seg["start"]
        current_pos = seg_end_pos
    if segments:
        return self.trimmed_audio_seconds + segments[-1]["start"]
    return self.trimmed_audio_seconds
```

### _trim_buffer_if_needed の変更

```python
removed_seconds = len(removed) / (sample_rate * channels * sample_width)
self.trimmed_audio_seconds += removed_seconds
```

### WebSocketレスポンス

```python
"transcription": {
    "confirmed": result.confirmed_text,
    "tentative": result.tentative_text,
    "full_text": result.full_text,
    "confirmed_timestamp": result.confirmed_timestamp,  # NEW
}
```

### クライアント側のタイムスタンプ取得

```javascript
const timestamp =
  transcription.confirmed_timestamp != null
    ? transcription.confirmed_timestamp
    : this.sessionStartTime
      ? (Date.now() - this.sessionStartTime) / 1000
      : 0;
```

## 実装順序

1. `async_processor.py`: 戻り値を `(text, segments_info)` に変更
2. `cumulative_buffer.py`: `trimmed_audio_seconds`、`TranscriptionResult.confirmed_timestamp`、タイムスタンプ計算メソッド追加
3. `main.py`: セグメント情報の受け渡し、レスポンスにタイムスタンプ追加
4. クライアント側: サーバー提供タイムスタンプの使用
5. 動作確認

## 検証方法

1. `docker compose up --build -d` でサーバー起動
2. Chrome拡張でYouTube動画の文字起こし → タイムスタンプが音声の発話位置に対応していることを確認
3. 30秒以上の音声でトリミング発生後もタイムスタンプが単調増加していることを確認
4. ブラウザUIでも同様に確認
5. ダウンロード機能は既存の `[HH:MM:SS]` 形式を維持（変更不要）
6. テスト実行: `docker compose exec voice-analyzer pytest /app/tests/ -v`

## 残課題

Phase 12.1では「確定テキストの開始タイムスタンプ」をサーバーから提供するが、文節の区切り方自体は変更しない。
文節分割の改善は Phase 12.2 で対応する。
