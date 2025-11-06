"""日本語フォントのセットアップスクリプト

EC2（Linux）環境で日本語フォントが不足している場合に自動インストールします。
起動時に main.py から呼び出されます。
"""

import subprocess
import sys
import os
import logging
import platform

logger = logging.getLogger(__name__)


def is_linux() -> bool:
    """Linux環境かどうかを判定"""
    return platform.system() == "Linux"


def has_japanese_fonts() -> bool:
    """システムに日本語フォントがインストールされているか確認"""
    if not is_linux():
        return True  # Windows/Macはチェックスキップ
    
    try:
        # fc-list コマンドで日本語フォントを検索
        result = subprocess.run(
            ["fc-list", ":lang=ja"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # 何かしら日本語フォントがあればTrue
        return bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.warning("フォント確認コマンドの実行に失敗しました: %s", e)
        return False


def install_japanese_fonts() -> bool:
    """Linux環境に日本語フォントをインストール
    
    Returns:
        bool: インストール成功時True
    """
    if not is_linux():
        logger.info("Linux以外の環境のため、フォントインストールをスキップします")
        return True
    
    # root権限が必要（os.geteuidはLinux専用）
    try:
        is_root = os.geteuid() == 0
    except AttributeError:
        # Windows環境などgeteuidがない場合
        logger.info("この環境ではroot権限チェックができません")
        return True
    
    if not is_root:
        logger.error("日本語フォントのインストールにはroot権限が必要です")
        logger.error("以下のコマンドを手動で実行してください:")
        logger.error("  sudo apt update")
        logger.error("  sudo apt install -y fonts-noto-cjk fonts-noto-cjk-extra")
        return False
    
    try:
        logger.info("日本語フォント（Noto CJK）をインストールしています...")
        
        # apt update
        subprocess.run(
            ["apt", "update"],
            check=True,
            capture_output=True,
            timeout=300
        )
        
        # fonts-noto-cjk をインストール
        subprocess.run(
            ["apt", "install", "-y", "fonts-noto-cjk", "fonts-noto-cjk-extra"],
            check=True,
            capture_output=True,
            timeout=600
        )
        
        # フォントキャッシュを更新
        subprocess.run(
            ["fc-cache", "-fv"],
            check=True,
            capture_output=True,
            timeout=60
        )
        
        logger.info("日本語フォントのインストールが完了しました")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error("フォントインストール中にエラーが発生しました: %s", e)
        logger.error("stderr: %s", e.stderr.decode() if e.stderr else "")
        return False
    except subprocess.TimeoutExpired:
        logger.error("フォントインストールがタイムアウトしました")
        return False
    except Exception as e:
        logger.error("予期しないエラーが発生しました: %s", e)
        return False


def setup_fonts_if_needed() -> None:
    """必要に応じて日本語フォントをセットアップ"""
    if not is_linux():
        logger.info("Linux以外の環境です。フォントセットアップをスキップします")
        return
    
    if has_japanese_fonts():
        logger.info("日本語フォントが既にインストールされています")
        return
    
    logger.warning("日本語フォントが見つかりません。インストールを試みます...")
    
    try:
        is_root = os.geteuid() == 0
    except AttributeError:
        is_root = False
    
    if is_root:
        # root権限がある場合は自動インストール
        if install_japanese_fonts():
            logger.info("フォントセットアップが完了しました")
        else:
            logger.warning("フォントインストールに失敗しました。手動でインストールしてください")
    else:
        # root権限がない場合は手動インストールを促す
        logger.warning("=" * 70)
        logger.warning("日本語フォントがインストールされていません")
        logger.warning("ボットを停止し、以下のコマンドを実行してください:")
        logger.warning("")
        logger.warning("  sudo apt update")
        logger.warning("  sudo apt install -y fonts-noto-cjk fonts-noto-cjk-extra")
        logger.warning("  sudo fc-cache -fv")
        logger.warning("")
        logger.warning("その後、ボットを再起動してください")
        logger.warning("=" * 70)


if __name__ == "__main__":
    # スタンドアロンで実行された場合
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    setup_fonts_if_needed()
