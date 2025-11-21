# Zircon Fun Tools

Discordサーバーで遊べる様々なゲームや娯楽機能を提供するボットです。

## 機能一覧

### 1. 誕生日管理 (`/birthday_*`)
キャラクターの誕生日を管理し、自動で誕生日を祝うメッセージを投稿します。

**利用可能なコマンド:**
- `/birthday_list` - 登録されている全ての誕生日を一覧表示（ページネーション付き）
- `/birthday_search id_or_name:<キャラID or キャラ名>` - 特定のキャラクターの誕生日をIDか名前で検索
- `/birthday_add id:<キャラID> month:<月> date:<日>` - 誕生日を登録（運営のみ）
- `/birthday_delete id:<キャラID>` - 誕生日を削除（運営のみ）
- `/birthday_import file:<CSVファイル>` - CSV形式で一括インポート（運営のみ）

**自動通知:**
- 毎日設定された時刻（デフォルト9:00 JST）に自動でお祝いメッセージを投稿

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
- 運営ロール、または権限を付与されたロールのメンバーのみ実行可能

### 4. ポスター生成 (`/poster`)
キャラクター情報からオリジナルポスター画像を生成します。

**利用可能なコマンド:**
- `/poster character_id:<キャラクターID>` - 指定したキャラクターIDのキャラ情報を公式サイトから抽出しポスター画像を作成します。

**注意事項:**
- 画像アセット（mask.png、国旗画像など）を `data/assets/` に配置すると見栄えが向上します（オプション）
- 詳細は `data/assets/README.md` を参照

### 5. 権限管理 (`/permit_*`)
コマンドの実行権限を特定のロールに付与します。

**利用可能なコマンド:**
- `/permit_grant command:<コマンド名> role:<ロール>` - 指定コマンドの実行権限を付与
- `/permit_revoke command:<コマンド名> role:<ロール>` - 付与した権限を取り消し
- `/permit_list` - 現在の権限設定を一覧表示

**制限:**
- 運営ロールを持つメンバーのみ実行可能

### 6. 名言投稿（定期配信）(`/quote_*`)
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
- `/quote_list [page:<ページ番号>]` – 登録されている全ての名言を一覧表示（ページネーション付き、1ページ10件）
- `/quote_search keyword:<キーワード>` – 発言者名または名言本文からキーワード検索
- `/quote_add speaker:<発言者名> text:<名言本文> [character_id:<キャラクターID>]` – 名言を1件登録（character_idは任意）
- `/quote_edit quote_id:<名言ID> [speaker:<発言者名>] [text:<名言本文>] [character_id:<キャラクターID>]` – 名言情報を編集（運営のみ）
- `/quote_delete quote_id:<名言ID>` – 名言を削除（運営のみ）
- `/quote_import file:<CSVファイル>` – 名言を一括登録（CSV）（運営のみ）
- `/quote_toggle enabled:<true|false>` – 定期投稿のON/OFF切替（運営のみ）
- `/quote_schedule days:<日数> hour:<時> minute:<分>` – 定期投稿のスケジュールを設定（例: days=1, hour=9, minute=0 で毎日9:00）（運営のみ）

**名言IDの確認方法:**
- `/quote_list` で一覧表示時に各名言のIDが表示されます
- `/quote_search` で検索した結果にもIDが表示されます
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
- 追加/編集/削除/インポート/設定系（toggle, schedule）は運営ロール、または `permissions.can_run_command()` により許可されたロールのみ
- 通常の閲覧や投稿はボットが自動で行います

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
- 設定はコマンドで変更可（オン/オフ、スケジュール）し、永続化

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
# 運営ロールのID（運営コマンド実行に必要）
OPERATOR_ROLE_ID_DEV=your_operator_role_id_here
OPERATOR_ROLE_ID_PROD=0

# 運営チャンネルのID
ADMIN_CHANNEL_ID_DEV=your_admin_channel_id_here
ADMIN_CHANNEL_ID_PROD=0

# ========================================
# 誕生日機能の設定
# ========================================
# 誕生日通知を投稿するチャンネルID
BIRTHDAY_CHANNEL_ID_DEV=your_birthday_channel_id_here
BIRTHDAY_CHANNEL_ID_PROD=0

# 通知時刻（24時間形式）
BIRTHDAY_ANNOUNCE_TIME_HOUR=9
BIRTHDAY_ANNOUNCE_TIME_MINUTE=0

# ========================================
# 名言機能の設定（オプション）
# ========================================
# 名言の定期投稿を行うチャンネル
QUOTE_CHANNEL_ID_DEV=your_quote_channel_id_here
QUOTE_CHANNEL_ID_PROD=0

# 名言定期投稿の有効/無効（コマンドで変更可能、ここは初期値）
QUOTE_POST_ENABLED=true

# 投稿間隔（分） 例: 1440=1日
QUOTE_POST_INTERVAL_MINUTES=1440

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
- `OPERATOR_ROLE_ID_DEV`: 運営ロールのID（運営コマンド使用に必要）
- `BIRTHDAY_CHANNEL_ID_DEV`: 誕生日通知チャンネルのID

5. **データディレクトリの確認**

`data/` ディレクトリが自動作成されます。以下のファイルが使用されます：
- `data/birthdays.json` - 誕生日データ（自動生成）
- `data/overrides.json` - 誕生日のオーバーライドデータ（自動生成）
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

**運営コマンドが使えない場合:**
- `OPERATOR_ROLE_ID_DEV` が正しく設定されているか確認
- 自分がそのロールを持っているか確認

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