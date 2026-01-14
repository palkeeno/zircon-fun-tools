# コードリファクタリング計画

## 発見された問題点と修正プラン

### 1. 未使用のインポート

#### 1.1 `cogs/birthday.py`
**問題:**
- `BeautifulSoup` (21行目) - 使用されていない
- `webdriver` (22行目) - 使用されていない  
- `Options` (23行目) - 使用されていない
- `Tuple` (19行目) - 271行目で使用されているため、これは有効

**修正プラン:**
- 21-23行目の未使用インポートを削除

#### 1.2 `cogs/birthday.py` - 未使用の関数
**問題:**
- `_get_member()` (206-211行目) - 定義されているが使用されていない

**修正プラン:**
- `_get_member()` メソッドを削除

#### 1.3 `cogs/poster.py`
**問題:**
- `ImageFilter` (150行目) - インポートされているが使用されていない
- `math` モジュールが関数内で複数回インポートされている（278, 298, 403行目）

**修正プラン:**
- `ImageFilter` のインポートを削除
- `math` をファイル先頭で一度だけインポート

### 2. 未使用の変数・パラメータ

#### 2.1 `cogs/poster.py` - `_draw_poster()` メソッド
**問題:**
- `peaceful`, `brave`, `glory`, `freedom` パラメータが関数に渡されているが、関数内で全く使用されていない
- これらの画像は読み込まれているが、実際には描画に使用されていない

**修正プラン:**
- `_draw_poster()` のシグネチャから `peaceful`, `brave`, `glory`, `freedom` を削除
- 呼び出し元（674行目）も修正
- 読み込み処理（619-622行目）を削除またはコメントアウト（将来使用する可能性がある場合はコメントで説明）

### 3. 重複したコードパターン

#### 3.1 タイムゾーン取得関数
**問題:**
- `birthday.py` と `quotes.py` の両方に `_get_timezone()` 関数が存在（実質的に同じ実装）

**修正プラン:**
- `config.py` または共通ユーティリティモジュールに移動して共有
- または、現状維持（各cogが独立しているため、この重複は許容範囲）

#### 3.2 型変換関数
**問題:**
- `birthday.py` の `_coerce_bool()` と `quotes.py` の `_coerce_bool()` が重複
- `birthday.py` の `_clamp_int()` と `quotes.py` の `_coerce_int()` が類似

**修正プラン:**
- 共通ユーティリティモジュール（例: `utils.py`）を作成して共有
- または、現状維持（各cogが独立しているため、この重複は許容範囲）

#### 3.3 データディレクトリの作成
**問題:**
- 複数のファイルで `os.makedirs(data_dir, exist_ok=True)` が重複

**修正プラン:**
- `config.py` に `ensure_data_dir()` 関数を追加（既に存在するが、各cogで個別に実装されている）
- 各cogで `config.ensure_data_dir()` を使用

### 4. 冗長なコード

#### 4.1 `cogs/oracle.py` の `setup()` 関数
**問題:**
- 他のcogと比較して冗長なエラーハンドリングがある
- `traceback` は使用されているため、これは有効

**修正プラン:**
- 他のcogと統一（簡潔な形式に変更）
- または、現状維持（エラーハンドリングが詳細なのは良いこと）

#### 4.2 `cogs/birthday.py` の `setup()` 関数
**問題:**
- 他のcogと比較して冗長なエラーハンドリングがある

**修正プラン:**
- `quotes.py` や `lottery.py` のように簡潔な形式に統一
- または、現状維持（エラーハンドリングが詳細なのは良いこと）

### 5. 重複した変数定義

#### 5.1 `cogs/poster.py` - `lines_text` の重複取得
**問題:**
- 177行目と210行目で `lines_text = info.get('lines', '')` が重複

**修正プラン:**
- 177行目の定義を削除し、210行目のみを使用

### 6. その他の改善点

#### 6.1 `cogs/poster.py` - グロー効果の重複コード
**問題:**
- グロー効果の実装が複数箇所で重複（269-281行目、297-312行目、402-417行目）

**修正プラン:**
- ヘルパーメソッド `_draw_text_with_glow()` を作成して重複を削減

---

## 優先度

### 高優先度（即座に修正すべき）
1. 未使用のインポート削除（`birthday.py`, `poster.py`）
2. 未使用の関数削除（`birthday.py` の `_get_member()`）
3. 未使用のパラメータ削除（`poster.py` の `_draw_poster()`）

### 中優先度（リファクタリング推奨）
4. `math` モジュールのインポート統一（`poster.py`）
5. `lines_text` の重複削除（`poster.py`）
6. グロー効果の共通化（`poster.py`）

### 低優先度（現状維持も可）
7. タイムゾーン取得関数の共通化
8. 型変換関数の共通化
9. `setup()` 関数の統一

---

## 修正後の期待効果

- **コードサイズ削減**: 約50-100行の削減見込み
- **可読性向上**: 未使用コードの削除により、コードの意図が明確になる
- **保守性向上**: 重複コードの削減により、バグ修正や機能追加が容易になる
- **パフォーマンス**: わずかな改善（未使用のインポート削除による起動時間の短縮）

---

## 修正完了状況

✅ **全ての修正が完了しました**

### 実施した修正内容

1. ✅ `birthday.py`: 未使用インポート削除（BeautifulSoup, webdriver, Options）
2. ✅ `birthday.py`: 未使用関数削除（_get_member()）
3. ✅ `poster.py`: 未使用インポート削除（ImageFilter）とmathの統一
4. ✅ `poster.py`: 未使用パラメータ削除（peaceful, brave, glory, freedom）
5. ✅ `poster.py`: lines_textの重複削除
6. ✅ `poster.py`: グロー効果の共通化（_draw_text_with_glow()メソッド作成）
7. ✅ 共通ユーティリティ作成（utils.py）とタイムゾーン・型変換関数の共通化
8. ✅ `setup()`関数の統一（birthday.py, oracle.pyを簡潔な形式に変更）
9. ✅ `oracle.py`: 未使用インポート削除（traceback）

### 新規作成ファイル

- `utils.py`: 共通ユーティリティ関数（get_timezone, coerce_bool, coerce_int, clamp_int）

### 修正されたファイル

- `cogs/birthday.py`
- `cogs/quotes.py`
- `cogs/poster.py`
- `cogs/oracle.py`
