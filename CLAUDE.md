# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

完了済みフェーズ:

- Phase 0: バッチ翻訳機能 ✅
- Phase 1: チャンク処理 ✅
- Phase 2: WebSocketストリーミング ✅
- Phase 3: リアルタイム音声入力 ✅
- Phase 4: 処理遅延の最適化 ✅
- Phase 4.1: 累積バッファ方式 ✅
- Phase 5: ブラウザUI実装 ✅
- Phase 5.1: 動画コンテンツ対応 ✅
- Phase 5.2: 処理オプション機能 ✅
- Phase 5.3: 句読点挿入処理の削除 ✅
- Phase 5.4: テキストファイル出力機能 ✅
- Phase 5.5: バグ修正・UI改善 ✅
- Phase 6.2: Chrome拡張機能化 ✅
- Phase 6.3: アイコン画像の改善 ✅
- Phase 6.4: 30秒問題の修正 ✅
- Phase 6.5: タイムアウト問題とセッション終了処理の修正 ✅
- Phase 6.6: バッファトリミング時の文脈保持（部分実装） ✅
- Phase 7.0: バッファトリミング時の文脈保持の完全実装 ✅
- Phase 8: ハルシネーション対策とテキスト管理の再設計 ✅
- Phase 9: ダウンロード機能バグ修正（ひらがな・翻訳の出力） ✅
- Phase 10: UI刷新 + Zenモード実装（ブラウザUI・Chrome拡張） ✅
- Phase 10.5: Chrome拡張UI改善 ✅
  - 上級者向け機能（ひらがな/翻訳）をデフォルト非表示化（`showAdvancedFeatures` フラグ）
  - 設定画面ヘッダーをサイドパネルと統一（graphic_eq + ZenVoice）
  - 拡張機能アイコンを Material Symbols 公式 `graphic_eq` に変更
- Phase 11: ブラウザ版レスポンシブ対応 ✅
  - Tailwind CSS のブレークポイント（`md`, `lg`）でレスポンシブ対応
  - 左サイドバー: `lg` 未満で非表示（`hidden lg:flex`）
  - 右サイドバー: モバイルで縦積み、`md` 以上でサイドバー表示
  - padding・余白をモバイル向けに最適化（`p-5 md:p-8 lg:p-12` 等）
- Phase 12.1: Whisperタイムスタンプのサーバー側伝搬 ✅
- Phase 12.2: Whisperセグメント単位での文節分割 ✅
- Phase 12.3: 重複テキスト問題の修正（stable_countリセット） ✅
- Phase 12.4: newly_confirmed決定ロジックのタイムスタンプベース化 ✅
- Phase 13: 要約機能の実装（Gemini 2.0 Flash / Ollama対応） ✅
- Phase 14: Raspberry Pi デプロイ対応 ✅
  - ARM64対応 Dockerfile 作成（`Dockerfile.arm64`）
  - Pi専用 docker-compose 作成（`docker-compose.pi.yml`）
- Phase 15: ブラウザUI・Chrome拡張の撤退判断 ✅
  - Pi 4 の実測性能（文字起こし 10.9〜17.3秒/回）ではリアルタイムUIが成立しないため、
    ブラウザUI・Chrome拡張を廃止し CLI に集約する判断をした
  - バッファ設定の矛盾（`MAX_AUDIO_SECONDS` < `3秒 × TRANSCRIPTION_INTERVAL`）による
    テキスト欠落バグを修正（`docker-compose.pi.yml`）
  - 拡張側の終了ハンドシェイクの問題は、廃止対象のため意図的に未対応
  - 詳細: `docs/PHASE15_DECISION.md`

---

## 主要機能

### Chrome拡張機能 (Phase 6.2, 6.3, 10.5)

- ワンクリックでタブ音声キャプチャ（chrome.tabCapture API）
- サイドパネルでリアルタイム文字起こし表示
- **上級者向け機能**: 設定画面で `showAdvancedFeatures` をONにした場合のみ、ひらがな正規化・翻訳タブを表示（デフォルトOFF）
- 設定画面でAPIサーバーURL・上級者向け機能のON/OFFを設定可能
- テキストファイル出力機能（タイムスタンプ付き、UTF-8 BOM対応）
- アイコン: Material Symbols `graphic_eq`（青い角丸正方形 + 白いイコライザー）

### ブラウザUI (Phase 5系, Phase 11)

- マイク入力、動画ファイル、タブ共有(YouTube等)の3モード
- リアルタイム文字起こし（確定/暫定テキストの区別）
- 処理オプション: ひらがな正規化、翻訳のオン/オフ切り替え
- 音量メーター、パフォーマンス表示
- テキストファイル出力機能（タイムスタンプ付き、UTF-8 BOM対応）
- レスポンシブ対応（モバイル〜デスクトップ）（Phase 11で実装済み）

### リアルタイム処理 (Phase 4系)

- 処理時間: 1.7〜2.2秒/チャンク (約43%削減達成)
- Whisperモデル: small (beam_size=1)
- 翻訳: num_beams=4に最適化
- 累積バッファによる文脈保持

### 負荷軽減 (Phase 5.2)

- 文字起こしのみ: 1.3〜1.6秒
- 翻訳オフ: 約30%削減
- 全てオフ: 約40%削減

## プロジェクト概要

音声を受け取り「文字起こし → フィルタリング → ひらがな正規化 → 翻訳」を行うFastAPI製の日本語音声解析API。

### アクセス方法

```bash
# サーバー起動（Raspberry Pi）
docker compose -f docker-compose.pi.yml up -d

# Chrome拡張機能（推奨）
# 1. chrome://extensions/ を開く
# 2. 「デベロッパーモード」を有効化
# 3. 「パッケージ化されていない拡張機能を読み込む」をクリック
# 4. extension/ フォルダを選択
# 5. 拡張機能アイコンをクリックしてサイドパネルを表示

# ブラウザUI（従来版）
open http://localhost:5001/static/index.html

# CLIクライアント (累積バッファモード)
python client/realtime_client.py --cumulative
```

## 開発コマンド

### Docker開発

```bash
# ビルド・起動（Raspberry Pi）
docker compose -f docker-compose.pi.yml up --build -d

# ログ確認
docker compose -f docker-compose.pi.yml logs -f voice-analyzer

# 停止
docker compose -f docker-compose.pi.yml down
```

### テスト実行

```bash
# 全テスト実行
# 注: Dockerfile.arm64 に pytest は含まれないため、テストは Mac 側 (Dockerfile) で実行する
docker compose exec voice-analyzer pytest /app/tests/ -v

# カバレッジ付き
docker compose exec voice-analyzer pytest /app/tests/ --cov=app --cov-report=term-missing
```

**テストカバレッジ: 98.9%**

- test_translator.py: 39件 ✅
- test_session_manager.py: 47件 ✅
- test_text_stats.py: 27件 ✅
- test_normalizer_comprehensive.py: 39件 ✅
- test_normalizer.py: 27件 (2件失敗は既知の制限)

## アーキテクチャ

### 処理フロー

```text
音声入力 (マイク/動画/タブ) → WebSocket
  ↓
音声チャンク受信 (cumulative buffer)
  ↓
faster-whisper文字起こし (initial_prompt対応)
  ↓
text_filter: フィラー除去
  ↓
normalizer: ひらがな正規化 (オプション)
  ↓
translator: 日→英翻訳 (オプション)
  ↓
確定/暫定テキスト返却
```

### 主要コンポーネント

**サーバー側:**

- `app/main.py`: FastAPIエンドポイント
- `app/services/audio_processor.py`: faster-whisper音声認識
- `app/services/cumulative_buffer.py`: 音声バッファ・差分抽出
- `app/services/translator.py`: Helsinki-NLP/opus-mt-ja-en翻訳
- `app/services/websocket_manager.py`: WebSocket接続管理
- `app/utils/normalizer.py`: janome形態素解析

**クライアント側:**

- `client/realtime_client.py`: CLIリアルタイムクライアント
- `app/static/`: ブラウザUI (HTML/CSS/JS)

### 外部依存

- **ffmpeg**: 音声変換
- **faster-whisper**: 音声認識 (CTranslate2)
- **janome**: 形態素解析
- **opus-mt**: 日英翻訳モデル
- **Ollama**: ローカルLLM (ブラウザ版の`local-llm`サービス。docker-compose.pi.yml からは削除済み)

## 設定 (app/config.py)

環境変数で上書き可能:

- `WHISPER_MODEL_SIZE`: small (デフォルト。ラズパイは base に上書き)
- `WHISPER_BEAM_SIZE`: 1 (デフォルト)
- `OLLAMA_BASE_URL`: <http://local-llm:11434> (ブラウザ版のみ。ラズパイ構成では未使用)
- `TRANSLATION_MODEL`: Helsinki-NLP/opus-mt-ja-en
- `CUMULATIVE_MAX_AUDIO_SECONDS`: 12.0秒 (バッファ最大長。ラズパイは 20.0)
- `CUMULATIVE_TRANSCRIPTION_INTERVAL`: 3チャンク (再処理間隔。ラズパイは 5)

## ファイル構成

```text
extension/                               # Chrome拡張機能（Phase 6.2, 6.3, 10.5）
├── manifest.json                        # Manifest V3設定
├── icons/                               # アイコン画像（16/48/128px）
│   ├── icon.svg                         # ソースSVG（graphic_eq Material Symbols公式パス）
│   ├── icon16.png                       # ツールバー用
│   ├── icon48.png                       # 拡張機能管理画面用
│   ├── icon128.png                      # Chromeウェブストア用
│   ├── create_icons.py                  # PNG生成スクリプト
│   ├── generate_icons.sh                # ワンコマンド生成スクリプト
│   └── README.md                        # アイコン生成ドキュメント
├── sidepanel/
│   ├── sidepanel.html                   # サイドパネルUI
│   ├── sidepanel.js                     # メインアプリケーション（showAdvancedFeatures対応）
│   ├── css/sidepanel.css                # サイドパネルスタイル
│   └── js/
│       ├── audio-capture.js             # 音声キャプチャ（chrome.tabCapture対応）
│       ├── audio-processor.js           # AudioWorklet
│       ├── websocket-client.js          # WebSocket通信
│       └── ui-controller.js             # UI制御
├── settings/
│   ├── settings.html                    # 設定画面（ZenVoiceヘッダー、上級者向け機能セクション）
│   └── settings.js                      # chrome.storage.sync（showAdvancedFeatures対応）
├── background/
│   └── service-worker.js                # 拡張機能アイコンクリック処理
└── README.md                            # インストール手順、使い方

app/
├── main.py                          # FastAPIエンドポイント
├── config.py                        # 設定管理
├── services/
│   ├── audio_processor.py           # Whisper文字起こし
│   ├── async_processor.py           # 非同期処理ラッパー
│   ├── cumulative_buffer.py         # 累積バッファ管理
│   ├── session_manager.py           # セッション管理
│   ├── text_filter.py               # フィラー除去
│   ├── translator.py                # 翻訳
│   ├── summarizer.py                # 要約（Gemini / Ollama）
│   ├── llm_analyzer.py              # Ollama連携
│   └── websocket_manager.py         # WebSocket管理
├── utils/
│   ├── normalizer.py                # ひらがな正規化
│   ├── number_converter.py          # 数字→漢数字変換
│   └── performance_monitor.py       # パフォーマンス計測
└── static/
    ├── index.html                   # ブラウザUI（Phase 11でレスポンシブ対応済み）
    ├── css/style.css
    └── js/
        ├── app.js                   # メインアプリケーション
        ├── ui-controller.js         # UI制御
        ├── websocket-client.js      # WebSocket通信
        ├── audio-capture.js         # 音声キャプチャ
        └── audio-processor.js       # 音声処理

client/
├── realtime_client.py               # CLIリアルタイムクライアント
├── ws_client.py                     # WebSocketクライアント (ファイル用)
├── chunk_client.py                  # HTTPクライアント (旧)
├── audio_capture.py                 # マイクキャプチャ (sounddevice)
└── audio_input.py                   # 音声分割ユーティリティ

tests/
├── test_translator.py
├── test_cumulative_buffer_trim.py
├── test_session_manager.py
├── test_text_stats.py
├── test_normalizer.py
└── test_normalizer_comprehensive.py

Dockerfile.arm64                         # ARM64（Raspberry Pi）向けDockerfile（Phase 14）
docker-compose.pi.yml                    # Raspberry Pi本番用docker-compose（Phase 14）

docs/                                    # 実装ドキュメント
├── IMPLEMENTION_PLAN.md                 # 全体実装計画
├── LEARNING_PLAN.md                     # 学習資料
├── PHASE11_PLAN.md                      # Phase 11実装計画（レスポンシブ対応）
├── PHASE11_COMPLETION.md                # Phase 11完了報告
├── PHASE12.1_PLAN.md                    # Phase 12.1実装計画
├── PHASE12.2_PLAN.md                    # Phase 12.2実装計画
├── PHASE12.3_PLAN.md                    # Phase 12.3実装計画
├── PHASE12.4_PLAN.md                    # Phase 12.4実装計画
├── PHASE13_PLAN.md                      # Phase 13実装計画
├── PHASE14_PLAN.md                      # Phase 14実装計画（Raspberry Piデプロイ）
├── PHASE15_DECISION.md                  # Phase 15撤退判断（拡張・ブラウザUIの廃止）
├── PHASE1_COMPLETION.md                 # Phase 1完了報告
├── PHASE2_COMPLETION.md                 # Phase 2完了報告
├── PHASE3_COMPLETION.md                 # Phase 3完了報告
├── PHASE3_PLAN.md                       # Phase 3実装計画
├── PHASE4.1_COMPLETION.md               # Phase 4.1完了報告
├── PHASE5.1_COMPLETION.md               # Phase 5.1完了報告
├── PHASE5.3_COMPLETION.md               # Phase 5.3完了報告
├── PHASE5.5_COMPLETION.md               # Phase 5.5完了報告
├── PHASE6.2_COMPLETION.md               # Phase 6.2完了報告
├── PHASE6.3_COMPLETION.md               # Phase 6.3完了報告
├── PHASE6.4_COMPLETION.md               # Phase 6.4完了報告
├── PHASE6.4_INVESTIGATION.md            # Phase 6.4調査資料
├── PHASE6.5_COMPLETION.md               # Phase 6.5完了報告
├── PHASE6.6_COMPLETION.md               # Phase 6.6完了報告
├── PHASE6.6_INVESTIGATION.md            # Phase 6.6調査資料
├── PHASE6.6_PLAN.md                     # Phase 6.6実装計画
├── PHASE7_COMPLETION.md                 # Phase 7.0完了報告
├── PHASE8_INVESTIGATION.md              # Phase 8調査資料
├── PHASE8_PLAN.md                       # Phase 8実装計画
└── WHISPER_SPECIFICATIONS.md            # Whisper仕様ドキュメント
```

## 使用方法

### Chrome拡張機能（推奨）

```bash
# 1. chrome://extensions/ を開く
# 2. 「デベロッパーモード」を有効化
# 3. 「パッケージ化されていない拡張機能を読み込む」をクリック
# 4. extension/ フォルダを選択
# 5. 拡張機能アイコンをクリックしてサイドパネルを表示

# 設定（初回のみ）
# - 拡張機能アイコンを右クリック → 「オプション」で設定画面を開く
# - APIサーバーURL: ws://<ラズパイのIP>:5001
# - 上級者向け機能: ひらがな正規化・翻訳を使う場合はONにする（デフォルトOFF）

# 操作
# 1. 文字起こししたいWebページを開く（YouTube等）
# 2. 拡張機能アイコンをクリック
# 3. 「開始」ボタンをクリック
# 4. リアルタイムで文字起こし結果が表示
# 5. 「停止」ボタンで終了
# 6. 「ダウンロード」ボタンでテキストファイル保存
```

### ブラウザUI（従来版）

```bash
# http://<ラズパイのIP>:5001/static/index.html にアクセス

# 入力ソース選択
# - マイク入力: デフォルトマイクから音声キャプチャ
# - 動画ファイル: ローカル動画アップロード (mp4/webm)
# - タブ共有: YouTube等のタブ音声をキャプチャ

# 処理オプション
# - ひらがな正規化: オン/オフ
# - 翻訳 (日→英): オン/オフ

# 操作
# 1. 入力ソースを選択
# 2. 処理オプションを選択
# 3. 「開始」ボタンをクリック
# 4. リアルタイムで文字起こし結果が表示
# 5. 「停止」ボタンで終了
```

### CLIクライアント

```bash
# venv環境有効化
source venv/bin/activate

# 依存関係インストール (初回のみ)
pip install -r client/requirements.txt

# デバイス一覧確認
python client/realtime_client.py --list-devices

# リアルタイム翻訳開始 (累積バッファモード)
python client/realtime_client.py --cumulative

# VADモード (音声区間検出)
python client/realtime_client.py --cumulative --enable-vad

# デバイス指定
python client/realtime_client.py --cumulative --device 2

# ラズパイサーバーに接続
python client/realtime_client.py --cumulative --url ws://<ラズパイのIP>:5001/ws/transcribe-stream-cumulative
```

## 既知の制限

### Chrome拡張機能

- Chrome専用 (Safari/Firefoxでは動作しない - chrome.tabCapture APIがChrome専用)
- APIサーバー必須 (ローカルまたはリモートでサーバー起動が必要)
- 現在のタブのみ (複数タブ同時録音は不可)

### ブラウザUI（従来版）

- HTTPSが必要 (localhost以外でマイクアクセス)
- Safari未対応 (将来対応候補)
- タブ共有時は「音声を共有」にチェック必須

### 翻訳機能

- Helsinki-NLP/opus-mt-ja-en (軽量モデル)
- 複雑な日本語表現は精度に限界あり
- 推奨用途: 大まかな内容把握の参考程度

### Whisperモデルの30秒制限（Phase 6.4, 6.5, 8で改善）

- Whisperは30秒のセグメントをネイティブサポート（アーキテクチャ上の制約）
- 30秒を超えると幻覚（hallucination）や精度低下が発生する可能性
- ✅ **Phase 6.4で修正**: 録音時間の表示は実際の経過時間を表示（30秒を超えても正しく表示）
- ✅ **Phase 6.4で修正**: 確定テキストロジックを安定性ベースに変更（句点なしでも動作）
- ✅ **Phase 6.5で修正**: タイムアウト延長（10秒→20秒）と強制確定処理で暫定テキストの喪失を防止
- ✅ **Phase 8で修正**: トリミング閾値を25秒に引き下げ（処理遅延を考慮して30秒超過を防止）
- 詳細: `docs/WHISPER_SPECIFICATIONS.md`、`docs/PHASE6.4_COMPLETION.md`、`docs/PHASE6.5_COMPLETION.md`を参照

### バッファトリミング時の文脈喪失（Phase 6.6, 7.0, 8で対応）

**Phase 7.0での改善**:

- ✅ トリミングタイミングを「文字起こし後」に変更
- ✅ 中間部分のテキスト喪失問題を改善

### テスト

- `test_normalizer.py`の2件失敗: 数え言葉変換の制限 (実用上の影響は軽微)

## 今後の拡張候補

**Phase 15以降の候補**

- 複数タブ対応
- Safari対応
- HTTPS対応・本番環境対応
- 字幕ファイル出力 (SRT/VTT)
- Chrome Web Storeへの公開

## 参考ドキュメント

詳細な実装内容・計画は`docs/`配下を参照:

### 実装計画

- `docs/PHASE11_PLAN.md`: Phase 11 (ブラウザ版レスポンシブ対応) の実装計画
- `docs/PHASE12.1_PLAN.md`: Phase 12.1 (Whisperタイムスタンプのサーバー側伝搬) の実装計画
- `docs/PHASE12.2_PLAN.md`: Phase 12.2 (Whisperセグメント単位での文節分割) の実装計画
- `docs/PHASE12.3_PLAN.md`: Phase 12.3 (重複テキスト問題の修正) の実装計画
- `docs/PHASE12.4_PLAN.md`: Phase 12.4 (タイムスタンプベース化) の実装計画
- `docs/PHASE13_PLAN.md`: Phase 13 (要約機能) の実装計画
- `docs/PHASE14_PLAN.md`: Phase 14 (Raspberry Piデプロイ対応) の実装計画
- `docs/IMPLEMENTION_PLAN.md`: 全体実装計画
- `docs/PHASE3_PLAN.md`: Phase 3の実装計画
- `docs/PHASE8_PLAN.md`: Phase 8の実装計画
- `docs/LEARNING_PLAN.md`: 学習資料・参考情報

### 完了報告

- `docs/PHASE11_COMPLETION.md`: Phase 11 (ブラウザ版レスポンシブ対応) の詳細
- `docs/PHASE1_COMPLETION.md`: Phase 1 (チャンク処理) の詳細
- `docs/PHASE2_COMPLETION.md`: Phase 2 (WebSocketストリーミング) の詳細
- `docs/PHASE3_COMPLETION.md`: Phase 3 (リアルタイム音声入力) の詳細
- `docs/PHASE4.1_COMPLETION.md`: Phase 4.1 (累積バッファ方式) の詳細
- `docs/PHASE5.1_COMPLETION.md`: Phase 5.1 (動画コンテンツ対応) の詳細
- `docs/PHASE5.3_COMPLETION.md`: Phase 5.3 (句読点挿入処理の削除) の詳細
- `docs/PHASE5.5_COMPLETION.md`: Phase 5.5 (バグ修正・UI改善) の詳細
- `docs/PHASE6.2_COMPLETION.md`: Phase 6.2 (Chrome拡張機能化) の詳細
- `docs/PHASE6.3_COMPLETION.md`: Phase 6.3 (アイコン画像の改善) の詳細
- `docs/PHASE6.4_COMPLETION.md`: Phase 6.4 (30秒問題の修正) の詳細
- `docs/PHASE6.5_COMPLETION.md`: Phase 6.5 (タイムアウト問題とセッション終了処理の修正) の詳細
- `docs/PHASE6.6_COMPLETION.md`: Phase 6.6 (バッファトリミング時の文脈保持の部分実装) の詳細
- `docs/PHASE7_COMPLETION.md`: Phase 7.0 (バッファトリミング時の文脈保持の完全実装) の詳細
- `docs/PHASE9_COMPLETION.md`: Phase 9 (ダウンロード機能バグ修正) の詳細

### 技術仕様・調査資料

- `docs/WHISPER_SPECIFICATIONS.md`: Whisper音声認識モデルの仕様と制限
- `docs/PHASE6.4_INVESTIGATION.md`: Phase 6.4 (30秒問題) の調査資料
- `docs/PHASE6.6_INVESTIGATION.md`: Phase 6.6 (バッファトリミング) の調査資料
- `docs/PHASE8_INVESTIGATION.md`: Phase 8 (ハルシネーション対策とテキスト管理) の調査資料
