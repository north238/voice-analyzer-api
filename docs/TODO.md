# TODO

## この文書の運用ルール

- **やることのみを書く。** 完了した項目は削除する（経緯は git 履歴に残る）
- Phase 別の `PLAN` / `COMPLETION` / `INVESTIGATION` は今後作らない
- 設計判断で記録を残す必要があるものだけ、独立した `DECISION` 文書にする
  （例: [`PHASE15_DECISION.md`](PHASE15_DECISION.md)）
- 各項目には**なぜ必要か**を1行添える。着手時に背景を再調査せずに済ませるため

---

## 第2段階の残り

- [ ] 追加検証（`docs/02_slience_and_verification.md` タスクB）を実施する
      **検証用音声の受領待ち。** 口ごもり・言い直し・10秒以上の沈黙・技術用語を
      意図的に含む発話が必要（既存の `sample/005` は口ごもりを含まず沈黙も最大3.74秒）。
      スクリプトは用意済みで、音声があれば即実行できる
      （`venv/bin/python spike/silence.py <音声ファイル>`）

## 第3段階以降の検討事項（実装しない）

第2段階の結果を見てから決める。先回りして実装しないこと。

- [ ] 沈黙マーカーの記法を確定する
      現在は `...` を暫定採用。閾値1.5秒も暫定値（`spike/silence.py`）
- [ ] 沈黙を記録する構成を本体へ取り込む
      `transcribe_async()` は「音声バイト列を丸ごと渡す」形で区間ごとの処理と合わない。
      インタフェースの変更が要る
- [ ] R-5（区切りで発話が欠落しないこと）とハルシネーション抑制設定の衝突を解消する
      `WHISPER_LOG_PROB_THRESHOLD` / `WHISPER_NO_SPEECH_THRESHOLD` は
      確信度の低いセグメントを捨てるため発話が欠落しうる
- [ ] app 側の依存を記録する場所を決める
      Docker 廃止により faster-whisper 等の依存記録が失われた。
      `client/requirements.txt` はマイク入力用の依存しか持たない。
      現在の導入内容: faster-whisper 1.2.1 / ctranslate2 4.8.1 / av 15.1.0 /
      onnxruntime 1.19.2（Python 3.9）
- [ ] `app/services/async_processor.py` の到達不能なコードを削除する
      139-140行目の `elif seg_text:` は直前の `if seg_text:` により常に偽。動作に影響はない
- [ ] 文字起こしエンジンの選定
      CTranslate2 は Metal 非対応で Apple Silicon では CPU 実行になる。
      ただし実測ではリアルタイム比 0.08〜0.10 で、現状ボトルネックにはなっていない
