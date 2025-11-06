#!/bin/bash
# EC2（Linux）での初回セットアップスクリプト
# 日本語フォントと必要なパッケージをインストールします

set -e

echo "==================================================="
echo "Zircon Fun Tools - EC2 セットアップスクリプト"
echo "==================================================="
echo ""

# システム更新
echo "[1/4] システムパッケージを更新しています..."
sudo apt update

# Python依存関係
echo "[2/4] Python3とpipをインストールしています..."
sudo apt install -y python3 python3-pip

# 日本語フォント
echo "[3/4] 日本語フォントをインストールしています..."
sudo apt install -y fonts-noto-cjk fonts-noto-cjk-extra

# フォントキャッシュ更新
echo "[4/4] フォントキャッシュを更新しています..."
sudo fc-cache -fv

echo ""
echo "==================================================="
echo "セットアップ完了！"
echo "==================================================="
echo ""
echo "次のステップ:"
echo "1. requirements.txtからPythonパッケージをインストール:"
echo "   pip3 install -r requirements.txt"
echo ""
echo "2. .envファイルを設定"
echo ""
echo "3. ボットを起動:"
echo "   python3 main.py"
echo ""
