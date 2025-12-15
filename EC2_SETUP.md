# Zircon Fun Tools - EC2デプロイガイド

## EC2での初回セットアップ

### 1. 自動セットアップ（推奨）

プロジェクトディレクトリで以下を実行：

```bash
chmod +x setup_ec2.sh
./setup_ec2.sh
```

このスクリプトは以下を自動的に実行します：
- システムパッケージの更新
- Python3とpipのインストール
- 日本語フォント（Noto CJK）のインストール
- フォントキャッシュの更新

### 2. 手動セットアップ

自動スクリプトが使えない場合は、以下を順番に実行：

```bash
# システム更新
sudo apt update

# Python環境
sudo apt install -y python3 python3-pip

# 日本語フォント
sudo apt install -y fonts-noto-cjk fonts-noto-cjk-extra

# フォントキャッシュ更新
sudo fc-cache -fv

# フォント確認
fc-list :lang=ja | head -5
```

### 3. Pythonパッケージのインストール

```bash
pip3 install -r requirements.txt
```

### 4. 環境変数の設定

`.env`ファイルを作成・編集：

```bash
cp .env.example .env  # サンプルがある場合
nano .env
```

必要な設定：
- `DISCORD_TOKEN_PROD`: 本番用Discordボットトークン
- その他、各機能の設定

### 5. ボットの起動

```bash
# 通常起動
python3 main.py

# バックグラウンド起動（推奨）
nohup python3 main.py > bot.log 2>&1 &

# systemdサービスとして起動（最も推奨）
# 後述のsystemd設定を参照
```

## systemdサービス設定（推奨）

### サービスファイルの作成

```bash
sudo nano /etc/systemd/system/zircon-bot.service
```

以下の内容を記述：

```ini
[Unit]
Description=Zircon Fun Tools Discord Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/zircon-fun-tools
Environment="ENV=production"
ExecStart=/usr/bin/python3 /home/ubuntu/zircon-fun-tools/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### サービスの有効化と起動

```bash
# サービスを有効化
sudo systemctl enable zircon-bot.service

# サービスを起動
sudo systemctl start zircon-bot.service

# ステータス確認
sudo systemctl status zircon-bot.service

# ログ確認
sudo journalctl -u zircon-bot.service -f
```

### サービスの管理コマンド

```bash
# 停止
sudo systemctl stop zircon-bot.service

# 再起動
sudo systemctl restart zircon-bot.service

# ログ表示
sudo journalctl -u zircon-bot.service --lines=100
```

## フォント関連のトラブルシューティング

### フォントが見つからない場合

```bash
# インストール済みフォント一覧
fc-list :lang=ja

# 日本語フォントを再インストール
sudo apt install --reinstall fonts-noto-cjk fonts-noto-cjk-extra

# キャッシュを強制更新
sudo fc-cache -fv
```

### 自動フォント機能について

起動時に `setup_fonts.py` が実行され、以下をチェック：
1. Linux環境かどうか
2. 日本語フォントがインストールされているか
3. root権限がある場合は自動インストール
4. ない場合は警告メッセージを表示

## セキュリティ設定

### ファイアウォール設定（必要に応じて）

```bash
# UFWを有効化
sudo ufw enable

# SSH許可
sudo ufw allow ssh

# HTTPSアウトバウンド（Discord API用）
sudo ufw allow out 443/tcp
```

### 定期的な更新

```bash
# システムパッケージの更新
sudo apt update && sudo apt upgrade -y

# Pythonパッケージの更新
pip3 install --upgrade -r requirements.txt
```

## 監視とメンテナンス

### ログのローテーション

`/etc/logrotate.d/zircon-bot` を作成：

```
/home/ubuntu/zircon-fun-tools/bot.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 644 ubuntu ubuntu
}
```

### リソース監視

```bash
# CPU/メモリ使用状況
top -p $(pgrep -f "python3 main.py")

# ディスク使用状況
df -h
```

## トラブルシューティング

### ボットが起動しない

```bash
# ログ確認
tail -100 bot.log
sudo journalctl -u zircon-bot.service -n 100

# 手動起動でエラー確認
python3 main.py
```

### 依存関係エラー

```bash
# requirements.txtを再インストール
pip3 install --force-reinstall -r requirements.txt
```

### ディスク容量不足

```bash
# 古いログを削除
find . -name "*.log" -mtime +30 -delete

# Pythonキャッシュをクリア
find . -type d -name __pycache__ -exec rm -r {} +
```
