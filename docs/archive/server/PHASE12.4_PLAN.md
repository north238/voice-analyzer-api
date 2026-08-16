# Phase 12.4: newly_confirmed 決定ロジックのタイムスタンプベース化

## 概要

`update_transcription()` の `newly_confirmed` 決定ロジックを、テキスト比較から
Whisperのセグメントタイムスタンプ比較に切り替える。

---

## 現状の問題

### 問題の根本原因

`_remove_confirmed_overlap()` がバッファトリミング後に失敗する。

```text
confirmed_text（累積）: 「ようこそ...Googleトレンド」  105文字（増え続ける）
new_text（バッファ分）: 「発を行う案件...Googleトレンド」  80文字（バッファ12秒分のみ）
```

`confirmed_text` が `new_text` より長くなると、方法1（完全一致）・方法2（類似度）が
いずれも「先頭から比較する」ため、内容がずれた2つのテキストの類似度が下がり失敗する。
方法3のフォールバックで `new_text` 全体を返してしまい重複が蓄積する。

### ログで確認された現象

```text
重複除外: confirmed を末尾144文字に絞って比較
重複除外: new_textが短い（144 <= 144）→ 新しいバッファと判断   ← 方法3のelseが毎回発動
```

修正を重ねてもテキスト比較の限界を超えられない。

---

## 解決方針: タイムスタンプベースへの切り替え

### 根拠

Whisper（faster-whisper）はデフォルトで各セグメントに `start`/`end` タイムスタンプを
返しており、既にコードで取得・保存している。`last_confirmed_segment_end` の管理も
Phase 12.2〜12.3 で実装済み。必要なピースは全て揃っている。

```python
# async_processor.py（現状）- すでに取得済み
segments_info.append({
    "text": s.text,
    "start": s.start,   # バッファ内相対タイムスタンプ（秒）
    "end":   s.end,
})
```

### 発想の転換

```text
現在（テキスト比較）:
  new_text から confirmed_text の重複を除去 → newly_confirmed を決定
  → confirmed_text が長くなると比較が破綻する

変更後（タイムスタンプ比較）:
  last_confirmed_segment_end（秒）以降のセグメントが新規確定
  → バッファが変化しても比較基準が変わらない
```

---

## 処理フロー（変更後）

### タイムスタンプの概念

```text
trimmed_audio_seconds = 25.0秒  ← バッファトリミングで削除された累計
seg["start"] = 3.0秒            ← Whisperが返すバッファ内相対時刻
abs_start = 28.0秒              ← セッション開始からの絶対時刻

last_confirmed_segment_end = 28.0秒  ← ここまで確定済み
```

### 安定性チェックは維持する理由

Whisperは同じ音声区間でも再処理するたびに微妙に異なるテキストを生成する。
安定（同じ出力が2回連続）してからセグメントを確定することで精度を保つ。

```text
1回目: セグメント [{0-5秒: "ようこそ"}, {5-10秒: "なぜ学ぶ"}]
2回目: セグメント [{0-5秒: "ようこそ"}, {5-11秒: "なぜ学ぶべきか"}]  ← 変化
3回目: セグメント [{0-5秒: "ようこそ"}, {5-11秒: "なぜ学ぶべきか"}]  ← 安定

→ 3回目で初めて確定
  新規確定の判断: abs_start(0秒) >= last_confirmed_segment_end(0秒) → 確定
```

### 変更後の `update_transcription()` の流れ

```text
【安定性チェック: stable_count >= 2】
    ↓
【タイムスタンプで新規セグメントを抽出】
  for seg in last_segments:
      abs_start = trimmed_audio_seconds + seg["start"]
      if abs_start >= last_confirmed_segment_end:
          → 新規セグメントとして収集
    ↓
【新規セグメントのテキストを newly_confirmed に設定】
  newly_confirmed = "".join(new_seg["text"] for new_seg in new_segs)
  confirmed_text += newly_confirmed
  last_confirmed_segment_end = new_segs[-1]["end"]  ← 更新
    ↓
【暫定テキスト = last_confirmed_segment_end 以降のセグメントテキスト】
  tentative = "".join(seg["text"] for seg in segs if abs_start > last_confirmed_segment_end)
```

### バッファトリミング後の動作

```text
トリミング前:
  trimmed_audio_seconds = 0.0
  バッファ: [0-12秒]
  セグメント: [{start:8, end:12, text:"Googleトレンド"}]
  abs_start = 0.0 + 8.0 = 8.0秒
  last_confirmed_segment_end = 8.0秒（前回確定済み）
  → このセグメントは確定済みのためスキップ ✅

トリミング後:
  trimmed_audio_seconds = 6.0  ← 6秒分削除された
  バッファ: [6-18秒]
  セグメント: [{start:2, end:6, text:"Googleトレンド"}, {start:6, end:12, text:"なんですけども"}]
  abs_start(seg1) = 6.0 + 2.0 = 8.0秒  → last_confirmed_segment_end(8.0) 以下 → スキップ
  abs_start(seg2) = 6.0 + 6.0 = 12.0秒 → last_confirmed_segment_end(8.0) 以上 → 新規確定 ✅

テキスト比較と違い、trimmed_audio_seconds が変わっても abs_start は不変のため正確に動作する。
```

---

## 変更内容

### `app/services/cumulative_buffer.py`

#### 変更1: `update_transcription()` の `newly_confirmed` 決定ロジック

**変更前（テキスト比較）:**

```python
if self.stable_count >= self.config.stable_text_threshold:
    if self.confirmed_text:
        remaining = remove_confirmed_overlap(self.confirmed_text, new_text)
        if remaining:
            break_points = [...]
            newly_confirmed = remaining[:cut_pos]
            self.confirmed_text += newly_confirmed
```

**変更後（タイムスタンプ比較）:**

```python
if self.stable_count >= self.config.stable_text_threshold:
    if self.last_segments:
        # last_confirmed_segment_end 以降の新規セグメントを抽出
        new_segs = []
        for seg in self.last_segments:
            abs_start = self.trimmed_audio_seconds + seg["start"]
            abs_end   = self.trimmed_audio_seconds + seg["end"]
            if abs_start >= self.last_confirmed_segment_end - 0.1:  # 0.1秒の余裕
                new_segs.append({"text": seg["text"], "start": abs_start, "end": abs_end})

        if new_segs:
            newly_confirmed = "".join(s["text"] for s in new_segs)
            self.confirmed_text += newly_confirmed
            self.last_confirmed_segment_end = new_segs[-1]["end"]
            self.stable_count = 0
```

#### 変更2: `tentative` の計算

**変更前:**

```python
tentative = remaining[cut_pos:]  # テキスト比較の残り
```

**変更後:**

```python
# last_confirmed_segment_end 以降の未確定セグメントテキスト
tentative = "".join(
    seg["text"] for seg in self.last_segments
    if (self.trimmed_audio_seconds + seg["start"]) > self.last_confirmed_segment_end
)
```

#### 変更3: `force_finalize_pending_text()` の修正

トリミング時の強制確定でも `_remove_confirmed_overlap()` を使っている箇所を
タイムスタンプベースに修正する。

```python
def force_finalize_pending_text(self, hiragana_converter=None) -> bool:
    if not self.last_segments:
        return False
    # last_confirmed_segment_end 以降のセグメントを全て確定
    new_segs = [
        seg for seg in self.last_segments
        if (self.trimmed_audio_seconds + seg["start"]) >= self.last_confirmed_segment_end - 0.1
    ]
    if not new_segs:
        return False
    remaining = "".join(s["text"] for s in new_segs)
    self.confirmed_text += remaining
    self.last_confirmed_segment_end = self.trimmed_audio_seconds + new_segs[-1]["end"]
    ...
```

#### 変更4: `_remove_confirmed_overlap()` の扱い

タイムスタンプベースへの移行後は不要になるが、セグメント情報がない場合のフォールバックとして残す。

```python
if self.last_segments:
    # タイムスタンプベースで処理
    ...
else:
    # セグメント情報がない場合のフォールバック（従来ロジック）
    remaining = self._remove_confirmed_overlap(self.confirmed_text, new_text)
    ...
```

---

## 変更ファイルまとめ

| ファイル                            | 変更内容                                                                                           |
| ----------------------------------- | -------------------------------------------------------------------------------------------------- |
| `app/services/cumulative_buffer.py` | `update_transcription()` と `force_finalize_pending_text()` のロジックをタイムスタンプベースに変更 |

UIファイル（`ui-controller.js`）は変更不要。`new_confirmed_segments` の構造は変わらない。

---

## 削除できるもの（移行完了後）

| 対象                                          | 理由                                   |
| --------------------------------------------- | -------------------------------------- |
| `_remove_confirmed_overlap()`                 | タイムスタンプベースに移行すれば不要   |
| `break_points` による句読点区切り             | セグメント単位での確定に変わるため不要 |
| `stable_count` のリセットロジックの複雑な条件 | シンプルになる                         |

ただし初回移行時はフォールバックとして残し、動作確認後に削除する。

---

## リスク・注意点

- **0.1秒の余裕マージン**: `abs_start >= last_confirmed_segment_end - 0.1` の `-0.1` は
  Whisperのタイムスタンプ誤差を吸収するためのもの。小さすぎると重複、大きすぎると抜け漏れが発生する。
- **セグメント境界とテキスト境界のずれ**: セグメントのテキストには前後のスペースが含まれる場合がある。`.strip()` で正規化する。
- **安定性チェックの維持**: 「安定したら確定」のロジックは残す。
  タイムスタンプだけでは Whisper の揺れを吸収できない。

---

## 検証方法

```bash
docker compose up --build -d
```

### ログで確認すべき点

```text
# 修正前: テキスト比較が失敗し続けた
重複除外: new_textが短い（X <= Y）→ 新しいバッファと判断

# 修正後: タイムスタンプで判断されるはず
🔍 タイムスタンプ確定: abs_start=12.0s >= last_end=8.0s → 新規セグメント
```

### 画面で確認すべき点

| 項目                 | 期待する結果                 |
| -------------------- | ---------------------------- |
| ブロック間の重複     | 完全に解消される             |
| テキストの抜け漏れ   | 正常な発話が確定されている   |
| タイムスタンプの精度 | 発話タイミングと一致している |

---

## 関連ドキュメント

- `docs/PHASE12.2_PLAN.md`: セグメント単位での文節分割（`last_confirmed_segment_end` の導入）
- `docs/PHASE12.3_PLAN.md`: 重複テキスト問題の修正
