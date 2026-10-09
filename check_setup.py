"""
環境セットアップの検証スクリプト
必要なファイルと設定が揃っているかをチェックします。
"""

import os

def check_file_exists(path, description):
    """ファイルの存在をチェック"""
    exists = os.path.exists(path)
    status = "✅" if exists else "❌"
    print(f"{status} {description}: {path}")
    return exists

def main():
    print("=" * 60)
    print("Zircon Fun Tools - 環境セットアップチェック")
    print("=" * 60)
    print()
    
    # プロジェクトルートを取得（環境に依存しない）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    all_ok = True
    
    # .env ファイルのチェック
    print("📋 環境変数ファイル")
    print("-" * 60)
    candidates = [os.path.join(script_dir, name) for name in ('.env', 'ENV', 'ZFT_ENV')]
    existing = [path for path in candidates if os.path.isfile(path)]
    env_path = existing[0] if existing else candidates[0]
    if len(existing) > 1:
        print(f'   複数の設定ファイルがあります。{env_path} のみを読み込みます')
    if not check_file_exists(env_path, '環境変数ファイル'):
        print("   ⚠️  .env ファイルを作成し、必要な環境変数を設定してください")
        all_ok = False
    print()
    
    # 必須データファイルのチェック
    print("📁 必須データファイル")
    print("-" * 60)
    birthdays_path = os.path.join(script_dir, 'data', 'birthdays.json')
    check_file_exists(birthdays_path, 'birthdays.json')
    print()
    
    # ポスター機能の画像アセットチェック
    print("🖼️  ポスター機能の画像アセット (オプション)")
    print("-" * 60)
    assets_dir = os.path.join(script_dir, 'data', 'assets')
    
    if not os.path.exists(assets_dir):
        print(f"❌ アセットディレクトリが存在しません: {assets_dir}")
        print("   ⚠️  /poster コマンドを使用する場合は作成してください")
    else:
        required_assets = [
            'mask.png',
            'peaceful.png',
            'brave.png',
            'glory.png',
            'freedom.png'
        ]
        
        missing_assets = []
        for asset in required_assets:
            asset_path = os.path.join(assets_dir, asset)
            if not check_file_exists(asset_path, asset):
                missing_assets.append(asset)
        
        if missing_assets:
            print()
            print("   ⚠️  不足している画像アセット:")
            for asset in missing_assets:
                print(f"      - {asset}")
            print()
            print("   📖 詳細は data/assets/README.md を参照してください")
            print("   💡 /poster コマンドを使用しない場合は無視して構いません")
    
    print()
    print("=" * 60)
    
    if all_ok:
        print("✅ すべての必須ファイルが揃っています！")
        print("   python main.py でボットを起動できます。")
    else:
        print("⚠️  いくつかの必須ファイルが不足しています。")
        print("   上記のメッセージを確認して、必要なファイルを設定してください。")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
