# Phase 3: リアルタイム音声入力の実装計画

## 概要

Phase 2で実装したWebSocketストリーミング処理を基盤として、マイク入力からのリアルタイム音声処理システムを構築します。

## 実装目標

- マイク入力から音声をキャプチャしてWebSocketでサーバーに送信
- VAD（Voice Activity Detection）による発話区間の自動検出
- リアルタイムな文字起こし・翻訳結果の表示
- 低遅延翻訳システムの実現

## 前提条件と課題

### パフォーマンス要件

Phase 2のテスト結果から、リアルタイム処理の実現には以下の課題があります:

#### Mac環境

- 処理時間: 4.840秒/チャンク（3秒音声）
- 遅延: 約1.6倍（許容範囲内）
- 評価: **リアルタイム処理可能** ✅

#### ラズパイ環境

- 処理時間: 24.318秒/チャンク（3秒音声）
- 遅延: 約8倍
- 評価: **リアルタイム処理には性能不足** ❌

### 対策案

#### Option 1: Whisperモデルの軽量化（推奨）

```python
# app/config.py
WHISPER_MODEL_SIZE = "tiny"  # small → tiny に変更
```

**期待効果**:

- 処理時間: 18.168秒 → 約6秒（1/3に短縮）
- 3秒音声に対して6秒処理 = 2倍の遅延（改善）

**デメリット**:

- 認識精度がやや低下

#### Option 2: チャンク長の延長

```bash
# 3秒 → 5秒チャンクに変更
--chunk-duration 5
```

**期待効果**:

- オーバーヘッド削減
- 効率向上

**デメリット**:

- 応答性の低下

#### Option 3: GPU対応（将来的）

- Raspberry Pi 4/5のGPU活用
- ONNX Runtimeでの最適化
- 外部GPUサーバーの利用

## アーキテクチャ設計

### 処理フロー

```text
クライアント側:
  マイク入力
    ↓
  PyAudio/sounddeviceで音声キャプチャ（16kHz, モノラル）
    ↓
  VADで発話区間検出
    ↓
  音声バッファに蓄積
    ↓
  無音検出 → チャンク確定
    ↓
  WebSocketでサーバーに送信（バイナリ）
    ↓
  進捗・結果を受信して表示

サーバー側:
  Phase 2の実装をそのまま利用
    ↓
  /ws/translate-stream で受信
    ↓
  transcribe → normalize → translate
    ↓
  結果を返却
```

### VAD（Voice Activity Detection）の実装

#### Option 1: webrtcvad（推奨）

```python
import webrtcvad

vad = webrtcvad.Vad(3)  # 攻撃性レベル 0-3
is_speech = vad.is_speech(audio_frame, sample_rate)
```

**メリット**:

- 軽量・高速
- 実績あり（WebRTC）

**デメリット**:

- サンプルレート制限（8kHz, 16kHz, 32kHz, 48kHz）
- フレーム長制限（10ms, 20ms, 30ms）

#### Option 2: silero-vad

```python
from silero_vad import VAD

vad = VAD()
speech_timestamps = vad(audio)
```

**メリット**:

- ディープラーニングベース
- 高精度

**デメリット**:

- モデルロードのオーバーヘッド
- PyTorch依存

## 実装内容

### 1. リアルタイム音声キャプチャクライアント

**ファイル**: `client/realtime_client.py`

**機能**:

- マイク入力のキャプチャ（PyAudio使用）
- VADによる発話区間検出
- 音声バッファ管理
- WebSocket接続とストリーミング送信
- リアルタイム結果表示

**主要クラス**:

```python
class RealtimeAudioClient:
    def __init__(self, server_url: str, vad_aggressiveness: int = 3):
        self.server_url = server_url
        self.vad = webrtcvad.Vad(vad_aggressiveness)
        self.sample_rate = 16000
        self.frame_duration_ms = 30  # 30ms frames
        self.buffer = []
        self.is_speaking = False

    async def start_recording(self):
        """マイク入力開始"""
        pass

    async def process_audio_frame(self, frame: bytes):
        """音声フレームを処理（VAD + バッファリング）"""
        pass

    async def send_chunk(self, audio_data: bytes):
        """音声チャンクをサーバーに送信"""
        pass

    def stop_recording(self):
        """マイク入力停止"""
        pass
```

### 2. VADマネージャー

**ファイル**: `client/vad_manager.py`

**機能**:

- 発話開始/終了の検出
- 無音区間の判定
- バッファ管理

**主要クラス**:

```python
class VADManager:
    def __init__(self, aggressiveness: int = 3,
                 speech_start_frames: int = 3,
                 speech_end_frames: int = 10):
        self.vad = webrtcvad.Vad(aggressiveness)
        self.speech_start_frames = speech_start_frames  # 発話開始判定フレーム数
        self.speech_end_frames = speech_end_frames      # 発話終了判定フレーム数

    def is_speech_frame(self, frame: bytes, sample_rate: int) -> bool:
        """1フレームが音声かどうか判定"""
        pass

    def detect_speech_state(self, frame: bytes, sample_rate: int) -> str:
        """発話状態を検出（"speaking", "silence", "transition"）"""
        pass
```

### 3. 音声キャプチャユーティリティ

**ファイル**: `client/audio_capture.py`

**機能**:

- PyAudioの初期化・終了
- マイクデバイスの選択
- 音声ストリームの開始・停止

**主要関数**:

```python
def list_audio_devices() -> List[Dict]:
    """利用可能な音声デバイスをリスト"""
    pass

def create_audio_stream(sample_rate: int,
                        frame_duration_ms: int,
                        callback) -> pyaudio.Stream:
    """音声ストリームを作成"""
    pass
```

## 依存関係の追加

### client/requirements.txt

```text
pydub>=0.25.0
requests>=2.31.0
python-dotenv>=1.0.0
websockets>=12.0
pyaudio>=0.2.13          # 新規: 音声入力
webrtcvad>=2.0.10        # 新規: VAD
numpy>=1.24.0            # 新規: 音声処理
```

### システム依存

#### Mac

```bash
# PortAudioのインストール（PyAudioの依存）
brew install portaudio

# PyAudioのインストール
pip install pyaudio
```

#### ラズパイ

```bash
# PortAudioのインストール
sudo apt-get update
sudo apt-get install portaudio19-dev python3-pyaudio

# PyAudioのインストール
pip install pyaudio
```

## ファイル構成

```text
client/
├── realtime_client.py           # 新規: リアルタイム音声キャプチャクライアント
├── vad_manager.py               # 新規: VAD管理
├── audio_capture.py             # 新規: 音声キャプチャユーティリティ
├── ws_client.py                 # 既存: ファイルベースWebSocketクライアント
├── chunk_client.py              # 既存: HTTPクライアント（参考用）
├── audio_input.py               # 既存: 音声分割ユーティリティ
└── requirements.txt             # 更新: pyaudio, webrtcvad追加

app/
├── main.py                      # 既存: 変更なし
├── services/
│   ├── websocket_manager.py     # 既存: 変更なし
│   ├── async_processor.py       # 既存: 変更なし
│   └── ...
└── ...
```

## 実装手順

### Phase 3.1: 音声キャプチャ基盤

1. **PyAudioの環境構築**
   - Mac/ラズパイでPortAudioをインストール
   - PyAudioの動作確認

2. **音声キャプチャユーティリティ実装**
   - `client/audio_capture.py` 作成
   - マイクデバイスのリスト取得
   - 音声ストリームの開始・停止

3. **基本的な音声キャプチャテスト**
   - マイク入力の動作確認
   - WAVファイルへの保存テスト

### Phase 3.2: VAD統合

1. **VADマネ��ジャー実装**
   - `client/vad_manager.py` 作成
   - webrtcvadの統合
   - 発話区間検出ロジック

2. **VAD動作確認**
   - 発話開始/終了の検出テスト
   - 各種パラメータの調整

### Phase 3.3: リアルタイムストリーミング

1. **リアルタイムクライアント実装**
   - `client/realtime_client.py` 作成
   - マイク入力 → VAD → WebSocket送信
   - 進捗・結果の表示

2. **統合テスト**
   - ローカル環境でのリアルタイム処理確認
   - ラズパイ環境での動作確認

## テスト方法

### 基本動作テスト

```bash
# サーバー起動
docker compose up -d

# venv環境有効化
source venv/bin/activate

# クライアント依存関係インストール
pip install -r client/requirements.txt

# システム依存インストール（Mac）
brew install portaudio

# リアルタイムクライアント実行
python client/realtime_client.py --url ws://localhost:5001
```

### VADテスト

```bash
# VADパラメータを変更してテスト
python client/realtime_client.py \
  --url ws://localhost:5001 \
  --vad-aggressiveness 2 \
  --speech-start-frames 5 \
  --speech-end-frames 15
```

### ラズパイリモートテスト

```bash
# Mac側: ラズパイのサーバーに接続
python client/realtime_client.py --url ws://<ラズパイのIP>:5001
```

## 成功基準

### 機能要件

- ✅ マイクから音声入力できる
- ✅ VADが発話区間を正しく検出する
- ✅ WebSocketでサーバーに音声が送信される
- ✅ リアルタイムで文字起こし結果が表示される
- ✅ 翻訳結果が即座に表示される

### 非機能要件

- ✅ 応答性: 発話終了から結果表示まで5秒以内（Mac環境）
- ✅ 安定性: 連続5分間の動作でエラーなし
- ✅ 音声品質: ノイズやドロップアウトがない

### パフォーマンス

#### Mac環境

- 発話終了から文字起こし完了まで: 5秒以内
- ユーザー体験: 実用的

#### ラズパイ環境

- Whisperモデルを`tiny`に変更
- 発話終了から文字起こし完了まで: 10秒以内
- ユーザー体験: やや遅延あるが使用可能

## リスクと対策

### リスク1: ラズパイでの処理遅延

**対策**:

- Whisperモデルを`tiny`に変更（必須）
- VADパラメータの最適化
- チャンク長の調整

### リスク2: VADの誤検出

**対策**:

- aggressivenessパラメータの調整
- speech_start_frames/speech_end_framesの最適化
- ノイズ除去の検討

### リスク3: マイク入力の品質

**対策**:

- サンプリングレート16kHzの厳守
- モノラル音声の使用
- 入力レベルの自動調整

## Phase 4への展望

Phase 3が完了すれば、次のような拡張が可能になります:

- **複数言語対応**: 他言語への翻訳
- **音声出力**: TTS（Text-to-Speech）による翻訳音声の再生
- **UI改善**: Webインターフェースの実装
- **クラウド連携**: より高精度なモデルの利用

## まとめ

Phase 3ではリアルタイム音声入力システムを実装し、実用的な音声翻訳アプリケーションの基盤を完成させます。

**実装の重点**:

- マイク入力とVADの安定動作
- リアルタイム性の確保（特にラズパイ環境）
- ユーザー体験の向上

**制約事項**:

- ラズパイ環境ではWhisper tinyモデルの使用推奨
- リアルタイム処理には一定の遅延が発生
