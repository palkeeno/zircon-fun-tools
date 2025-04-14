"""
設定ファイルのテスト
このモジュールは、config.pyの機能をテストします。
"""

import unittest
import os
from unittest.mock import patch, MagicMock
import config

class TestConfig(unittest.TestCase):
    """設定ファイルのテストクラス"""

    def setUp(self):
        """テストの前準備"""
        # 環境変数をクリア
        self.original_env = dict(os.environ)
        os.environ.clear()

    def tearDown(self):
        """テストの後処理"""
        # 環境変数を元に戻す
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_token_validation(self):
        """トークンの検証テスト"""
        # 開発環境のトークンが設定されていない場合
        os.environ['ENV'] = 'development'
        with self.assertRaises(ValueError):
            _ = config.TOKEN

        # 開発環境のトークンが設定されている場合
        os.environ['DISCORD_TOKEN_DEV'] = 'valid_token'
        self.assertEqual(config.TOKEN, "valid_token")

        # 本番環境のトークンが設定されていない場合
        os.environ['ENV'] = 'production'
        os.environ.pop('DISCORD_TOKEN_DEV', None)
        with self.assertRaises(ValueError):
            _ = config.TOKEN

        # 本番環境のトークンが設定されている場合
        os.environ['DISCORD_TOKEN_PROD'] = 'valid_token'
        self.assertEqual(config.TOKEN, "valid_token")

    def test_is_feature_enabled(self):
        """機能の有効/無効判定テスト"""
        # 有効な機能
        self.assertTrue(config.is_feature_enabled('ramble_game'))
        self.assertTrue(config.is_feature_enabled('comedy_game'))
        self.assertTrue(config.is_feature_enabled('janken'))

        # 無効な機能
        self.assertFalse(config.is_feature_enabled('birthday'))
        self.assertFalse(config.is_feature_enabled('dictionary'))
        self.assertFalse(config.is_feature_enabled('omikuji'))

        # 存在しない機能
        self.assertFalse(config.is_feature_enabled('nonexistent_feature'))

    def test_get_feature_settings(self):
        """機能の設定取得テスト"""
        # 有効な機能の設定
        settings = config.get_feature_settings('ramble_game')
        self.assertEqual(settings['min_players'], 2)
        self.assertEqual(settings['max_players'], 10)
        self.assertEqual(settings['round_duration'], 60)

        # 無効な機能の設定
        settings = config.get_feature_settings('birthday')
        self.assertEqual(settings['notification_time'], "09:00")
        self.assertEqual(settings['timezone'], "Asia/Tokyo")

        # 存在しない機能の設定
        settings = config.get_feature_settings('nonexistent_feature')
        self.assertEqual(settings, {})

if __name__ == '__main__':
    unittest.main() 