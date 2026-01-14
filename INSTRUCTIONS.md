# AI Development Instructions for Zircon Fun Tools

このドキュメントは、AI（GitHub Copilot、ChatGPT等）が本プロジェクトを理解し、一貫性のある修正・拡張を行うためのガイドです。

---

## プロジェクト概要

**Zircon Fun Tools** は、Discordサーバー向けの多機能Botです。誕生日管理、占い、抽選、ポスター生成などの娯楽機能を提供します。

### 主要な設計思想

1. **モジュール性**: 各機能は `cogs/` ディレクトリ内の独立した Cog として実装
2. **設定の一元管理**: 環境変数は `.env` → `config.py` で管理
3. **エラーハンドリング**: ログ出力とユーザーへの適切なフィードバック
4. **Discord のベストプラクティス準拠**: スラッシュコマンド、Embed、View システムの活用

---

## アーキテクチャ

### ディレクトリ構造

```
zircon-fun-tools/
├── main.py              # Bot起動のエントリーポイント
├── config.py            # 環境変数と設定の管理
├── utils.py             # ユーティリティ関数
├── setup_fonts.py       # フォント自動セットアップ（Linux用）
├── requirements.txt     # Pythonパッケージ依存関係
├── .env                 # 環境変数（Gitには含まれない）
├── cogs/                # 機能モジュール（Cog）
│   ├── __init__.py
│   ├── birthday.py      # 誕生日管理機能
│   ├── oracle.py        # 占い機能
│   ├── lottery.py       # 抽選機能
│   ├── poster.py        # ポスター生成機能
│   └── quotes.py        # 名言投稿機能
├── data/                # 永続化データ（自動生成）
│   ├── birthdays.json   # 誕生日データ
│   ├── config.json      # ランタイム設定（定期投稿スケジュール等）
│   ├── quotes.json      # 名言データ
│   └── assets/          # 画像アセット（手動配置）
└── test/                # ユニットテスト
    ├── __init__.py
    ├── run_tests.py
    ├── test_bot.py
    ├── test_cogs.py
    ├── test_config.py
    ├── test_quotes.py
    └── test_setup_fonts.py
```

### 主要コンポーネント

#### `main.py`
- Bot の起動とライフサイクル管理
- Cog の動的ロード
- スラッシュコマンドの同期（ギルド即時同期 or グローバル同期）
- エラーハンドリングとログ出力

#### `config.py`
- `.env` ファイルから環境変数を読み込み
- 環境（development/production）に応じた設定の切り替え
- 機能の有効/無効フラグ管理
- ヘルパー関数（`get_feature_settings()` 等）

#### `cogs/`
各 Cog は `commands.Cog` を継承し、スラッシュコマンドを `@app_commands.command` で定義します。

- **birthday.py**: 誕生日の登録・検索・一覧表示・通知機能
- **oracle.py**: 選択肢から1つをランダムに選ぶ占い機能
- **lottery.py**: ロールメンバーからランダムに抽選
- **poster.py**: キャラクター情報から画像ポスターを生成
- **quotes.py**: 名言の登録・検索・定期投稿機能

---

## コーディング規約

### 全般

- **PEP 8** に準拠した Python コードを書く
- **型ヒント** を可能な限り使用（`from typing import ...`）
- **Docstring** を関数・クラスに記述（Google スタイル推奨）
- **ログ出力** は `logging` モジュールを使用し、適切なレベル（INFO, WARNING, ERROR）を設定

### 命名規則

- **変数名・関数名**: `snake_case`
- **クラス名**: `PascalCase`
- **定数**: `UPPER_SNAKE_CASE`
- **プライベート関数/変数**: 先頭に `_` を付ける

### Cog の実装パターン

```python
import discord
from discord import app_commands
from discord.ext import commands
import logging
import config

logger = logging.getLogger(__name__)

class MyCog(commands.Cog):
    """Cog の説明"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MyCog が初期化されました")
    
    @app_commands.command(name="mycommand", description="コマンドの説明")
    async def my_command(self, interaction: discord.Interaction, arg: str):
        """コマンドの実装"""
        try:
            # 処理の実装
            await interaction.response.send_message(f"引数: {arg}")
        
        except Exception as e:
            logger.error(f"コマンド実行エラー: {e}", exc_info=True)
            await interaction.response.send_message(
                "エラーが発生しました。",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(MyCog(bot))
```

### エラーハンドリング

1. **try-except ブロック** でコマンド全体を囲む
2. **ログ出力** でスタックトレースを記録
3. **ユーザーへのフィードバック** を適切に返す（ephemeral メッセージ推奨）

```python
try:
    # 処理
    pass
except Exception as e:
    logger.error(f"エラー内容: {e}", exc_info=True)
    await interaction.response.send_message(
        "エラーが発生しました。管理者にお問い合わせください。",
        ephemeral=True
    )
```

### Discord API の使い方

#### Interaction レスポンス

```python
# 即座に応答（3秒以内）
await interaction.response.send_message("メッセージ", ephemeral=True)

# 遅延応答（処理に時間がかかる場合）
await interaction.response.defer(ephemeral=True)
# ... 処理 ...
await interaction.followup.send("結果")
```

#### Embed の使用

```python
embed = discord.Embed(
    title="タイトル",
    description="説明",
    color=discord.Color.blue()
)
embed.add_field(name="フィールド名", value="値", inline=False)
embed.set_footer(text="フッター")
await interaction.response.send_message(embed=embed)
```

#### View（ボタン・セレクト）の使用

```python
class MyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
    
    @discord.ui.button(label="ボタン", style=discord.ButtonStyle.primary)
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("ボタンが押されました")

view = MyView()
await interaction.response.send_message("メッセージ", view=view)
```

---

## データの永続化

### JSON ファイル

`data/` ディレクトリ配下にJSON形式でデータを保存します。

```python
import json
import os

DATA_FILE = "data/my_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

### 注意事項

- **UTF-8 エンコーディング** を使用
- **ディレクトリの自動作成** を行う
- **排他制御** が必要な場合は asyncio.Lock を検討

---

## テスト

`test/` ディレクトリに unittest ベースのテストコードを配置しています。

### テストの実行

```bash
python -m unittest discover test
# または
python test/run_tests.py
```

### テストの書き方

```python
import unittest
from unittest.mock import MagicMock, patch

class TestMyFeature(unittest.TestCase):
    def setUp(self):
        # テストの準備
        pass
    
    def test_something(self):
        # テストケース
        result = some_function()
        self.assertEqual(result, expected_value)
```

---

## 環境変数の管理

`.env` ファイルで環境変数を管理し、`config.py` で読み込みます。

### 環境変数の追加手順

1. `.env` に新しい変数を追加
2. `config.py` で `os.getenv()` を使って読み込み
3. 必要に応じてデフォルト値を設定
4. `README.md` に説明を追加

```python
# config.py の例
NEW_SETTING = os.getenv('NEW_SETTING', 'default_value')
```

---

## 新機能の追加手順

### 1. Cog ファイルの作成

`cogs/new_feature.py` を作成し、以下の構造で実装：

```python
import discord
from discord import app_commands
from discord.ext import commands
import logging
import config

logger = logging.getLogger(__name__)

class NewFeature(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("NewFeature が初期化されました")
    
    @app_commands.command(name="newcommand", description="新しいコマンド")
    async def new_command(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message("Hello!")
        except Exception as e:
            logger.error(f"エラー: {e}", exc_info=True)
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(NewFeature(bot))
```

### 2. main.py に登録

```python
self.initial_extensions = [
    'cogs.birthday',
    'cogs.oracle',
    'cogs.lottery',
    'cogs.poster',
    'cogs.quotes',
    'cogs.new_feature',  # 追加
]
```

### 3. config.py に機能フラグを追加（任意）

```python
FEATURES = {
    # ... 既存の機能 ...
    "new_feature": {
        "enabled": True,
        "settings": {}
    }
}
```

### 4. README.md に使い方を追加

新機能のコマンドと使い方を `README.md` の「機能一覧」セクションに記載します。

### 5. テストコードを作成

`test/test_new_feature.py` を作成し、ユニットテストを実装します。

---

## 修正・デバッグの方針

### 既存コードの修正

1. **影響範囲の確認**: 修正がどの機能に影響するか確認
2. **テストの実行**: 修正後は必ずテストを実行
3. **ログの確認**: エラーログを見て原因を特定
4. **段階的な修正**: 一度に多くを変えず、小さな単位で修正

### よくある問題と解決策

#### スラッシュコマンドが表示されない

- `.env` の `GUILD_ID_DEV` を設定してギルド即時同期を有効化
- Bot の OAuth2 スコープに `applications.commands` が含まれているか確認

#### データの読み込みエラー

- JSON ファイルのフォーマットが正しいか確認
- ファイルパスが正しいか確認
- エンコーディングが UTF-8 になっているか確認

---

## AIがコードを修正する際の注意事項

### 必ず守ること

1. **既存の設計思想を尊重する**: モジュール性、権限管理、エラーハンドリングのパターンを維持
2. **後方互換性を保つ**: 既存のデータ構造やコマンドの動作を壊さない
3. **ログを残す**: 重要な処理やエラーは必ずログ出力する
4. **ドキュメントを更新する**: コードの変更に合わせて `README.md` や `INSTRUCTIONS.md` を更新

### 推奨事項

- **型ヒント** を使って可読性を向上
- **Docstring** でコードの意図を明確化
- **テストコード** を書いて動作を保証
- **コミットメッセージ** は変更内容を簡潔に記述

### 禁止事項

- **直接的な `.env` ファイルの編集**: 環境変数の追加/変更は `README.md` に記載のみ
- **セキュリティリスクのあるコード**: トークンやAPIキーをハードコードしない
- **依存パッケージの無断追加**: 新しいパッケージは `requirements.txt` に追加し、理由を明記

---

## 自動実行の許可（AI向け）

### AI が許可を求めずに実行してよいこと

以下の操作は、ユーザーの明示的な許可を得ずに実行して構いません：

1. **コードの読み取り**: すべてのファイルの内容を読む
2. **コードの修正**: 
   - バグ修正
   - 機能追加
   - リファクタリング
   - ドキュメントの更新
3. **ファイルの作成**:
   - 新しい Cog ファイル
   - テストファイル
   - ドキュメントファイル
4. **依存関係の追加**: `requirements.txt` への追加（理由を明記）
5. **ログの追加**: デバッグやエラー追跡のためのログ出力
6. **テストの実行**: ユニットテストの実行と結果の報告

### AI が許可を求めるべきこと

以下の操作は、実行前にユーザーに確認を取るべきです：

1. **破壊的な変更**:
   - データファイルの削除
   - 大規模なアーキテクチャ変更
   - 後方互換性を破壊する変更
2. **外部サービスへの接続**: 
   - 新しい API の利用
   - 外部データベースの接続
3. **セキュリティに関わる変更**:
   - 権限管理の大幅な変更
   - 認証システムの変更

### 自動実行のガイドライン

- **段階的に進める**: 小さな変更を繰り返し、動作を確認しながら進める
- **変更内容を報告する**: 何を変更したか、なぜ変更したかを明確に説明する
- **エラーが出たら報告する**: 実行中にエラーが発生した場合は、ユーザーに報告して次の手順を相談する
- **テストを重視する**: コード変更後は必ずテストを実行し、動作を確認する

---

## よく使うコマンド例

### 開発環境の起動

```bash
# 仮想環境の有効化
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Bot の起動
python main.py
```

### テストの実行

```bash
# すべてのテストを実行
python -m unittest discover test

# 特定のテストのみ実行
python -m unittest test.test_cogs.TestBirthday
```

### 依存パッケージの更新

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# 新しいパッケージの追加
pip install new-package
pip freeze > requirements.txt
```

---

## まとめ

このドキュメントは、AI が本プロジェクトを効率的かつ一貫性を持って修正・拡張するためのガイドです。コードを変更する際は、以下を意識してください：

1. **設計思想を理解する**: モジュール性、権限管理、エラーハンドリング
2. **既存パターンを踏襲する**: Cog の実装、権限チェック、ログ出力
3. **ドキュメントを更新する**: コードの変更に合わせて `README.md` を更新
4. **テストを実行する**: 変更後は必ずテストで動作確認
5. **自動実行の範囲を理解する**: 許可なく実行してよいこと、確認が必要なこと

このガイドラインに従うことで、プロジェクトの品質と一貫性を保ちながら、効率的に開発を進めることができます。

---

**最終更新日**: 2026-01-15
