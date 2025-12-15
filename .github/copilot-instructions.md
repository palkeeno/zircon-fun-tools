# GitHub Copilot Instructions for Zircon Fun Tools

このファイルは、GitHub Copilot がこのリポジトリで作業する際の動作指示を定義します。

---

## 自動実行ポリシー

GitHub Copilot は、以下の操作を**ユーザーの明示的な許可を求めずに自動で実行してよい**ものとします：

### ✅ 許可なく実行してよい操作

#### 1. コードの読み取り
- すべてのファイルの内容を読む
- ディレクトリ構造の確認
- 依存関係の調査

#### 2. コードの修正・追加
- **バグ修正**: エラーログに基づく修正、論理エラーの修正
- **機能追加**: 新しい Cog の作成、コマンドの追加
- **リファクタリング**: コードの可読性向上、パフォーマンス改善
- **型ヒントの追加**: 既存コードへの型アノテーション追加
- **Docstring の追加**: 関数やクラスへのドキュメンテーション
- **ログの追加**: デバッグやエラー追跡のためのログ出力

#### 3. ファイルの作成
- 新しい Cog ファイル（`cogs/` 配下）
- テストファイル（`test/` 配下）
- ドキュメントファイル（Markdown 形式）
- 設定ファイル（JSON 形式、データファイル等）

#### 4. 依存関係の管理
- `requirements.txt` への新しいパッケージの追加（理由を明記）
- 既存パッケージのバージョン更新（互換性が保証される場合）

#### 5. テストとデバッグ
- ユニットテストの実行
- テストコードの作成・修正
- エラーログの確認と原因特定

#### 6. ドキュメントの更新
- `README.md` の更新（機能追加時）
- `INSTRUCTIONS.md` の更新（設計変更時）
- コメントの追加・修正

---

### ⚠️ 実行前に確認が必要な操作

以下の操作は、実行前にユーザーに確認を取る必要があります：

#### 1. 破壊的な変更
- データファイル（`data/` 配下）の削除
- 大規模なアーキテクチャ変更（Cog の構造変更、config.py の大幅な変更）
- 後方互換性を破壊する変更（既存コマンドの削除、データフォーマットの変更）

#### 2. 外部サービスへの接続
- 新しい外部 API の利用
- 外部データベースへの接続
- 外部サービスとの認証連携

#### 3. セキュリティに関わる変更
- 権限管理システムの大幅な変更
- 認証システムの導入・変更
- 環境変数の削除（追加は OK）

#### 4. 本番環境への影響
- 本番環境固有の設定変更
- デプロイスクリプトの大幅な変更

---

## プロジェクトの設計思想

Copilot は以下の設計思想を理解し、コードを修正する際は必ず従ってください。

### 1. モジュール性
- 各機能は独立した Cog として実装
- Cog 間の依存は最小限に
- `config.py`は共通モジュールとして利用可

### 2. 権限管理
- すべてのコマンドはDiscordサーバー側で権限設定を行うためコード上では制御しない

### 3. エラーハンドリング
- すべての非同期コマンドは `try-except` で囲む
- エラーは `logger.error()` でログ出力（スタックトレース含む）
- ユーザーには分かりやすいエラーメッセージを返す（`ephemeral=True` 推奨）

### 4. 設定の一元管理
- 環境変数は `.env` ファイルで管理
- `config.py` で読み込み、デフォルト値を設定
- 機能の有効/無効は `config.FEATURES` で管理

### 5. Discord API のベストプラクティス
- スラッシュコマンド（`@app_commands.command`）を使用
- インタラクションには3秒以内に応答（長時間処理は `defer()` を使用）
- Embed や View を活用してリッチな UI を提供

---

## コーディング規約

### 命名規則
- 変数名・関数名: `snake_case`
- クラス名: `PascalCase`
- 定数: `UPPER_SNAKE_CASE`
- プライベート関数/変数: 先頭に `_`

### 型ヒント
- 可能な限り型ヒントを使用
- `from typing import ...` で必要な型をインポート

### Docstring
- すべての関数とクラスに Docstring を記述
- Google スタイルを推奨

### ログ出力
- `logging` モジュールを使用
- ログレベルは適切に設定（DEBUG, INFO, WARNING, ERROR）

---

## Cog 実装のテンプレート

新しい Cog を作成する際は、以下のテンプレートを使用してください：

```python
"""新機能の説明"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
import config
import permissions

logger = logging.getLogger(__name__)

class NewFeature(commands.Cog):
    """新機能を提供する Cog"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("NewFeature が初期化されました")
    
    @app_commands.command(name="newcommand", description="コマンドの説明")
    async def new_command(self, interaction: discord.Interaction, arg: str):
        """
        コマンドの詳細説明
        
        Args:
            interaction: Discord インタラクション
            arg: 引数の説明
        """
        try:
            # 権限チェック（必要な場合）
            if not permissions.can_run_command(interaction, 'newcommand'):
                await interaction.response.send_message(
                    "このコマンドを実行する権限がありません。",
                    ephemeral=True
                )
                return
            
            # 処理の実装
            await interaction.response.send_message(f"引数: {arg}")
        
        except Exception as e:
            logger.error(f"コマンド実行エラー: {e}", exc_info=True)
            await interaction.response.send_message(
                "エラーが発生しました。管理者にお問い合わせください。",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(NewFeature(bot))
```

---

## 作業の進め方

### 段階的なアプローチ
1. **現状把握**: ファイルを読み、既存のコード構造を理解
2. **小さな変更**: 一度に多くを変えず、小さな単位で修正
3. **テスト実行**: 変更後は必ずテストを実行して動作確認
4. **ドキュメント更新**: コードの変更に合わせて `README.md` を更新

### 変更内容の報告
コードを修正した後は、以下の情報をユーザーに報告してください：
- 何を変更したか
- なぜ変更したか
- どのような影響があるか
- 追加のアクションが必要か（依存パッケージのインストール等）

### エラー発生時
エラーが発生した場合は、以下の手順で対処してください：
1. エラーメッセージとスタックトレースを確認
2. 原因を特定
3. 修正案をユーザーに提示
4. ユーザーの承認を得て修正を実行

---

## よくあるタスクと対応方法

### 新しいコマンドの追加
1. 適切な Cog ファイルに `@app_commands.command` を追加
2. 権限チェックが必要な場合は `permissions.can_run_command()` を呼び出し
3. エラーハンドリングを実装
4. `README.md` に使い方を追加

### バグ修正
1. ログやエラーメッセージから原因を特定
2. 該当箇所を修正
3. テストを実行して動作確認
4. 変更内容をユーザーに報告

### 機能の追加
1. 新しい Cog ファイルを作成
2. `main.py` の `initial_extensions` に追加
3. 必要に応じて `config.py` に設定を追加
4. テストコードを作成
5. `README.md` に使い方を追加

---

## 禁止事項

以下の行為は禁止されています：

1. **トークンやAPIキーのハードコード**: 必ず環境変数を使用
2. **`.env` ファイルの編集**: 環境変数の追加/変更は `README.md` に記載のみ
3. **データの無断削除**: `data/` 配下のファイルは慎重に扱う
4. **セキュリティリスクのあるコード**: 権限チェックを省略しない
5. **依存パッケージの無断追加**: 理由を明記し、`requirements.txt` に記載

---

## まとめ

このファイルに従うことで、GitHub Copilot は以下を実現できます：

1. **自律的な作業**: 許可を求めずに効率的にコードを修正・追加
2. **一貫性のある実装**: 既存の設計思想とコーディング規約に従った実装
3. **高品質なコード**: エラーハンドリング、ログ出力、ドキュメントを含む
4. **ユーザーとの協調**: 重要な変更は確認を取り、変更内容を報告

**重要**: このファイルは、GitHub Copilot が効率的に作業を進めるためのガイドラインです。実行前に確認が必要な操作については、必ずユーザーに確認を取ってください。

---

**最終更新日**: 2025-11-11
