"""
設定ファイルのテスト
このモジュールは、config.pyの機能をテストします。
"""

import unittest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock
import config

class TestConfig(unittest.TestCase):
    """設定ファイルのテストクラス"""

    def setUp(self):
        """テストの前準備"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings_file = os.path.join(self.temp_dir.name, 'settings.json')
        
        # テスト用の設定ファイルを作成
        self.test_settings = {
            "bot": {
                "token": "test_token",
                "prefix": "!",
                "admin_ids": [123456789],
                "log_channel_id": 987654321
            },
            "features": {
                "test_feature": {
                    "enabled": True,
                    "settings": {
                        "test_setting": "value"
                    }
                }
            }
        }
        
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_settings, f)
        
        # 設定ファイルのパスを設定
        os.environ['SETTINGS_FILE_PATH'] = self.settings_file

    def tearDown(self):
        """テストの後処理"""
        self.temp_dir.cleanup()
        if 'SETTINGS_FILE_PATH' in os.environ:
            del os.environ['SETTINGS_FILE_PATH']

    @patch('config.load_dotenv')
    def test_load_settings(self, mock_load_dotenv):
        """設定ファイルの読み込みテスト"""
        settings = config.load_settings()
        self.assertEqual(settings, self.test_settings)

    def test_get_default_settings(self):
        """デフォルト設定のテスト"""
        with patch.dict('os.environ', {
            'ENV': 'development',
            'DISCORD_TOKEN_DEV': 'test_token'
        }):
            default_settings = config.get_default_settings()
            self.assertIn('bot', default_settings)
            self.assertIn('features', default_settings)
            self.assertEqual(default_settings['bot']['token'], 'test_token')

    @patch('os.getenv')
    def test_token_validation(self, mock_getenv):
        """トークンの検証テスト"""
        # 開発環境のトークンが設定されていない場合
        mock_getenv.side_effect = lambda x, default=None: (
            'development' if x == 'ENV' else
            None if x == 'DISCORD_TOKEN_DEV' else
            default
        )
        with self.assertRaises(ValueError):
            _ = config.TOKEN

        # 開発環境のトークンが設定されている場合
        mock_getenv.side_effect = lambda x, default=None: (
            'development' if x == 'ENV' else
            'valid_token' if x == 'DISCORD_TOKEN_DEV' else
            default
        )
        self.assertEqual(config.TOKEN, "valid_token")

        # 本番環境のトークンが設定されていない場合
        mock_getenv.side_effect = lambda x, default=None: (
            'production' if x == 'ENV' else
            None if x == 'DISCORD_TOKEN_PROD' else
            default
        )
        with self.assertRaises(ValueError):
            _ = config.TOKEN

        # 本番環境のトークンが設定されている場合
        mock_getenv.side_effect = lambda x, default=None: (
            'production' if x == 'ENV' else
            'valid_token' if x == 'DISCORD_TOKEN_PROD' else
            default
        )
        self.assertEqual(config.TOKEN, "valid_token")

    def test_is_feature_enabled(self):
        """機能の有効/無効判定テスト"""
        # 有効な機能
        with patch('config.SETTINGS', self.test_settings):
            self.assertTrue(config.is_feature_enabled('test_feature'))

        # 無効な機能
        with patch('config.SETTINGS', self.test_settings):
            self.assertFalse(config.is_feature_enabled('nonexistent_feature'))

if __name__ == '__main__':
    unittest.main() 