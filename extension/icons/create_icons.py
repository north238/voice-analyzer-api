#!/usr/bin/env python3
"""
Chrome拡張機能用のアイコン画像生成スクリプト

icon.svgから各サイズ（16x16, 48x48, 128x128）のPNGファイルを生成します。
"""
import sys
from pathlib import Path

try:
    import cairosvg
except ImportError:
    print("Error: cairosvg がインストールされていません。")
    print("インストール方法: pip install cairosvg")
    sys.exit(1)


def create_icon(svg_path: str, output_path: str, size: int):
    """
    SVGファイルから指定サイズのPNG画像を生成

    Args:
        svg_path: 入力SVGファイルのパス
        output_path: 出力PNGファイルのパス
        size: 出力サイズ（幅と高さ）
    """
    try:
        cairosvg.svg2png(
            url=svg_path,
            write_to=output_path,
            output_width=size,
            output_height=size,
        )
        print(f"✓ 生成完了: {output_path} ({size}x{size})")
    except Exception as e:
        print(f"✗ エラー: {output_path} の生成に失敗しました - {e}")
        sys.exit(1)


def main():
    """メイン処理"""
    # スクリプトのディレクトリを取得
    script_dir = Path(__file__).parent
    svg_path = script_dir / "icon.svg"

    # SVGファイルの存在確認
    if not svg_path.exists():
        print(f"Error: {svg_path} が見つかりません。")
        sys.exit(1)

    print(f"入力SVG: {svg_path}")
    print("-" * 50)

    # 各サイズのアイコンを生成
    sizes = [16, 48, 128]
    for size in sizes:
        output_path = script_dir / f"icon{size}.png"
        create_icon(str(svg_path), str(output_path), size)

    print("-" * 50)
    print(f"✓ 全てのアイコン生成が完了しました！")
    print(f"\n生成されたファイル:")
    for size in sizes:
        print(f"  - icon{size}.png")


if __name__ == "__main__":
    main()
