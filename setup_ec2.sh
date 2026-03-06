#!/bin/bash
# EC2（Linux）での初回セットアップスクリプト
# 日本語フォントと必要なパッケージをインストールします

set -e

echo "==================================================="
echo "Zircon Fun Tools - EC2 セットアップスクリプト"
echo "==================================================="
echo ""

# システム更新
echo "[1/5] システムパッケージを更新しています..."
sudo yum update -y

# Python依存関係（Python 3.12）
echo "[2/5] Python 3.12をインストールし、デフォルトに設定しています..."
sudo dnf install -y python3.12 python3.12-pip

# python3 コマンドを 3.12 に切り替え
sudo alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 100
sudo alternatives --set python3 /usr/bin/python3.12
echo "  python3 → $(python3 --version)"
# 日本語フォント
echo "[3/5] 日本語フォントをインストールしています..."
sudo yum install -y fontconfig google-noto-sans-cjk-jp-fonts

# フォントキャッシュ更新
echo "[4/5] フォントキャッシュを更新しています..."
sudo fc-cache -fv

# Chrome/ChromiumとChromeDriver（Selenium用）
echo "[5/5] Google Chromeをインストールしています..."
# Google Chrome リポジトリを追加
sudo tee /etc/yum.repos.d/google-chrome.repo <<EOF
[google-chrome]
name=google-chrome
baseurl=https://dl.google.com/linux/chrome/rpm/stable/x86_64
enabled=1
gpgcheck=1
gpgkey=https://dl.google.com/linux/linux_signing_key.pub
EOF

sudo yum install -y google-chrome-stable || {
    echo "警告: Google Chromeのインストールに失敗しました。"
    echo "Poster機能を使用する場合は手動でインストールしてください。"
}

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
