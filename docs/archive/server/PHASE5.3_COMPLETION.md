# Phase 5.3 完了報告: 句読点挿入処理の削除

## 概要

句読点挿入処理を削除し、処理フローを簡素化しました。

## 実装日時

- 実装完了: 2026-01-30

## 削除理由

1. **コア機能ではない**: プロジェクトの主な用途（レシートや買い物メモの短文）に句読点は不要
2. **効果が未検証**: 翻訳精度向上の効果が検証されていない
3. **処理速度向上**: 形態素解析の重複を解消
4. **コードの簡素化**: 不要な処理パスを削減

## 削除した処理

### 1. app/main.py

**削除箇所 (4箇所):**

- POST /translate エンドポイント
- POST /translate-chunk エンドポイント
- WebSocket /ws/translate-stream エンドポイント
- WebSocket /ws/transcribe-stream-cumulative エンドポイント

**変更内容:**

- `add_punctuation_async()` の呼び出しを削除
- `text_with_punctuation` → `text` に置き換え
- `keep_punctuation=True` → `keep_punctuation=False` に変更
- パフォーマンス計測の `punctuation` 項目を削除
- 進捗通知の「句読点挿入中...」を削除
- レスポンスから `text_with_punctuation` フィールドを削除

### 2. app/services/async_processor.py

**削除した関数:**

- `_add_punctuation_sync()` - 同期版句読点挿入
- `add_punctuation_async()` - 非同期版句読点挿入

### 3. インポート文の更新

```python
# 変更前
from services.async_processor import (
    transcribe_async,
    normalize_async,
    translate_async,
    add_punctuation_async,  # 削除
)

# 変更後
from services.async_processor import (
    transcribe_async,
    normalize_async,
    translate_async,
)
```

## 残した処理

以下は削除せず残しました（将来の利用可能性のため）:

- `app/utils/normalizer.py` の `add_punctuation()` メソッド
- `keep_punctuation` パラメータの機能
- 関連するテストコード

## 処理フロー変更

### 変更前

```text
Whisper文字起こし
  ↓
句読点挿入 ← 削除
  ↓
ひらがな正規化 (keep_punctuation=True)
  ↓
翻訳
```

### 変更後

```text
Whisper文字起こし
  ↓
ひらがな正規化 (keep_punctuation=False)
  ↓
翻訳
```

## パフォーマンス改善

| 項目       | 変更前       | 変更後  | 効果    |
| ---------- | ------------ | ------- | ------- |
| 句読点挿入 | 0.02〜0.08秒 | 0秒     | 削除    |
| 形態素解析 | 2回          | 1回     | 50%削減 |
| コード行数 | -            | -約50行 | 簡素化  |

## テスト結果

```text
154 passed, 2 failed (既知の制限)
```

- 句読点削除による新たな失敗なし
- 2件の失敗は数え言葉変換の既知の制限（今回の変更とは無関係）

## 影響範囲

### 影響あり

- POST /translate エンドポイントのレスポンスから `text_with_punctuation` フィールドが削除
- ひらがな正規化結果に句読点が含まれなくなった

### 影響なし

- 文字起こし機能
- 翻訳機能
- ブラウザUI
- CLIクライアント

## まとめ

句読点挿入処理を削除し、処理フローを簡素化しました。

**主な成果:**

- ✅ 不要な処理の削除
- ✅ 形態素解析の重複解消
- ✅ コードの簡素化
- ✅ 既存テストへの影響なし
