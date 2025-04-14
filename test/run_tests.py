"""
テスト実行スクリプト
このスクリプトは、すべてのテストを実行します。
"""

import unittest
import sys
import os

def run_tests():
    """すべてのテストを実行します。"""
    # テストディレクトリをPythonパスに追加
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

    # テストをロード
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(os.path.abspath(__file__))
    suite = loader.discover(start_dir, pattern='test_*.py')

    # テストを実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # テスト結果に基づいて終了コードを設定
    sys.exit(not result.wasSuccessful())

if __name__ == '__main__':
    run_tests() 