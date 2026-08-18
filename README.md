# voice-analyzer-api

[![テスト](https://github.com/north238/voice-analyzer-api/actions/workflows/test.yml/badge.svg)](https://github.com/north238/voice-analyzer-api/actions/workflows/test.yml)

開発中の思考を音声で吐き出し、**LLM に渡すための忠実なテキスト**として残すためのツールです。

キーボードで書くと思考が止まるが、声に出すだけなら止まらない。
その発話をテキストとして残し、最終的に LLM へ渡して要約・整理させることを目的としています。

マイクに向かって話すと、文字起こしされた結果が画面に出て、
同時に Markdown ファイルへ書き出されます。それだけのツールです。
要約も翻訳も行いません。

> 本リポジトリのコードおよびドキュメントは、生成AI（Claude Code）を活用して作成しています。

## 中核となる方針: 何も直さない

読み手は人間ではなく LLM です。言い直しの過程そのものが思考の情報であり、
読みやすさを優先して除去・修正すると LLM が判断材料を失います。

そのため、次のことを**行いません**。

- 言い間違い、言い直し、口ごもりの除去
- 読みやすさのための整形
- 意味を推測した補完・修正

要求と、その判断根拠は [`docs/requirements.md`](docs/requirements.md) に記録しています。

---

## セットアップ

### 1. 動作環境を確認する

- Apple Silicon（M1）搭載の Mac
- Python 3.9
- ffmpeg（音声ファイルを扱う場合のみ。マイク入力だけなら不要）

ffmpeg が未導入の場合は Homebrew で入れられます。

```bash
brew install ffmpeg
```

### 2. インストールする

```bash
git clone https://github.com/north238/voice-analyzer-api.git
cd voice-analyzer-api

python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 3. 動作を確認する

```bash
venv/bin/python cli.py
```

「録音を開始しました」と表示されたら話しかけてください。
数秒後に文字起こしが表示されます。`Ctrl+C` で終了します。

初回はモデル（small、約 500MB）のダウンロードが走るため時間がかかります。
2 回目以降はキャッシュから読み込まれます。

マイクへのアクセス許可を求められた場合は許可してください。

### 4. どこからでも呼び出せるようにする（任意）

このままでもリポジトリ内から実行できますが、
エイリアスを設定すると任意のディレクトリから使えます。

```bash
# ~/.zshrc に追記（パスは実際の配置に合わせる）
alias v="$HOME/voice-analyzer-api/venv/bin/python $HOME/voice-analyzer-api/cli.py"
```

```bash
source ~/.zshrc
```

`cd` を含まないため、実行してもカレントディレクトリは移動しません。
以降、本 README では `v` と表記します。

---

## 使い方

```bash
# マイクから入力する（Ctrl+C で終了）
v

# 文字起こし結果だけを表示する
v 2>/dev/null

# 音声ファイルを処理する（mp3 / m4a / wav など、ffmpeg が読める形式）
v ~/Downloads/recording.m4a
```

実行すると、画面下部に動作状態が表示されます。

```text
| 待機中
| 発話を検出中
| 文字起こし中
```

長い沈黙を挟んでも、止まっているのではなく待機中であることが分かります。
この表示は標準エラーへ出るため、`2>/dev/null` で消しても結果には影響しません。

### オプション

| オプション            | 説明                   |
| --------------------- | ---------------------- |
| `--output-dir <パス>` | 記録の保存先を指定する |
| `--device <番号>`     | 入力デバイスを指定する |

---

## 出力

### 保存先

実行したディレクトリの `notes/` に作られます。
ファイル名は開始日時です。

```text
notes/2026-08-15_073442.md
```

保存先を固定したい場合は、設定ファイルで絶対パスを指定してください。

### 記録の形式

発話ごとに段落が分かれます。
発話の間が 1.5 秒以上あいた場合は `[沈黙]` が挿入されます。長短は区別しません。

```markdown
# 2026-08-15 07:34:42

今日はキャッシュの設計を見直そうと思っていて

[沈黙]

いや、その前にログの出力先を決めた方がいいかもしれない
```

発話が確定するたびに書き出すため、途中で異常終了しても、
それまでに書き出された内容は残ります。

---

## 設定

`config.json` をリポジトリ直下に置くと、次回以降も設定が引き継がれます。
**無くても動きます。**

```json
{
  "output_dir": "~/Documents/voice-notes",
  "model_size": "small"
}
```

| 項目         | 既定値  | 説明                                                                 |
| ------------ | ------- | -------------------------------------------------------------------- |
| `output_dir` | `notes` | 記録の保存先。相対パスなら実行したディレクトリ基準、絶対パスなら固定 |
| `model_size` | `small` | Whisper のモデルサイズ                                               |

`--output-dir` を指定した場合は、そちらが優先されます。

### Whisper の詳細な設定（app/config.py）

環境変数で上書きできます。通常は変更する必要はありません。
既定値は `app/config.py` を参照してください。

| 変数名                       | 説明                        |
| ---------------------------- | --------------------------- |
| `WHISPER_MODEL_SIZE`         | モデルサイズ                |
| `WHISPER_COMPUTE_TYPE`       | 計算精度                    |
| `WHISPER_BEAM_SIZE`          | ビームサーチ幅              |
| `WHISPER_VAD_MIN_SILENCE_MS` | 外部VAD（Silero）の無音判定 |

Whisper 内蔵の VAD は使いません（`vad_filter=False` 固定）。

---

## 既知の制約

### 話している最中には結果が出ない

発話の区切りを検出してから認識するため、話し終わるまで何も表示されません。

発話が終わってから画面に出るまで、**実測で 3.1〜7.1秒（平均 4.9秒）**かかります。
発話が長いほど文字起こしに時間がかかります。

### 発話が失われうる

発話が出力に現れないまま失われる経路が、実測で確認されています。
**欠落したこと自体が出力から分かりません。**

- 外部 VAD の切り出し漏れ（小声や語尾の減衰が落ちる可能性がある）
- 認識処理内部の閾値による破棄（296秒・16区間の実測では発生 0 件）

詳細は [`docs/requirements.md`](docs/requirements.md) 5.7 を参照してください。

### 異常終了時に一部が失われる

発話は「終了後 2.0 秒の無音」が確認されてから文字起こしされます。
それまではメモリ上にのみ存在するため、異常終了すると失われます（実測で最長 40 秒）。

対処は行っていません（[`docs/requirements.md`](docs/requirements.md) 5.8）。

### GPU を利用していない

CTranslate2（faster-whisper のバックエンド）は Metal に非対応のため、
Apple Silicon では CPU 実行になります。

現状はリアルタイム比 0.08〜0.10 で処理できているため、移行は行っていません。

| 選択肢                 | GPU                   | 速度                  |
| ---------------------- | --------------------- | --------------------- |
| mlx-whisper            | Metal + Neural Engine | whisper.cpp の約2.0倍 |
| whisper.cpp            | Metal + Core ML       | CPU比 3倍以上         |
| faster-whisper（現行） | なし                  | —                     |

---

## テスト

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest app/tests/ -q
```

音声認識そのものは対象にしていません。モデルのロードに時間がかかり、
結果も録音条件に左右されるためです。代わりに、要求に直結する挙動を対象にしています
（沈黙マーカーの挿入条件、記録の即時書き出し、設定の反映、欠落や異常が記録に残ること）。

`main` と `development` への push、および Pull Request で GitHub Actions が同じテストを実行します。

---

## ファイル構成

```text
cli.py                          # エントリポイント（これ1つで動く）
config.json                     # 設定ファイル（任意。無くても動く）
requirements.txt                # 実行に必要なもの
requirements-dev.txt            # テストに必要なもの

.github/workflows/test.yml      # push と Pull Request でテストを実行する

app/
├── config.py                   # Whisper のパラメータ
├── services/
│   └── whisper_model.py        # モデルのロード
├── tests/                      # テスト
└── utils/
    └── logger.py               # ログ（画面は異常時のみ、ファイルには詳細）

docs/
├── requirements.md               # 要求定義（R-1〜R-22）
├── TODO.md                       # やること
├── DECISION_cli_migration.md     # 方針転換の判断記録
├── 01_cleanup_and_spike.md       # 第1段階の作業指示書
├── 02_silence_and_verification.md
├── 03_usable_state.md
├── 04_finalize_and_config.md
└── archive/                      # 過去の構成のドキュメント（更新しない）
    ├── server/                   # Raspberry Pi + API サーバ時代
    └── browser/                  # ブラウザUI・Chrome拡張

notes/                          # 文字起こしの記録（gitignore）
```

---

## 設計判断の経緯

このリポジトリは元々、Raspberry Pi 上で動作する音声解析 API サーバとして開発され、
ブラウザUI と Chrome拡張を持っていました。

Pi の実測性能（文字起こし 10.9〜17.3秒/回）が要求に対して構造的に不足すると判断し、
段階的に機能を削ってローカル CLI ツールへ方針転換しています。
Docker による構成も、この過程で廃止しました。

判断の詳細は [`docs/DECISION_cli_migration.md`](docs/DECISION_cli_migration.md) に記録しています。

過去の状態はタグから参照できます。

| タグ                 | 内容                               |
| -------------------- | ---------------------------------- |
| `v1.0-extension`     | Chrome拡張・ブラウザUIを含む版     |
| `v1.1-full-pipeline` | 翻訳・要約・ひらがな正規化を含む版 |

### 現在の状態

第4段階（暫定値の確定と運用の整備）まで完了しています。
経緯は [`docs/`](docs/) の作業指示書を参照してください。
