# Changelog

## [0.5.0] - 2026-06-05

### Added

- 母集団サンプリング: `population.yaml`（7ロール原型・60人）+ `sim_core/population.py`（決定的生成・spec バリデーション・golden fixture テスト）。seed ごとに別の村を生成し、mean/std が「村ごとの違い」を含むようになった。
- `run_sweep.py --population sampled60|fixed8`。fixed8 は v0.4.0 の8人村実験を byte 一致で再現（タグ v0.4.0 と diff 検証済み）。
- エンジンに `agents_rows`（エージェント注入）を追加。デフォルトでは既存挙動と完全に同一。
- 各 run の summary.json に `population_mode` / `population_seed` を自己記述。
- 母集団生成のテスト13件（計31件）。

### Findings

- **H1「危機→救済志向」: 整合に転換**（famine 改宗 22.70 ≥ パリティ下限15。8人村の単純スケール予想13.5を大きく超過 = 規模の増幅効果）。
- **H2: 整合に昇格**（両シナリオで単調増加。平時でも実利欲求の効果が観測可能に）。
- H5: 整合（噂改宗の約8割蒸発は村構成に対して頑健）。
- 新しい創発知見: 救済と実利は競合する対処チャネル（実利欲求が増えると救済系改宗が減る）。
- 不安スイープは形式上整合だが実質フラット。単調増加基準が平坦系列を排除できない欠陥として記録。

### Changed

- 判定の絶対下限は v0.4.0 と per-capita 完全パリティ（25% = 15/60件）。基準緩和の余地を排除。
- v0.4.0 設計書を `docs/design_history/` へ移動。README・実験ログ・仮説検証状況を60人村の結果で更新。
- 図4枚を60人村データで再生成（タイトルをデータ非依存の中立表現に変更）。

## [0.4.0] - 2026-06-05

### Added

- パラメータスイープ（`experiments/run_sweep.py`）：4本のスイープ・計1,050 run。run ごとの集計（`results.tsv`）、条件ごとの統計（`stats.json`）、宣言済み基準による仮説判定（`--judge`）。
- 図表生成（`experiments/plot_sweeps.py`）：スイープ結果から README 用の図4枚を生成。
- エンジンに `trait_adjustments`（特性への加算デルタ介入、0–1 クランプ）を追加。デフォルトでは既存挙動と完全に同一。
- スイープ機能のテスト9件（既存9件と合わせて計18件）。
- H5 を直接測る指標 `early_conversions` / `early_convert_retention` を追加。

### Changed

- README を研究レポート構成（問い→仮説→手法→結果→発見→限界→再現方法）に再編。
- `docs/hypotheses.md` に各仮説の検証状況（H3/H4 未検証、H6 はモデル仕様により検証不能）を注記。
- `pyproject.toml` の version を実態に合わせて 0.4.0 に更新（0.1.0 のまま放置されていた）。

### Findings

- H5「噂は速いが定着しない」: 整合（早期改宗 mean 2.8、定着率 11.8%）。
- H1「危機→救済志向」: 事前宣言基準では不整合（famine 改宗 mean 1.80 < 絶対下限 2）。方向は仮説どおり。
- H2「実利圧力→現世利益」: 条件付き整合（famine 側のみ単調増加）。
- 創発的知見: 危機経由の改宗は 100% 定着、噂経由は 88% 蒸発。個人特性は単独では改宗を駆動しない。寛容性は信仰地図を流動化させる。

## [0.3.0] - 2026-06-05

### Added

- ブラウザビューア：`experiments/render_viewer.py` が実行結果からスタンドアロンの `viewer.html` を生成。村マップ上で信仰の移り変わりを再生できる（再生・速度・スライダー・村人詳細・改宗フィード・信者数グラフ）。`?step=N` で開始位置指定可。
- ドメインパックの TSV（beliefs / agents / places / events）に `label_ja` 列を追加。

### Changed

- 場所 `local_shrine` の日本語名を「神社」に（古典神道の場所のため）。

## [0.2.0] - 2026-06-05

### Added

- シミュレーションエンジン本体（`sim_core/engine.py`）：イベント減衰、信念スコア計算（訴求×特性・共同体圧力・慣性・イベントシグナル）、改宗・習合判定、理由トレース。seed 固定で決定的。
- 出力ファイル群：`agent_turns.tsv` / `belief_shares.tsv` / `conversions.tsv` / `events_log.tsv` / `summary.json`。
- LLM バックエンド（`sim_core/llm_backend.py`）：claude CLI / Ollama 抽象化と `--narrate` による日本語ナラティブ生成（`narrative.md`）。
- `validation/validation_plan.md` の5項目を固定する engine テスト（計9テスト）。
- ランナーに `--seed` / `--narrate` / `--narrate-model` オプションを追加。

## [0.1.1] - 2026-06-05

### Changed

- README・CHANGELOG・AGENTS.md・docs 配下のドキュメントを日本語化。

## [0.1.0] - 2026-06-05

### Added

- 公開リポジトリの初期スケルトン。
- `japan_religion` を含むドメインパック構造。
- 日本の宗教に関する初期データ：信念、エージェント、場所、イベント、ルール、メトリクス、プロンプト、シナリオ。
- ドメインパック読み込みのスモークランナーとテスト。
