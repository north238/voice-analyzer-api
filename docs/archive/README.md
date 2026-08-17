# アーカイブ

**過去の構成のドキュメントです。現行の実装とは一致しません。追加も更新もしません。**

現在のツールはローカル（Mac）で動作する CLI です。
かつては Raspberry Pi 上の API サーバとして動作し、ブラウザUI と Chrome拡張を持っていました。
ここにあるのは、その時代に書かれたドキュメントです。

方針転換の判断と経緯は [`../DECISION_cli_migration.md`](../DECISION_cli_migration.md) を参照してください。

実装そのもの、および UI のデザインモックアップ（`design/`）はタグから参照できます。

| タグ                 | 内容                               |
| -------------------- | ---------------------------------- |
| `v1.0-extension`     | Chrome拡張・ブラウザUIを含む版     |
| `v1.1-full-pipeline` | 翻訳・要約・ひらがな正規化を含む版 |

```bash
git checkout v1.0-extension
```

---

## 読むときの注意

- **文書中のファイルパスは古いままです。** 移動前の `docs/PHASE6.4_COMPLETION.md` のような
  表記が残っていますが、実体は `docs/archive/server/` または `docs/archive/browser/` にあります。
  歴史的記録として書かれた当時のまま残すため、リンクの修正は行っていません
- **記載されているコードの多くは削除済みです。** `cumulative_buffer.py`、`text_filter.py`、
  `async_processor.py`、FastAPI サーバ、WebSocket 層などは現行に存在しません
- 当時の Phase 番号は、`server/` と `browser/` にまたがって振られています
  （例: 5.1 は browser、5.3 は server）。番号の連続性はディレクトリ内では保たれません

---

## `server/` — Raspberry Pi + API サーバ時代

FastAPI サーバ、WebSocket による逐次配信、累積バッファ、翻訳・要約・ひらがな正規化など、
CLI 集約前の実装に関するドキュメントです。

| ファイル                        | 内容                                                     |
| ------------------------------- | -------------------------------------------------------- |
| `IMPLEMENTION_PLAN.md`          | 全体の実装計画（ファイル名の綴りは当時のまま）           |
| `LEARNING_PLAN.md`              | 学習計画                                                 |
| `WHISPER_SPECIFICATIONS.md`     | Whisper の仕様と 30秒セグメント制限                      |
| `PHASE1_COMPLETION.md`          | 基盤構築                                                 |
| `PHASE2_COMPLETION.md`          | 音声認識の実装                                           |
| `PHASE3_PLAN.md` / `_COMPLETION.md` | リアルタイム処理                                     |
| `PHASE4.1_COMPLETION.md`        | パフォーマンス改善                                       |
| `PHASE5.3_COMPLETION.md`        | 句読点挿入処理の削除                                     |
| `PHASE6.4_INVESTIGATION.md` / `_COMPLETION.md` | 30秒問題の調査と修正                      |
| `PHASE6.6_INVESTIGATION.md` / `_PLAN.md` / `_COMPLETION.md` | バッファトリミングの順序問題  |
| `PHASE7_COMPLETION.md`          | トリミングを文字起こし後へ移動                           |
| `PHASE8_INVESTIGATION.md` / `_PLAN.md` / `_COMPLETION.md` | 文脈引き継ぎ                   |
| `PHASE12.1〜12.4_PLAN.md`       | セグメント分割・重複テキストの修正                       |
| `PHASE13_PLAN.md`               | 要約機能（`summarizer.py`）                              |

## `browser/` — ブラウザUI・Chrome拡張

`app/static/` のブラウザUI と `extension/` の Chrome拡張に関するドキュメントです。
両機能は Phase 15 で廃止しました。

| ファイル                  | 内容                                                           |
| ------------------------- | -------------------------------------------------------------- |
| `PHASE5.1_COMPLETION.md`  | 動画ファイル対応・タブ共有（YouTube等）                        |
| `PHASE5.5_COMPLETION.md`  | バグ修正（ダウンロードボタン活性化ほか）                       |
| `PHASE6.2_COMPLETION.md`  | Chrome拡張機能化（`chrome.tabCapture` 統合）                   |
| `PHASE6.3_COMPLETION.md`  | 拡張のアイコン画像デザイン改善                                 |
| `PHASE6.5_COMPLETION.md`  | セッション終了タイムアウト問題の修正（`forceFinalize()`）      |
| `PHASE8.UI_COMPLETION.md` | 確定移行ハイライトアニメーション等の体験改善                   |
| `PHASE9_COMPLETION.md`    | テキストファイルダウンロード機能のバグ修正                     |
| `PHASE10_COMPLETION.md`   | UI刷新と Zenモード実装                                         |
| `PHASE11_PLAN.md` / `_COMPLETION.md` | レスポンシブ対応                                    |
| `PHASE14_PLAN.md`         | 拡張機能の整理                                                 |
