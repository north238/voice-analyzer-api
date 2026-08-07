# voice-analyzer-api

日本語音声をリアルタイムで「文字起こし → ひらがな正規化 → 翻訳 → 要約」する FastAPI ベースのサービスです。
ローカル環境での実行を前提とし、CLIクライアントから利用します。

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

`docker-compose.yml` は Docker ネットワークとボリュームを external として参照するため、
初回のみ手動で作成する必要があります。

```bash
# ネットワーク・ボリューム作成（初回のみ）
docker network create voice_analysis_network
docker volume create ollama_data

# ビルド・起動
docker compose up --build -d
```

`voice-analyzer` は `depends_on` で `local-llm`（Ollama）を参照しているため、
上記では Ollama も起動します。要約機能を使わない場合は `--no-deps` で除外できます。

```bash
docker compose up -d --no-deps voice-analyzer
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

# 別ホストのサーバーに接続する場合
python client/realtime_client.py --cumulative \
  --url ws://<サーバーのIP>:5001/ws/transcribe-stream-cumulative
```

---

## リアルタイム性について

「発話してから画面に出るまで数秒以内」を要件とし、ローカル実行(Mac)で実測して
既定値を決めています。

| 項目            | 値                       |
| --------------- | ------------------------ |
| 遅延            | 3.7〜4.6秒（累積しない） |
| 画面更新        | 5秒ごと                  |
| 1回の文字起こし | 3〜4秒（small / int8）   |

### 設定の考え方

```text
CUMULATIVE_TRANSCRIPTION_INTERVAL=1   チャンクが届くたびに文字起こしする
CUMULATIVE_MAX_AUDIO_SECONDS=10.0     累積バッファの上限
--chunk-duration 5.0                  クライアントのチャンク長
```

**チャンク長は「処理時間 < チャンク間隔」を満たす必要があります。**
3秒間隔にすると、1回3〜4秒かかる処理が追いつかず遅延が累積します
（実測で7秒超まで悪化）。5秒あれば処理が間に合い、遅延が一定に保たれます。

### 調整する場合の注意

- **Whisper は30秒単位でパディングするため、処理対象の音声を短くしても
  処理時間はほとんど減りません**（9秒分でも18秒分でも3〜4秒台）。
  `CUMULATIVE_MAX_AUDIO_SECONDS` を削っても遅延は縮まりません。
  遅延に効くのは**モデルサイズとチャンク間隔**だけです。
- `WHISPER_MODEL_SIZE=base` にすると遅延は1.3〜1.9秒まで縮みますが、
  固有名詞と数字が崩れます（「すこやかに」→「スクイアカ」、
  電話番号が分断される）。精度を優先して `small` を既定にしています。
- `CUMULATIVE_MAX_AUDIO_SECONDS` は
  `チャンク長 × CUMULATIVE_TRANSCRIPTION_INTERVAL` より大きくすること。
  下回ると毎回トリミングが走り、タイムスタンプ整合が壊れて
  文字起こし結果が段落単位で欠落します。

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

その後、CLI の要件を「発話から数秒以内に表示される」と定めた結果、
これも Pi 4 では達成できないことが確定したため、**実行環境をローカルに一本化し
Raspberry Pi 向けの構成（`Dockerfile.arm64` / `docker-compose.pi.yml`）も削除した**。
同時に、文字起こしに専念する方針としてひらがな正規化・翻訳・要約は
CLI から提供していない（サーバー側の実装は残置）。

判断の詳細（実測データ、撤退の過程で発見した設計上の問題、
あえて修正を見送った理由）は [`docs/PHASE15_DECISION.md`](docs/PHASE15_DECISION.md) に記録している。
UI と Pi デプロイに関する実装ドキュメントは [`docs/archive/`](docs/archive/) に移した。

拡張機能・ブラウザUIを含む最終版は、タグ `v1.0-extension` で参照できる。

```bash
git checkout v1.0-extension
```
