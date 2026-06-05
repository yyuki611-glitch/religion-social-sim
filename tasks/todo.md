# パラメータスイープ + README研究レポート化

2026-06-05 設計 rev4。
- rev2: evaluator モード1指摘（HIGH3・MEDIUM4）反映
- rev3: codex-reviewer 指摘（HIGH5・MEDIUM5・LOW2）反映
- rev4: evaluator 再レビュー指摘（HIGH1・MEDIUM5）反映

目的：単発実験（seed=42 1回）しかない現状から、
「仮説とモデル挙動の整合を統計的に示せる」研究リポジトリへ引き上げる。

## スコープ

### 1. エンジン拡張（最小変更）
- `run_scenario()` に `trait_adjustments: dict[str, float] | None = None` を追加（**加算デルタ方式**。乗算は上限張り付きで条件間差が潰れるため不採用 ← evaluator HIGH-2）
- `_load_agents()` 後に各エージェントの指定特性へデルタを加算し `_clamp` で 0–1 に収める
- デフォルト `None` で既存挙動は完全不変（既存テスト9件がそのまま通ること）
- **rng 規律**: 各 run は `run_scenario()` 内部の `random.Random(seed)` のみ使用。スイープランナーでグローバル `random.seed()` を呼ぶこと・並列実行は禁止（逐次実行。1 run は8エージェント×50ステップで軽量）

### 2. スイープランナー `experiments/run_sweep.py`
4本のスイープを定義（定義はスクリプト内の定数。実験ファースト方式）:

| スイープ | 軸 | 位置づけ |
|---|---|---|
| A `scenario_seeds` | 3シナリオ × seed 1–50（150 run） | H1/H5 の検証（シナリオ間比較） |
| B `tolerance` | {baseline, famine} × tolerance デルタ {-0.20, -0.10, 0, +0.10, +0.20} × seed 1–30（300 run） | **感度分析**（H6 はモデル仕様により検証不能 ← evaluator HIGH-1 / codex HIGH-1） |
| C `anxiety` | {baseline, famine} × anxiety デルタ {-0.20, -0.10, 0, +0.10, +0.20} × seed 1–30（300 run） | H1 の**補助検証**（H1 の主検証はスイープA）。**事前感度見積もり（← evaluator rev3 HIGH-1）**: anxiety の openness 係数は 0.25（belief.py 実測）でデルタ ±0.20 の openness 変化は最大 ±0.05。さらに改宗は gap > threshold が3ステップ続いて初めて openness が効く構造のため、イベントの乏しい baseline 側では**全条件ゼロ改宗となり判定不能になる可能性が高いことを設計段階で受け入れる**。ゼロ改宗フラットならそれ自体を発見として報告する（「本モデルでは不安は改宗の駆動因子ではなく変調因子。改宗の駆動はイベント由来の gap 形成」）。モデル係数を結果が出る方向に調整することはしない（実験装置の恣意的調整にあたるため）。famine 側は飽和（イベント delta 合算で 1.0 張り付き）の注記付きで補助系列として報告 |
| D `practical_need` | {baseline, famine} × practical_benefit_need デルタ {-0.20, -0.10, 0, +0.10, +0.20} × seed 1–30（300 run） | H2（実利欲求→現世利益信仰）の検証。**専用スイープなしでは H2 は判定不能になるため新設**（← codex HIGH-3。famine イベントは inari に anxiety/community 信号を同時に与えるため、A だけでは実利欲求の単独効果を分離できない） |

- 特性の値域（agents.tsv 実測）: anxiety 0.25–0.75 / tolerance 0.45–0.85 / practical_benefit_need 0.20–0.90。デルタ ±0.20 での上限クランプは tolerance +0.20 で1名、practical +0.20 で1名のみ
- **stats.json に記録**: 条件ごとの mean/std に加え、(a) 調整後の実効 trait 分布（min/mean/max・クランプ発生エージェント数）、(b) スイープBでは `tolerance >= 0.65`（SYNCRETISM_TOLERANCE）を満たすエージェント数（閾値が二値スイッチとして効くことの明示 ← codex HIGH-1/MEDIUM-8。**エージェント特性は固定で seed 間不変のため、条件ごとに1値。results.tsv の列にはしない** ← evaluator rev3 MEDIUM-6）、(c) スイープCでは run 中に anxiety が 1.0 に張り付いた agent-step 比率の条件平均（飽和率 ← codex MEDIUM-7）
- **baseline 側の good_harvest 干渉（← evaluator rev3 MEDIUM-5）**: baseline シナリオの good_harvest（step 10、anxiety_delta=-0.20）はスイープCのデルタと逆方向に働く。ただし全デルタ条件に同一に作用するため条件間比較は成立する（ベースライン水準が下がるだけ）。これは「イベントを含む現実的な村でのデルタ効果」を見る設計意図として明記し、README 限界セクションにも記載する。イベントなし純粋環境のシナリオ追加はやらない（スコープ外）
- CLI: `run_sweep.py --sweep all|scenario_seeds|tolerance|anxiety|practical_need --output-dir outputs/sweeps`
- 1 run = `run_scenario()` 呼び出し。raw 出力は `outputs/sweeps/<sweep>/runs/<run_id>/`（gitignore）
- **run_id は決定的に採番**（uuid・timestamp 禁止 / ← evaluator rev3 MEDIUM-3 でスイープ別に明確化）:
  - スイープA: `{scenario}_s{seed:03d}`（delta 軸を持たないため）
  - スイープB/C/D: `{scenario}_{trait}_d{delta:+.2f}_s{seed:03d}`
- 集計: `outputs/sweeps/<sweep>/results.tsv`（1 run 1 行。**行順は (scenario, trait, delta, seed) の昇順ソートで固定**）と `stats.json`。両方コミット対象
- results.tsv の列: sweep, scenario, trait, delta, seed, steps, conversions, syncretisms, retention_rate, conv_to_salvation, conv_to_practical, conv_to_other, early_conversions, early_convert_retention
  - スイープAでは trait=none, delta=0.00 を明示的に埋める（全スイープで同一スキーマ）
  - `early_conversions` の窓は**シナリオごとに「最初の非 generation イベント発火 step を基点に +5 ステップ」**（← evaluator rev3 MEDIUM-4。実測: baseline=step 10–15(good_harvest), famine=step 8–13(famine), miracle_rumor=step 5–10(miracle_rumor)）。**H5 の判定には miracle_rumor のみを使い**、baseline/famine の同列は参考値（判定に使わない）
  - `early_convert_retention`: 早期改宗したエージェントのうち最終ステップでその信仰を保持している割合（H5 を直接測る指標。全体 retention_rate では測れない ← codex HIGH-4）。早期改宗ゼロの run は N/A（空欄）とし、集計の分母から除外

### 3. 信念ファミリー分類（集計用・設計時固定）
- 救済系 = `jodo_buddhism`（appeal: salvation,grief,afterlife）
- 実利系 = `inari_belief`, `ryujin_belief`（appeal: practical_benefit/harvest/water 等）
- その他 = classical_shinto, ujigami_shinto, zen_buddhism, mountain_belief
- run_sweep.py 内に定数として記述し、docstring に根拠（beliefs.tsv の appeal 列）を書く

### 4. 判定基準と判定語（実装前に宣言・後から動かさない）
**判定語は「整合（consistent）/不整合（inconsistent）/判定不能（inconclusive）」に統一**。supported/rejected は使わない（8エージェント・モデル内実験での「支持」は過大主張 ← codex HIGH-5/LOW-11）。

- **H1 整合**（主検証=A、補助=C）: A で famine の mean(conversions) **≥ 2（絶対下限）** かつ > baseline の mean + 1×std(baseline)（← evaluator rev3 MEDIUM-2: baseline がゼロ集中で std≈0 になると相対基準だけでは「1件で整合」になるため絶対下限を併用）、かつ famine の改宗先の60%以上が救済+実利系。C（baseline 側）は anxiety デルタと救済+実利系改宗数の条件平均が単調増加なら補強材料。**C が全条件ゼロ改宗なら C は判定不能と記録し、H1 の判定は A のみで行う**（事前見積もり上この可能性が高い。前掲スイープC欄参照）
- **H2 整合**（D）: practical_benefit_need デルタと実利系改宗数の条件平均が単調増加（同上）。baseline/famine 両方で同傾向なら整合、片方のみなら条件付き
- **H5 整合**（A）: miracle_rumor の early_conversions mean ≥ 2 かつ early_convert_retention mean ≤ 0.5。**限界として明記**: miracle_rumor シナリオには step 20 shrine_patronage・step 34 temple_corruption が含まれ、揺り戻しは「噂の自然減衰」と「権威イベントの引き戻し」の複合（← codex MEDIUM-10）。早期窓（step 5–10）は patronage 前なので速さ側の測定は汚染されない
- **H3/H4**: 今回スイープなし → **判定不能（未検証）** と明記（← codex HIGH-3/5）
- **H6**: エンジンが `tolerance >= 0.65` で習合を直接ゲートしているため**判定不能（モデル仕様＝トートロジー）**。スイープBは感度分析として報告し、見る創発的な問いは「tolerance が上がると正面改宗が減り信仰地図が安定するか（conversions / retention_rate の変化）」

### 5. 図表生成 `experiments/plot_sweeps.py`
- matplotlib（既存 `analysis` extra）で4枚:
  - fig1: シナリオ別の改宗数分布（箱ひげ）+ early_convert_retention（スイープA）
  - fig2: anxiety デルタ × 救済+実利系改宗数の折れ線（baseline/famine 2系列、スイープC。famine 系列に飽和注記）
  - fig3: practical デルタ × 実利系改宗数の折れ線（baseline/famine 2系列、スイープD）
  - fig4: tolerance デルタ × (改宗数 / 習合数 / retention) の折れ線 + 閾値跨ぎ人数の注釈（感度分析、スイープB）
- 出力: `outputs/sweeps/figures/*.png`（コミット対象）。ラベルは英語表記+READMEで日本語説明

### 6. README 研究レポート化
- 構成:「問い → 仮説 → 手法 → 実験結果（図表embed）→ 発見 → **限界** → 再現方法 → セットアップ」
- 限界セクションに必ず書く（← codex MEDIUM-6/LOW-12）: (1) 8エージェント固定で母集団サンプリングではない、(2) 歴史再現ではなくモデル内実験、(3) H6 トートロジー問題、(4) miracle_rumor の権威イベント交絡、(5) 統計的検定なし（mean/std のみ）
- 各仮説の整合/不整合/判定不能を判定基準とともに明記。図と `docs/references.md` が README から辿れる構造にする
- 既存の使い方・ビューア説明は後半に残す（削除しない）

### 7. ドキュメント
- `docs/experiment_log.md` にスイープ結果を追記（判定の数値根拠付き）
- `docs/hypotheses.md` の H6 に検証可能性の注記、H3/H4 に未検証の注記を追加
- `CHANGELOG.md` に v0.3.0 追記
- `.gitignore` に `outputs/sweeps/*/runs/` を追加
- 確認済み事実: 現リポで outputs/ 配下のコミット済みファイルは `outputs/runs/.gitkeep` のみ（ローカルの既存実行結果は untracked。evaluator MEDIUM-7 は誤認）

## 完了基準

1. `run_sweep.py --sweep all` が手元で完走し、results.tsv ×4 + stats.json ×4 + 図4枚が生成される（1050 run、逐次実行）
2. 既存テスト9件 + 新規テスト（trait_adjustments の加算とクランプ、デフォルトNoneで既存結果不変、results.tsv スキーマと行順決定性、early_convert_retention の計算）が全て pass
3. 同じ sweep を2回実行して results.tsv が byte 一致。**前回の出力ディレクトリが残った状態で再実行しても一致**（← codex MEDIUM-9）
4. 静的チェック: README 内の図パスが実ファイルと一致（grep/ls で確認）。GitHub 上での図表示の目視確認は push 後に 作者へ依頼
5. H1/H2/H5 の判定が宣言済み基準・判定語（整合/不整合/判定不能）で行われ、数値根拠付きで experiment_log.md に記録される。H3/H4/H6 は判定不能として理由付きで記録される
6. `git status --porcelain` に `outputs/sweeps/*/runs/` 配下が現れない（gitignore 機能確認）

## 検証方法

- `pytest` 全件 pass
- sweep 2回実行 → `diff results.tsv` で byte 一致確認（出力ディレクトリ残存ケース含む）
- 完了基準4・6 の静的チェックコマンドを実行してログを残す
- evaluator モード2で完了基準1–3・5–6 を検証（4のGitHub目視のみ 作者確認）

## やらないこと

- LLM観測器（次フェーズ）
- 習合メカニズムの独立実装（H6 を検証可能にする改修。次フェーズ候補として experiment_log に記録）
- H3（共同体依存）/H4（権威）の専用スイープ（次フェーズ候補。今回は判定不能と明記）
- エージェント数の拡大・母集団サンプリング（次フェーズ候補）
- ドメインパックのデータ拡充、ビューアの変更
- 統計的検定（t検定等）。mean/std と分布図まで

## 進め方

1. 設計レビュー: codex-reviewer + evaluator モード1 ← 両方の指摘を rev3 に反映済み。evaluator に再レビュー依頼中（APPROVE まで実装しない）
2. 実装: エンジン拡張 → sweep → plot → 実行 → README
3. 検証: pytest + 決定性確認 + evaluator モード2
4. PR 作成 → merge（承認済み「進めていきましょう」、public repo 既承認）
