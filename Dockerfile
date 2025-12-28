FROM python:3.10-slim

WORKDIR /app

# 必要なパッケージ（音声解析系には ffmpeg が必須）
RUN apt-get update && apt-get install -y ffmpeg git && rm -rf /var/lib/apt/lists/*

# Python依存関係をインストール
RUN pip install --no-cache-dir fastapi uvicorn openai-whisper python-multipart jaconv pykakasi

# アプリケーションコードをコピー
COPY ./app /app

# 非rootユーザで実行（軽量・安全）
RUN useradd -m appuser
USER appuser

# FastAPIサーバ起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001", "--reload"]
