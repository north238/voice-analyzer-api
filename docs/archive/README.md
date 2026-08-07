# アーカイブ

ブラウザUI（`app/static/`）と Chrome拡張（`extension/`）に関するドキュメントです。
両機能は Phase 15 で廃止し CLI に集約したため、ここへ移しました。

廃止の判断と経緯は [`../PHASE15_DECISION.md`](../PHASE15_DECISION.md) を参照してください。
実装そのもの、および UI のデザインモックアップ（`design/`）は
タグ `v1.0-extension` から参照できます。

```bash
git checkout v1.0-extension
```

## 収録ドキュメント

| ファイル                  | 内容                                                           |
| ------------------------- | -------------------------------------------------------------- |
| `PHASE5.1_COMPLETION.md`  | ブラウザUIの動画ファイル対応・タブ共有（YouTube等）            |
| `PHASE5.5_COMPLETION.md`  | ブラウザUIのバグ修正（ダウンロードボタン活性化ほか）           |
| `PHASE6.2_COMPLETION.md`  | ブラウザUIのChrome拡張機能化（`chrome.tabCapture` 統合）       |
| `PHASE6.3_COMPLETION.md`  | Chrome拡張のアイコン画像デザイン改善                           |
| `PHASE6.5_COMPLETION.md`  | セッション終了タイムアウト問題の修正（`forceFinalize()` 実装） |
| `PHASE8.UI_COMPLETION.md` | 確定移行ハイライトアニメーション等の体験改善                   |
| `PHASE9_COMPLETION.md`    | テキストファイルダウンロード機能のバグ修正                     |
| `PHASE10_COMPLETION.md`   | UI刷新とZenモード実装                                          |
| `PHASE11_COMPLETION.md`   | ブラウザ版レスポンシブ対応 完了報告                            |
| `PHASE11_PLAN.md`         | ブラウザ版レスポンシブ対応 実装計画                            |

## 移していないもの

次の2件は UI とサーバー側の内容が混在し、コア部分（タイムスタンプ管理 / Gemini要約）が
CLI 集約後も価値を持つため `docs/` に残しています。

- `PHASE6.4_COMPLETION.md` — 30秒問題の修正（累積バッファの確定ロジック）
- `PHASE13_PLAN.md` — 要約機能の実装（`summarizer.py`）
