# Phase 12.3: 重複テキスト問題の修正

## 概要

Phase 12.2で実装したセグメント単位の分割により、以下のような重複が発生している：

```text
[00:51] ここ近年ではですねGoogleの検索トレンドでも急上昇していまして世界的にもですね非常に注目されているプログラミング言語となって
[01:07] ここ近年ではですね Googleの検索トレンドでも急上昇していまして世界的にもですね非常に注目されているプログラミング言語となっています
```

同じ内容が異なるタイムスタンプで2回表示されている。

## 根本原因

### 1. `stable_count` がリセットされない問題

`cumulative_buffer.py` の安定性確定ロジックにバグがある：

```python
if new_text == self.previous_full_text:
    self.stable_count += 1
    if self.stable_count >= self.config.stable_text_threshold:
        remaining = remove_confirmed_overlap(confirmed_text, new_text)
        if remaining:
            newly_confirmed = remaining[:cut_pos]
            self.confirmed_text += newly_confirmed
            # ← stable_count がリセットされていない！
```

`stable_text_threshold = 2` の状態で同じテキストが3回、4回と続いた場合：

- 3回目: `stable_count=3 >= 2` → また `newly_confirmed` が生成される
- 4回目: `stable_count=4 >= 2` → また `newly_confirmed` が生成される

毎回 `_remove_confirmed_overlap()` で重複除外されるが、精度が完全ではないため同じ内容が再確定される。

### 2. `_remove_confirmed_overlap()` の精度問題

3種類のアルゴリズムのうち「類似度ベース」と「文字数推定」は不正確な場合がある：

```python
# 方法3: 文字数推定（精度が低い）
if len(new) > len(confirmed):
    estimated_skip = len(confirmed)  # ← 大雑把な推定
    result = new[estimated_skip:]
```

Whisperの再処理で表記が微妙に変わると、完全一致・類似度マッチが失敗し方法3が使われて重複が発生する。

### 重複が発生する具体的なシナリオ

```text
チャンク3: new_text = "A" → stable_count=1 → 確定なし
チャンク6: new_text = "A" → stable_count=2 → newly_confirmed="A_1" 確定
チャンク9: new_text = "A" → stable_count=3 → _remove_confirmed_overlap()で重複除外
           ↓ 失敗した場合 → newly_confirmed="A_1" が再度確定 ← 重複発生！
```

## 修正方針

### 方針1: 確定後に `stable_count` をリセット（推奨）

```python
if self.stable_count >= self.config.stable_text_threshold:
    remaining = remove_confirmed_overlap(self.confirmed_text, new_text)
    if remaining and break_points:
        newly_confirmed = remaining[:cut_pos]
        self.confirmed_text += newly_confirmed
        self.stable_count = 0  # ← 確定後にリセット
```

**効果**: 一度確定されたら、次に同じテキストが続いても即座には再確定されない。

**注意**: `stable_count = 0` にリセットすると、次の確定には再度 `threshold` 回分待つ必要がある。
→ 実際には `stable_count = self.config.stable_text_threshold - 1` にすれば、次の同じテキストで即確定できる。

### 方針2: `_remove_confirmed_overlap()` の精度向上

完全一致の比較長を拡張する：

```python
# 現在: confirmed[-i:] == new[:i] で最大 min(len(confirmed), len(new)) 文字
# → 先頭からの一致も検査する
```

ただし、これだけでは不十分な場合がある。

### 方針3: クライアント側でタイムスタンプ重複を排除

```javascript
// 既に表示済みのタイムスタンプ範囲を記録
if (seg.start < this._lastConfirmedTimestamp) {
    continue;  // 既に表示済みの範囲はスキップ
}
```

**問題**: タイムスタンプが単調増加しない場合があるため完全ではない。

## 推奨実装

**方針1（`stable_count` リセット）を主とし、方針2を補助として実装する。**

### サーバー側の変更

#### `cumulative_buffer.py`

安定性確定後に `stable_count` をリセット：

```python
if self.stable_count >= self.config.stable_text_threshold:
    if self.confirmed_text:
        remaining = remove_confirmed_overlap(self.confirmed_text, new_text)
        if remaining:
            break_points = [...]
            if break_points:
                cut_pos = min(break_points)
                newly_confirmed = remaining[:cut_pos]
                self.confirmed_text += newly_confirmed
                tentative = remaining[cut_pos:]
                # ✅ 確定後に stable_count をリセット
                self.stable_count = self.config.stable_text_threshold - 1
                logger.debug(f"   新規確定: {newly_confirmed[:30]}... → stable_count リセット")
```

`stable_text_threshold - 1` にすることで：

- 次の同一テキストで即座に再確定可能（ちょうど1回で確定できる状態を維持）
- 連続して同じテキストが来る場合でも、1チャンクに1回のみ確定

### クライアント側の変更

不要（サーバー側修正で対応完了の見込み）。

ただし、防御的実装として既表示タイムスタンプの範囲チェックを追加することも検討。

## 変更ファイル

| ファイル                            | 変更内容                                                    |
| ----------------------------------- | ----------------------------------------------------------- |
| `app/services/cumulative_buffer.py` | 安定性確定後に `stable_count` を `threshold - 1` にリセット |

## 実装順序

1. `cumulative_buffer.py`: `stable_count` リセットロジックを追加
2. Docker再ビルドして動作確認
3. テスト実行

## 検証方法

1. `docker compose up --build -d` でサーバー起動
2. YouTube動画で長時間（2分以上）文字起こし
3. 確認項目:
   - 同じ内容が2回出現しないか
   - 確定のタイミングが遅くなりすぎないか
   - 30秒超のトリミング後も正常に動作するか

## リスク・注意点

- `stable_count` のリセット後、確定が遅くなる可能性がある（ただし `threshold - 1` にすることで次の1チャンクで確定可能）
- トリミング時の `force_finalize_pending_text()` との組み合わせが正しく動作するか確認が必要

## 関連ドキュメント

- `docs/PHASE12.2_PLAN.md`: セグメント単位での文節分割
- `docs/WHISPER_SPECIFICATIONS.md`: Whisperの仕様
