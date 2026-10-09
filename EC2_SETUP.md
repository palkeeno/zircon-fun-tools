# EC2/Linux運用ガイド

本番のプロセス管理は **systemdのみ** に統一します。Discord再接続はdiscord.pyが担当し、プロセス終了時の再起動はsystemdのRestart=on-failureです。watchdog・監視cron・nohupは併用しません。旧watchdog.sh/setup_cron.shは移行案内を表示して終了します。

## 初回セットアップ

Python 3.10以上（推奨3.12）、Chrome/Chromium、日本語フォントが必要です。トークン・チャンネル設定はリポジトリ直下の.envへ設定します。systemdのZFT_ENV=productionで本番設定を選びます。

Amazon Linux 2023の例:

```bash
sudo dnf install -y python3.12 python3.12-pip fontconfig google-noto-sans-cjk-jp-fonts
cd /path/to/zircon-fun-tools
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python setup_fonts.py --prepare
.venv/bin/python test/run_tests.py
bash scripts/install_service.sh
```

Ubuntu/DebianはディストリビューションのPython 3.10以上、venv、fontconfig、fonts-noto-cjkを準備してください。Chrome/Chromiumは公式のインストール手順で準備します。Seleniumが利用できるブラウザが必要です。

インストーラーはサービスのテンプレートに現在の絶対パスと実行ユーザーのUIDを埋め込み、.venv/bin/pythonを使用します。実行ユーザーは通常そのスクリプトを起動したユーザーです。別ユーザーで動かす場合はSERVICE_USER=ec2-user bash scripts/install_service.shと指定し、そのユーザーにリポジトリ・フォント・データのアクセス権を与えてください。テンプレートを直接コピーしないでください。

フォントは起動前に検証します。既存の日本語フォントがない場合だけ--prepareがNoto Sans JPを取得し、data/fontsへ保存します。生成中にダウンロードやシステムパッケージ変更は行いません。フォントのライセンスは配布元のGoogle Fonts/SIL Open Font Licenseを参照してください。

## 旧運用からの移行

1. 旧watchdogの常駐プロセスを特定して停止します。Botを先に止めるとwatchdogが再起動するため、この順序を守ります。
2. crontab -lでこのプロジェクトのwatchdog.sh --cronエントリーを確認し、crontab -eでその行だけ削除します。別プロジェクトのcronは変更しません。
3. 旧BotのPIDとコマンド行を確認し、そのBotだけを停止します。pkill -f "python3 main.py"のような広範な停止は避けてください。
4. Botの停止を確認してから、そのbot.pidを削除します。
5. 仮想環境と事前フォント準備を済ませ、bash scripts/install_service.shを実行します。

インストーラーは旧bot.pidや該当プロジェクトの監視cronが残っている場合に停止します。別ユーザーのcronや常駐watchdogは管理者が確認してください。既存JSONデータは削除・初期化しません。

## 起動・停止・ログ

```bash
sudo systemctl start zircon-bot.service
sudo systemctl stop zircon-bot.service
sudo systemctl restart zircon-bot.service
sudo systemctl status zircon-bot.service
sudo journalctl -u zircon-bot.service -n 100 --no-pager
sudo journalctl -u zircon-bot.service -f
```

start_bot.sh/stop_bot.sh/check_bot.sh/view_logs.shもsystemd操作に委譲します。ログはjournaldで管理し、Bot専用のログ監視cronは作りません。journaldの保存上限はホスト管理者が設定してください。旧ログを手動整理するcleanup_logs.shは残しています。

サービスはSIGINTで終了し、停止猶予は120秒です。ポスター処理中はワーカースレッドの完了を待ちます。再起動制限はUnit側のStartLimitIntervalSec=60とStartLimitBurst=5です。

## 更新と障害対応

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python test/run_tests.py
sudo systemctl restart zircon-bot.service
sudo journalctl -u zircon-bot.service -n 100 --no-pager
```

起動失敗時はログで設定・依存・データ形式を確認します。不正レコードは.rejected.jsonに報告されます。誕生日データの不正時は元データ保護のため機能ロードを停止します。修正後に再起動してください。再起動制限へ達した場合、原因修正後にsudo systemctl reset-failed zircon-bot.serviceを実行します。

本番へ適用する際は実サーバーのsystemd状態、Discordコマンド、実際の投稿を確認してください。ユニットテストは実Botログインや公式サイトの稼働を保証しません。
