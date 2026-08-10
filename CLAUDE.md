# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

開発中の思考を音声で吐き出し、LLM に渡すための忠実なテキストとして残すツール。
ローカル（Mac）で動作する CLI として作り替えている途中。

## 最優先の前提: 何も直さないツールである

中核要求は**発話に忠実であること**（`docs/requirements.md` の R-1〜R-4）。

- 言い間違い、言い直し、口ごもりを**そのまま残す**
- 読みやすさのための整形を**行わない**
- 意味を推測して補完・修正を**行わない**

読み手は人間ではなく LLM。言い直しの過程そのものが思考の情報であり、
除去すると下流の LLM が判断材料を失う。

**「一般的にはこうする」という理由で整形・補正を加えないこと。**

## 作業を始める前に読むもの

- [`docs/requirements.md`](docs/requirements.md) — 要求定義（R-1〜R-21）。**実装前に必ず読む**
- [`docs/01_cleaanup_and_spike.md`](docs/01_cleaanup_and_spike.md) — 第1段階の作業指示書

### 守る原則（作業指示書 5章より）

- **要求を勝手に弱めない。** 実現困難と判断したら、書き換えずに理由とともに報告する
- **要求にないものを追加しない。** 必要と考えるなら実装せず提案として報告する
- **削除をためらわない。** 動作するコードでも要求に照らして不要なら削除する
- **段階を先に進めない。** 次段階の内容は実装せず提案に留める

## ドキュメント運用ルール

- **やることは [`docs/TODO.md`](docs/TODO.md) に集約する。** 完了した項目は削除する
  （経緯は git 履歴に残るため、完了報告のドキュメントは作らない）
- **Phase 別の `PLAN` / `COMPLETION` / `INVESTIGATION` は作らない**
- 設計判断で記録を残す必要があるものだけ、独立した `DECISION` 文書にする
  （例: [`docs/PHASE15_DECISION.md`](docs/PHASE15_DECISION.md)）
- `docs/archive/` は廃止した機能のドキュメント置き場。追加も更新もしない

## 現在の状態

**第1段階（不要機能の削除）が完了した時点。動作する CLI はまだない。**

サーバ構成（FastAPI + WebSocket）から削除を進めた結果、残っているのは部品のみ。
CLI の組み立ては第2段階以降。

| ファイル                           | 役割                                         |
| ---------------------------------- | -------------------------------------------- |
| `app/services/async_processor.py`  | faster-whisper のロードと文字起こし実行      |
| `app/config.py`                    | Whisper のパラメータ設定                     |
| `client/audio_capture.py`          | マイク入力（sounddevice）と VAD（webrtcvad） |
| `app/utils/logger.py`              | ロガー                                       |
| `app/utils/performance_monitor.py` | 処理時間の計測                               |

いずれも単体で import でき、互いに強く結合していない。

### 削除済み（復元はタグから）

- FastAPI サーバ、WebSocket 層、セッション管理
- 累積バッファ（リアルタイム表示用の差分抽出）とチャンク間の文脈引き継ぎ
- `text_filter.py`（相槌の破棄とハルシネーション検出。R-2 に違反するため）
- Docker 関連、翻訳・要約・ひらがな正規化、ブラウザUI・Chrome拡張

| タグ                 | 内容                               |
| -------------------- | ---------------------------------- |
| `v1.0-extension`     | Chrome拡張・ブラウザUIを含む版     |
| `v1.1-full-pipeline` | 翻訳・要約・ひらがな正規化を含む版 |

## 実行環境

- Apple Silicon（M1）、Python 3.9、venv
- Docker は廃止済み
- `faster-whisper` / `ctranslate2` は venv に未導入（実行には別途インストールが必要）

**CTranslate2 は Metal 非対応**のため、Apple Silicon では CPU 実行になる。
GPU を使うなら mlx-whisper / whisper.cpp が候補だが、**移行はまだ判断していない**。

## 要求との衝突（未解決・報告済み）

第2段階で扱う。勝手に解決しないこと。

- **R-7（沈黙が分かること）と `WHISPER_VAD_ENABLED`**
  内蔵VADは無音区間をスキップするため、沈黙の情報が失われる
- **R-5（区切りで発話が欠落しないこと）とハルシネーション抑制設定**
  `WHISPER_LOG_PROB_THRESHOLD` や `WHISPER_NO_SPEECH_THRESHOLD` は
  確信度の低いセグメントを捨てるため、発話が欠落しうる

## Git

- ブランチ: `main`（本番）← `development`（開発）← `feature/*`
- コミットメッセージは日本語。プレフィックス例: 追加、修正、削除、改修、リファクタ
