# TODO

## この文書の運用ルール

- **やることのみを書く。** 完了した項目は削除する（経緯は git 履歴に残る）
- Phase 別の `PLAN` / `COMPLETION` / `INVESTIGATION` は今後作らない
- 設計判断で記録を残す必要があるものだけ、独立した `DECISION` 文書にする
  （例: [`PHASE15_DECISION.md`](PHASE15_DECISION.md)）
- 各項目には**なぜ必要か**を1行添える。着手時に背景を再調査せずに済ませるため

---

## 第1段階の残り

- [ ] 認識精度の検証スパイク（`docs/01_cleaanup_and_spike.md` タスクB）
      **検証用音声の受領待ち。** 技術用語・言い直し・沈黙を含む実際の発話が必要で、
      サンプル音声や合成音声では検証にならない（指示書7章）
- [ ] 検証にあたり `faster-whisper` / `ctranslate2` を venv へ導入する
      Docker 廃止により、ローカルに実行環境がない状態

## 第2段階以降の検討事項（実装しない）

第1段階の検証結果を見てから決める。先回りして実装しないこと。

- [ ] R-7（沈黙が分かること）と `WHISPER_VAD_ENABLED` の衝突を解消する
      内蔵VADは無音区間をスキップするため沈黙の情報が失われる
- [ ] R-5（区切りで発話が欠落しないこと）とハルシネーション抑制設定の衝突を解消する
      `WHISPER_LOG_PROB_THRESHOLD` / `WHISPER_NO_SPEECH_THRESHOLD` は
      確信度の低いセグメントを捨てるため発話が欠落しうる
- [ ] 文字起こしエンジンの選定
      CTranslate2 は Metal 非対応で Apple Silicon では CPU 実行になる。
      mlx-whisper / whisper.cpp が候補だが、速度が要求上の問題になるかは未確認
