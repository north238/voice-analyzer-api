# Chrome拡張機能アイコン

リアルタイム音声文字起こしChrome拡張機能のアイコンファイルです。

## デザイン

- **コンセプト**: マイク + 音波で「音声文字起こし」を表現
- **カラースキーム**: 青系グラデーション（#3b82f6 → #2563eb）
- **構成要素**:
  - 中央: 白いマイク（カプセル形状）
  - 周囲: 8方向に広がる音波
  - 背景: 青のグラデーション円形

## ファイル構成

```
icons/
├── icon.svg          # ソースSVGファイル（128x128）
├── icon16.png        # ツールバー用（16x16）
├── icon48.png        # 拡張機能管理画面用（48x48）
├── icon128.png       # Chromeウェブストア用（128x128）
├── create_icons.py   # PNG生成スクリプト
└── README.md         # このファイル
```

## アイコンの再生成

SVGファイルを編集した後、以下のコマンドでPNGファイルを再生成できます。

### 前提条件

```bash
# cairosvgのインストール（初回のみ）
pip install cairosvg
```

### 生成手順

#### 方法1: シェルスクリプトを使用（推奨）

```bash
# iconsディレクトリに移動
cd extension/icons

# スクリプト実行
bash generate_icons.sh
```

#### 方法2: Pythonスクリプトを直接実行

```bash
# iconsディレクトリに移動
cd extension/icons

# venv環境を有効化
source ../../venv/bin/activate

# 環境変数を設定してスクリプト実行
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib python create_icons.py
```

実行すると、以下のファイルが生成されます：
- `icon16.png` (16x16px)
- `icon48.png` (48x48px)
- `icon128.png` (128x128px)

## デザイン変更時の注意

### サイズ別の視認性

各サイズで視認性を確保するため、以下に注意してください：

- **16x16**: 最小サイズ。線の太さは2.5px以上推奨
- **48x48**: 中サイズ。詳細が見えるが、複雑すぎないように
- **128x128**: 最大サイズ。グラデーションや細かいディテール可

### カラーコントラスト

- 背景色と前景色のコントラスト比は4.5:1以上を推奨
- Chromeツールバーは明るい背景・暗い背景両方で使用されるため、どちらでも視認できるように

### Chrome拡張機能ガイドライン

- 背景は透過または単色/グラデーション
- シンプルで認識しやすいデザイン
- ブランドカラーの統一

## トラブルシューティング

### cairosvgのインストールエラー

Macの場合、以下の依存関係が必要です：

```bash
# Homebrewでcairoをインストール
brew install cairo pkg-config

# その後、cairosvgをインストール
pip install cairosvg
```

Linuxの場合：

```bash
# Ubuntuの場合
sudo apt-get install libcairo2-dev pkg-config python3-dev

# その後、cairosvgをインストール
pip install cairosvg
```

### SVGの表示確認

ブラウザでSVGを直接開いて確認できます：

```bash
# Macの場合
open icon.svg

# Linuxの場合
xdg-open icon.svg
```

## 参考リンク

- [Chrome Extension Icon Guidelines](https://developer.chrome.com/docs/webstore/images/)
- [cairosvg Documentation](https://cairosvg.org/)
- [SVG Tutorial](https://developer.mozilla.org/ja/docs/Web/SVG/Tutorial)
