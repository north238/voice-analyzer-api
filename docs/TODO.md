# TODO

## この文書の運用ルール

- **やることのみを書く。** 完了した項目は削除する（経緯は git 履歴に残る）
- Phase 別の `PLAN` / `COMPLETION` / `INVESTIGATION` は今後作らない
- 設計判断で記録を残す必要があるものだけ、独立した `DECISION` 文書にする
  （例: [`PHASE15_DECISION.md`](PHASE15_DECISION.md)）
- 各項目には**なぜ必要か**を1行添える。着手時に背景を再調査せずに済ませるため

---

## 残っている整理

- [ ] `/sample` マウント（`app/main.py`）の要否を判断する
      どこからも参照されていない。サンプル音声をHTTPで配信する必要がなければ削除できる
- [ ] `client/realtime_client.py` のクラス名 `RealtimeTranslationClient` を実態に合わせる
      翻訳を削除したため名前が合っていない（例: `RealtimeTranscriptionClient`）

## 改善候補

- [ ] 文字起こし結果のファイル出力を検討する
      現在は標準出力のみ。長時間の録音では保存できると使いやすい
- [ ] `initial_prompt` の活用を検討する
      固有名詞の認識精度を上げられる可能性がある（`app/services/audio_processor.py`）
