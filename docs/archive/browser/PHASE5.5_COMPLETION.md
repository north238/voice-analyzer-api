# Phase 5.5: バグ修正・UI改善 - 完了報告

**実装日**: 2026年2月1日
**ステータス**: ✅ 完了

## 概要

Phase 5.4のテキストファイル出力機能実装後に発見された複数のバグを修正し、ユーザー体験を改善しました。

## 修正した問題

### 1. ダウンロードボタンの活性化問題

**問題:**
録音を停止して確定テキストに文字が表示されているにも関わらず、ダウンロードボタンが活性化されない。

**原因:**
セッション終了時に暫定テキストが確定テキストに移行される処理で、UIには表示されるが`transcriptionHistory`に記録されていなかった。ダウンロードボタンの活性化条件が`transcriptionHistory.length > 0`のため、履歴が空の場合はボタンが有効にならなかった。

**解決策:**
`ui-controller.js`のセッション終了処理（`updateTranscription`メソッド内）で、最終確定テキストを`transcriptionHistory`に記録するロジックを追加。

**修正箇所:**

- `app/static/js/ui-controller.js:120-147`

```javascript
// 最終的に追加されたテキストを履歴に記録
if (finalText.length > this.currentConfirmedText.length) {
  const addedText = finalText.slice(this.currentConfirmedText.length);
  const timestamp = this.sessionStartTime
    ? (Date.now() - this.sessionStartTime) / 1000
    : 0;

  // ... hiragana, translation も記録

  this.transcriptionHistory.push({
    timestamp: timestamp,
    text: addedText.trim(),
    hiragana: addedHiragana.trim(),
    translation: addedTranslation.trim(),
  });
}
```

### 2. 動画再利用時のcreateMediaElementSourceエラー

**問題:**
動画ファイルを一度読み込んだ後、別の動画の音声を解析しようとすると以下のエラーが発生：

```text
InvalidStateError: Failed to execute 'createMediaElementSource' on 'AudioContext':
HTMLMediaElement already connected previously to a different MediaElementSourceNode.
```

**原因:**
Web Audio APIの制約により、以下の2つの問題が存在：

1. **video要素**: 一度`createMediaElementSource`で接続された要素は再利用不可（Phase 5.1で対応済み）
2. **AudioContext**: 古い`AudioContext`を閉じずに新しいものを作成すると、メモリリークや予期しない動作が発生

**解決策:**

**①AudioContextのクリーンアップ（`audio-capture.js`）:**
`startFromVideo`メソッドで、新しい`AudioContext`を作成する前に既存のものを確実に閉じる処理を追加。

```javascript
// 既存のAudioContextがあれば閉じる
if (this.audioContext) {
  await this.audioContext.close();
  this.audioContext = null;
}
```

**②録音開始時のvideo要素再作成（`app.js`）:**
録音開始のたびにvideo要素を強制的に再作成し、常に新しい要素で`createMediaElementSource`を実行。

```javascript
// video要素を再作成（createMediaElementSourceのエラー回避）
const oldSrc = this.videoElement.src;

// 古い要素を削除
this.videoElement.pause();
this.videoElement.remove();

// 新しい要素を作成
const newVideoElement = document.createElement("video");
newVideoElement.id = "video-player";
newVideoElement.src = oldSrc;
// ... イベントリスナー設定、ロード待機

this.videoElement = newVideoElement;
```

**修正箇所:**

- `app/static/js/audio-capture.js:58-89`
- `app/static/js/app.js:333-390`

### 3. ひらがな正規化がダウンロードに含まれない問題

**問題:**
ひらがな正規化オプションを有効にして文字起こしを実行しても、ダウンロードしたテキストファイルにひらがなテキストが含まれていない。

**原因:**

1. `transcriptionHistory`に`hiragana`フィールドが記録されていなかった
2. セッション終了時に、サーバーからひらがなデータが送られてこない場合の対処が不足
3. `generateTranscriptText`でひらがなテキストを出力する処理がなかった

**解決策:**

**①履歴記録に`hiragana`フィールドを追加:**
確定テキスト追加時とセッション終了時の両方で、ひらがなテキストを履歴に記録。

```javascript
const addedHiragana = newHiraganaConfirmed
  ? newHiraganaConfirmed.slice(this.currentHiraganaConfirmed.length)
  : "";

this.transcriptionHistory.push({
  timestamp: timestamp,
  text: addedText.trim(),
  hiragana: addedHiragana.trim(),
  translation: addedTranslation.trim(),
});
```

**②セッション終了時のローカルひらがな使用:**
サーバーからひらがなデータが来ない場合、ローカルに保持している暫定ひらがなテキストを使用。

```javascript
const localHiraganaFinal =
  this.currentHiraganaConfirmed + this.previousHiraganaTentative;

if (
  newHiraganaConfirmed &&
  newHiraganaConfirmed.length > this.currentHiraganaConfirmed.length
) {
  // サーバーからひらがなデータがある場合
  addedHiragana = newHiraganaConfirmed.slice(
    this.currentHiraganaConfirmed.length,
  );
} else if (localHiraganaFinal.length > this.currentHiraganaConfirmed.length) {
  // サーバーからひらがなデータがない場合は、ローカルのデータを使う
  addedHiragana = localHiraganaFinal.slice(
    this.currentHiraganaConfirmed.length,
  );
}
```

**③ダウンロード時の出力改善:**
処理オプションに応じて、ひらがなテキストと翻訳を出力。

```javascript
// ひらがな正規化がある場合は追加
if (processingOptions.enableHiragana && entry.hiragana) {
  content += `${entry.hiragana}\n`;
}

// 翻訳がある場合は追加
if (processingOptions.enableTranslation && entry.translation) {
  content += `${entry.translation}\n`;
}
```

**修正箇所:**

- `app/static/js/ui-controller.js:191-210` - 履歴記録に`hiragana`追加
- `app/static/js/ui-controller.js:120-147` - セッション終了時の`hiragana`処理
- `app/static/js/ui-controller.js:655-673` - ダウンロード時の出力

### 4. デバッグログの整理

**実施内容:**
問題修正時に追加した詳細なデバッグログを整理し、重要な情報のみを残した。

**削除したログ:**

- 履歴記録時の詳細な内部データ（text, hiragana, translationの個別値）
- ひらがな取得時の詳細情報（サーバー/ローカル使用の表示）
- ダウンロード生成時のすべての詳細ログ

**残したログ:**

- `📝 履歴記録: [3.2s] テキスト内容` - 履歴記録の確認用
- `📝 最終履歴記録: [14.2s] テキスト内容` - セッション終了時の確認用
- その他の重要なログ（接続、エラーなど）

**修正箇所:**

- `app/static/js/ui-controller.js:210, 153, 133-143, 658-683`

## 出力フォーマット

修正後のダウンロードファイルの出力フォーマット：

```text
===========================
文字起こし結果
日時: 2026/02/01 06:52:09
入力ソース: 動画ファイル
処理: ひらがな正規化=ON, 翻訳=ON
===========================

[00:00:16] ワークライフバランス 仕事と指生活の両面でうまくバランスを取ることはとても大切なことです
わーくらいふばらんすしごととゆびせいかつのりょうめんでうまくばらんすをとることはとてもたいせつなことです
It's very important to balance work life with work and finger life.

[00:00:23] 豊かな個性を持ち、家庭や地域生活などにおいても人生の充実を図ること
ゆたかなこせいをもちかていやちいきせいかつなどにおいてもじんせいのじゅうじつをはかること
It is important to have a rich personality and to enrich life in the home and community.
```

## テスト結果

### ダウンロードボタンの活性化

- ✅ 確定テキストのみの場合: ボタンが有効化
- ✅ 暫定→確定移行時: ボタンが有効化
- ✅ 空データの場合: ボタンは無効のまま

### 動画再利用

- ✅ 同じ動画で「開始→停止→開始」: エラーなし
- ✅ 異なる動画に切り替えて「開始→停止→開始」: エラーなし
- ✅ サンプル動画の連続切り替え: エラーなし
- ✅ 動画ロード待機処理: 正常動作

### ひらがな正規化のダウンロード

- ✅ ひらがな正規化ON: ファイルに含まれる
- ✅ ひらがな正規化OFF: ファイルに含まれない
- ✅ 翻訳ON: ファイルに含まれる
- ✅ 翻訳OFF: ファイルに含まれない

## 変更ファイル

```text
app/static/js/
├── ui-controller.js     # ダウンロードボタン、ひらがな履歴、ログ整理
├── audio-capture.js     # AudioContextクリーンアップ
└── app.js               # video要素再作成、ロード待機
```

## 成功基準（すべて達成）

1. ✅ 録音停止後、確定テキストがあればダウンロードボタンが有効化される
2. ✅ 同じ動画で複数回「開始→停止」を繰り返してもエラーが発生しない
3. ✅ ひらがな正規化を有効にした場合、ダウンロードファイルにひらがなテキストが含まれる
4. ✅ 処理オプションに応じて、適切なデータがダウンロードファイルに含まれる
5. ✅ コンソールログがすっきりして、重要な情報のみが表示される

## 技術的な詳細

### Web Audio APIの制約

**問題の本質:**
一度`createMediaElementSource`で接続されたHTMLMediaElementは、AudioContextを閉じても二度と使えない。

**解決のアプローチ:**

1. **video要素**: 録音開始のたびに新しい要素を作成
2. **AudioContext**: 既存のものを確実に閉じてから新しいものを作成

### 履歴データの構造

```javascript
{
    timestamp: 14.2,           // セッション開始からの経過秒数
    text: "原文テキスト",       // 文字起こし結果
    hiragana: "ひらがな",       // ひらがな正規化（オプション）
    translation: "English"      // 翻訳（オプション）
}
```

## 既知の制限

- なし（すべての問題を解決）

## 次のステップ（Phase 6候補）

現在、Phase 0〜5.5まですべて完了。次の拡張候補：

- **Phase 6.1**: 字幕ファイル出力（SRT/VTT形式）
- **Phase 6.2**: Chrome拡張機能化
- **Phase 6.3**: Safari対応
- **Phase 6.4**: HTTPS対応・本番環境対応
- **Phase 7**: 複数言語対応（英語→日本語など）

---

**Phase 5.5 完了**: 2026年2月1日
**次のフェーズ**: Phase 6（拡張機能）
