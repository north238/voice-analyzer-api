# Phase 8: ハルシネーション対策とテキスト管理の再設計 - 実装計画

## 概要

Phase 4.1で導入した累積バッファ方式において、Phase 6.6/7.0でのトリミング機能追加により設計の前提が崩れた。Phase 8では、ハルシネーション対策と確定/暫定テキストの管理方法を再設計する。

## 実装タスク

### タスク1: 繰り返しパターンの検出強化 ✅ 完了

**ファイル:** `app/services/text_filter.py`

**実装内容:**

```python
def _has_repeated_phrases(text: str, min_phrase_len: int = 3, max_phrase_len: int = 15) -> bool:
    """繰り返し単語・フレーズが異常に多いかチェック

    N-gram（3〜15文字）で繰り返しパターンを検出。
    全体の60%以上を同一のN-gramが占める場合は無効と判定。
    """
```

**テスト結果:**

```text
✅ 繰り返し単語の検出: "ゲンゴロラング ゲンゴロラング..." → False
✅ 正常なテキストの通過: "こんにちは。今日は良い天気です。" → True
✅ 同一文字の繰り返し検出: "あああああああ..." → False
✅ 繰り返し文の検出: "プログラミング言語を学びます。プログラミング..." → False
```

**効果:**

- ハルシネーションの早期検出
- 無効なテキストが`initial_prompt`に含まれるのを防止

### タスク2: initial_promptのクリーンアップ ✅ 完了

**ファイル:** `app/services/cumulative_buffer.py`

**実装内容:**

```python
def get_initial_prompt(self) -> Optional[str]:
    """次回の文字起こし用initial_promptを取得

    確定済みテキストの末尾を返す（文脈として使用）
    ハルシネーション対策: 無効なテキストは除外
    """
    # ... 既存処理 ...

    # ハルシネーション対策: 無効なテキスト（繰り返しパターン等）は除外
    if prompt and not is_valid_text(prompt):
        logger.warning("⚠️ initial_promptに無効なテキストを検出、除外します")
        return None
```

**効果:**

- ハルシネーションの連鎖を防止

### タスク3: バッファ長の制限 ✅ 完了

**ファイル:** `app/config.py`, `app/services/cumulative_buffer.py`

**変更内容:**

```python
# 30秒 → 25秒に変更
CUMULATIVE_MAX_AUDIO_SECONDS: float = 25.0
```

**理由:**

```text
25秒でトリミング開始
  ↓
文字起こし処理（16秒）
  ↓
その間にチャンク追加（+9秒）
  ↓
実際のバッファ: 25 - 削除分 + 9 = 約27〜29秒
  ↓
30秒以下をキープ ✅
```

**効果:**

- Whisperの30秒制限を超えない
- ハルシネーションの発生を防止
- 処理速度と精度の向上

### タスク4: 確定テキストの独立管理 🔄 実装中

**ファイル:** `app/services/cumulative_buffer.py`

**現在の問題:**

```python
elif self.confirmed_text:
    # 確定テキストが含まれていない → 認識結果が大きく変わった
    tentative = new_text  # ❌ 問題: 確定と暫定が重複
```

**修正方針:**

確定テキストをバッファとは独立に管理し、全体テキストを蓄積型にする。

**設計:**

```python
confirmed_text:
  - セッション開始からの全確定テキスト
  - トリミングされても消えない
  - 常に追記のみ（削除されない）
  - バッファとは独立

tentative_text:
  - 現在のバッファの文字起こし結果から確定済みを除いた部分
  - 変更される可能性がある

displayed_text = confirmed_text + tentative_text
```

**修正箇所:**

1. **`update_transcription`メソッドの修正**

   ```python
   def update_transcription(self, new_text: str, ...) -> TranscriptionResult:
       # 確定テキストとバッファの文字起こし結果は独立

       # 安定性チェック（同じ結果が連続）
       if new_text == self.previous_full_text:
           self.stable_count += 1
           if self.stable_count >= self.config.stable_text_threshold:
               # 適切な区切りまでを確定に追加
               newly_confirmed = extract_confirmed_part(new_text)
               self.confirmed_text += newly_confirmed  # 追記のみ

       # 暫定テキストの計算
       if self.confirmed_text and self.confirmed_text in new_text:
           # バッファに確定テキストが含まれる場合
           idx = new_text.find(self.confirmed_text) + len(self.confirmed_text)
           tentative = new_text[idx:]
       else:
           # バッファがトリミングされた場合
           # 新しいバッファの内容を暫定として扱う
           tentative = new_text

       # 全体テキスト = 確定 + 暫定（常に連続）
       full_text = self.confirmed_text + tentative

       return TranscriptionResult(
           confirmed_text=self.confirmed_text,
           tentative_text=tentative,
           full_text=full_text,  # ← 修正ポイント
           ...
       )
   ```

2. **`force_finalize_pending_text`メソッドの修正**

   ```python
   def force_finalize_pending_text(self, hiragana_converter=None) -> bool:
       """暫定テキストを強制的に確定テキストに移行

       バッファトリミング時に呼ばれる。
       確定テキストは追記のみで、削除されない。
       """
       if not self.last_transcription:
           return False

       # 確定済みテキストを除いた残り（暫定部分）
       if self.confirmed_text in self.last_transcription:
           remaining = self.last_transcription[len(self.confirmed_text):]
       else:
           # バッファがトリミングされた場合、全体を確定に追加
           remaining = self.last_transcription

       if not remaining:
           return False

       # 暫定テキストを確定に追加（追記のみ）
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

3. **確定テキストのリセット防止**
   - トリミング時も確定テキストは削除しない
   - `confirmed_text`は`audio_chunks`とは独立

**期待される動作:**

```text
[初期状態]
バッファ: "ようこそ。今日は"
確定: ""
暫定: "ようこそ。今日は"
表示: "ようこそ。今日は"

[安定して確定]
バッファ: "ようこそ。今日はGoについて"
確定: "ようこそ。今日は"
暫定: "Goについて"
表示: "ようこそ。今日はGoについて"

[トリミング実行]
バッファ: "Goについて説明します" (古いチャンク削除)
確定: "ようこそ。今日はGoについて"  ← 保持！
暫定: "説明します"
表示: "ようこそ。今日はGoについて説明します"  ← 連続！

[さらに発話]
バッファ: "説明します。Goは高速です"
確定: "ようこそ。今日はGoについて説明します。"  ← 追記
暫定: "Goは高速です"
表示: "ようこそ。今日はGoについて説明します。Goは高速です"
```

**テスト項目:**

- [ ] 初期状態で暫定テキストが正しく表示される
- [ ] 安定性チェックで確定テキストに移行する
- [ ] トリミング時に確定テキストが保持される
- [ ] トリミング後も全体テキストが連続している
- [ ] 確定テキストと暫定テキストが重複しない
- [ ] セッション終了時に全体テキストが正しく保存される

### タスク5: UI改善（オプション）

**実装済み（未コミット）:**

- トリミングインジケーター表示
- パフォーマンス情報の詳細化
- 確定移行時のハイライト効果

**今回のスコープ:**

- タスク4が完了してから再度評価
- 動作確認後にコミット

## 実装順序

1. ✅ タスク1: 繰り返しパターン検出（完了）
2. ✅ タスク2: initial_promptクリーンアップ（完了）
3. ✅ タスク3: バッファ長制限（完了）
4. 🔄 タスク4: 確定テキスト独立管理（実装中）
5. ⏸️ タスク5: UI改善（保留）

## テスト計画

### ユニットテスト

1. **text_filter.py**

   ```bash
   # 繰り返しパターンの検出テスト
   docker compose exec voice-analyzer python3 -c "
   from services.text_filter import is_valid_text

   test_cases = [
       ('ゲンゴロラング ' * 20, False, '繰り返し単語'),
       ('正常なテキストです', True, '正常'),
   ]

   for text, expected, desc in test_cases:
       result = is_valid_text(text)
       print(f'{"✅" if result == expected else "❌"} {desc}')
   "
   ```

2. **cumulative_buffer.py**

   ```python
   # 確定テキストの独立管理テスト
   def test_confirmed_text_persistence():
       buffer = CumulativeBuffer(config)

       # 初期文字起こし
       result1 = buffer.update_transcription("ようこそ")
       assert result1.confirmed_text == ""
       assert result1.tentative_text == "ようこそ"

       # 安定して確定
       result2 = buffer.update_transcription("ようこそ")
       # ... 安定性チェック

       # トリミング実行
       buffer._trim_buffer_if_needed()

       # 新しい文字起こし
       result3 = buffer.update_transcription("こんにちは")
       assert "ようこそ" in result3.confirmed_text  # 確定テキストは保持
       assert result3.full_text == result3.confirmed_text + result3.tentative_text
   ```

### 統合テスト

```bash
# 長時間セッション（60秒以上）
# - バッファが複数回トリミングされる
# - 確定テキストが失われない
# - 全体テキストが連続している

python client/realtime_client.py --cumulative
# 1分以上話し続ける
# 確定テキスト（白色）が増え続けることを確認
# 暫定テキスト（グレー）がバッファの内容を表示することを確認
```

### リグレッションテスト

- Phase 4.1の基本機能が維持されている
- Phase 6.6のバッファトリミングが動作している
- Phase 7.0のトリミングタイミングが正しい

## 成功基準

- ✅ ハルシネーション（繰り返しパターン）が検出される
- ✅ バッファが30秒以下に保たれる
- [ ] 確定テキストと暫定テキストが重複しない
- [ ] トリミング後も全体テキストが連続している
- [ ] セッション全体の文字起こし履歴が保持される
- [ ] 一般的な文字起こしツールと同等のユーザー体験

## 完了条件

1. タスク1〜4が完了
2. 全テストが成功
3. 実機で60秒以上の音声で動作確認
4. ドキュメント（PHASE8_COMPLETION.md）作成
5. コミット＆プッシュ

## 参考資料

- Phase 4.1完了報告: `docs/PHASE4.1_COMPLETION.md`
- Phase 6.6完了報告: `docs/PHASE6.6_COMPLETION.md`
- Phase 7.0完了報告: `docs/PHASE7_COMPLETION.md`
- Whisper仕様: `docs/WHISPER_SPECIFICATIONS.md`
