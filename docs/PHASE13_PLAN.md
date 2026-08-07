# Phase 13: 要約機能の実装

## 概要

録音終了後の確定テキストを外部API（Gemini 2.0 Flash）で要約する機能を追加する。

## トリガー

| パターン | タイミング                | 動作                                          |
| -------- | ------------------------- | --------------------------------------------- |
| 手動     | 「要約」ボタン押下        | 確定テキスト全文をAPIに送信し、要約結果を表示 |
| 自動     | 要約トグルON + 録音停止時 | session_end処理内で自動的に要約APIを呼び出す  |

## API選定

| API               | モデル        | 入力 ($/1M tokens) | 出力 ($/1M tokens) | 備考                                |
| ----------------- | ------------- | ------------------ | ------------------ | ----------------------------------- |
| **Google Gemini** | **2.0 Flash** | **$0.10**          | **$0.40**          | **採用: 最安。無料枠あり（15RPM）** |
| OpenAI            | GPT-4o-mini   | $0.15              | $0.60              | 次点                                |
| Anthropic         | Haiku 4.5     | $0.80              | $4.00              | 高コスト                            |

---

## アーキテクチャ

### 処理フロー

```text
[Chrome拡張 / ブラウザUI]
    │
    ├─ パターン1: 「要約」ボタン押下
    │   └─ POST /summarize { text: "確定テキスト全文" }
    │
    └─ パターン2: 要約トグルON + 録音停止
        └─ サーバー側 finalize_cumulative_session() 内で自動実行
            └─ session_end レスポンスに summary フィールドを追加
    │
    ▼
[FastAPI サーバー]
    │
    POST /summarize  ← REST エンドポイント（新規）
    │
    ▼
[app/services/summarizer.py]  ← 要約サービス（新規）
    │
    └─ Google Gemini API (generativelanguage.googleapis.com)
        モデル: gemini-2.0-flash
    │
    ▼
[レスポンス]
    { "summary": "要約テキスト" }
```

### session_end内の自動要約フロー

```python
# finalize_cumulative_session() 内
if options.get("summary", False) and final_result.confirmed_text:
    summary = await summarize_text(final_result.confirmed_text)
    response_data["summary"] = summary
```

---

## 変更ファイル一覧

| #   | ファイル                                     | 変更種別 | 内容                                                         |
| --- | -------------------------------------------- | -------- | ------------------------------------------------------------ |
| 1   | `app/config.py`                              | 修正     | Gemini API設定追加                                           |
| 2   | `app/services/summarizer.py`                 | **新規** | 要約サービス（Gemini API呼び出し）                           |
| 3   | `app/main.py`                                | 修正     | POST /summarize エンドポイント追加 + session_end内の自動要約 |
| 4   | `extension/sidepanel/sidepanel.html`         | 修正     | 要約表示エリア + 要約ボタン追加                              |
| 5   | `extension/sidepanel/sidepanel.js`           | 修正     | 要約トリガー処理追加                                         |
| 6   | `extension/sidepanel/css/sidepanel.css`      | 修正     | 要約エリアのスタイル追加                                     |
| 7   | `extension/sidepanel/js/ui-controller.js`    | 修正     | 要約表示メソッド追加                                         |
| 8   | `extension/sidepanel/js/websocket-client.js` | 修正     | session_endの要約データ処理                                  |
| 9   | `extension/settings/settings.html`           | 修正     | Gemini APIキー設定欄追加                                     |
| 10  | `extension/settings/settings.js`             | 修正     | APIキーの保存/読み込み                                       |
| 11  | `requirements.txt` or `Dockerfile`           | 修正     | google-generativeai パッケージ追加                           |

---

## 実装詳細

### 1. config.py - Gemini API設定

```python
# Gemini要約設定（Phase 13追加）
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_MAX_OUTPUT_TOKENS: int = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "512"))
GEMINI_TEMPERATURE: float = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
```

### 2. summarizer.py - 要約サービス（新規）

```python
"""
要約サービス
Google Gemini APIを使用してテキストを要約する
"""

import google.generativeai as genai
from config import settings
from utils.logger import logger

# システムプロンプト
SUMMARY_SYSTEM_PROMPT = """あなたは日本語の文字起こしテキストを要約する専門家です。

【タスク】
音声の文字起こし結果を簡潔に要約してください。

【ルール】
1. 日本語で出力すること
2. 要点を箇条書きで整理すること
3. 元のテキストの意味を損なわないこと
4. 要約は元のテキストの1/3程度の長さにすること
5. フィラー（えー、あのー等）は除去すること"""


def _get_gemini_model():
    """Geminiモデルを取得"""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEYが設定されていません")

    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(
        settings.GEMINI_MODEL,
        generation_config=genai.GenerationConfig(
            max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
            temperature=settings.GEMINI_TEMPERATURE,
        ),
        system_instruction=SUMMARY_SYSTEM_PROMPT,
    )


async def summarize_text(text: str) -> str:
    """
    テキストを要約する

    Args:
        text: 要約対象のテキスト

    Returns:
        str: 要約結果
    """
    if not text or not text.strip():
        return ""

    try:
        model = _get_gemini_model()
        response = await model.generate_content_async(
            f"以下の文字起こしテキストを要約してください:\n\n{text}"
        )
        summary = response.text.strip()
        logger.info(f"📋 要約完了: {len(summary)}文字")
        return summary

    except Exception as e:
        logger.error(f"❌ 要約エラー: {e}")
        raise
```

### 3. main.py - エンドポイント追加

#### 3a. POST /summarize（手動要約用）

```python
class SummarizeRequest(BaseModel):
    text: str

@app.post("/summarize")
async def summarize(request: SummarizeRequest):
    """テキストを要約するエンドポイント"""
    try:
        if not request.text or not request.text.strip():
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "テキストが空です"},
            )

        from services.summarizer import summarize_text
        summary = await summarize_text(request.text)

        return JSONResponse(
            status_code=200,
            content={"status": "success", "summary": summary},
        )

    except ValueError as e:
        # APIキー未設定等
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)},
        )
    except Exception as e:
        logger.exception("❌ 要約処理中にエラー発生")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "要約処理中にエラーが発生しました", "detail": str(e)},
        )
```

#### 3b. finalize_cumulative_session()への要約追加

```python
# 既存のfinalize_cumulative_session()内に追加

# 要約（オプション）: 確定テキスト全体を一括要約
summary_text = ""
if options.get("summary", False) and final_result.confirmed_text:
    try:
        await ws_manager.send_progress(session_id, "summarizing", "要約中...", 0)
        from services.summarizer import summarize_text
        summary_text = await summarize_text(final_result.confirmed_text)
        logger.info(f"📋 要約完了: {len(summary_text)}文字")
    except Exception as e:
        logger.error(f"❌ 要約エラー（スキップ）: {e}")
        summary_text = ""

# response_dataに追加
if options.get("summary", False):
    response_data["summary"] = summary_text
```

### 4. Chrome拡張 - UI変更

#### 4a. sidepanel.html - 要約表示エリア追加

文字起こしカードの下、タブカードの上に要約カードを追加:

```html
<!-- 要約カード -->
<div class="ios-card summary-card" id="summary-card" style="display: none;">
  <div class="summary-header">
    <div class="summary-title">
      <span class="material-symbols-outlined" style="font-size:16px;"
        >summarize</span
      >
      <span>要約</span>
    </div>
    <button id="summary-button" class="btn-icon" disabled title="要約">
      <span class="material-symbols-outlined" style="font-size:18px;"
        >auto_awesome</span
      >
    </button>
  </div>
  <div id="summary-text" class="summary-body custom-scrollbar"></div>
  <div id="summary-loading" class="summary-loading" style="display: none;">
    <span class="material-symbols-outlined rotating">progress_activity</span>
    <span>要約を生成中...</span>
  </div>
</div>
```

#### 4b. sidepanel.js - 要約処理

```javascript
// 初期化時
this.processingOptions = {
    enableHiragana: false,
    enableTranslation: false,
    enableSummary: false,     // 追加
};

// 要約ボタンのイベントリスナー
document.getElementById("summary-button").addEventListener("click", () => {
    this.requestSummary();
});

// session_endイベントハンドラ内
this.wsClient.on("session_end", (data) => {
    // ... 既存処理 ...

    // 自動要約結果の表示
    if (data.summary) {
        this.uiController.showSummary(data.summary);
    }

    // 要約ボタンを有効化（手動要約用）
    if (this.uiController.transcriptionHistory.length > 0) {
        document.getElementById("summary-button").disabled = false;
    }
});

// 手動要約リクエスト
async requestSummary() {
    const confirmedText = this.uiController.getConfirmedText();
    if (!confirmedText) {
        this.uiController.showToast("要約するテキストがありません", "warning");
        return;
    }

    this.uiController.showSummaryLoading(true);

    try {
        // HTTP APIサーバーURLを構築（wsをhttpに変換）
        const httpUrl = this.apiServerUrl
            .replace('ws://', 'http://')
            .replace('wss://', 'https://');

        const response = await fetch(`${httpUrl}/summarize`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: confirmedText }),
        });

        const result = await response.json();

        if (result.status === 'success') {
            this.uiController.showSummary(result.summary);
        } else {
            this.uiController.showToast(result.message || "要約に失敗しました", "error");
        }
    } catch (error) {
        console.error("要約エラー:", error);
        this.uiController.showToast("要約リクエストに失敗しました", "error");
    } finally {
        this.uiController.showSummaryLoading(false);
    }
}
```

### 5. 設定画面 - APIキー入力

#### 5a. settings.html

上級者向け機能セクションの後に追加:

```html
<div class="section">
  <h2>AI要約機能</h2>
  <div class="form-group">
    <label for="geminiApiKey">Gemini APIキー</label>
    <input type="text" id="geminiApiKey" placeholder="AIza..." />
    <p class="help-text">
      Google AI Studioで取得したAPIキーを入力してください。
      <a href="https://aistudio.google.com/apikey" target="_blank"
        >APIキーを取得</a
      >
    </p>
  </div>
</div>
```

#### 5b. settings.js

```javascript
const DEFAULT_CONFIG = {
  apiServerUrl: "ws://localhost:5001",
  showAdvancedFeatures: false,
  defaultHiragana: false,
  defaultTranslation: false,
  geminiApiKey: "", // 追加
};
```

### 6. APIキーの受け渡し方式

Chrome拡張の設定に保存したGemini APIキーをサーバーに渡す方法:

**方式A: サーバー側の環境変数（推奨）**

- `docker-compose.yml` の `environment` に `GEMINI_API_KEY` を設定
- Chrome拡張からは設定不要（サーバー管理者が設定）
- セキュリティが高い（キーがクライアントに露出しない）

**方式B: Chrome拡張から都度送信**

- 要約リクエスト時にヘッダーまたはボディでAPIキーを送信
- ユーザーごとに異なるキーを使える
- キーがネットワーク上を流れる（localhost利用なら問題なし）

**→ 方式Aを基本とし、方式Bも補助的にサポートする**

```python
# main.py - /summarize エンドポイント
# 1. リクエストにAPIキーがあればそちらを優先
# 2. なければ環境変数のGEMINI_API_KEYを使用

class SummarizeRequest(BaseModel):
    text: str
    api_key: Optional[str] = None  # クライアントから直接指定も可能
```

```python
# summarizer.py
async def summarize_text(text: str, api_key: Optional[str] = None) -> str:
    key = api_key or settings.GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_API_KEYが設定されていません")
    # ...
```

---

## パッケージ依存

### 追加パッケージ

```text
google-generativeai>=0.8.0
```

Dockerfileの`pip install`に追加、またはrequirements.txtに追記する。

---

## 設定一覧

| 環境変数                   | デフォルト         | 説明                          |
| -------------------------- | ------------------ | ----------------------------- |
| `GEMINI_API_KEY`           | `""`               | Google Gemini APIキー（必須） |
| `GEMINI_MODEL`             | `gemini-2.0-flash` | 使用するGeminiモデル          |
| `GEMINI_MAX_OUTPUT_TOKENS` | `512`              | 最大出力トークン数            |
| `GEMINI_TEMPERATURE`       | `0.3`              | 生成の温度パラメータ          |

---

## UIデザイン

### 要約カードの表示タイミング

1. **初期状態**: 非表示（`display: none`）
2. **録音停止後（テキストあり）**: 要約ボタン付きで表示
3. **要約生成中**: ローディングインジケーター表示
4. **要約完了**: 要約テキスト表示

### レイアウト（サイドパネル）

```text
┌─────────────────────────┐
│  ZenVoice          [Zen]│  ← ヘッダー
├─────────────────────────┤
│                         │
│  確定テキスト...         │  ← 文字起こしカード
│  暫定テキスト...         │
│                         │
│  [▶] 録音中... [📥][🔊]│
├─────────────────────────┤
│  📋 要約     [✨]       │  ← 要約カード（録音停止後に表示）
│  ・要点1                │
│  ・要点2                │
│  ・要点3                │
├─────────────────────────┤
│  [ひらがな] [翻訳]      │  ← タブカード（上級者向け）
│  ひらがなテキスト...     │
└─────────────────────────┘
```

---

## 検証方法

1. Docker再ビルド: `docker compose up --build -d`
2. 環境変数に `GEMINI_API_KEY` を設定
3. Chrome拡張でYouTube音声を文字起こし
4. 録音停止後に「要約」ボタンを押して要約結果を確認
5. 要約トグルON + 録音停止で自動要約が動作することを確認
6. APIキー未設定時に適切なエラーメッセージが表示されることを確認
7. 既存テスト: `docker compose exec voice-analyzer pytest /app/tests/ -v`

---

## ロールバック

- 要約機能は完全にオプション（APIキー未設定時は無効）
- 既存の文字起こし・翻訳機能には一切影響しない
- `GEMINI_API_KEY` を空にすれば要約機能は自動的に無効化される

---

## 今後の拡張候補

- 要約の言語切り替え（日本語/英語）
- 要約スタイルの選択（箇条書き/段落/一行）
- 要約結果のダウンロード機能
- リアルタイム要約（一定間隔で中間要約を生成）

---

## Phase 13.1: 要約出力タイミングの修正

### 問題の根本原因

要約ONで録音停止すると、**最終文字起こしと要約が同時に画面に出力される**。
ユーザーが最後の一文を読もうとした瞬間に要約が割り込んでくるため、最後の一文を読むことができない。

**旧実装のフロー（問題あり）:**

```text
[停止クリック]
  → サーバー: Whisper処理 + Gemini API処理（5〜30秒）← 全部待つ
  → session_end に最終文字起こし + 要約を同梱して送信
  → クライアント: 最終文字起こしと要約を同時に受信・表示
     ★ ユーザーは最後の一文を読む間もなく要約が出現する
```

---

### 実施済みの修正

#### サーバー側: `session_end` と `summary_result` を分離送信済み

`app/main.py` の `finalize_cumulative_session()` で、`session_end`（最終文字起こし）を要約処理の**前**に送信するよう変更済み:

```python
# session_end を先に送信（要約を待たない）
await ws_manager.send_json(session_id, response_data)

# 要約は別メッセージとして後から送信
if options.get("summary", False) and final_result.confirmed_text:
    await asyncio.sleep(0.15)
    await ws_manager.send_progress(session_id, "summarizing", "要約中...", 0)
    summary_text = await summarize_text(final_result.confirmed_text)
    await ws_manager.send_json(session_id, {
        "type": "summary_result",
        "summary": summary_text,
    })
```

これにより、ユーザーは Gemini の推論時間（5〜30秒）を待たずに最終文字起こしを受け取れる。

**修正後のサーバーフロー:**

```text
[停止クリック]
  → サーバー: Whisper処理（1〜3秒のみ）
  → session_end 送信 → クライアント: 最終文字起こし表示
  → ユーザーが最後の一文を読む（5〜30秒の余裕）
  → サーバー: Gemini API処理（5〜30秒）
  → summary_result 送信 → クライアント: 要約表示
```

---

### 未解決の問題: クライアント側が要約カードを早期表示している

サーバー側の分離は完了しているが、クライアント側の `stop()` で要約カードのアニメーションが即座に開始されている:

```javascript
// ★ 問題箇所: stop() の中（sidepanel.js / app.js 両方）
if (this.processingOptions.enableSummary) {
  const summaryCard = document.getElementById("summary-card");
  summaryCard.style.display = "";
  summaryCard.classList.add("summary-loading-border"); // 停止クリック直後に出現
}
```

ユーザーが停止ボタンを押した瞬間に要約カードが現れ、最終文字起こしが表示される頃には要約カードのアニメーションが競合している。最後の一文を読もうとする視線が分散される。

**また、`session_end` ハンドラでも要約カードを表示している:**

```javascript
// session_end ハンドラ内
document.getElementById("summary-card").style.display = ""; // ← 要約結果到着前に表示
```

---

### これから実施する修正

#### 方針: 要約カードは `summary_result` 受信時にのみ表示する

ローディング状態を一切見せない。要約テキストが揃ったタイミングで初めてカードを出現させる。
これにより、ユーザーは最終文字起こしを邪魔されずに読むことができる。

**目標フロー:**

```text
[停止クリック]
  → 要約カード: 非表示のまま（何も変化しない）
  → session_end 受信 → 最終文字起こし表示
  → ユーザーが最後の一文を読む（5〜30秒）
  → summary_result 受信 → 要約カードを初めて表示（テキスト込み）
```

#### 修正1: `stop()` から要約カード操作を削除

**対象**: `extension/sidepanel/sidepanel.js`、`app/static/js/app.js`

削除対象:

```javascript
// この処理を削除する
if (this.processingOptions.enableSummary) {
  const summaryCard = document.getElementById("summary-card");
  summaryCard.style.display = "";
  summaryCard.classList.add("summary-loading-border");
}
```

#### 修正2: `session_end` ハンドラから要約カード表示を削除

**対象**: `extension/sidepanel/sidepanel.js`、`app/static/js/app.js`

削除対象:

```javascript
// session_end ハンドラ内のこの処理を削除する
document.getElementById("summary-card").style.display = "";
```

#### 修正3: `summary_result` ハンドラで要約カードを初めて表示

**対象**: `extension/sidepanel/sidepanel.js`、`app/static/js/app.js`（および `ui-controller.js` の `showSummary()`）

`showSummary()` がカードの表示 + テキストセットを一括で行うため、既存の実装で対応済み。
`stop()` と `session_end` から不要な操作を取り除くだけでよい。

```javascript
// summary_result ハンドラ（変更不要、参考）
this.wsClient.on("summary_result", (data) => {
  if (data.summary) {
    this.uiController.showSummary(data.summary); // ここで初めてカード表示
  }
  this.forceCleanup();
});
```

---

### 変更不要なファイル

| ファイル                                | 理由                                         |
| --------------------------------------- | -------------------------------------------- |
| `app/main.py`                           | サーバー側の分離送信は実装済み               |
| `app/static/css/app.css`                | CSS は実装済み（不要になるが残置で問題なし） |
| `extension/sidepanel/css/sidepanel.css` | 同上                                         |
| `*/websocket-client.js`                 | `summary_result` のパース処理は実装済み      |
| `*/ui-controller.js` の `showSummary()` | カード表示 + テキストセットは実装済み        |

---

### 対象ファイル一覧

| #   | ファイル                           | 変更内容                                                                          |
| --- | ---------------------------------- | --------------------------------------------------------------------------------- |
| 1   | `extension/sidepanel/sidepanel.js` | `stop()` から要約カード操作を削除、`session_end` ハンドラから要約カード表示を削除 |
| 2   | `app/static/js/app.js`             | 同上（ブラウザUI版）                                                              |
