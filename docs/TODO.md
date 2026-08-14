# TODO

## この文書の運用ルール

- **やることのみを書く。** 完了した項目は削除する（経緯は git 履歴に残る）
- Phase 別の `PLAN` / `COMPLETION` / `INVESTIGATION` は今後作らない
- 設計判断で記録を残す必要があるものだけ、独立した `DECISION` 文書にする
  （例: [`PHASE15_DECISION.md`](PHASE15_DECISION.md)）
- 各項目には**なぜ必要か**を1行添える。着手時に背景を再調査せずに済ませるため

---

## 第3段階以降の検討事項（実装しない）

第2段階の結果を見てから決める。先回りして実装しないこと。

- [ ] 沈黙マーカーの記法を確定する
      現在は `...` を暫定採用。閾値1.5秒も暫定値（`spike/silence.py`）
- [ ] 沈黙を記録する構成を本体へ取り込む
      `transcribe_async()` は「音声バイト列を丸ごと渡す」形で区間ごとの処理と合わない。
      インタフェースの変更が要る
- [ ] 発話区間の切り出しによる欠落を検証・対処する（R-5）
      VAD が発話と判定しなかった音声は認識処理に到達しない。小声のつぶやき、
      語尾の減衰、息継ぎ直後の立ち上がりが落ちうる。**落ちたことは出力から分からない**
      （沈黙マーカーすら入らず、単に無かったことになる）。
      `speech_pad_ms` は既定400msが効いているが、区間として検出されなかった小声には効かない。
      **音声条件で結果が大きく変わる。** Whisperへ渡した部と渡さなかった部の音量差は
      `sample/005` で 5.3dB（余裕が小さい）、`sample/006` で 26.8dB（明確に分離）だった。
      006（語尾の減衰・小声を意図的に含む）では取りこぼしが発生しなかったが、
      005 のような条件では余裕がない。録音環境に依存するため、対処の要否は継続判断

- [ ] `no_speech_threshold` によるセグメント破棄を解消する（R-5）
      `faster_whisper/transcribe.py` の `generate_segments` に、
      `no_speech_prob > no_speech_threshold` かつ `avg_logprob < log_prob_threshold` のとき
      `seek += segment_size; continue` で**30秒窓を丸ごと飛ばす**処理がある。
      現在の設定（0.6 / -1.0）で発話が黙って消えうる。ログも DEBUG レベルのみ。
      なお `compression_ratio_threshold` は破棄ではなく温度を上げての再試行のため、
      こちらは R-5 のリスクではない
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
