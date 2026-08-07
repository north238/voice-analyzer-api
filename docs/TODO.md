# TODO

## この文書の運用ルール

- **やることのみを書く。** 完了した項目は削除する（経緯は git 履歴に残る）
- Phase 別の `PLAN` / `COMPLETION` / `INVESTIGATION` は今後作らない
- 設計判断で記録を残す必要があるものだけ、独立した `DECISION` 文書にする
  （例: [`PHASE15_DECISION.md`](PHASE15_DECISION.md)）
- 各項目には**なぜ必要か**を1行添える。着手時に背景を再調査せずに済ませるため

---

## CLI の機能復活

ブラウザUI・Chrome拡張の廃止により、ひらがな・翻訳・要約が使えない状態になっている。
`client/realtime_client.py` は `{"type": "options"}` を送信しないため、
サーバー側の処理オプションが常に全て `False` のまま（受信側の処理は実装済み）。

- [ ] `realtime_client.py` に `{"type": "options"}` 送信を追加する
- [ ] CLI 引数 `--hiragana` / `--translate` / `--summary` を追加する
- [ ] 要約結果の表示に対応する（`summary_result` の受信ハンドリング）

## 性能（Raspberry Pi 4）

Pi 4 では文字起こしに実測 10.9〜17.3秒/回かかり、3秒チャンクに追いつかない。
int8 非対応・torch 2.0.1 固定というハード制約があり、設定では解決できない。

- [ ] チャンク間隔の延長を検討する（3秒 → 10〜15秒。リアルタイム性を落として追いつかせる）
- [ ] 上記で不十分な場合、ハード変更（Pi 5 等）の要否を判断する

## 開発環境（docker-compose.yml）

CLI 集約により Ollama を使わなくなったため、Mac 側の compose を整理できる。

- [ ] `voice-analyzer` の `depends_on: local-llm` を外す
      要約を使わない構成では Ollama の起動が不要
- [ ] `local-llm` サービスと external な `voice_analysis_network` / `ollama_data` の要否を判断する
      不要なら Pi 版（`docker-compose.pi.yml`）と同じく bridge ネットワークに寄せられる

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

## 要約機能の環境整備

- [ ] ラズパイで要約を使うなら、`Dockerfile.arm64` に `google-generativeai` を追加し
      `SUMMARY_PROVIDER=gemini` を設定する
      （現状 `docker-compose.pi.yml` から Ollama を削除済みだが `SUMMARY_PROVIDER` は
      既定の `ollama` のままで、Gemini に切り替えても ImportError になる）
