# Phase 10 完了報告: UI刷新 + Zenモード実装

## 概要

ブラウザUI（`app/static/`）とChrome拡張サイドパネル（`extension/sidepanel/`）のデザインを全面刷新。
`design/`フォルダのHTMLデザイン案をベースに、Tailwind CSS（ブラウザUI）と独自CSS（Chrome拡張）でZenモードを含むUI改修を実施。

---

## 実装内容

### タスク1・2: ブラウザUI 通常モード + Zenモード

**変更ファイル:** `app/static/index.html`

- Tailwind CSS CDN + Material Symbols Outlined（Google Fonts）を導入
- 3カラムレイアウトに変更（左サイドバー / 中央テキスト / 右パネル）
- 入力ソース選択をセグメントコントロール（タブUI）に変更
- 処理オプション（ひらがな・翻訳）を右パネルのトグルスイッチUIに変更
- ヘッダーにZenモードトグルボタン（`#zen-toggle`）を配置
- ヘッダーにダークモードトグルボタンを配置
- `body.zen-mode`クラスで以下を切り替え:
  - 左右サイドバーを非表示
  - 中央テキストエリアをmax-width: 640px・margin: autoに変更
  - font-size: 17px、line-height: 1.85に拡大
- `localStorage`でZenモード・ダークモード状態を永続化

**ブラウザUIはTailwind CDN利用可能**（FastAPIが静的ファイルとして配信するため、CSP制約なし）

---

### タスク3・4: Chrome拡張サイドパネル刷新 + Zenモード

**変更ファイル:**

- `extension/sidepanel/sidepanel.html` — 全面書き換え
- `extension/sidepanel/css/sidepanel.css` — iOS風デザインCSSに全面書き換え
- `extension/sidepanel/js/zen-mode.js` — 新規作成

**デザイン:**

- iOS風カード（`border-radius: 2rem`、柔らかいシャドウ）
- 背景色 `#f8fafc`（白に近いグレー）
- Material Symbols Outlined アイコン使用
- ヘッダー: ロゴ・ステータスバッジ・Zenトグルボタン
- コントロールカード: 処理オプション（トグルスイッチ）・音量メーター・操作ボタンを1枚のカードに統合
- 操作ボタン: 丸型アイコンボタン（開始・停止・ダウンロード）
- ひらがな・翻訳・パフォーマンス情報は個別カード

**Zenモード:**

- `#zen-toggle`ボタンでトグル
- `body.zen-mode`クラスで`#controls-section`・`#perf-section`を非表示
- 文字起こしテキストをfont-size: 16px・line-height: 1.85に拡大
- `chrome.storage.local`でZenモード状態を永続化（`js/zen-mode.js`）

---

## Chrome拡張のCSP制約対応

### 問題

Manifest V3のContent Security Policy（`script-src 'self'`）により以下がブロックされた:

1. **外部CDNスクリプト禁止**: `https://cdn.tailwindcss.com` の読み込みがブロック
2. **インラインスクリプト禁止**: `<script>tailwind.config = ...</script>` や Zenモードのインラインスクリプトがブロック

```text
Loading the script 'https://cdn.tailwindcss.com/...' violates the following
Content Security Policy directive: "script-src 'self'"

Executing inline script violates the following Content Security Policy directive 'script-src 'self''
```

### 解決策

| 問題                                  | 対処                                                       |
| ------------------------------------- | ---------------------------------------------------------- |
| Tailwind CDN読み込みエラー            | Tailwind CDNを削除し、必要なCSSを`sidepanel.css`に直接記述 |
| `tailwind.config`インラインスクリプト | Tailwindごと削除したため不要に                             |
| Zenモードのインラインスクリプト       | `js/zen-mode.js`として外部ファイルに分離                   |

**ポイント**: Chrome拡張では外部CDNスクリプト・インラインスクリプトは一切使用不可。
必要なCSSは`sidepanel.css`に手書きし、JSは必ず外部ファイル（`src=""`）として読み込む。

---

## 維持した既存id属性（JSとの互換性）

### ブラウザUI（`app.js` / `ui-controller.js`が参照）

- `#start-button`, `#stop-button`, `#download-button`
- `#enable-hiragana`, `#enable-translation`
- `#transcription-text`, `#hiragana-text`, `#translation-text`
- `#status-text`, `#volume-bar`, `#toast-container`, `#trim-indicator`

### Chrome拡張（`sidepanel.js` / `ui-controller.js`が参照）

- `#start-button`, `#stop-button`, `#download-button`
- `#enable-hiragana`, `#enable-translation`
- `#confirmed-text`, `#tentative-text`
- `#confirmed-translation`, `#tentative-translation`
- `#hiragana-text`、`.hiragana-results`（クラス）、`#translation-section`
- `#status-text`, `#volume-bar`, `#toast-container`, `#trim-indicator`
- `#performance-info`, `#perf-transcription`, `#perf-normalization`, `#perf-translation`
- `#perf-total`, `#perf-recording`
- `#perf-bar-transcription`, `#perf-bar-normalization`, `#perf-bar-translation`
- `#perf-item-transcription`, `#perf-item-normalization`, `#perf-item-translation`

---

## 変更ファイル一覧

| ファイル                                | 変更内容                                     |
| --------------------------------------- | -------------------------------------------- |
| `app/static/index.html`                 | 全面書き換え（3カラムレイアウト、Zenモード） |
| `extension/sidepanel/sidepanel.html`    | 全面書き換え（iOS風デザイン、CSP対応）       |
| `extension/sidepanel/css/sidepanel.css` | 全面書き換え（iOS風デザインCSS）             |
| `extension/sidepanel/js/zen-mode.js`    | 新規作成（Zenモードトグル処理）              |

---

## 参考デザインファイル

- `design/browser_code_1.html` — ブラウザUI 通常モードの参考
- `design/browser_code_2.html` — ブラウザUI Zenモードの参考
- `design/mobile_code_1.html` — Chrome拡張サイドパネルの参考
