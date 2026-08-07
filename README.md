# voice-analyzer-api

日本語音声をリアルタイムで「文字起こし → ひらがな正規化 → 翻訳 → 要約」する FastAPI ベースのサービスです。
Raspberry Pi 上で動作させることを想定し、CLIクライアントから利用します。

> 本リポジトリのコードおよびドキュメントは、生成AI（Claude Code）を活用して作成しています。

## 主な機能

- **リアルタイム文字起こし**: faster-whisper による高速・高精度な日本語音声認識
- **タイムスタンプ表示**: Whisperセグメント単位の正確な発話タイムスタンプ付き表示
- **ひらがな正規化**: janome 形態素解析によるひらがな変換（オプション）
- **日英翻訳**: Helsinki-NLP/opus-mt-ja-en による日本語→英語翻訳（オプション）
- **AI要約**: 録音終了後にGemini 2.0 Flash または Ollama で要約生成（オプション）
- **CLIクライアント**: マイク入力からのリアルタイム文字起こし（VADモード対応）

> ひらがな正規化・翻訳・要約はサーバー側に実装済みですが、CLIからの有効化は未対応です。
> 対応予定は [`docs/TODO.md`](docs/TODO.md) を参照してください。

---

## クイックスタート（開発環境）

```bash
# サーバー起動
docker compose up -d
```

### CLIクライアント

```bash
source venv/bin/activate
pip install -r client/requirements.txt   # 初回のみ

# デバイス一覧を確認
python client/realtime_client.py --list-devices

# リアルタイム文字起こし（累積バッファモード）
python client/realtime_client.py --cumulative

# VADモード（音声区間検出）
python client/realtime_client.py --cumulative --enable-vad

# リモートのサーバーに接続する場合
python client/realtime_client.py --cumulative \
  --url ws://<ラズパイのIP>:5001/ws/transcribe-stream-cumulative
```

---

## Raspberry Pi 4 環境構築

### 動作確認済み構成

| 項目            | 内容                        |
| --------------- | --------------------------- |
| ハードウェア    | Raspberry Pi 4 (8GB)        |
| OS              | Ubuntu 64bit (aarch64)      |
| IPアドレス      | 192.168.0.x（有線固定推奨） |
| Dockerイメージ  | `Dockerfile.arm64`          |
| composeファイル | `docker-compose.pi.yml`     |

### 注意事項（ハマりポイント）

> **torch は `==2.0.1` に固定すること。**
> 2.1以降のバージョンはARMv8.2以降向けにコンパイルされており、
> Pi 4（ARMv8.0-A / Cortex-A72）では SIGILL クラッシュが発生する。

> **WHISPER_COMPUTE_TYPE は `float32` を使用すること。**
> Pi 4は int8 演算に非対応のため、`int8` を指定するとエラーが発生する。

> **CUMULATIVE_MAX_AUDIO_SECONDS は `3秒 × CUMULATIVE_TRANSCRIPTION_INTERVAL` より大きくすること。**
> トリミングは文字起こし後にしか実行されないため、これを下回る値を設定すると
> 毎回トリミングが走り、タイムスタンプ整合が壊れて文字起こし結果が段落単位で欠落する。

### 初回セットアップ

```bash
# リポジトリのクローン
git clone https://github.com/north238/voice-analyzer-api.git
cd voice-analyzer-api

# ネットワーク作成（初回のみ）
docker network create pi_network

# ビルド・起動（初回は30〜60分かかる場合あり）
docker compose -f docker-compose.pi.yml build --no-cache
docker compose -f docker-compose.pi.yml up -d
```

### 通常の起動・停止

```bash
# 起動
dc -f docker-compose.pi.yml up -d

# 停止
dc -f docker-compose.pi.yml down

# ログ確認
docker logs voice-analyzer-api

# 状態確認
dc ps
```

### 動作確認

```bash
# ヘルスチェック
curl http://<ラズパイのIP>:5001/health

# 音声ファイルでテスト
curl -X POST http://<ラズパイのIP>:5001/transcribe \
  -F "file=@sample/001-sibutomo.mp3" \
  -F "intent=raw"
```

### Pi向け環境変数（docker-compose.pi.yml）

```yaml
environment:
  - TZ=Asia/Tokyo
  - LOG_LEVEL=INFO
  - ENV=production
  - LOG_BACKUP_COUNT=14
  - LOG_DIR=/logs
  # Whisper設定（Pi 4向け最適化）
  - WHISPER_MODEL_SIZE=base # tiny も可（2倍速、精度低）
  - WHISPER_BEAM_SIZE=1
  - WHISPER_BEST_OF=1
  - WHISPER_CPU_THREADS=4
  - WHISPER_COMPUTE_TYPE=float32 # Pi 4はint8非対応のためfloat32必須
  - WHISPER_VAD_ENABLED=false # onnxruntime未インストール時はfalse（Dockerfile.arm64 line:28）
  # 累積バッファ（処理速度とのトレードオフ）
  - CUMULATIVE_MAX_AUDIO_SECONDS=20.0 # 3秒 × TRANSCRIPTION_INTERVAL より大きくすること
  - CUMULATIVE_TRANSCRIPTION_INTERVAL=5
```

### パフォーマンス目安（float32 / Pi 4）

| モデル | 処理時間 | 精度 | メモリ |
| ------ | -------- | ---- | ------ |
| tiny   | 約14秒   | 低   | ~0.8GB |
| base   | 約28秒   | 中   | ~1.5GB |

### CLIクライアントからの接続

`--url` でラズパイのサーバーを指定します。

```bash
python client/realtime_client.py --cumulative \
  --url ws://<ラズパイのIP>:5001/ws/transcribe-stream-cumulative
```

---

## アーキテクチャ

```text
音声入力（タブ / マイク / 動画）
  ↓
WebSocket (累積バッファ方式)
  ↓
faster-whisper 文字起こし（セグメントタイムスタンプ付き）
  ↓
text_filter: フィラー除去
  ↓
normalizer: ひらがな正規化（オプション）
  ↓
translator: 日→英翻訳（オプション）
  ↓
確定テキスト返却
  ↓
summarizer: AI要約（オプション・録音終了後）
```

---

## 開発コマンド

```bash
# ビルド・起動
docker compose up --build -d

# ログ確認
docker compose logs -f voice-analyzer

# テスト実行
docker compose exec voice-analyzer pytest /app/tests/ -v

# カバレッジ付き
docker compose exec voice-analyzer pytest /app/tests/ --cov=app --cov-report=term-missing
```

---

## テストカバレッジ

| テストファイル                   | テスト数 | 対象機能                 |
| -------------------------------- | -------- | ------------------------ |
| test_translator.py               | 39       | 日英翻訳                 |
| test_session_manager.py          | 47       | セッション管理           |
| test_text_stats.py               | 27       | テキスト統計             |
| test_normalizer_comprehensive.py | 39       | ひらがな正規化（包括）   |
| test_normalizer.py               | 27       | ひらがな正規化（基本）   |
| **合計**                         | **179**  | **総合カバレッジ 98.9%** |

---

## ファイル構成

```text
app/
├── main.py             # FastAPIエンドポイント
├── config.py           # 設定管理
├── services/
│   ├── audio_processor.py      # Whisper文字起こし
│   ├── async_processor.py      # 非同期処理ラッパー（セグメント情報付き）
│   ├── cumulative_buffer.py    # 累積バッファ管理（タイムスタンプベース確定）
│   ├── session_manager.py      # セッション管理
│   ├── translator.py           # 日英翻訳
│   ├── summarizer.py           # AI要約（Gemini / Ollama）
│   └── websocket_manager.py    # WebSocket管理
├── utils/
│   └── normalizer.py           # ひらがな正規化
└── tests/              # テストスイート

client/
├── realtime_client.py  # CLIリアルタイムクライアント（マイク入力）
├── ws_client.py        # WebSocketクライアント（音声ファイル用）
├── chunk_client.py     # HTTPチャンククライアント
└── audio_capture.py    # マイクキャプチャ（sounddevice）

docs/
├── TODO.md             # やることリスト
├── PHASE15_DECISION.md # UI廃止の判断記録
└── archive/            # 廃止したUIに関するドキュメント
```

---

## 設定

環境変数で上書き可能（`app/config.py`）:

| 変数名                              | デフォルト               | 説明                                |
| ----------------------------------- | ------------------------ | ----------------------------------- |
| `WHISPER_MODEL_SIZE`                | small                    | Whisperモデルサイズ                 |
| `WHISPER_COMPUTE_TYPE`              | int8                     | 計算精度（Pi 4はfloat32必須）       |
| `WHISPER_BEAM_SIZE`                 | 1                        | ビームサーチ幅                      |
| `WHISPER_VAD_ENABLED`               | true                     | VAD有効/無効                        |
| `CUMULATIVE_MAX_AUDIO_SECONDS`      | 12.0                     | バッファ最大長（秒）                |
| `CUMULATIVE_TRANSCRIPTION_INTERVAL` | 3                        | 再処理間隔（チャンク数）            |
| `SUMMARY_PROVIDER`                  | ollama                   | 要約プロバイダー（gemini / ollama） |
| `GEMINI_API_KEY`                    | （空）                   | Google Gemini APIキー               |
| `GEMINI_MODEL`                      | gemini-2.0-flash         | 使用するGeminiモデル                |
| `OLLAMA_BASE_URL`                   | `http://local-llm:11434` | OllamaサーバーURL                   |

---

## 既知の制限

- APIサーバー必須（ローカルまたはリモートでサーバー起動が必要）
- ひらがな正規化・翻訳・要約はCLIから有効化できない（[`docs/TODO.md`](docs/TODO.md) で対応予定）
- Pi 4 では文字起こしに 10.9〜17.3秒/回かかり、リアルタイム処理には追いつかない
- 翻訳は大まかな内容把握用途（Helsinki-NLP 軽量モデル）
- AI要約はGemini利用時はAPIキーが必要
- Pi 4では float32 のみ対応（int8 不可）

---

## 設計判断の経緯

Phase 5系〜10.5 で実装した **ブラウザUI と Chrome拡張機能は、Phase 15 で廃止し CLI に集約した**。

Raspberry Pi 4（ARMv8.0-A / Cortex-A72）上では文字起こしに **実測 10.9〜17.3秒/回**かかり、
3秒チャンクを前提としたリアルタイムUIが成立しなかったことが理由である。
int8 非対応・torch 2.0.1 固定というハード制約があり、量子化やモデル縮小を試みても
最小の tiny モデルで約14秒と、性能面の打ち手が残っていなかった。

判断の詳細（実測データ、撤退の過程で発見した設計上の問題、
あえて修正を見送った理由）は [`docs/PHASE15_DECISION.md`](docs/PHASE15_DECISION.md) に記録している。
UIに関する実装ドキュメントは [`docs/archive/`](docs/archive/) に移した。

拡張機能・ブラウザUIを含む最終版は、タグ `v1.0-extension` で参照できる。

```bash
git checkout v1.0-extension
```
