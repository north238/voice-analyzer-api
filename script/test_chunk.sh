#!/bin/bash

# チャンクエンドポイントのテスト

echo "=== チャンクエンドポイントのテスト ==="
echo "音声ファイル: sample/001-sibutomo.mp3"
echo ""

curl -X POST http://localhost:5001/translate-chunk \
  -F "file=@sample/001-sibutomo.mp3" \
  -F "chunk_id=0" \
  -F "is_final=true" \
  2>/dev/null | python3 -m json.tool