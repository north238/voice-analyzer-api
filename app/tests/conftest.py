"""
pytest設定ファイル

Dockerコンテナ内およびローカル環境でのテスト実行時にインポートパスを調整する
"""
import sys
from pathlib import Path

# プロジェクトルート（voice-analyzer-api/）をPYTHONPATHに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# appディレクトリ（voice-analyzer-api/app/）もPYTHONPATHに追加
# これにより、services/内のファイルから "from utils.logger import" が動作する
app_dir = Path(__file__).parent.parent
sys.path.insert(0, str(app_dir))
