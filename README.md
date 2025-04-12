# Zircon Fun Tools

Discordサーバーで遊べる様々なゲームや娯楽機能を提供するボットです。

## 機能

### 1. じゃんけんゲーム
- 1対1のじゃんけんができます
- ボタンUIで直感的な操作
- タイムアウト機能付き

### 2. 占い機能
- 選択肢の数（1-20）を指定して占うことができます
- ランダムな結果を表示
- 装飾的なメッセージと埋め込み表示

### 3. コメディゲーム
- キャット＆チョコレート風の大喜利ゲーム
- お題に対して解決策を考え、投票で判定
- カードシステム（アイテムやスキル）を使用

## セットアップ

### 必要な環境
- Python 3.8以上
- pip（Pythonパッケージマネージャー）

### インストール方法

1. リポジトリをクローン
```bash
git clone https://github.com/your-username/zircon-fun-tools.git
cd zircon-fun-tools
```

2. 仮想環境の作成と有効化
```bash
python -m venv venv
# Windowsの場合
venv\Scripts\activate
# Linux/Macの場合
source venv/bin/activate
```

3. 依存パッケージのインストール
```bash
pip install -r requirements.txt
```

4. 環境変数の設定
`.env`ファイルを作成し、以下の内容を記述：
```env
# 環境設定
ENV=development  # または production

# Discordボットトークン
DISCORD_TOKEN_DEV=your_development_token_here
DISCORD_TOKEN_PROD=your_production_token_here
```

### 実行方法

```bash
python main.py
```

## コマンド一覧

### じゃんけん
- `/janken @ユーザー` - 指定したユーザーとじゃんけんを開始

### 占い
- `/fortune 選択肢の数` - 指定した数の選択肢から1つを選ぶ占い

### コメディゲーム
- `/comedy` - 大喜利ゲームを開始
- `/answer カード数 回答` - お題に対する回答を提出

## エラーハンドリング

- ログファイルに詳細なエラー情報が記録されます
- エラー発生時は適切なエラーメッセージが表示されます
- トークンが無効な場合は起動時にエラーを表示

## ライセンス

MIT License

## 作者

palkeeno