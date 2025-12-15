# Zircon Fun Tools

Discordサーバーで遊べる様々なゲームや娯楽機能を提供するボットです。

## 設定管理ポリシー

- `.env` で定義する内容は環境依存の設定（トークンやチャンネルIDなど）です。
- 環境に依存しない静的な既定値は `config.py` の `FEATURES` で管理します。
- 運営コマンドで変更される設定のうち、定期投稿のオン/オフや投稿時刻などは `data/config.json` に保存し、ボット再起動後も保持します。

## 機能一覧

### 1. 誕生日管理 (`/birthday`)
キャラクターの誕生日を管理し、自動で誕生日を祝うメッセージを投稿します。

**利用可能なコマンド:**
- `/birthday [id_or_name]` - 誕生日一覧を表示。引数（IDまたは名前）を指定すると検索。
- `/birthday_update file:<CSV/JSON>` - ファイルをアップロードして誕生日データを一括更新（全置換）。**管理者のみ**
- `/birthday_toggle enabled:<true|false>` - 誕生日自動投稿のON/OFF切替（管理者のみ）
- `/birthday_schedule hour:<時>` - 誕生日自動投稿の時刻を設定（管理者のみ）

**自動通知:**
- 毎日設定された時刻（デフォルト: 9:00 JST）に自動でお祝いメッセージを投稿
- 時刻・有効/無効の設定はコマンドで変更でき、永続化されます
- 設定内容は `data/config.json` に保存され、ボット再起動後も維持されます

### 2. 占い機能 (`/oracle`)
複数の選択肢から1つをランダムに選んでアドバイスします。

**利用可能なコマンド:**
- `/oracle choices:<選択肢の数>` - 選択肢の数（1以上の整数）の中から、ランダムに選ばれた番号とメッセージが表示されます

### 3. 抽選機能 (`/lottery`)
指定されたロールを持つメンバーから指定人数をランダムに抽選します。

**利用可能なコマンド:**
- `/lottery role:<@参加者ロール> count:<当選者数>` - 抽選対象のロールから当選者数分、1人ずつカウントダウン演出付きで発表されます

**注意事項:**
- Next ボタンで次の当選者の発表に進みます
- キャンセル ボタンで抽選を中断できます

**制限:**
- 実行権限はDiscordの「連携 > アプリ」設定でロールやユーザーごとに制御してください。


### 4. ポスター生成 (`/poster`)
キャラクター情報からオリジナルポスター画像を生成します。

**利用可能なコマンド:**
- `/poster character_id:<キャラクターID>` - 指定したキャラクターIDのキャラ情報を公式サイトから抽出しポスター画像を作成します。

**注意事項:**
- 画像アセット（mask.png、国旗画像など）を `data/assets/` に配置すると見栄えが向上します（オプション）
- 詳細は `data/assets/README.md` を参照



### 5. 名言投稿（定期配信）(`/quote`)
名言を登録し、指定したスケジュールで自動投稿します。キャラクターIDが登録されている場合は公式サイトからキャラクター画像を取得し、埋め込みのサムネイルに設定します。

公式サイト: https://zircon.konami.net/nft/character/{character_id}

サムネイル画像取得は、既存のポスター機能と同様に以下のURLを利用します（高速・安定のため）。
- https://storage.googleapis.com/prd-azz-image/pfp_{character_id}.webp（主に4桁以下）
- https://storage.googleapis.com/prd-azz-image/pfp_{character_id}.png

埋め込みの構成:
- タイトル: 発言者名（必須フィールド）
- 説明: 名言本文
- サムネイル: キャラクター画像（キャラクターIDが登録されている場合のみ）
- URL: 公式キャラページ（キャラクターIDが登録されている場合のみ）
- フッター: `#<character_id> · quote_id:<内部ID>` （キャラクターIDが登録されている場合は `#` 付き、未登録の場合は `quote_id:<内部ID>` のみ）

利用可能なコマンド:
- `/quote [keyword]` – 名言一覧を表示。キーワードを指定すると検索。
- `/quote_update file:<CSV/JSON>` – 名言データをファイルで一括更新（全置換）。**管理者のみ**
- `/quote_toggle enabled:<true|false>` – 定期投稿のON/OFF切替（管理者のみ）
- `/quote_schedule days:<日数> hour:<時> minute:<分>` – 定期投稿のスケジュールを設定（例: days=1, hour=9, minute=0 で毎日9:00）（管理者のみ）

**名言IDの確認方法:**
- `/quote` (or search) で一覧表示時に各名言のIDが表示されます
- 定期投稿された名言のフッターに `quote_id:<ID>` が表示されます

CSVフォーマット（UTF-8 / BOM可）:
```
speaker,text[,character_id]
リオン,この勝負、もらった！,123
アリア,やるしかないんだ！,045
ナレーター,物語は続く...
```
- ヘッダ行は任意（上記例を推奨）
- `speaker`（発言者名）は必須
- `text`（名言本文）は必須
- `character_id` は任意（指定するとサムネイルと公式ページURLが設定される）

権限:
- 各コマンドの実行権限は、Discordサーバー設定の「連携 > アプリ > [Bot名]」から設定してください。
- デフォルトでは管理系コマンドは管理者（Administrator権限）のみ実行可能に設定されています。
- `/quote_update` などの管理コマンドは、特定の運用ロールにのみ許可することをお勧めします。

データ保存:
- `data/quotes.json` に保存（自動生成）
- レコード例:
   ```json
   {
      "id": "uuid-v4",
      "speaker": "リオン",
      "character_id": "123",
      "text": "名言本文",
      "created_by": 123456789012345678,
      "created_at": "2025-11-13T09:00:00+09:00",
      "updated_at": "2025-11-13T09:00:00+09:00"
   }
   ```

定期投稿の動作:
- 既定では `days=1, hour=9, minute=0`（毎日9:00）に `QUOTE_CHANNEL_ID_*` へランダムな1件を投稿
- 同一名言の連続投稿は避ける（直前投稿の再選出をスキップ）
- キャラクターIDが登録されている場合のみ、既存 `cogs/poster.py` と同様のロジックで画像取得（公式ページのスクレイピング + 画像は GCS の pfp_*）
- 設定はコマンドで変更可（オン/オフ、スケジュール）し、`data/config.json` に永続化

## セットアップ

### 必要な環境
- Python 3.8以上
- pip（Pythonパッケージマネージャー）
- Discord Bot アカウント（[Discord Developer Portal](https://discord.com/developers/applications)で作成）

### Discord Bot の準備

1. [Discord Developer Portal](https://discord.com/developers/applications)にアクセス
2. 「New Application」をクリックしてアプリケーションを作成
3. 左メニューから「Bot」を選択し、「Add Bot」をクリック
4. Bot のトークンをコピー（後で `.env` ファイルに記載）
5. 「Privileged Gateway Intents」で以下を有効化:
   - **MESSAGE CONTENT INTENT**
   - **SERVER MEMBERS INTENT**
6. 左メニューから「OAuth2」→「URL Generator」を選択
7. 「SCOPES」で `bot` と `applications.commands` をチェック
8. 「BOT PERMISSIONS」で以下をチェック:
   - Send Messages
   - Embed Links
   - Attach Files
   - Read Message History
   - Use Slash Commands
   - Manage Roles（抽選機能を使う場合）
9. 生成されたURLからBotをサーバーに招待

### インストール方法

1. **リポジトリをクローン**
```bash
git clone https://github.com/palkeeno/zircon-fun-tools.git
cd zircon-fun-tools
```

2. **仮想環境の作成と有効化**
```bash
# 仮想環境を作成
python -m venv venv

# Windowsの場合
venv\Scripts\activate

# Linux/Macの場合
source venv/bin/activate
```

3. **依存パッケージのインストール**
```bash
pip install -r requirements.txt
```

4. **環境変数の設定**

`.env` ファイルをプロジェクトルートに作成し、以下の内容を記述：

```env
# ========================================
# 環境設定
# ========================================
# development または production を指定
ENV=development

# ========================================
# Discord Bot トークン（必須）
# ========================================
# Discord Developer Portal で取得したトークンを設定
DISCORD_TOKEN_DEV=your_development_token_here
DISCORD_TOKEN_PROD=your_production_token_here

# ========================================
# ギルド（サーバー）設定
# ========================================
# スラッシュコマンドの即時同期用（開発時は設定推奨）
# サーバーIDを右クリック→「IDをコピー」で取得（開発者モード有効化が必要）
GUILD_ID_DEV=your_guild_id_here
GUILD_ID_PROD=0

# ========================================
# 権限設定
# ========================================
# 運営チャンネルのID
ADMIN_CHANNEL_ID_DEV=your_admin_channel_id_here
ADMIN_CHANNEL_ID_PROD=0

# ========================================
# 誕生日機能の設定
# ========================================
# 誕生日通知を投稿するチャンネルID
BIRTHDAY_CHANNEL_ID_DEV=your_birthday_channel_id_here
BIRTHDAY_CHANNEL_ID_PROD=0

# 通知設定はボット内の設定ファイル（data/config.json）で管理されます
# 初期値は「有効・毎日9:00 JST」。コマンドで変更すると自動的に保存されます

# ========================================
# 名言機能の設定（オプション）
# ========================================
# 名言の定期投稿を行うチャンネル
QUOTE_CHANNEL_ID_DEV=your_quote_channel_id_here
QUOTE_CHANNEL_ID_PROD=0

# 名言の定期投稿スケジュールは data/config.json に保存されます（初期値: 有効・1日おき 9:00）

# ========================================
# ポスター機能の設定（オプション）
# ========================================
# 画像アセットのパス（デフォルトは data/assets/ 配下）
# POSTER_MASK_PATH=data/assets/mask.png
# POSTER_PEACEFUL_PATH=data/assets/peaceful.png
# POSTER_BRAVE_PATH=data/assets/brave.png
# POSTER_GLORY_PATH=data/assets/glory.png
# POSTER_FREEDOM_PATH=data/assets/freedom.png

# ポスター投稿先チャンネルID
POSTER_CHANNEL_ID=0

# フォント設定（システムにインストールされているフォント名またはパス）

```

**重要な設定項目:**
- `DISCORD_TOKEN_DEV` / `DISCORD_TOKEN_PROD`: Discord Bot のトークン（**必須**）
- `GUILD_ID_DEV`: 開発用サーバーのID（設定すると即時コマンド反映）
- `BIRTHDAY_CHANNEL_ID_DEV`: 誕生日通知チャンネルのID

5. **データディレクトリの確認**

`data/` ディレクトリが自動作成されます。以下のファイルが使用されます：
- `data/birthdays.json` - 誕生日データ（自動生成）
- `data/config.json` - 各アプリの設定（自動生成）
- `data/overrides.json` - 権限オーバーライドデータ（自動生成）
- `data/quotes.json` - 名言データ（自動生成）
- `data/assets/` - ポスター機能用の画像アセット（手動配置）

6. **ポスター機能の画像アセット設定（オプション）**

`/poster` コマンドを使用する場合は、以下の画像ファイルを `data/assets/` ディレクトリに配置：
- `mask.png` - キャラクター画像合成用のマスク
- `peaceful.png`, `brave.png`, `glory.png`, `freedom.png` - 各国旗画像

詳細は `data/assets/README.md` を参照してください。

### 実行方法

```bash
python main.py
```

正常に起動すると以下のようなログが表示されます：
```
INFO - Logged in as YourBotName (ID: 123456789)
INFO - cogs.birthday をロードしました
INFO - cogs.oracle をロードしました
INFO - cogs.admin をロードしました
INFO - cogs.lottery をロードしました
INFO - cogs.poster をロードしました
INFO - ギルド 123456789 に X 個のスラッシュコマンドを同期しました
```

### トラブルシューティング

**Bot が起動しない場合:**
- `.env` ファイルのトークンが正しいか確認
- Python 3.8以上がインストールされているか確認
- `pip install -r requirements.txt` を再実行

**スラッシュコマンドが表示されない場合:**
- Bot の権限設定で `applications.commands` スコープが有効か確認
- `.env` の `GUILD_ID_DEV` を設定すると即時反映されます
- グローバル同期の場合、反映まで最大1時間かかります

**誕生日通知が来ない場合:**
- `BIRTHDAY_CHANNEL_ID_DEV` が正しく設定されているか確認
- Bot がそのチャンネルへの投稿権限を持っているか確認
- `/birthday_test` コマンドでテスト送信できるか確認

## 開発者向け情報

### ディレクトリ構造

```
zircon-fun-tools/
├── main.py              # エントリーポイント
├── config.py            # 設定管理
├── permissions.py       # 権限管理
├── setup_fonts.py       # フォント自動セットアップ
├── requirements.txt     # 依存パッケージ
├── .env                 # 環境変数（自分で作成）
├── cogs/                # 機能モジュール
│   ├── __init__.py
│   ├── birthday.py      # 誕生日機能
│   ├── oracle.py        # 占い機能
│   ├── lottery.py       # 抽選機能
│   ├── poster.py        # ポスター生成機能
│   ├── quotes.py        # 名言投稿機能（新規）
│   └── admin.py         # 権限管理機能
├── data/                # データファイル（自動生成）
│   ├── birthdays.json
│   ├── overrides.json
│   ├── quotes.json      # 名言データ
│   └── assets/          # 画像アセット（手動配置）
└── test/                # テストコード
    └── ...
```

### アーキテクチャ

- **discord.py**: Discord Bot フレームワーク
- **Cog システム**: 機能ごとにモジュール化
- **環境変数管理**: `.env` + `config.py` で一元管理
- **権限システム**: `permissions.py` で柔軟な権限制御
- **名言機能**: CSV/単発登録・編集・削除・定期投稿（埋め込みにキャラ画像・名前）

詳細な設計思想やコーディング規約については、`INSTRUCTIONS.md` を参照してください。

## エラーハンドリング

- ログに詳細なエラー情報が記録されます
- エラー発生時は適切なエラーメッセージが表示されます
- トークンが無効な場合は起動時にエラーを表示

## ライセンス

MIT License

## 作者

palkeeno

## 関連ドキュメント

- `INSTRUCTIONS.md` - AI 向け開発ガイド（設計思想・コーディング規約）
- `data/assets/README.md` - ポスター機能の画像アセット詳細
- `EC2_SETUP.md` - AWS EC2 での運用ガイド
- `POSTER_SETUP.md` - ポスター機能セットアップ詳細