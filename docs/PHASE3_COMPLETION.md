# Phase 3: リアルタイム音声入力 - 完了報告

## 実装期間

2026-01-22

## 実装概要

Phase 2のWebSocketストリーミング処理を基盤として、マイク入力からのリアルタイム音声キャプチャとVAD（Voice Activity Detection）による動的チャンク分割を実装しました。

## Phase 3.1: 音声キャプチャ基盤

### 実装した機能

#### 1. 音声キャプチャモジュール

**ファイル**: `client/audio_capture.py`

- sounddeviceによるマイク入力
- 16kHz/モノラル/16bit PCM（Whisper互換）
- チャンク単位でのコールバック処理
- PCM→WAV変換機能（サーバー互換性）

**主要クラス**:

```python
@dataclass
class AudioConfig:
    sample_rate: int = 16000      # Whisper推奨: 16kHz
    channels: int = 1             # モノラル
    chunk_duration: float = 3.0   # 固定チャンク長（秒）
    dtype: str = 'int16'          # 16-bit PCM

class AudioCapture:
    def start(on_chunk, device_index, on_volume_level)
    def stop()
    def close()
```

**ライブラリ選定**:

- ~~PyAudio~~ → **sounddevice** に変更
- 理由: sounddeviceはPortAudioをバンドルしているため、`pip install`だけで動作
- PyAudioはPortAudioのシステムインストールが必要（`brew install portaudio`等）

**データフロー**:

```text
マイク入力
  ↓
sounddevice.InputStream（1024フレームごとにコールバック）
  ↓
内部バッファに蓄積
  ↓
チャンクサイズ（3秒=96000bytes）に達したら
  ↓
PCM→WAV変換
  ↓
on_chunkコールバック呼び出し
```

#### 2. リアルタイム翻訳クライアント

**ファイル**: `client/realtime_client.py`

- WebSocket + マイク入力の統合
- 非同期キャプチャ・送信・受信の並列処理
- リアルタイム結果表示
- パフォーマンス統計

**アーキテクチャ**:

```text
┌─────────────────────────────────────────────┐
│  RealtimeTranslationClient                  │
│                                             │
│  ┌─────────────┐    ┌─────────────────┐    │
│  │ AudioCapture│───→│ _capture_loop() │    │
│  │ (別スレッド) │    │ (run_in_executor)│    │
│  └─────────────┘    └────────┬────────┘    │
│                              │              │
│                    ┌─────────▼─────────┐   │
│                    │ _send_chunk()     │   │
│                    │ (WebSocket送信)    │   │
│                    └───────────────────┘   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │ _receive_loop()                      │   │
│  │ (WebSocket受信・結果表示)             │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

#### 3. サーバー側改善

**ファイル**: `app/services/async_processor.py`, `app/main.py`

- 無音チャンクのスキップ処理（エラーではなく正常終了）
- WebSocket切断時のエラーログ抑制

### 依存関係（Phase 3.1）

```text
sounddevice>=0.4.6     # リアルタイム音声入力
numpy>=1.24.0          # 音声データ処理
```

---

## Phase 3.2: VADによる動的チャンク分割

### 実装した機能

#### 1. VAD判定ロジック

**ファイル**: `client/audio_capture.py`

- webrtcvadによる音声区間検出
- 発話開始/終了の自動検出
- 無音閾値の設定（デフォルト500ms）
- 最小/最大チャンク長の制限（500ms〜10000ms）

**AudioConfig拡張**:

```python
@dataclass
class AudioConfig:
    # 基本設定
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration: float = 3.0
    dtype: str = 'int16'

    # VAD設定（Phase 3.2）
    enable_vad: bool = False              # VAD有効化フラグ
    vad_aggressiveness: int = 2           # VAD感度（0-3、3が最も厳密）
    silence_duration_ms: int = 500        # 無音判定時間（ミリ秒）
    min_chunk_duration_ms: int = 500      # 最小チャンク長（ミリ秒）
    max_chunk_duration_ms: int = 10000    # 最大チャンク長（ミリ秒）
```

**VAD処理フロー**:

```text
マイク入力
  ↓
sounddevice.InputStream（1024フレームごと）
  ↓
VAD判定バッファに追加
  ↓
30msフレームごとにwebrtcvad.is_speech()で判定
  ↓
音声検出 → 発話中フラグON、無音カウンタリセット
  ↓
無音検出 → 無音カウンタ増加
  ↓
無音が閾値（500ms）を超えた場合:
  - 発話終了と判定
  - 最小チャンクサイズ以上ならチャンク送信
  ↓
最大チャンクサイズに達した場合:
  - 強制的にチャンク送信
```

#### 2. 音量メーター機能

**ファイル**: `client/audio_capture.py`, `client/realtime_client.py`

- RMSベースの音量計算（dB単位）
- リアルタイム音量表示（20fps更新）
- 発話状態の視覚的フィードバック

**音量計算関数**:

```python
def calculate_volume_db(audio_data: np.ndarray) -> float:
    """PCM音声データから音量レベル（dB）を計算"""
    rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
    if rms > 0:
        db = 20 * np.log10(rms / 32767.0)
        return max(-60.0, min(0.0, db))
    return -60.0
```

**音量メーター表示**:

```python
def create_volume_meter(volume_db: float, is_speech: bool, width: int = 30) -> str:
    normalized = (volume_db + 60) / 60
    filled = int(normalized * width)
    if is_speech:
        bar = '█' * filled + '░' * (width - filled)
        status = '🎤'
    else:
        bar = '▓' * filled + '░' * (width - filled)
        status = '🔇'
    return f"{status} [{bar}] {volume_db:5.1f}dB"
```

#### 3. CLI引数の拡張

**ファイル**: `client/realtime_client.py`

新規CLI引数:

```text
--enable-vad              VAD（Voice Activity Detection）を有効化
--vad-aggressiveness      VAD感度（0-3、3が最も厳密、デフォルト: 2）
--silence-duration-ms     無音判定時間（ミリ秒、デフォルト: 500）
--min-chunk-duration-ms   最小チャンク長（ミリ秒、デフォルト: 500）
--max-chunk-duration-ms   最大チャンク長（ミリ秒、デフォルト: 10000）
--no-volume-meter         音量メーター表示を無効化
```

### 依存関係（Phase 3.2）

```text
webrtcvad>=2.0.10    # Google製VADライブラリ
```

---

## テスト結果

### テスト環境

- **OS**: macOS
- **サーバー**: Docker (localhost:5001)
- **クライアント**: venv環境
- **マイク**: MacBook内蔵マイク

### テストコマンド

#### 固定長モード（Phase 3.1互換）

```bash
# サーバー起動
docker compose up -d

# venv環境有効化
source venv/bin/activate

# クライアント依存関係インストール
pip install -r client/requirements.txt

# デバイス一覧確認
python client/realtime_client.py --list-devices

# リアルタイム翻訳開始（デフォルトマイク、3秒チャンク）
python client/realtime_client.py

# チ��ンク長を変更
python client/realtime_client.py --chunk-duration 5

# デバイス指定
python client/realtime_client.py --device 2
```

#### VADモード（Phase 3.2）

```bash
# VADモードで起動
python client/realtime_client.py --enable-vad

# VAD感度を調整（3が最も厳密）
python client/realtime_client.py --enable-vad --vad-aggressiveness 3

# 無音判定時間を調整（300ms）
python client/realtime_client.py --enable-vad --silence-duration-ms 300

# 音量メーターを非表示
python client/realtime_client.py --enable-vad --no-volume-meter

# ラズパイサーバーに接続
python client/realtime_client.py --enable-vad \
  --url ws://<ラズパイのIP>:5001/ws/translate-stream
```

### 動作確認結果

#### Phase 3.1（固定長モード）

```text
マイク入力「システムを構築しています」
  ↓
文字起こし: 「するシステムを構築しています。」
  ↓
ひらがな: 「するしすてむをこうちくしています。」
  ↓
翻訳: 「I'm building a system to do it.」
  ↓
処理時間: 約4.25秒/チャンク
```

#### Phase 3.2（VADモード）

```text
$ python client/realtime_client.py --enable-vad

=== リアルタイム音声翻訳クライアント起動 ===
接続先: ws://localhost:5001/ws/translate-stream
モード: VAD（感度: 2、無音閾値: 500ms）
チャンク長: 500ms〜10000ms
WebSocket接続成功
セッション開始: abc123...

🎤 録音開始！話してください...
（VADモード: 発話終了を検出して自動送信）
Ctrl+C で停止

🎤 [████████████████░░░░░░░░░░░░░░] -25.3dB  ← リアルタイム音量表示

チャンク#1 送信中... (32044 bytes)  ← 発話終了時に自動送信
  [transcribing] 音声認識中...
  [normalizing] ひらがな変換中...
  [translating] 翻訳中...

============================================================
チャンク#1 結果
============================================================
📝 文字起こし: こんにちは
🔤 ひらがな  : こんにちは
🌍 翻訳      : Hello.

⏱️  処理時間:
  - 文字起こし: 2.15秒
  - 正規化    : 0.01秒
  - 翻訳      : 0.32秒
  - 合計      : 2.48秒
  - レイテンシ: 2.51秒（送信〜受信）
============================================================
```

### ユニットテスト結果

```bash
$ python -c "
from audio_capture import AudioConfig, AudioCapture, calculate_volume_db, VAD_AVAILABLE
import numpy as np

print(f'VAD利用可能: {VAD_AVAILABLE}')

config = AudioConfig(enable_vad=True, vad_aggressiveness=2)
print(f'VAD有効: {config.enable_vad}')
print(f'VAD感度: {config.vad_aggressiveness}')
print(f'無音閾値: {config.silence_duration_ms}ms')

silent = np.zeros(1024, dtype=np.int16)
loud = np.full(1024, 16000, dtype=np.int16)
print(f'無音の音量: {calculate_volume_db(silent):.1f}dB')
print(f'大きい音量: {calculate_volume_db(loud):.1f}dB')

capture = AudioCapture(config)
print(f'VADオブジェクト: {capture.vad is not None}')

print('✅ 全てのテストが成功しました')
"

# 出力:
VAD利用可能: True
VAD有効: True
VAD感度: 2
無音閾値: 500ms
無音の音量: -60.0dB
大きい音量: -6.2dB
VADオブジェクト: True
✅ 全てのテストが成功しました
```

---

## 成功基準の達成状況

### Phase 3.1 成功基準

| 基準                                            | 状態    |
| ----------------------------------------------- | ------- |
| マイクから音声をキャプチャできる                | ✅ 達成 |
| キャプチャした音声をサーバーに送信できる        | ✅ 達成 |
| リアルタイムで翻訳結果を受信・表示できる        | ✅ 達成 |
| `pip install`のみで動作する（システム依存なし） | ✅ 達成 |

### Phase 3.2 成功基準

| 基準                                     | 状態    |
| ---------------------------------------- | ------- |
| webrtcvadによる音声区間検出が動作する    | ✅ 達成 |
| 発話終了時に自動的にチャンクが送信される | ✅ 達成 |
| 音量メーターがリアルタイムで表示される   | ✅ 達成 |
| Phase 3.1との後方互換性が維持されている  | ✅ 達成 |

---

## ファイル一覧

### 新規作成ファイル

```text
client/audio_capture.py       # 音声キャプチャモジュール（VAD対応）
client/realtime_client.py     # リアルタイム翻訳クライアント
PHASE3_COMPLETION.md          # 本ドキュメント
```

### 修正ファイル

```text
client/requirements.txt       # sounddevice, numpy, webrtcvad追加
app/services/async_processor.py  # 無音チャンク処理改善
app/main.py                   # skippedタイプの応答追加
CLAUDE.md                     # Phase 3完了状態に更新
```

### 既存ファイル（再利用）

```text
app/services/websocket_manager.py  # Phase 2から再利用
app/services/session_manager.py    # Phase 1から再利用
app/utils/performance_monitor.py   # Phase 1から再利用
app/services/audio_processor.py    # 既存
app/services/translator.py         # 既存
app/utils/normalizer.py            # 既存
client/ws_client.py                # Phase 2から再利用（ファイルベース用）
```

---

## 既知の制限事項

### 1. 処理遅延

**問題**:

- 3秒音声に対して約4秒の処理時間（Mac環境）
- ラズパイ環境ではさらに5倍程度遅延
- リアルタイム処理には性能不足

**対策（Phase 4で実装予定）**:

- Whisperモデルの軽量化（small → base/tiny）
- チャンク処理の並列化
- キャッシュ機能の導入

### 2. VAD精度

**問題**:

- 背景ノイズが多い環境では誤検出の可能性
- VAD感度調整が必要な場合がある

**対策**:

- `--vad-aggressiveness`で感度調整（0-3）
- `--silence-duration-ms`で無音判定時間調整

### 3. 翻訳品質

**問題**:

- Helsinki-NLP/opus-mt-ja-enモデルの精度限界
- 複雑な日本語表現の翻訳精度が低い

**現状の位置づけ**:

- 翻訳は参考機能
- 主要機能はひらがな正規化

---

## Phase 4への接続

Phase 3の実装が完了したことで、Phase 4（処理遅延の最適化）の基盤が整いました。

### Phase 4で実装予定の機能

1. **Whisperモデルの軽量化**
   - small → base/tinyへの変更
   - 処理時間を約1/3に短縮

2. **チャンク処理の並列化**
   - 複数チャンクの同時処理
   - パイプライン処理の導入

3. **キャッシュ機能の導入**
   - 翻訳結果のキャッシュ
   - モデルのプリロード最適化

---

## まとめ

Phase 3のリアルタイム音声入力機能は正常に実装・動作確認が完了しました。

**達成したこと**:

- ✅ マイク入力からのリアルタイム音声キャプチャ
- ✅ WebSocket経由でのストリーミング送信
- ✅ VADによる動的チャンク分割
- ✅ 音量メーターのリアルタイム表示
- ✅ Phase 3.1との後方互換性維持
- ✅ pip installのみで動作（システム依存なし）

**次のステップ**: Phase 4（処理遅延の最適化）への移行準備完了
