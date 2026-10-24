# 設計判断とリファクタリング（2026-10-25）

## 選定結果

このBotには、既存のCogを入口に保ち、Discordに依存しない処理を関数へ分離する構成が適する。
機能ごとのCog、画面ごとのView、ファイル保存の仕組みはそのまま利用する。

| 候補 | 判断 | コード上の理由 |
| --- | --- | --- |
| Cogによる機能分割 | 継続 | コマンド・listener・定期タスクのライフサイクルをdiscord.pyに任せられる |
| 関数ベースのStrategy | 採用 | イベントのrandom/majority/minorityを同じ呼出し口で切り替える。投票の同票・0票ルールは一箇所で定義できる |
| ドメイン処理の共通サービス化 | 採用 | 名言の通常読込とバックアップ復元で、正規化・旧ID生成・重複検査が重複していた |
| 汎用Repository / Unit of Work | 今回は導入しない | 名言・誕生日・イベントで形式、検証方針、副作用の保存順が異なる。既存の原子的JSON保存とロックを維持する |
| 状態ごとのStateクラス | 今回は導入しない | イベントのopen/drawing/cleanupは既存の永続化された状態機械で表現できる。クラス分割より再開時の保存境界が重要 |
| 共通の基底Cog / Singleton | 今回は導入しない | 機能別のスケジュールやデータ検証が異なり、共通の継承階層やグローバル状態を追加する根拠が薄い |

## 責務と保存境界

- `main.py`: 拡張の登録とBotのライフサイクル。
- `cogs/*.py`: Discordの入出力、権限、ロック、API呼出しと保存の順序。
- `event_selection.py`: Strategyの選択と当選者の計算。Discord・設定・ファイルに依存しない。
- `quote_records.py`: レコード検証・同一性・取込。`normalize_records()`を通常読込と復元で共有する。
- `birthday_records.py`: 誕生日の検証と並び替え。
- `utils.atomic_write_json()` / `cogs/backups.py`: 原子的保存、直前世代、管理者操作の復元点。

イベントは選出結果を保存してから発表し、再開時に引き直さない。
名言の通常読込は不正行を報告し、元ファイルを保護する。復元は全行を検証してから適用する。
旧名言IDは正規化済み本文と同内容の受理済み件数から生成し、不正行や重複IDで件数を進めない。
JSON形式、現行コマンド、権限、参加条件、同票と0票の扱いは維持する。
未定義の抽選方式だけは、従来の少数派扱いをやめ、明示的なエラーで停止する。

## 不要コードの特定と整理

| 対象 | 根拠と対応 |
| --- | --- |
| `cogs/lottery.py`全体 | 起動時の拡張一覧では既に`cogs.events`へ移行済み。旧パッケージ再exportと旧テストだけが参照していたため削除。`cogs.__init__`も`Events`に更新 |
| 旧抽選専用テスト | 現行イベントの参加資格テストへ置換。ヘルプの統合テストも`Events`をロードするよう修正 |
| `BirthdayPaginationView`と誕生日の旧検索・詳細・一覧処理 | 現行`birthday()`は直接`select()`と共通`Pagination`を利用。旧メソッド同士の参照しかない閉じた経路のため削除 |
| `Birthday.save_birthdays_async()` | 呼出し元なし。現行の更新処理はロック内で保存と復元点を管理するため削除 |
| 誕生日・名言の型変換ラッパー4個 | 単にutilsを呼ぶだけのため直接呼出しへ統一 |
| `utils.clamp_int()` | 上記整理で利用者がなくなり、同じ処理の`coerce_int()`へ統一 |
| 名言Cogの旧`_DATA_DIR`、未使用`io` import | 保存先は`config._DATA_DIR`から決まるため削除 |
| 名言の読込・復元それぞれのID生成ループ | `normalize_records()`に統合。uuid importも呼出し側から削除 |

削除の判断は起動時の拡張一覧、コード全体の参照検索、現行コマンドの呼出し経路で行った。
Discordのデコレーター経由のコマンド・listener・callbackは通常の直接参照がなくても利用されるため残している。
`save_snapshot()`はバックアップ機能の直接テストにも使うため維持した。
`cogs.lottery`や旧クラスを直接importする外部スクリプトがある場合は`cogs.events.Events`へ移行が必要。

## 検証

変更前の160テストを基準に、通常読込と復元の一致、旧IDの固定値、入力不変性、
不正復元時のメモリー・ファイル保護、投票の順序と同票、未定義方式、作成者・別サーバーの参加拒否を検証する。
`test/run_tests.py`は新しいドメインモジュールも一時コピーに含め、認証情報と実データを隔離して実行する。
Discordでの実操作と本番デプロイはこのローカル/CI検証には含まれない。

## 参考資料

- [discord.py公式: Cogs](https://discordpy.readthedocs.io/en/stable/ext/commands/cogs.html): コマンド・listener・状態を機能別にまとめる仕組み。
- [Patterns of Enterprise Application Architecture: Service Layer](https://martinfowler.com/eaaCatalog/serviceLayer.html): 複数の入口で重複する処理を共有する境界の考え方。今回の実装は純粋なレコード処理の抽出に限定し、トランザクション全体のサービス層化は行わない。
