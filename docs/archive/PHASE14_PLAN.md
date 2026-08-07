# Phase 14: Raspberry Pi デプロイ対応 実装計画

## 概要

ZenVoice APIサーバーをRaspberry Pi (ARM64) 上で動作させ、
自宅ネットワーク内からChrome拡張機能で利用できるようにする。

## 構成図

```text
[自宅ネットワーク]
  Chrome（PC）
    └── Chrome拡張機能（ZenVoice）
          └── ws://<ラズパイのIP>:5001
                └── Raspberry Pi
                      └── Docker（voice-analyzer-api）
```

## スペック

| 項目           | 内容                           |
| -------------- | ------------------------------ |
| RAM            | 8GB                            |
| アーキテクチャ | ARM64                          |
| Docker         | インストール済み               |
| Whisperモデル  | base                           |
| アクセス範囲   | 自宅内ローカルネットワークのみ |

---

## Phase 14.1: ARM64対応 Dockerfile の作成 ✅

**作成ファイル:** `Dockerfile.arm64`

**現行 Dockerfile からの主な変更点:**

| 変更点                                                               | 理由                                      |
| -------------------------------------------------------------------- | ----------------------------------------- |
| `libgomp1` を追加                                                    | ctranslate2 の OpenMP 依存（ARM64で必要） |
| `torch` に `--index-url https://download.pytorch.org/whl/cpu` を追加 | CPU版を明示的に指定                       |
| `onnxruntime`（GPU版なし）を使用                                     | ARM64にGPU不要                            |
| `--reload` を削除                                                    | 本番運用向け                              |

---

## Phase 14.2: docker-compose の整備 ✅

**作成ファイル:** `docker-compose.pi.yml`

**現行 docker-compose.yml からの主な変更点:**

| 変更点                                | 理由                                             |
| ------------------------------------- | ------------------------------------------------ |
| `dockerfile: Dockerfile.arm64` に変更 | ARM64向けビルド                                  |
| `external: true` を削除               | Pi上で新規作成するネットワーク・ボリュームを使用 |
| `LOG_LEVEL=INFO` に変更               | 本番向け（DEBUG→INFO）                           |
| `ENV=production` に変更               | 本番環境                                         |
| `WHISPER_MODEL_SIZE=base` を明示      | ラズパイ向けに軽量モデルを指定                   |
| `restart: unless-stopped` を追加      | 再起動時に自動起動                               |

---

## Phase 14.3: ラズパイへのデプロイ手順

### 1. ラズパイのIPアドレスを確認

```bash
# ラズパイ上で実行
hostname -I
# 例: 192.168.0.x
```

### 2. リポジトリをクローン

```bash
# ラズパイ上で実行
git clone https://github.com/<your-username>/voice-analyzer-api.git
cd voice-analyzer-api
```

### 3. 必要なディレクトリを作成

```bash
mkdir -p models logs sample
```

### 4. 起動

```bash
docker compose -f docker-compose.pi.yml up --build -d
```

> 初回ビルドは時間がかかります（ARM64向けのtorchのダウンロードに数分）

### 5. Whisperモデルのダウンロード確認

```bash
# ログを確認してモデルのダウンロードが完了するまで待つ
docker compose -f docker-compose.pi.yml logs -f voice-analyzer
```

### 6. 動作確認

```bash
# ヘルスチェック（PCのブラウザからでも可）
curl http://<ラズパイのIP>:5001/health
```

---

## Phase 14.4: Chrome拡張機能の接続先変更

**コード変更不要**。設定画面から変更するだけ。

1. Chrome拡張機能アイコンを右クリック →「オプション」
2. APIサーバーURL を変更:

   ```text
   変更前: ws://localhost:5001
   変更後: ws://192.168.0.x:5001  ← ラズパイのIP
   ```

3. 「保存」をクリック

---

## トラブルシューティング

### ctranslate2 のビルドエラー

```bash
# ctranslate2のバージョンを固定して試す
pip install ctranslate2==4.4.0
```

### torch のインストールが遅い / 失敗する

ARM64向けのtorchは容量が大きいため時間がかかります（通常5〜15分）。
タイムアウトする場合:

```bash
pip install --no-cache-dir torch --timeout=300 \
    --index-url https://download.pytorch.org/whl/cpu
```

### メモリ不足でビルドが失敗する

```bash
# スワップを一時的に増やす
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### 処理が遅い場合

`docker-compose.pi.yml` の環境変数を調整:

```yaml
- WHISPER_MODEL_SIZE=tiny # base → tiny に変更
- WHISPER_CPU_THREADS=4 # ラズパイのコア数
```

---

## 参考

- [faster-whisper ARM64サポート](https://github.com/SYSTRAN/faster-whisper)
- [ctranslate2 ARM64](https://github.com/OpenNMT/CTranslate2)
- [PyTorch ARM64](https://pytorch.org/get-started/locally/)
