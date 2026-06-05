# 母集団サンプリング（村人 8 → 60、seed ごとに別の村）v0.5.0

2026-06-05 設計 rev3。
- rev2: evaluator モード1指摘（HIGH5・MEDIUM4）反映
- rev3: codex-reviewer 指摘（HIGH3・MEDIUM7・LOW2）反映 ※codex は （非公開設定ファイル） 流出問題の再発により本タスクではこれ以降使用しない（メモリ記録済み）

v0.4.0 の限界1「エージェント8体の固定集団。seed は同じ村の並行世界にすぎない」への正面対応。

## 測定対象（estimand）の変更を明示する（← codex HIGH-2）

v0.4.0 の mean/std は「**1つの固定村**における改宗ロールの確率的ばらつき」を測っていた。
v0.5.0 の mean/std は「**村の構成のばらつき + 確率的ばらつきの混合**」を測る。つまり測定対象そのものが変わる。
- v0.4.0 と v0.5.0 の数値は**直接比較できない**（対比表は「参考対比」と明記する）
- この estimand の違いを experiment_log と README 限界セクションの両方に記載する
- 分散の分解（村固定×シミュレーションseed の直交設計）は次フェーズ候補として記録する

## 目的

- 村人を 8 → **60** に拡大する
- seed ごとに**別の村人集団を生成**する（真の母集団サンプリング）。これにより mean/std が「村のばらつき」を意味するようになる
- v0.4.0 の4スイープを 60 人村で再実験し、仮説を**新しく宣言した基準**で再判定する

## スコープ

### 1. 母集団仕様 `domain_packs/japan_religion/data/population.yaml`
- 既存 agents.tsv の8人をロール原型（archetype）として一般化:

| ロール | 人数 | 原型 |
|---|---|---|
| farmer | 24 | 米農家 A01 / 水守 A08 |
| household | 12 | 寡婦・家内 A03 |
| merchant | 6 | 商人 A02 |
| artisan | 6 | 職人 A07 |
| religious_specialist | 6 | 旅の僧 A05 / 山伏 A06 |
| authority | 3 | 庄屋 A04 |
| elder | 3 | 新設（高伝統・低新奇） |
| **計** | **60** | |

- 各ロールに: 特性ごとの `center`（spread は全特性共通 **0.12**）、初期信仰の確率分布、信仰強度は全ロール共通 `uniform(0.50, 0.80)`
- サンプリングは `rng.uniform(center - 0.12, center + 0.12)`。**バリデーション: 全ての center は [0.12, 0.88] に収まること（= クランプ前の範囲が [0,1] 内）を生成時にチェックし、違反は ValueError**（クランプによる分布の非対称バイアスを構造的に排除する ← evaluator HIGH-4。よって生成時クランプは発生しない）
- **center の宣言値**（既存8人の実測値（複数人ロールは平均）を [0.12, 0.88] に収めて丸めたもの。Builder の裁量にしない ← evaluator MEDIUM-6）:

| ロール | anx | comm | auth | trad | novel | salv | prac | tol | 初期信仰の確率 |
|---|---|---|---|---|---|---|---|---|---|
| farmer | 0.50 | 0.82 | 0.48 | 0.78 | 0.30 | 0.35 | 0.78 | 0.55 | ujigami .5 / ryujin .3 / inari .1 / classical .1 |
| household | 0.75 | 0.70 | 0.50 | 0.60 | 0.35 | 0.85 | 0.35 | 0.70 | jodo .5 / ujigami .3 / inari .2 |
| merchant | 0.35 | 0.55 | 0.35 | 0.45 | 0.70 | 0.25 | 0.86 | 0.65 | inari .7 / ujigami .2 / zen .1 |
| artisan | 0.50 | 0.50 | 0.35 | 0.40 | 0.75 | 0.45 | 0.65 | 0.70 | inari .5 / ujigami .3 / zen .2 |
| religious_specialist | 0.33 | 0.33 | 0.33 | 0.62 | 0.70 | 0.70 | 0.33 | 0.72 | jodo .4 / mountain .4 / zen .2 |
| authority | 0.30 | 0.88 | 0.85 | 0.85 | 0.20 | 0.30 | 0.50 | 0.45 | classical .8 / ujigami .2 |
| elder | 0.45 | 0.80 | 0.60 | 0.86 | 0.15 | 0.60 | 0.40 | 0.55 | ujigami .4 / classical .3 / jodo .3 |

- **rng 呼び出し順序の固定（← evaluator HIGH-1）**: spec 記載のロール順 → ロール内で人数分のエージェントループ。各エージェントにつき (1) TRAIT_KEYS 順に8特性を `rng.uniform`、(2) 信仰強度を `rng.uniform(0.50, 0.80)`、(3) 初期信仰を `rng.choices(beliefs, weights)[0]`。この順序を population.py の docstring に明記し、テストで byte 同一性を固定する

### 2. 母集団生成 `sim_core/population.py`
- `generate_agents(spec: dict, rng: random.Random) -> list[dict[str, str]]`
- 出力は agents.tsv と同スキーマの行リスト（`_load_agents` 互換）
- **決定的**: 同じ spec + 同じ rng seed → byte 同一の行リスト。ID は `P001`〜`P060` の連番、ロール順も spec 記載順で固定
- グローバル random 禁止（渡された rng のみ使用）
- **`validate_spec(spec, belief_rows)` を必須実装**（← codex HIGH-1。silent failure 防止）。チェック項目:
  (1) 初期信仰 ID が beliefs.tsv に存在、(2) 各ロールの信仰確率の合計 = 1.0（誤差 1e-9）、(3) TRAIT_KEYS 全8特性が定義済み、(4) 人数合計 = 60、(5) center ∈ [0.12, 0.88]（クランプ前範囲が [0,1] 内）。違反は ValueError
- **golden fixture テスト**（← codex LOW-2）: `generate_agents(spec, random.Random(1))` の出力を `tests/fixtures/population_seed1.tsv` にコミットし、byte 一致を pytest で固定（results.tsv の間接検証ではなく生成仕様そのものを固定）
- elder ロールの根拠注記: 世代交代イベントの「伝統が薄まる」方向に対する保持側の社会型として置く設計上の原型。特定の歴史史料に基づくものではないことを population.yaml のコメントに明記（← codex MEDIUM-4）
- 初期信仰はロール内で独立サンプリング（少数ロールで偏る run も「村のばらつき」の正当なサンプルとして許容）。その代わり **stats.json（sampled60）に条件ごとの初期信仰分布の平均を記録**し、判定が初期分布の偏りに引きずられていないか検査可能にする（← codex MEDIUM-2）

### 3. エンジン拡張（最小変更）
- `run_scenario()` に `agents_rows: list[dict] | None = None` を**既存引数の最後に追加**（位置引数呼び出しを壊さない ← codex MEDIUM-5）。指定時は agents.tsv の代わりに使う。**デフォルト None で既存挙動完全不変**（既存テスト18件パス維持）
- trait_adjustments は生成後の集団に同じく適用（既存コードパスのまま）
- summary.json に `population_mode`（fixed8 / sampled60）と `population_seed`（sampled60 時のみ、fixed8 は null）を記録し、再現に必要な情報を自己記述にする（← codex MEDIUM-1）。これは run_scenario ではなく run_sweep 側で summary に追記する形でもよい（実装裁量）。results.tsv のスキーマは変えない

### 4. スイープ再実験 `run_sweep.py` 拡張
- `--population sampled60 | fixed8` フラグ（**デフォルト sampled60**）
  - `sampled60`: run ごとに `population_rng = random.Random(POPULATION_SEED_OFFSET + seed)` で村を生成。`POPULATION_SEED_OFFSET = 10**6`（**値自体に意味はなく、シミュレーション rng の seed 空間（1–50）と重ならないこと・コード上で定数として明示することだけが要件** ← evaluator HIGH-2 注記。Mersenne Twister はインスタンス分離されており系列相関は実用上無視できる）。**seed = 村の個体 + 改宗ロールの両方が変わる** = 母集団サンプリング
  - `fixed8`: 従来の agents.tsv（v0.4.0 の再現用。HEAD のまま両方再現可能にする）
- **run_id 形式（← evaluator HIGH-5）**: 両モードとも v0.4.0 と同一（`{scenario}_s{seed:03d}` / `{scenario}_{trait}_d{delta:+.2f}_s{seed:03d}`）。モードの区別は run_id ではなく**出力ルートで行う**: sampled60 → `outputs/sweeps/`、fixed8 → `outputs/sweeps_fixed8/`（同一ディレクトリへの書き込み衝突は構造上起きない。設計として明記）
- 出力先: sampled60 → `outputs/sweeps/`（コミット対象を v0.5.0 結果で更新）、fixed8 → `outputs/sweeps_fixed8/`（gitignore、再現確認用）
- **results.tsv スキーマは v0.4.0 と同一**（列の追加・削除なし ← evaluator MEDIUM-9）
- スイープ構成は v0.4.0 と同一（A: 3シナリオ×50 seeds、B/C/D: 2シナリオ×5デルタ×30 seeds、計1,050 run）。1 run 60人×50ステップでも総実行時間は1〜2分程度の見込み
- stats.json の補足項目（**sampled60 のみ**。fixed8 は v0.4.0 実装をそのまま使い、stats.json も v0.4.0 と同一出力 ← evaluator HIGH-2）:
  - 実効 trait 分布・デルタ適用時のクランプ発生数・tolerance 閾値跨ぎ人数は、**いずれも run ごとに変わる値になるため統一して mean ± std で記録**（v0.4.0 の「条件ごと1値」はエージェント固定の帰結であり、サンプリング下では全項目を同じ扱いにする ← evaluator MEDIUM-7）
  - anxiety 飽和率: 従来どおり条件平均

### 5. 判定基準の再宣言（実装前に宣言・事後変更禁止）
**v0.4.0 の判定（8人村）は確定済みのまま残す。今回は N が変わる新実験なので基準を新規宣言するが、絶対下限は v0.4.0 の per-capita と完全パリティで引き継ぐ（← evaluator HIGH-3 への対応として選択肢(c)を採用）**。

- 採用理由: rev1 では per-capita 10% を提案したが、「v0.4.0 で H1 不整合（1.80 < 2）が確定した直後に per-capita 基準を 25%→10% に下げるのは、理由をどう書いても基準緩和の事後正当化と区別がつかない」という evaluator 指摘を受け、**緩和の余地を残さない per-capita 完全パリティ（25%）に統一する**。これにより v0.5.0 で H1 が整合になった場合も「基準を緩めたからだ」という批判が構造的に成立しなくなる
- 離散性の注記: 8人村では改宗1件 = 12.5% 刻みの粗い観測だったのに対し、60人村では1件 = 1.67% 刻みで観測できる。この違いは判定基準ではなく**結果の解釈（experiment_log の対比表）**で扱う
- **H1 整合**（A）: famine の mean(conversions) ≥ **15（= 60 × 0.25、v0.4.0 の 2/8 と per-capita パリティ）** かつ > baseline mean + 1σ かつ 改宗先の60%以上が救済+実利系
- **H2 整合**（D）: famine/baseline 両側で実利系改宗の条件平均が単調増加（隣接減少1箇所以下）。片方のみなら条件付き整合。全条件ゼロは判定不能（v0.4.0 と同一基準・絶対下限なし）
- **H5 整合**（A）: miracle_rumor の early_conversions mean ≥ **15（= 60 × 0.25、v0.4.0 の 2/8 とパリティ）** かつ early_convert_retention mean ≤ 0.5（割合基準なのでそのまま）
- パリティの帰結も受け入れる: v0.4.0 の famine per-capita 実測は 22.5%（1.8/8）だった。60人村で同水準なら H1 は再び不整合になる。それでよい（基準は予言ではなく物差し）
- **スケール換算の透明性（← codex HIGH-3）**: v0.4.0 実測値を単純スケールすると famine ≈ 13.5/60（< 下限15）、rumor 早期 ≈ 21/60（≥ 下限15）。つまりパリティ基準は「素直なスケール予想で H1 が通らない」側に立っており、通りやすい閾値を選んだという批判は構造的に成立しない。この換算値を experiment_log の対比表に明記する
- **H1 補助**（C）: v0.4.0 と同じ扱い（baseline 側単調増加で補強、全ゼロなら判定不能）。60人村では特性の裾が広がる（クランプ前の高 anxiety 個体が増える）ため、8人村よりは感度が出る可能性がある — 事前見積もりとして記録
- **H6**: 引き続き判定不能（モデル仕様。今回も習合メカニズムは触らない）
- **H3/H4**: 引き続き判定不能（スコープ外）

### 6. 図表・ドキュメント
- 図4枚を v0.5.0 データで再生成。**plot_sweeps.py の stats.json 新スキーマ対応（fig4 の閾値跨ぎ注釈 = mean±std、effective_trait の mean±std 化）を明示的にスコープに含める**（← codex MEDIUM-7。旧スキーマ前提のままだと実行時エラーか無言の誤表示）
- README: 結果セクションを 60 人村の結果で更新。「8人村 (v0.4.0) の結果と判定は experiment_log 参照」の1行を追加。限界セクションの「8体固定」を「60人・ロール原型からのサンプリング（それでも1つの村落類型にすぎない）」に更新
- experiment_log.md: v0.5.0 セクション追加（新基準の宣言経緯、v0.4.0 との対比表を含む）
- hypotheses.md: 検証状況を v0.5.0 で更新
- CHANGELOG: v0.5.0
- pyproject: 0.5.0

## 完了基準

1. `run_sweep.py --sweep all --judge`（デフォルト sampled60）が完走し、results.tsv ×4 + stats.json ×4 + 図4枚が v0.5.0 データで更新される
2. `--population fixed8` で v0.4.0 と同一の **results.tsv** が再現できる（byte 一致。**stats.json も byte 一致を要求**——fixed8 パスは v0.4.0 実装をそのまま通すため ← evaluator HIGH-2 の明確化）
   - **比較参照元（← codex MEDIUM-6）**: 実装開始前に main の v0.4.0 マージコミットへ git tag `v0.4.0` を打つ。outputs/sweeps/ は v0.5.0 で上書きされるため、比較は `git show v0.4.0:outputs/sweeps/<sweep>/results.tsv` と `outputs/sweeps_fixed8/<sweep>/results.tsv` の diff で行う
3. 既存テスト18件 + 新規テスト全てパス。新規テストの内訳:
   - population 生成の決定性（同じ seed → 同一行リスト、2回生成で一致）
   - 人数（60）とスキーマ（agents.tsv 互換列）
   - **スペックのバリデーション**: center ± 0.12 が [0,1] を外れる spec で ValueError（「クランプ後 [0,1]」の自明なテストではなく、生成時クランプが起きないことの検証 ← evaluator HIGH-4 / MEDIUM-8）
   - 宣言済み population.yaml が実際にバリデーションを通ること
   - agents_rows 注入（指定時は agents.tsv を読まない、None で既存挙動不変）
   - sampled60 の results.tsv 決定性（縮小版）
4. sampled60 を2回実行して results.tsv が byte 一致
5. H1/H2/H5 の判定が**上記5の宣言基準（per-capita パリティ）**で行われ、v0.4.0 判定との対比付きで experiment_log.md に記録される
6. 静的チェック: README の図パス・数値が stats.json と一致。`git status --porcelain` に runs/ や sweeps_fixed8/ が現れない
7. GitHub 上の図表示の目視確認は push 後に 作者へ依頼

## 検証方法

- pytest 全件
- 完了基準2と4は diff による byte 比較
- evaluator モード2で基準1–6を検証

## やらないこと

- 習合メカニズムの独立実装（H6 対応は次フェーズのまま）
- H3/H4 の専用スイープ
- 統計的検定（記述統計のまま。村が真にサンプリングされるようになったので、検定導入は次フェーズの有力候補として experiment_log に記す）
- ビューアの 60 人対応の最適化（描画されることだけ確認、レイアウト改善はしない）
- イベント・信念・シナリオの追加

## 進め方

1. 設計レビュー: codex-reviewer + evaluator モード1（APPROVE まで実装しない）
2. 実装 → 検証 → evaluator モード2
3. PR → merge（公開リポ既承認・進行承認済み）
