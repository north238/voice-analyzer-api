# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

音声を受け取り「文字起こし → フィルタリング → ひらがな正規化 → 翻訳 → 要約」を行う
FastAPI 製の日本語音声解析API。Raspberry Pi 上での動作を想定し、CLIクライアントから利用する。

## ドキュメント運用ルール

**このルールに従うこと。過去の Phase 別ドキュメントは参考にしない。**

- **やることは [`docs/TODO.md`](docs/TODO.md) に集約する。** 完了した項目は削除する
  （経緯は git 履歴に残るため、完了報告のドキュメントは作らない）
- **Phase 別の `PLAN` / `COMPLETION` / `INVESTIGATION` は今後作らない。**
  この運用で不要なドキュメントが増えたため、Phase 15 で方針を変更した
- 設計判断で記録を残す必要があるものだけ、独立した `DECISION` 文書にする
  （例: [`docs/PHASE15_DECISION.md`](docs/PHASE15_DECISION.md)）
- `docs/archive/` は廃止した機能のドキュメント置き場。追加も更新もしない

`docs/` 直下に残っている Phase 別ドキュメントは、過去の技術的な調査結果として
参照する価値があるため残しているもの。新しく同種のファイルを作る必要はない。

## 現在の構成

CLIクライアント + サーバーのみ。ブラウザUI・Chrome拡張は Phase 15 で廃止した。

- 廃止の判断と経緯: [`docs/PHASE15_DECISION.md`](docs/PHASE15_DECISION.md)
- 廃止した実装: タグ `v1.0-extension`（`git checkout v1.0-extension`）
- 廃止に関するドキュメント: `docs/archive/`

### 既知の状態

- **CLIからひらがな・翻訳・要約が使えない。**
  `client/realtime_client.py` が `{"type": "options"}` を送信しないため、
  サーバー側の処理オプションが常に全て `False` になる（受信側の処理は実装済み）。
  対応は `docs/TODO.md` に記載
- **Pi 4 では文字起こしに 10.9〜17.3秒/回かかる。**
  3秒チャンク前提の設計に追いつかない。int8 非対応・torch 2.0.1 固定というハード制約があり、
  設定では解決できない

## 開発コマンド

### Docker

```bash
# Mac（開発環境）
docker compose up --build -d
docker compose logs -f voice-analyzer
docker compose down

# Raspberry Pi（本番）
docker compose -f docker-compose.pi.yml up --build -d
docker compose -f docker-compose.pi.yml logs -f voice-analyzer
```

### テスト

テストは `app/tests/` にある（`tests/` ではない）。
`Dockerfile.arm64` に pytest は含まれないため、**テストは Mac 側（`Dockerfile`）で実行する**。

```bash
docker compose exec voice-analyzer pytest /app/tests/ -v
docker compose exec voice-analyzer pytest /app/tests/ --cov=app --cov-report=term-missing
```

`test_normalizer.py` の2件失敗は数え言葉変換の既知の制限（実用上の影響は軽微）。

### CLIクライアント

```bash
source venv/bin/activate
pip install -r client/requirements.txt   # 初回のみ

python client/realtime_client.py --list-devices    # デバイス一覧
python client/realtime_client.py --cumulative      # 累積バッファモード
python client/realtime_client.py --cumulative --enable-vad   # VADモード
python client/realtime_client.py --cumulative --device 2     # デバイス指定

# ラズパイのサーバーに接続
python client/realtime_client.py --cumulative \
  --url ws://<ラズパイのIP>:5001/ws/transcribe-stream-cumulative
```

## アーキテクチャ

### 処理フロー

```text
マイク入力（CLI） → WebSocket
  ↓
音声チャンク受信（cumulative buffer）
  ↓
faster-whisper 文字起こし（initial_prompt対応）
  ↓
text_filter: フィラー除去
  ↓
normalizer: ひらがな正規化（オプション）
  ↓
translator: 日→英翻訳（オプション）
  ↓
確定/暫定テキスト返却
```

### 主要コンポーネント

**サーバー側:**

- `app/main.py`: FastAPIエンドポイント
- `app/services/audio_processor.py`: faster-whisper音声認識
- `app/services/cumulative_buffer.py`: 音声バッファ・差分抽出
- `app/services/translator.py`: Helsinki-NLP/opus-mt-ja-en翻訳
- `app/services/summarizer.py`: 要約（Gemini / Ollama）
- `app/services/websocket_manager.py`: WebSocket接続管理
- `app/utils/normalizer.py`: janome形態素解析

**クライアント側:**

- `client/realtime_client.py`: CLIリアルタイムクライアント（マイク入力）
- `client/ws_client.py`: WebSocketクライアント（音声ファイル用）
- `client/chunk_client.py`: HTTPチャンククライアント

### エンドポイント

| エンドポイント                        | 利用者                               |
| ------------------------------------- | ------------------------------------ |
| `WS /ws/transcribe-stream-cumulative` | `realtime_client.py`（推奨）         |
| `WS /ws/translate-stream`             | `ws_client.py`, `realtime_client.py` |
| `POST /translate-chunk`               | `chunk_client.py`                    |
| `POST /summarize`                     | 現在未使用（CLI対応予定）            |
| `GET /health`                         | 外形監視用                           |

`POST /transcribe`、`POST /translate` は参照ゼロのデッドコード（`docs/TODO.md` 参照）。

### 外部依存

- **ffmpeg**: 音声変換
- **faster-whisper**: 音声認識（CTranslate2）
- **janome**: 形態素解析
- **opus-mt**: 日英翻訳モデル

## 設定（app/config.py）

環境変数で上書き可能。主なもの:

- `WHISPER_MODEL_SIZE`: small（デフォルト。ラズパイは base に上書き）
- `WHISPER_BEAM_SIZE`: 1
- `WHISPER_COMPUTE_TYPE`: int8（**ラズパイは float32 必須**。Pi 4 は int8 非対応）
- `TRANSLATION_MODEL`: Helsinki-NLP/opus-mt-ja-en
- `CUMULATIVE_MAX_AUDIO_SECONDS`: 12.0秒（ラズパイは 20.0）
- `CUMULATIVE_TRANSCRIPTION_INTERVAL`: 3チャンク（ラズパイは 5）

**重要な制約**: `CUMULATIVE_MAX_AUDIO_SECONDS` は
`3秒 × CUMULATIVE_TRANSCRIPTION_INTERVAL` より大きくすること。
トリミングは文字起こし後にしか実行されないため、下回ると毎回トリミングが走り、
タイムスタンプ整合が壊れて文字起こし結果が段落単位で欠落する。

## 既知の制限

### 翻訳機能

- Helsinki-NLP/opus-mt-ja-en（軽量モデル）
- 複雑な日本語表現は精度に限界あり。大まかな内容把握の参考程度

### Whisperモデルの30秒制限

- Whisperは30秒のセグメントをネイティブサポート（アーキテクチャ上の制約）
- 30秒を超えると幻覚（hallucination）や精度低下が発生する可能性
- Phase 6.4〜8 で対策済み（安定性ベースの確定ロジック、トリミング閾値の引き下げ、
  強制確定処理）
- 詳細: `docs/WHISPER_SPECIFICATIONS.md`

### バッファトリミング時の文脈保持

Phase 7.0 でトリミングタイミングを「文字起こし後」に変更し、中間部分のテキスト喪失を改善。
処理順序（データ更新 → コールバック → クリーンアップ）が重要で、
文字起こし前にトリミングすると `last_transcription` が古いまま強制確定が失敗する。

### Raspberry Pi 4 の制約

- **int8 非対応** — `WHISPER_COMPUTE_TYPE=float32` が必須（int8 はエラー）
- **torch は `==2.0.1` 固定** — 2.1以降は ARMv8.2 向けビルドで SIGILL クラッシュ
- 処理速度は tiny で約14秒、base で約28秒

## Git

- ブランチ: `main`（本番）← `development`（開発）← `feature/*`
- コミットメッセージは日本語。プレフィックス例: 追加、修正、削除、改修、リファクタ
