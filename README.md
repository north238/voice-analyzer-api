# voice-analyzer-api

音声を受け取り文字起こし → 簡易フィルタリング → 構造化（品目・個数・単位）を返す軽量な FastAPI ベースのサービスです。

主な用途: レシートや買い物メモなどの短い日本語音声から「品名」「数量」「単位」を抽出するプロトタイプ。

## 🎉 NEW: Phase 5.1完了（2026年1月28日）

**動画コンテンツ対応**を実装しました：

- 🎤 **マイク入力**（Phase 5）
- 🎥 **動画ファイル**（Phase 5.1）- ローカル動画ファイルをアップロードして音声解析
- 📺 **タブ共有（YouTube等）**（Phase 5.1）- ブラウザで再生中のYouTube等の音声をリアルタイム文字起こし

**使い方：**
```bash
docker compose up -d
open http://localhost:5001/static/index.html
```

詳細は [PHASE5.1_COMPLETION.md](PHASE5.1_COMPLETION.md) を参照。

## 特徴

- Whisper（openai/whisper）モデルを用いたローカル文字起こし（`tiny`モデルを想定）
- ffmpeg による音声フォーマット/サンプリングレート変換（16kHz, モノラル）
- NGワードによる簡易フィルタリング
- 正規表現ベースのシンプルなテキストパーサで品目と数量を抽出
- オプション: LLM（OpenAI API）による抽出結果の補正・正規化
- Docker / docker-compose による起動サポート

## 必要条件

- macOS / Linux / Windows
- Python 3.10
- ffmpeg（システムにインストールされていること）
- Whisper の依存パッケージ（requirements に記載されていればそれを使用）
- （LLM 機能を使う場合）ローカルで動作する Ollama コンテナ（docker-compose の `local-llm` サービス）

※ コンテナで動かす場合は Docker が必要です。

## すぐに試す（Docker Compose）

docker-compose.yml にサービス定義があります。既存の外部ネットワーク `voice_analysis_network` を参照する設定になっているため、そのネットワークが存在することを確認してください。

ローカルで起動する例:

1. ネットワークがない場合（作成例）
   docker network create voice_analysis_network

2. コンテナ起動
   docker compose up --build -d

サービスはホストの 5001 ポートで待ち受けます（`5001:5001` を公開）。

## ローカル開発（ホスト環境）

1. 仮想環境を作成し有効化
   python -m venv .venv
   source .venv/bin/activate

2. ffmpeg が PATH にあることを確認
   ffmpeg -version

3. 開発サーバ起動
   uvicorn app.main:app --host 0.0.0.0 --port 5001 --reload

## LLM（ローカル Ollama）による補正機能（追加）

このプロジェクトでは外部の OpenAI API を使わず、ローカルで動作する Ollama を用いて抽出結果の補正・ひらがなから適切な日本語文章への変換を行う想定です。

docker-compose.yml には `local-llm` サービスが定義されており、`ollama/ollama` イメージを使ってローカル LLM を立ち上げます。主なポイント:

- サービス名: `local-llm`（Docker Compose で定義）
- ホスト公開ポート: `11434:11434`（必要に応じて変更）
- データ永続化: `ollama_data` ボリュームをマウント
- `voice-analyzer` サービスは `depends_on: - local-llm` により LLM の起動を待ちます
- 両サービスは `voice_analysis_network` ネットワークで接続されます。ネットワークがない場合は作成してください:

  docker network create voice_analysis_network

- Ollama 本体に対してはコンテナ内でモデルをプルしておく必要があります。例:

  docker exec -it local-llm ollama pull <model-name>

アプリケーションからのアクセス方法:

- コンテナ内からは `local-llm:11434` で Ollama の API に到達できます（Compose のネットワーク内）。
- 実装に応じて HTTP API もしくは CLI 呼び出しでモデルを利用してください。

注意点:

- ローカル LLM を使うと外部 API のコストは発生しませんが、ホストごとのリソース消費（メモリ/CPU）は増えます。
- 公開環境でポートを公開する場合は適切なセキュリティ対策を行ってください（ファイアウォール、認証など）。

## API

POST /transcribe
- 説明: 音声ファイルを受け取り、文字起こし → フィルタ → 解析して JSON を返します。LLM が有効な場合は最終的な解析結果を LLM で補正します。
- リクエスト: multipart/form-data, フィールド名 `file` に音声ファイル（webm/mp3/wav 等）
- レスポンス例 (成功, HTTP 200):
  {
    "status": "success",
    "message": "音声解析に成功しました。",
    "data": {
      "input": "卵1個 砂糖100g",
      "items": [
        {"item":"卵","quantity":"1","unit":"個"},
        {"item":"砂糖","quantity":"100","unit":"g"}
      ]
    }
  }

- エラー例 (NG ワード等, HTTP 400):
  {
    "status": "error",
    "message": "品名として認識できませんでした。再度お試しください。",
    "input": "こんにちは"
  }

- 内部エラー (HTTP 500) は `detail` を含みます。

## 主要ファイル構成

- app/main.py - FastAPI アプリとエンドポイント
- app/services/audio_processor.py - ファイル受け取り、ffmpeg 変換、Whisper での文字起こし処理
- app/services/text_filter.py - NGワードや簡易ノイズ判定
- app/services/text_parser.py - 正規表現ベースの品目/数量/単位抽出
- app/services/llm_processor.py - （追加）OpenAI API を使った抽出結果の補正・正規化
- app/services/translator.py - Helsinki-NLP/opus-mt-ja-en による日本語→英語翻訳
- app/services/session_manager.py - セッション管理（チャンク処理用）
- app/services/websocket_manager.py - WebSocket 接続管理
- app/utils/normalizer.py - janome 形態素解析を使った日本語→ひらがな変換
- app/utils/logger.py - 共通ロガー設定
- Dockerfile / docker-compose.yml - コンテナ化設定

## テスト

本プロジェクトには包括的なテストスイートが用意されています。

### テスト実行方法

#### Dockerコンテナ内での実行（推奨）

```bash
# すべてのテストを実行
docker compose exec voice-analyzer pytest /app/tests/ -v

# 特定のテストファイルのみ実行
docker compose exec voice-analyzer pytest /app/tests/test_translator.py -v

# カバレッジ付き実行
docker compose exec voice-analyzer pytest /app/tests/ --cov=app --cov-report=html
```

#### ローカル環境での実行

```bash
# 仮想環境を有効化
source .venv/bin/activate

# pytest インストール（初回のみ）
pip install pytest pytest-cov

# テスト実行
pytest app/tests/ -v
```

### テストカバレッジ

| テストファイル | テスト数 | 対象機能 |
|---------------|---------|---------|
| test_translator.py | 39 | 日英翻訳機能 |
| test_session_manager.py | 47 | セッション管理 |
| test_text_stats.py | 27 | テキスト統計 |
| test_normalizer.py | 27 | ひらがな正規化（基本） |
| test_normalizer_comprehensive.py | 39 | ひらがな正規化（包括） |
| **合計** | **179** | **総合カバレッジ 98.9%** |

## 注意点 / 制限

- Whisper モデルの読み込みに GPU があると高速ですが、CPU でも動作します。モデルのロードに時間がかかる場合があります。
- parser はシンプルな正規表現方式のため、複雑な文や連続発話の精度は保証されません。
- NGワードリストや補正辞書は随時プロジェクト内で調整してください（`app/services/text_filter.py`, `audio_processor.py` 内の corrections）。
- docker-compose.yml は既存の外部ネットワーク `voice_analysis_network` を参照します。不要なら `external: true` を外すか設定を調整してください。

## ロギング

標準出力に INFO レベルでログを出します。コンテナ内で動かすと Docker ログに流れます。

## ライセンス

適宜追加してください。


以上。問題や追加したい機能があれば指示してください。
