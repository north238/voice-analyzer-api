#!/bin/bash
# Chrome拡張機能アイコン生成スクリプト
#
# 使用方法:
#   cd extension/icons
#   bash generate_icons.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🎨 アイコン生成を開始します..."
echo ""

# venv環境の有効化
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
    echo "✓ venv環境を有効化しました"
else
    echo "✗ エラー: venv環境が見つかりません"
    exit 1
fi

# cairoライブラリのパスを設定（Mac）
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib

# アイコン生成
cd "$SCRIPT_DIR"
python create_icons.py

echo ""
echo "✓ アイコン生成が完了しました！"
echo ""
echo "次のステップ:"
echo "1. Chrome拡張機能を再読み込み (chrome://extensions/)"
echo "2. ツールバーのアイコンを確認"
