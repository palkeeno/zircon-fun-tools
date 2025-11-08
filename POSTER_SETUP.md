# ポスター機能セットアップガイド

## 概要

`/poster` コマンドは、キャラクター情報を基にカスタムポスター画像を生成する機能です。この機能を使用するには、いくつかの画像アセットが必要です。

## 必要な画像ファイル

以下の画像ファイルを `data/assets/` ディレクトリに配置してください：

### 2. mask.png（必須）
- **説明**: キャラクター画像を合成するためのマスク画像
- **推奨サイズ**: 1920x1920ピクセル
- **フォーマット**: PNG（グレースケールまたは透過）
- **用途**: キャラクター画像の表示範囲を制御

### 3. 国旗画像（必須）
以下の4つの国旗画像が必要です：
- **peaceful.png** - Peaceful国の旗
- **brave.png** - Brave国の旗  
- **glory.png** - Glory国の旗
- **freedom.png** - Freedom国の旗

各画像の仕様：
- **推奨サイズ**: 適切なサイズ（ポスター上での表示位置に応じて調整）
- **フォーマット**: PNG（透過推奨）

## セットアップ手順

### ステップ1: 画像ファイルの準備

必要な画像ファイルを用意します。これらは：
- 自分で作成する
- デザイナーに依頼する
- プロジェクトの他のメンバーから取得する

### ステップ2: ファイルの配置

```
zircon-fun-tools/
├── data/
│   ├── assets/
│   │   ├── mask.png          ← ここに配置
│   │   ├── peaceful.png      ← ここに配置
│   │   ├── brave.png         ← ここに配置
│   │   ├── glory.png         ← ここに配置
│   │   └── freedom.png       ← ここに配置
│   └── ...
└── ...
```

### ステップ3: セットアップの確認

以下のコマンドで設定を確認できます：

```bash
python check_setup.py
```

すべての画像ファイルに ✅ が表示されれば完了です！

## トラブルシューティング

### Q: ボット起動時に警告が表示される

```
WARNING:cogs.poster:⚠️ 以下の画像アセットが見つかりません:
```

**A**: 画像ファイルが正しい場所に配置されていません。
- ファイル名が正確に一致しているか確認
- `data/assets/` ディレクトリに配置されているか確認
- ファイルの拡張子が `.png` であることを確認

### Q: `/poster` コマンドを実行するとエラーが出る

**A**: 以下を確認してください：
1. すべての必須画像ファイルが配置されているか
2. `check_setup.py` を実行して確認
3. ボットを再起動して変更を適用

### Q: ポスター機能を使用しない場合

**A**: 画像アセットは不要です。警告メッセージは無視して構いません。`/poster` コマンドを実行しなければエラーは発生しません。

## カスタマイズ

### 環境変数での画像パス指定

デフォルト以外の場所に画像を配置したい場合は、`.env` ファイルで指定できます：

```env
# ポスター画像のカスタムパス
POSTER_MASK_PATH=/path/to/custom/mask.png
POSTER_PEACEFUL_PATH=/path/to/custom/peaceful.png
POSTER_BRAVE_PATH=/path/to/custom/brave.png
POSTER_GLORY_PATH=/path/to/custom/glory.png
POSTER_FREEDOM_PATH=/path/to/custom/freedom.png
```

### フォントのカスタマイズ

`.env` ファイルでフォントも指定できます：

```env
# ポスター用フォント
POSTER_FONT_A=C:\Windows\Fonts\meiryo.ttc
POSTER_FONT_B=C:\Windows\Fonts\meiryo.ttc
POSTER_FONT_C=C:\Windows\Fonts\meiryo.ttc
POSTER_FONT_D=C:\Windows\Fonts\meiryo.ttc
```

フォントが見つからない場合は、自動的にシステムフォントまたはNoto Sans JPがダウンロードされます。

## 技術的な詳細

- **画像形式**: PNG推奨（透過チャンネル対応）
- **色空間**: RGB/RGBA
- **処理ライブラリ**: Pillow (PIL)
- **合成方法**: Alpha合成、マスク合成

## サポート

問題が解決しない場合は、以下の情報を添えて管理者に連絡してください：
- エラーメッセージ全文
- `check_setup.py` の実行結果
- ボット起動時のログ

---

このガイドに関する質問や提案があれば、GitHubのIssueで報告してください。
