# voice-analyzer-api

音声を受け取り文字起こし → 簡易フィルタリング → 構造化（品目・個数・単位）を返す軽量な FastAPI ベースのサービスです。

主な用途: レシートや買い物メモなどの短い日本語音声から「品名」「数量」「単位」を抽出するプロトタイプ。

## 特徴

- Whisper（openai/whisper）モデルを用いたローカル文字起こし（`small`モデルを想定）
- ffmpeg による音声フォーマット/サンプリングレート変換（16kHz, モノラル）
- NGワードによる簡易フィルタリング
- 正規表現ベースのシンプルなテキストパーサで品目と数量を抽出
- Docker / docker-compose による起動サポート

## 必要条件

- macOS / Linux / Windows
- Python 3.10
- ffmpeg（システムにインストールされていること）
- Whisper の依存パッケージ（requirements に記載されていればそれを使用）

※ コンテナで動かす場合は Docker が必要です。

## すぐに試す（Docker Compose）

docker-compose.yml にサービス定義があります。既存の外部ネットワーク `uchistock_network` を参照する設定になっているため、そのネットワークが存在することを確認してください。

ローカルで起動する例:

1. ネットワークがない場合（作成例）
   docker network create uchistock_network

2. コンテナ起動
   docker compose up --build -d

サービスはホストの 5001 ポートで待ち受けます（`5001:5001` を公開）。

## ローカル開発（ホスト環境）

1. 仮想環境を作成し有効化
   python -m venv .venv
   source .venv/bin/activate

2. 依存パッケージをインストール
   pip install -r requirements.txt

3. ffmpeg が PATH にあることを確認
   ffmpeg -version

4. 開発サーバ起動
   uvicorn app.main:app --host 0.0.0.0 --port 5001 --reload

## API

POST /transcribe
- 説明: 音声ファイルを受け取り、文字起こし → フィルタ → 解析して JSON を返します。
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
- app/utils/logger.py - 共通ロガー設定
- Dockerfile / docker-compose.yml - コンテナ化設定

## 注意点 / 制限

- Whisper モデルの読み込みに GPU があると高速ですが、CPU でも動作します。モデルのロードに時間がかかる場合があります。
- parser はシンプルな正規表現方式のため、複雑な文や連続発話の精度は保証されません。
- NGワードリストや補正辞書は随時プロジェクト内で調整してください（`app/services/text_filter.py`, `audio_processor.py` 内の corrections）。
- docker-compose.yml は既存の外部ネットワーク `uchistock_network` を参照します。不要なら `external: true` を外すか設定を調整してください。

## ロギング

標準出力に INFO レベルでログを出します。コンテナ内で動かすと Docker ログに流れます。
