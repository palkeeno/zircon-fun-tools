"""フォントセットアップ機能のテスト

開発環境でLinux環境をシミュレートしてテストします。
"""

import unittest
from unittest.mock import patch, MagicMock
import setup_fonts


class TestSetupFonts(unittest.TestCase):
    """setup_fonts モジュールのテスト"""

    @patch('setup_fonts.platform.system')
    def test_is_linux_true(self, mock_system):
        """Linux環境の判定テスト"""
        mock_system.return_value = "Linux"
        self.assertTrue(setup_fonts.is_linux())

    @patch('setup_fonts.platform.system')
    def test_is_linux_false(self, mock_system):
        """非Linux環境の判定テスト"""
        mock_system.return_value = "Windows"
        self.assertFalse(setup_fonts.is_linux())

    @patch('setup_fonts.is_linux')
    def test_has_fonts_non_linux(self, mock_is_linux):
        """非Linux環境ではフォントチェックをスキップ"""
        mock_is_linux.return_value = False
        self.assertTrue(setup_fonts.has_japanese_fonts())

    @patch('setup_fonts.subprocess.run')
    @patch('setup_fonts.is_linux')
    def test_has_fonts_with_fonts(self, mock_is_linux, mock_run):
        """日本語フォントがある場合"""
        mock_is_linux.return_value = True
        mock_run.return_value = MagicMock(stdout="Noto Sans CJK JP\n")
        self.assertTrue(setup_fonts.has_japanese_fonts())

    @patch('setup_fonts.subprocess.run')
    @patch('setup_fonts.is_linux')
    def test_has_fonts_without_fonts(self, mock_is_linux, mock_run):
        """日本語フォントがない場合"""
        mock_is_linux.return_value = True
        mock_run.return_value = MagicMock(stdout="")
        self.assertFalse(setup_fonts.has_japanese_fonts())

    @patch('setup_fonts.is_linux')
    def test_install_fonts_non_linux(self, mock_is_linux):
        """非Linux環境ではインストールをスキップ"""
        mock_is_linux.return_value = False
        self.assertTrue(setup_fonts.install_japanese_fonts())

    @patch('setup_fonts.os.geteuid', create=True)
    @patch('setup_fonts.is_linux')
    def test_install_fonts_no_root(self, mock_is_linux, mock_geteuid):
        """root権限がない場合はFalseを返す"""
        mock_is_linux.return_value = True
        mock_geteuid.return_value = 1000  # 非root
        self.assertFalse(setup_fonts.install_japanese_fonts())

    @patch('setup_fonts.subprocess.run')
    @patch('setup_fonts.os.geteuid', create=True)
    @patch('setup_fonts.is_linux')
    def test_install_fonts_with_root(self, mock_is_linux, mock_geteuid, mock_run):
        """root権限がある場合はインストールを実行"""
        mock_is_linux.return_value = True
        mock_geteuid.return_value = 0  # root
        mock_run.return_value = MagicMock(returncode=0)
        
        self.assertTrue(setup_fonts.install_japanese_fonts())
        
        # apt update/install/fc-cache が呼ばれたことを確認
        self.assertEqual(mock_run.call_count, 3)

    @patch('setup_fonts.has_japanese_fonts')
    @patch('setup_fonts.is_linux')
    def test_setup_skip_non_linux(self, mock_is_linux, mock_has_fonts):
        """非Linux環境では何もしない"""
        mock_is_linux.return_value = False
        setup_fonts.setup_fonts_if_needed()
        mock_has_fonts.assert_not_called()

    @patch('setup_fonts.has_japanese_fonts')
    @patch('setup_fonts.is_linux')
    def test_setup_fonts_already_installed(self, mock_is_linux, mock_has_fonts):
        """フォントが既にある場合は何もしない"""
        mock_is_linux.return_value = True
        mock_has_fonts.return_value = True
        setup_fonts.setup_fonts_if_needed()


if __name__ == '__main__':
    unittest.main()
