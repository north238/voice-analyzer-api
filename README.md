# voice-analyzer-api

日本語音声をリアルタイムで「文字起こし → ひらがな正規化 → 翻訳」する FastAPI ベースのサービスです。
Chrome拡張機能として動作し、YouTubeなどのタブ音声をワンクリックで文字起こしできます。

## 主な機能

- **リアルタイム文字起こし**: faster-whisper による高速・高精度な日本語音声認識
- **ひらがな正規化**: janome 形態素解析によるひらがな変換（オプション）
- **日英翻訳**: Helsinki-NLP/opus-mt-ja-en による日本語→英語翻訳（オプション）
- **Chrome拡張機能**: ワンクリックでタブ音声をキャプチャしてサイドパネルに表示
- **テキスト出力**: タイムスタンプ付きテキストファイルのダウンロード

## クイックスタート

```bash
# サーバー起動
docker compose up -d
```

### Chrome拡張機能（推奨）

1. `chrome://extensions/` を開く
2. 「デベロッパーモード」を有効化
3. 「パッケージ化されていない拡張機能を読み込む」をクリック
4. `extension/` フォルダを選択
5. 拡張機能アイコンをクリックしてサイドパネルを表示

### ブラウザUI（従来版）

```bash
open http://localhost:5001/static/index.html
```

### CLIクライアント

```bash
source venv/bin/activate
python client/realtime_client.py --cumulative
```

## アーキテクチャ

```
音声入力（タブ / マイク / 動画）
  ↓
WebSocket (累積バッファ方式)
  ↓
faster-whisper 文字起こし
  ↓
text_filter: フィラー除去
  ↓
normalizer: ひらがな正規化（オプション）
  ↓
translator: 日→英翻訳（オプション）
  ↓
確定テキスト返却
```

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

## テストカバレッジ

| テストファイル                   | テスト数 | 対象機能                 |
| -------------------------------- | -------- | ------------------------ |
| test_translator.py               | 39       | 日英翻訳                 |
| test_session_manager.py          | 47       | セッション管理           |
| test_text_stats.py               | 27       | テキスト統計             |
| test_normalizer_comprehensive.py | 39       | ひらがな正規化（包括）   |
| test_normalizer.py               | 27       | ひらがな正規化（基本）   |
| **合計**                         | **179**  | **総合カバレッジ 98.9%** |

## ファイル構成

```
extension/              # Chrome拡張機能
├── manifest.json
├── sidepanel/          # サイドパネルUI
├── settings/           # 設定画面
└── background/         # Service Worker

app/
├── main.py             # FastAPIエンドポイント
├── config.py           # 設定管理
├── services/
│   ├── audio_processor.py      # Whisper文字起こし
│   ├── cumulative_buffer.py    # 累積バッファ管理
│   ├── session_manager.py      # セッション管理
│   ├── translator.py           # 日英翻訳
│   └── websocket_manager.py    # WebSocket管理
├── utils/
│   └── normalizer.py           # ひらがな正規化
└── static/             # ブラウザUI（従来版）

client/
└── realtime_client.py  # CLIリアルタイムクライアント

tests/                  # テストスイート
docs/                   # 実装ドキュメント
```

## 設定

環境変数で上書き可能（`app/config.py`）:

| 変数名                              | デフォルト | 説明                     |
| ----------------------------------- | ---------- | ------------------------ |
| `WHISPER_MODEL_SIZE`                | base       | Whisperモデルサイズ      |
| `WHISPER_BEAM_SIZE`                 | 3          | ビームサーチ幅           |
| `CUMULATIVE_MAX_AUDIO_SECONDS`      | 30         | バッファ最大長（秒）     |
| `CUMULATIVE_TRANSCRIPTION_INTERVAL` | 3          | 再処理間隔（チャンク数） |

## 既知の制限

- Chrome専用（Safari / Firefox では動作しない）
- APIサーバー必須（ローカルまたはリモートでサーバー起動が必要）
- 翻訳は大まかな内容把握用途（Helsinki-NLP 軽量モデル）
