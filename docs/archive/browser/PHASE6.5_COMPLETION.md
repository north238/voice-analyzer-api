# Phase 6.5: タイムアウト問題とセッション終了処理の修正

**実施日**: 2026-02-06
**ステータス**: ✅ 完了

## 概要

Chrome拡張機能とブラウザUIにおいて、停止ボタン押下後に暫定テキストが確定テキストに移動しない問題を修正しました。根本原因は、サーバー側の最終処理に時間がかかり、クライアント側の10秒タイムアウトで`session_end`メッセージを受信する前に切断されることでした。

## 問題の詳細

### 1. 暫定テキストが確定テキストに移動しない

**症状**:

- 停止ボタン押下後、暫定テキスト欄にテキストが残ったまま
- ダウンロード時に最後の暫定テキストが含まれない
- 「セッションの接続が切れました」というメッセージが表示される

**ユーザー報告のログ**:

```text
websocket-client.js:82 ⏳ 処理中: transcribing 累積音声を文字起こし中...
sidepanel.js:266 ⚠️ session_end待機タイムアウト。強制切断します。
websocket-client.js:176 🔌 WebSocket切断
```

### 2. タイムアウトの発生

**原因分析**:

クライアント側のタイムライン:

```text
📤 終了メッセージ送信
↓
📨 transcription_update 受信（最後の文字起こし開始）
↓
📦 accumulating
📦 progress（累積音声を文字起こし中...）
↓
⚠️ 10秒タイムアウト → 強制切断
```

サーバー側のタイムライン:

```text
累積文字起こし開始（約6-7秒かかる）
↓
✅ 累積文字起こし完了
↓
🏁 session_end送信（タイムアウト後のため届かない）
```

**根本原因**:

1. サーバー側の最終文字起こし処理に約6-7秒かかる
2. クライアント側のタイムアウトが10秒で短すぎる
3. タイムアウト時に暫定テキストを確定に移動する処理がない

### 3. 30秒問題の表示

**症状**:

- 録音時間が30秒でリセットされる表示になっている
- 実際には`session_elapsed_seconds`が送信されているが、クライアント側のキャッシュが古かった

## 修正内容

### 1. タイムアウト時間の延長

**変更**: 10秒 → 20秒

**ファイル**:

- `extension/sidepanel/sidepanel.js`
- `app/static/js/app.js`

**修正箇所**:

```javascript
// 修正前
setTimeout(() => {
  console.warn("⚠️ session_end待機タイムアウト。強制切断します。");
  this.forceCleanup();
  this.uiController.showToast(
    "タイムアウトにより接続を切断しました",
    "warning",
  );
}, 10000);

// 修正後
setTimeout(() => {
  console.warn("⚠️ session_end待機タイムアウト。強制切断します。");

  // タイムアウト時に暫定テキストを強制的に確定に移行
  this.uiController.forceFinalize();

  this.forceCleanup();
  this.uiController.showToast(
    "タイムアウトにより接続を切断しました",
    "warning",
  );
}, 20000);
```

### 2. 強制確定メソッドの追加

**新規メソッド**: `forceFinalize()`

**ファイル**:

- `extension/sidepanel/js/ui-controller.js`
- `app/static/js/ui-controller.js`

**実装内容**:

```javascript
/**
 * 強制確定処理（タイムアウト時用）
 * 現在の暫定テキストを確定テキストに強制的に移行します。
 */
forceFinalize() {
    console.log("⚠️ 強制確定処理を実行");

    // 暫定テキストが存在する場合のみ処理
    if (this.previousTentativeText) {
        // 暫定テキストを確定テキストに追加
        this.currentConfirmedText += this.previousTentativeText;
        this.confirmedText.textContent = this.currentConfirmedText;

        // 履歴に記録
        const timestamp = this.sessionStartTime
            ? (Date.now() - this.sessionStartTime) / 1000
            : 0;

        this.transcriptionHistory.push({
            timestamp: timestamp,
            text: this.previousTentativeText.trim(),
            hiragana: this.previousHiraganaTentative.trim(),
            translation: this.previousTentativeTranslation.trim()
        });

        console.log(`📝 強制確定履歴記録: [${timestamp.toFixed(1)}s] ${this.previousTentativeText.trim()}`);

        // 暫定テキストをクリア
        this.tentativeText.textContent = "";
        this.previousTentativeText = "";
        this.previousConfirmedText = this.currentConfirmedText;

        console.log("✅ 強制確定完了: 暫定→確定移行");
    }

    // ひらがなの暫定を確定に移行
    if (this.previousHiraganaTentative) {
        this.currentHiraganaConfirmed += this.previousHiraganaTentative;
        this._updateHiraganaDisplay("", this.currentHiraganaConfirmed);
        this.previousHiraganaTentative = "";
    }

    // 翻訳の暫定を確定に移行
    if (this.previousTentativeTranslation && this.confirmedTranslation && this.tentativeTranslation) {
        this.currentConfirmedTranslation += this.previousTentativeTranslation;
        this.confirmedTranslation.textContent = this.currentConfirmedTranslation;
        this.tentativeTranslation.textContent = "";
        this.previousTentativeTranslation = "";
    }
}
```

### 3. `is_final`フラグのチェック追加

**変更**: `data.is_final`もチェックするように修正

**ファイル**:

- `extension/sidepanel/js/ui-controller.js`
- `app/static/js/ui-controller.js`

**修正箇所**:

```javascript
// 修正前
const isSessionEnd = !newTentativeText && this.previousTentativeText;

// 修正後
const isSessionEnd =
  data.is_final || (!newTentativeText && this.previousTentativeText);
```

これにより、サーバーから`is_final: true`が送られた場合も最終確定処理が実行されるようになりました。

## 修正ファイル一覧

### Chrome拡張機能

- ✅ `extension/sidepanel/js/ui-controller.js`
  - 104行目: `is_final`チェック追加
  - 710-755行: `forceFinalize()`メソッド追加

- ✅ `extension/sidepanel/sidepanel.js`
  - 264-273行: タイムアウト20秒 + `forceFinalize()`呼び出し

### ブラウザUI

- ✅ `app/static/js/ui-controller.js`
  - 100行目: `is_final`チェック追加
  - 715-760行: `forceFinalize()`メソッド追加

- ✅ `app/static/js/app.js`
  - 526-535行: タイムアウト20秒 + `forceFinalize()`呼び出し

## テスト結果

### 修正前のログ（問題発生時）

```text
websocket-client.js:82 ⏳ 処理中: transcribing 累積音声を文字起こし中...
sidepanel.js:266 ⚠️ session_end待機タイムアウト。強制切断します。
websocket-client.js:176 🔌 WebSocket切断
websocket-client.js:53 WebSocket接続終了
```

→ `session_end`を受信できず、暫定テキストが残る

### 修正後のログ（正常動作）

```text
📦 録音中: 30.663062 秒
📦 録音中: 33.275878 秒
📦 録音中: 36.273445 秒
📦 録音中: 39.750616 秒
websocket-client.js:71 📨 受信メッセージ: session_end Object
websocket-client.js:111 🏁 セッション終了: Object
ui-controller.js:103 🏁 セッション終了: 暫定テキストを確定に移行
ui-controller.js:151 📝 最終履歴記録: [43.0s] ...
ui-controller.js:194 ✅ 翻訳の暫定→確定移行完了
app.js:298 📥 ダウンロードボタンを有効化しました
```

### 確認事項

✅ **タイムアウトなし**: `session_end`が正常に受信される
✅ **秒数が正しい**: 30秒を超えても増え続ける（30.6秒 → 33.2秒 → 36.2秒 → 39.7秒）
✅ **暫定→確定移行**: 停止後に暫定テキストが確定テキストに移行
✅ **履歴記録**: タイムスタンプ付きで履歴に記録される
✅ **ダウンロード可能**: すべてのテキストがダウンロードできる

## 既知の制限と今後の課題

### 1. 文脈が失われる問題（未解決）

**症状**:
累積バッファが30秒の上限に達すると、古い音声チャンクが削除されます。その結果、削除された部分のテキストも文字起こし結果から消えてしまい、確定テキストに移行していない場合は完全に失われます。

**例**:

```text
1回目: 皆さんおはようございます 今日は2月前か金曜日 時間は5時29分です...
↓
2回目: 時間は5時29分です 金曜日の花金というところで...
       （「皆さんおはようございます 今日は2月前か金曜日」が消失）
↓
3回目: 金用の花金というところで...
       （さらに前半部分が消失）
```

**原因**:

- バッファトリミング（`_trim_buffer_if_needed`）で古いチャンクを削除
- 削除される前にテキストが確定テキストに移行していない

**解決策候補**:

1. **バッファトリミング時に強制確定**（推奨）: 古いチャンクが削除される直前に、その部分のテキストを確定テキストに移行
2. **確定しきい値を下げる**: `stable_text_threshold`を2→1に変更
3. **バッファサイズを増やす**: 30秒→60秒（Whisperの精度に影響）

**対応計画**:
新しいPhaseとして実装を予定（Phase 6.6または7.0）

### 2. サーバー側の処理時間

最後の文字起こし処理に約6-7秒かかるため、タイムアウトを20秒に延長しました。将来的にはサーバー側の最適化も検討できます。

## まとめ

### 達成した改善

1. ✅ **タイムアウト延長**: 10秒→20秒でサーバー処理完了を待てるように
2. ✅ **強制確定処理**: タイムアウト時も暫定テキストが確定テキストに移行
3. ✅ **`is_final`対応**: サーバーからのフラグを正しく処理
4. ✅ **30秒表示問題**: キャッシュクリアで解決（コードは既に修正済み）

### 効果

- 停止ボタン押下後、暫定テキストが確定テキストに正しく移行
- ダウンロードファイルに全てのテキストが含まれる
- タイムアウトエラーが発生しない
- 録音時間が30秒を超えても正しく表示される

### 次のステップ

Phase 6.6/7.0として、バッファトリミング時の文脈保持機能を実装予定。
