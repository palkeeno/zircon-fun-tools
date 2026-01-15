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
- Chrome/ChromiumとChromeDriverのインストール（Selenium用）

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

# Chrome/ChromiumとChromeDriver（Selenium用）
sudo apt install -y chromium-browser chromium-chromedriver

# または、Google Chromeを使用する場合
# wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
# echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
# sudo apt update
# sudo apt install -y google-chrome-stable
```

### 3. Chrome/ChromiumとChromeDriverのインストール（Selenium用）

`poster`コマンドでWebスクレイピングを行うため、Chrome/ChromiumとChromeDriverが必要です。

```bash
# Chromium（推奨、軽量）
sudo apt install -y chromium-browser chromium-chromedriver

# または、Google Chromeを使用する場合
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable

# ChromeDriverのパス確認（必要に応じて）
which chromedriver
# または
which google-chrome-stable
```

**注意**: Selenium 4.6以降では、ChromeDriverを自動的にダウンロード・管理する機能がありますが、システムにインストールされたChromeDriverを使用することもできます。

### 4. Pythonパッケージのインストール

```bash
pip3 install -r requirements.txt
```

### 5. 環境変数の設定

`.env`ファイルを作成・編集：

```bash
cp .env.example .env  # サンプルがある場合
nano .env
```

必要な設定：
- `DISCORD_TOKEN_PROD`: 本番用Discordボットトークン
- その他、各機能の設定

### 6. ボットの起動

```bash
# 通常起動
python3 main.py

# バックグラウンド起動（推奨）
nohup python3 main.py > bot.log 2>&1 &

# スクリプトを使った起動（最も推奨）
./scripts/start_bot.sh

# systemdサービスとして起動
# 後述のsystemd設定を参照
```

## 自動再起動の設定（nohup + watchdog）

### スクリプト一覧

| スクリプト | 説明 |
|-----------|------|
| `scripts/start_bot.sh` | Botをnohupで起動し、PIDとログを記録 |
| `scripts/stop_bot.sh` | Botを安全に停止 |
| `scripts/check_bot.sh` | Botの状態を確認 |
| `scripts/watchdog.sh` | Botを監視し、停止時に自動再起動 |
| `scripts/setup_cron.sh` | cronジョブを設定 |
| `scripts/view_logs.sh` | ログを閲覧 |

### 初回セットアップ

```bash
# スクリプトに実行権限を付与
chmod +x scripts/*.sh

# Botを起動
./scripts/start_bot.sh

# ステータス確認
./scripts/check_bot.sh
```

### 自動再起動の設定（2つの方法）

#### 方法1: Watchdogをバックグラウンドで常駐（推奨）

```bash
# Watchdogをバックグラウンドで起動
nohup ./scripts/watchdog.sh > logs/watchdog_daemon.log 2>&1 &

# 30秒ごとにBotの状態を監視し、停止していれば自動で再起動
```

#### 方法2: Cronで定期チェック

```bash
# セットアップスクリプトを実行
./scripts/setup_cron.sh

# または手動でcronを設定
crontab -e
# 以下を追加（5分ごとにチェック）:
# */5 * * * * /home/ubuntu/zircon-fun-tools/scripts/watchdog.sh --cron
```

### ログの確認

```bash
# 最新のBotログを表示
./scripts/view_logs.sh

# リアルタイムでログを追跡
./scripts/view_logs.sh -f

# クラッシュログを確認
./scripts/view_logs.sh crash

# 監視ログを確認
./scripts/view_logs.sh watchdog

# 全ログファイル一覧
./scripts/view_logs.sh all

# 古いログを削除（7日以上前）
./scripts/view_logs.sh clean
```

### ログファイルの種類

| ファイル | 場所 | 内容 |
|---------|------|------|
| `bot_YYYYMMDD_HHMMSS.log` | `logs/` | Bot本体のログ（起動ごとに新規作成） |
| `crash.log` | `logs/` | クラッシュ時の詳細（最後の50行を記録） |
| `watchdog.log` | `logs/` | 監視スクリプトのログ |
| `shutdown.log` | `logs/` | 停止履歴 |

### 運用コマンド

```bash
# Botの状態確認
./scripts/check_bot.sh

# Botを再起動
./scripts/stop_bot.sh && ./scripts/start_bot.sh

# Botを停止（自動再起動を止める場合はwatchdogも停止）
./scripts/stop_bot.sh
pkill -f "watchdog.sh"
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

### ログのローテーション（自動化推奨）

ログファイルの肥大化を防ぐため、自動クリーンアップを設定してください。

#### 方法1: cronによる自動クリーンアップ（推奨）

```bash
# セットアップスクリプトを実行
./scripts/setup_cron.sh
```

これにより以下が設定されます：
- 5分ごとのBot監視と自動再起動
- 毎日午前3時に7日以上前のログファイルを自動削除

#### 方法2: 手動でログを削除

```bash
# 古いログを削除
./scripts/view_logs.sh clean

# または cleanup_logs.sh を直接実行（日数指定可能）
./scripts/cleanup_logs.sh 14  # 14日以上前を削除
```

#### 方法3: logrotateを使用

`/etc/logrotate.d/zircon-bot` を作成：

```
/home/ubuntu/zircon-fun-tools/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 644 ubuntu ubuntu
}
```

### クリーンアップスクリプトの機能

`scripts/cleanup_logs.sh` は以下を実行します：
- 指定日数（デフォルト7日）以上前の `bot_*.log` ファイルを削除
- `cron.log` が10MB超の場合、最新1000行に切り詰め
- `watchdog.log` が5MB超の場合、最新500行に切り詰め
- `crash.log` が5MB超の場合、最新1000行に切り詰め
- 空のログファイルを削除

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
