# voice-analyzer-api

開発中の思考を音声で吐き出し、**LLM に渡すための忠実なテキスト**として残すためのツールです。

キーボードで書くと思考が止まるが、声に出すだけなら止まらない。
その発話をテキストとして残し、最終的に LLM へ渡して要約・整理させることを目的としています。

> 本リポジトリのコードおよびドキュメントは、生成AI（Claude Code）を活用して作成しています。

## 中核となる方針: 何も直さない

読み手は人間ではなく LLM です。言い直しの過程そのものが思考の情報であり、
読みやすさを優先して除去・修正すると LLM が判断材料を失います。

そのため、次のことを**行いません**。

- 言い間違い、言い直し、口ごもりの除去
- 読みやすさのための整形
- 意味を推測した補完・修正

要求の詳細は [`docs/requirements.md`](docs/requirements.md) を参照してください。

---

## 現在の状態

**第1段階（不要機能の削除）が完了した時点です。動作する CLI はまだありません。**

サーバ構成（FastAPI + WebSocket）からローカル CLI ツールへ作り替える途中で、
通信層・セッション管理・リアルタイム表示の仕組みを削除しました。
CLI の組み立ては第2段階以降で行います。

作業範囲は [`docs/01_cleaanup_and_spike.md`](docs/01_cleaanup_and_spike.md) を参照してください。

### 残っている部品

| ファイル                           | 役割                                          |
| ---------------------------------- | --------------------------------------------- |
| `app/services/async_processor.py`  | faster-whisper のモデルロードと文字起こし実行 |
| `app/config.py`                    | Whisper のパラメータ設定                      |
| `client/audio_capture.py`          | マイク入力（sounddevice）と VAD（webrtcvad）  |
| `app/utils/logger.py`              | ロガー                                        |
| `app/utils/performance_monitor.py` | 処理時間の計測                                |

いずれも単体で import でき、互いに強く結合していません。

### 動作環境

- Apple Silicon（M1）搭載の Mac
- Python 3.9

Docker は廃止しました。ローカルの venv で動かします。
`faster-whisper` / `ctranslate2` は未導入のため、実行には別途インストールが必要です。

---

## ファイル構成

```text
app/
├── config.py                   # Whisper設定
├── services/
│   └── async_processor.py      # faster-whisper 呼び出し
├── utils/
│   ├── logger.py
│   └── performance_monitor.py
└── tests/

client/
├── audio_capture.py            # マイク入力・VAD
└── requirements.txt

docs/
├── requirements.md             # 要求定義（R-1〜R-21）
├── 01_cleaanup_and_spike.md    # 第1段階の作業指示書
├── TODO.md
├── PHASE15_DECISION.md         # 方針転換の判断記録
└── archive/                    # 廃止した機能のドキュメント
```

---

## 設定（app/config.py）

環境変数で上書きできます。すべて Whisper 関連です。

| 変数名                 | デフォルト | 説明           |
| ---------------------- | ---------- | -------------- |
| `WHISPER_MODEL_SIZE`   | small      | モデルサイズ   |
| `WHISPER_COMPUTE_TYPE` | int8       | 計算精度       |
| `WHISPER_BEAM_SIZE`    | 1          | ビームサーチ幅 |
| `WHISPER_VAD_ENABLED`  | true       | Whisper内蔵VAD |

> **注意**: `WHISPER_VAD_ENABLED` は無音区間をスキップします。
> R-7「沈黙が含まれていたことが分かること」と衝突するため、扱いは第2段階で検討します。

---

## 実行環境についての制約

**CTranslate2（faster-whisper のバックエンド）は Metal に非対応**のため、
Apple Silicon では GPU を利用できず CPU 実行になります。

GPU を使う場合の選択肢は次の通りですが、**現時点で移行は行っていません**。

| 選択肢                 | GPU                   | 速度                  |
| ---------------------- | --------------------- | --------------------- |
| mlx-whisper            | Metal + Neural Engine | whisper.cpp の約2.0倍 |
| whisper.cpp            | Metal + Core ML       | CPU比 3倍以上         |
| faster-whisper（現行） | なし                  | —                     |

---

## 設計判断の経緯

このリポジトリは元々、Raspberry Pi 上で動作する音声解析 API サーバとして開発され、
ブラウザUI と Chrome拡張を持っていました。
Pi の実測性能（文字起こし 10.9〜17.3秒/回）が要求に対して構造的に不足すると判断し、
段階的に機能を削ってローカル CLI ツールへ方針転換しています。

判断の詳細は [`docs/PHASE15_DECISION.md`](docs/PHASE15_DECISION.md) に記録しています。

過去の状態はタグから参照できます。

| タグ                 | 内容                               |
| -------------------- | ---------------------------------- |
| `v1.0-extension`     | Chrome拡張・ブラウザUIを含む版     |
| `v1.1-full-pipeline` | 翻訳・要約・ひらがな正規化を含む版 |
