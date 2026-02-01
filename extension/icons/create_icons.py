#!/usr/bin/env python3
from PIL import Image, ImageDraw
import sys

def create_icon(size):
    # 青い円形アイコンを作成
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 青い円
    margin = size // 10
    draw.ellipse([margin, margin, size-margin, size-margin], fill='#3b82f6')
    
    # マイクアイコン（簡易版）
    center = size // 2
    mic_width = size // 6
    mic_height = size // 4
    
    # マイク本体
    draw.ellipse([center-mic_width, center-mic_height*1.5, center+mic_width, center+mic_height*0.5], fill='white')
    # マイクスタンド
    draw.rectangle([center-2, center+mic_height*0.5, center+2, center+mic_height*1.2], fill='white')
    # マイクベース
    draw.rectangle([center-mic_width*0.8, center+mic_height*1.2, center+mic_width*0.8, center+mic_height*1.4], fill='white')
    
    return img

# 各サイズのアイコンを生成
for size in [16, 48, 128]:
    icon = create_icon(size)
    icon.save(f'icon{size}.png')
    print(f'Created icon{size}.png')
