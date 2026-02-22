#!/bin/bash

# 複数チャンクのテスト（セッション管理の確認）

echo "=== 複数チャンクのテスト ==="
echo ""

# 1つ目のチャンク（セッションID取得）
echo "📦 チャンク 1/3 送信中..."
RESPONSE1=$(curl -s -X POST http://localhost:5001/translate-chunk \
  -F "file=@sample/001-sibutomo.mp3" \
  -F "chunk_id=0" \
  -F "is_final=false")

SESSION_ID=$(echo "$RESPONSE1" | python3 -c "import sys, json; print(json.load(sys.stdin)['session_id'])")
echo "✅ セッションID取得: $SESSION_ID"
echo "$RESPONSE1" | python3 -m json.tool | grep -A 3 "context"
echo ""

# 2つ目のチャンク（同じセッションIDを使用）
echo "📦 チャンク 2/3 送信中..."
RESPONSE2=$(curl -s -X POST http://localhost:5001/translate-chunk \
  -F "file=@sample/002-worklife.mp3" \
  -F "session_id=$SESSION_ID" \
  -F "chunk_id=1" \
  -F "is_final=false")

echo "✅ チャンク 2 完了"
echo "$RESPONSE2" | python3 -m json.tool | grep -A 3 "context"
echo ""

# 3つ目のチャンク（最終チャンク）
echo "📦 チャンク 3/3 送信中（最終チャンク）..."
RESPONSE3=$(curl -s -X POST http://localhost:5001/translate-chunk \
  -F "file=@sample/003-sikouryou.mp3" \
  -F "session_id=$SESSION_ID" \
  -F "chunk_id=2" \
  -F "is_final=true")

echo "✅ チャンク 3 完了"
echo "$RESPONSE3" | python3 -m json.tool | grep -A 3 "context"
echo ""

echo "=== パフォーマンスサマリー ==="
echo "チャンク 1:"
echo "$RESPONSE1" | python3 -m json.tool | grep -A 6 "performance"
echo ""
echo "チャンク 2:"
echo "$RESPONSE2" | python3 -m json.tool | grep -A 6 "performance"
echo ""
echo "チャンク 3:"
echo "$RESPONSE3" | python3 -m json.tool | grep -A 6 "performance"