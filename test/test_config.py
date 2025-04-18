"""
設定ファイルのテスト
このモジュールは、config.pyの機能をテストします。
"""

import unittest
import os
from unittest.mock import patch
import importlib

class TestConfig(unittest.TestCase):
    """設定ファイルのテストクラス（ユニットテスト向けに修正）"""

    def setUp(self):
        self.original_env = dict(os.environ)
        os.environ.clear()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_token_validation(self):
        # 開発環境のトークンが設定されていない場合
        os.environ['ENV'] = 'development'
        if 'DISCORD_TOKEN_DEV' in os.environ:
            del os.environ['DISCORD_TOKEN_DEV']
        import config
        with self.assertRaises(ValueError):
            config.get_token()

        # 開発環境のトークンが設定されている場合
        os.environ['DISCORD_TOKEN_DEV'] = 'valid_token'
        self.assertEqual(config.get_token(), 'valid_token')

        # 本番環境のトークンが設定されていない場合
        os.environ['ENV'] = 'production'
        if 'DISCORD_TOKEN_PROD' in os.environ:
            del os.environ['DISCORD_TOKEN_PROD']
        with self.assertRaises(ValueError):
            config.get_token()

        # 本番環境のトークンが設定されている場合
        os.environ['DISCORD_TOKEN_PROD'] = 'valid_token_prod'
        self.assertEqual(config.get_token(), 'valid_token_prod')

    def test_is_feature_enabled(self):
        import config
        self.assertFalse(config.is_feature_enabled('ramble_game'))
        self.assertTrue(config.is_feature_enabled('comedy_game'))
        self.assertTrue(config.is_feature_enabled('janken'))
        self.assertFalse(config.is_feature_enabled('birthday'))
        self.assertFalse(config.is_feature_enabled('dictionary'))
        self.assertFalse(config.is_feature_enabled('omikuji'))
        self.assertFalse(config.is_feature_enabled('nonexistent_feature'))

    def test_get_feature_settings(self):
        import config
        settings = config.get_feature_settings('ramble_game')
        self.assertEqual(settings['round_duration'], 30)
        settings = config.get_feature_settings('birthday')
        self.assertEqual(settings['notification_time'], '09:00')
        self.assertEqual(settings['timezone'], 'Asia/Tokyo')
        settings = config.get_feature_settings('nonexistent_feature')
        self.assertEqual(settings, {})

if __name__ == '__main__':
    unittest.main()