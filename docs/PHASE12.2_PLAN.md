# Phase 12.2: Whisperセグメント単位での文節分割

## 概要

Phase 12.1でWhisperタイムスタンプをサーバーからクライアントに伝搬する仕組みを導入した。
しかし、文字起こし結果の「文節の区切り方」自体は改善されていない。

### 現状の問題

現在の確定テキストの分割は以下の2つのタイミングで行われる:

1. **安定性ベースの確定**: 同じ文字起こし結果が2回連続で出現 → 句読点までを確定
2. **トリミング時の強制確定**: バッファが25秒を超えた際に暫定テキスト全体を一括確定

これにより以下の問題が発生:

```text
[00:37] マンスを発揮できています。4.標準パッケージが豊富
[00:37] が高い                    ← 短すぎる断片
[00:57] 5.安全性が高い5.正的片付け言語片宣言が厳格で...
```

- 文の途中で切れる（「ングの...」「が高い」）
- 短すぎる断片が独立したブロックになる
- 同じタイムスタンプで複数ブロックが生成される

### 根本原因

現在の確定ロジックは **「テキストの安定性」** に基づいており、 **「音声の自然な区切り」** を考慮していない。
Whisperは音声を自然なセグメント（文や句の単位）に分割しており、この情報を活用すべき。

## 改善方針

Whisperのセグメント境界を確定テキストの分割単位として使用する。

### 基本アイデア

```text
現状: 安定性チェック → テキスト全体で確定 → 句読点で分割
改善: 安定性チェック → セグメント単位で確定 → セグメントごとにタイムスタンプ付きブロック
```

## 設計

### サーバー側の変更

#### `TranscriptionResult` の拡張

```python
@dataclass
class TranscriptionResult:
    confirmed_text: str
    tentative_text: str
    full_text: str
    confirmed_hiragana: str
    tentative_hiragana: str
    is_final: bool
    # Phase 12.1
    confirmed_timestamp: float = 0.0
    # Phase 12.2: 新規確定セグメントのリスト
    new_confirmed_segments: list = field(default_factory=list)
    # [{"text": "...", "start": 0.0, "end": 1.5}, ...]
```

#### `CumulativeBuffer.update_transcription()` の変更

確定テキストが増加した際に、新規確定部分をセグメント単位で分割して返す:

```python
# 新規確定テキストに対応するセグメントを特定
new_confirmed_segments = []
if newly_confirmed and self.last_segments:
    # 新規確定テキストの範囲に含まれるセグメントを抽出
    for seg in self.last_segments:
        # セグメントが新規確定範囲に含まれるかチェック
        # 含まれる場合、絶対タイムスタンプ付きで追加
        new_confirmed_segments.append({
            "text": seg["text"].strip(),
            "start": self.trimmed_audio_seconds + seg["start"],
            "end": self.trimmed_audio_seconds + seg["end"],
        })
```

#### WebSocketレスポンスの変更

```python
"transcription": {
    "confirmed": result.confirmed_text,
    "tentative": result.tentative_text,
    "full_text": result.full_text,
    "confirmed_timestamp": result.confirmed_timestamp,
    "new_confirmed_segments": result.new_confirmed_segments,  # NEW
}
```

### クライアント側の変更

#### `updateTranscription()` の修正

```javascript
// セグメント単位でブロックを追加
const segments = transcription.new_confirmed_segments || [];
if (segments.length > 0) {
  for (const seg of segments) {
    if (seg.text.trim()) {
      this._appendConfirmedBlock(seg.text, seg.start);
      this.transcriptionHistory.push({
        timestamp: seg.start,
        text: seg.text.trim(),
        hiragana: "",
        translation: "",
      });
    }
  }
} else {
  // フォールバック: セグメント情報がない場合は従来の方式
  this._appendConfirmedBlock(addedText, timestamp);
}
```

### 短いセグメントの結合

Whisperが非常に短いセグメント（1〜2文字）を生成する場合がある。
これを前のセグメントに結合するロジックを追加:

```python
MIN_SEGMENT_LENGTH = 5  # 最小文字数

def _merge_short_segments(self, segments: list) -> list:
    """短すぎるセグメントを前のセグメントに結合"""
    if not segments:
        return []

    merged = [segments[0]]
    for seg in segments[1:]:
        if len(seg["text"].strip()) < MIN_SEGMENT_LENGTH:
            # 前のセグメントに結合
            merged[-1]["text"] += seg["text"]
            merged[-1]["end"] = seg["end"]
        else:
            merged.append(seg)

    return merged
```

## 変更ファイル

### サーバー側

| ファイル                            | 変更内容                                                                                    |
| ----------------------------------- | ------------------------------------------------------------------------------------------- |
| `app/services/cumulative_buffer.py` | `TranscriptionResult.new_confirmed_segments` 追加、セグメント分割ロジック、短セグメント結合 |
| `app/main.py`                       | レスポンスに `new_confirmed_segments` 追加                                                  |

### クライアント側

| ファイル                                  | 変更内容                     |
| ----------------------------------------- | ---------------------------- |
| `extension/sidepanel/js/ui-controller.js` | セグメント単位のブロック表示 |
| `app/static/js/ui-controller.js`          | 同上                         |

## 実装順序

1. `cumulative_buffer.py`: `new_confirmed_segments` の算出ロジック追加
2. `cumulative_buffer.py`: 短セグメント結合ロジック追加
3. `main.py`: レスポンスに `new_confirmed_segments` 追加
4. クライアント側: セグメント単位のブロック表示に変更
5. 動作確認・調整

## 期待される改善

### Before (現状)

```text
[00:37] マンスを発揮できています。4.標準パッケージが豊富
[00:37] が高い
[00:57] 5.安全性が高い5.正的片付け言語片宣言が厳格で...
```

### After (改善後)

```text
[00:32] マンスを発揮できています。
[00:35] 4.標準パッケージが豊富で信頼性が高い
[00:50] 5.安全性が高い
[00:55] 正的片付け言語で宣言が厳格でタイプセーフであって...
```

- セグメント単位で分割されるため、文の途中で切れにくい
- 各ブロックに正確な音声位置のタイムスタンプが付く
- 短い断片は前のセグメントに結合される

## 検証方法

1. `docker compose up --build -d` でサーバー起動
2. Chrome拡張でYouTube動画の文字起こし
3. 確認項目:
   - 各ブロックが自然な文単位で分割されているか
   - タイムスタンプが音声の発話位置に対応しているか
   - 短すぎる断片が独立したブロックになっていないか
   - 30秒超でトリミング発生後もタイムスタンプが単調増加しているか
4. ブラウザUIでも同様に確認
5. ダウンロード機能が正常に動作するか確認
6. テスト実行: `docker compose exec voice-analyzer pytest /app/tests/ -v`

## リスク・注意点

- Whisperのセグメント分割は必ずしも完璧ではない（短すぎる or 長すぎるセグメントが生成される場合がある）
- 累積バッファ方式では再文字起こし時にセグメント境界が変わる可能性がある
- 強制確定時（トリミング時）はセグメント情報が古い可能性があるため、フォールバック処理が必要
