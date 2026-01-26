FROM python:3.11-slim

WORKDIR /app

# 必要なパッケージ（音声解析系には ffmpeg が必須）
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# pipのアップグレード
RUN pip install --upgrade pip

# Python依存関係のインストール
RUN pip install --no-cache-dir \
    fastapi>=0.104.0 \
    uvicorn[standard]>=0.24.0 \
    python-multipart>=0.0.6 \
    pykakasi>=2.2.0 \
    jaconv>=0.3.0 \
    janome>=0.4.2 \
    requests>=2.31.0

# faster-whisperのみインストール（PyAV依存を回避）
RUN pip install --no-cache-dir av==12.0.0
RUN pip install --no-cache-dir faster-whisper --no-deps
RUN pip install --no-cache-dir \
    ctranslate2>=4.0.0 \
    huggingface-hub>=0.13 \
    tokenizers>=0.13 \
    onnxruntime>=1.14

# Hugging Face Transformers（翻訳用）
RUN pip install --no-cache-dir \
    torch>=2.0.0 \
    transformers>=4.30.0 \
    sentencepiece>=0.1.99

# テストツール
RUN pip install --no-cache-dir \
    pytest>=7.0.0 \
    pytest-cov>=4.0.0

# アプリケーションコードをコピー
COPY ./app /app

# 非rootユーザで実行（軽量・安全）
RUN useradd -m -u 1000 appuser  # ← UID=1000 を明示的に指定

# ログディレクトリを作成し、appuserに権限を付与
RUN mkdir -p /app/logs && chown -R appuser:appuser /app/logs

# FastAPIサーバ起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001", "--reload"]
