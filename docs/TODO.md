# TODO

## この文書の運用ルール

- **やることのみを書く。** 完了した項目は削除する（経緯は git 履歴に残る）
- Phase 別の `PLAN` / `COMPLETION` / `INVESTIGATION` は今後作らない
- 設計判断で記録を残す必要があるものだけ、独立した `DECISION` 文書にする
  （例: [`PHASE15_DECISION.md`](PHASE15_DECISION.md)）
- 各項目には**なぜ必要か**を1行添える。着手時に背景を再調査せずに済ませるため

---

## 未使用機能の整理（要判断）

CLI は文字起こしに専念する方針としたため、ひらがな正規化・翻訳・要約は
どこからも呼ばれていない（サーバー側の実装は残置している）。
削除すれば依存パッケージと Docker イメージを大きく削減できるが、
影響範囲が広いので着手前に要否を判断する。

- [ ] `app/services/translator.py` の要否を判断する
      削除できれば torch / transformers / sentencepiece を落とせる（イメージ削減効果が最大）
- [ ] `app/services/summarizer.py` の要否を判断する
      削除できれば google-generativeai と Ollama 連携を落とせる
- [ ] `app/utils/normalizer.py` の要否を判断する（janome）
- [ ] 上記に伴い `POST /summarize` と `finalize_cumulative_session` の
      オプション分岐（`app/main.py`）を整理する

## 開発環境（docker-compose.yml）

要約を使わない構成では Ollama が不要なため、compose を単純化できる。

- [ ] `voice-analyzer` の `depends_on: local-llm` を外す
- [ ] `local-llm` サービスと external な `voice_analysis_network` / `ollama_data` の要否を判断する
      不要なら bridge ネットワークに寄せて、初回セットアップの手作業をなくせる

## 技術的負債

いずれも UI 削除以前から参照が切れているコード。動作に影響はないが、
CLI 集約でリポジトリを小さく保つ方針のため整理したい。

- [ ] `app/services/inventory_parser.py` を削除する（`main.py` でコメントアウト済み、未呼び出し）
- [ ] `app/services/llm_analyzer.py` を削除する（同上）
- [ ] `app/utils/number_normalizer.py` の要否を判断する（`app/tests/` からのみ参照）
- [ ] `app/utils/text_stats.py` の要否を判断する（同上）
- [ ] `POST /transcribe`、`POST /translate` を削除する（どこからも呼ばれていない）
- [ ] `/sample` マウント（`app/main.py`）の要否を判断する（どこからも参照なし）
- [ ] `summarizer.py` の同期 `requests.post` を `run_in_executor` 経由にする
      `async def` の中で同期呼び出しをしており、実行中はイベントループ全体が止まる
- [ ] `session_manager.delete_session()` を呼ぶ（`main.py` でコメントアウト。
      セッション辞書が30分間残り続ける）
