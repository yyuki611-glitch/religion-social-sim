# religion-social-sim

日本の宗教の伝播と衰退を扱う社会シミュレーション。

8人の村人エージェントが「不安・共同体の圧力・権威・噂・現世利益・救済欲求・世代交代」のもとで信仰を変え、混ぜ（習合）、捨てる過程を、決定的（再現可能）なエンジンでシミュレートし、パラメータスイープで仮説とモデル挙動の整合を検証する研究プロトタイプです。

## 問い

- なぜ危機（飢饉・疫病）は人を新しい信仰へ向かわせるのか
- なぜ噂は爆発的に広がるのに、定着しないのか
- なぜ日本では「改宗」ではなく「習合」（神と仏を両方拝む）が起きるのか

## 仮説

[docs/hypotheses.md](docs/hypotheses.md) の6仮説のうち、本バージョンでは以下を実験対象とした。

- **H1**: 高い不確実性と苦難は、救済志向の信念を増やす
- **H2**: 農業・商業の圧力は、現世利益の祈願を増やす
- **H5**: 噂は急速な伝播を生むが、定着は共同体と実利的な見返りに依存する

H3（共同体依存）・H4（権威）は専用スイープ未実施のため**判定不能（未検証）**。H6（寛容性→習合）は現エンジンが寛容度の閾値で習合を直接ゲートしておりトートロジーになるため**判定不能（モデル仕様）** — 「限界」の節を参照。

## 手法

- 決定的エンジン（同一 seed なら同一結果）。改宗イベント全件に理由トレース付き
- 4本のパラメータスイープ、計 **1,050 run**（`experiments/run_sweep.py`）:

| スイープ | 軸 | 目的 |
|---|---|---|
| A | 3シナリオ × seed 1–50 | H1/H5 の検証（シナリオ間比較） |
| B | {baseline, famine} × 寛容度デルタ 5段階 × seed 1–30 | 感度分析（H6 は検証不能） |
| C | {baseline, famine} × 不安デルタ 5段階 × seed 1–30 | H1 の補助検証 |
| D | {baseline, famine} × 実利欲求デルタ 5段階 × seed 1–30 | H2 の検証 |

- 特性の介入は**加算デルタ**（±0.20、0–1 にクランプ。乗算は上限張り付きで条件差が潰れるため不採用）
- 判定基準（数値閾値）は**実装前に宣言**し、結果を見てから動かしていない（[tasks/todo.md](tasks/todo.md)）。判定語は「整合 / 不整合 / 判定不能」を使い、「証明」「支持」は使わない

## 実験結果

### 危機は改宗を生み、それは定着する。噂も改宗を生むが、蒸発する（スイープA）

![シナリオ別の改宗数と早期改宗の定着率](outputs/sweeps/figures/fig1_scenarios.png)

| シナリオ | 改宗数 mean±std（50 seeds） | 早期改宗の定着率 | 最終定着率（初期信仰の保持） |
|---|---|---|---|
| baseline | 0.00 ± 0.00 | —（早期改宗なし） | 1.000 |
| famine | 1.80 ± 0.40 | **1.000**（全員が新信仰を維持） | 0.775 |
| miracle_rumor | 7.94 ± 0.70 | **0.118**（88%が新信仰を放棄） | 0.370 |

- 飢饉での改宗先は **100% が救済系（浄土仏教）+ 実利系（稲荷・龍神）**
- 噂（奇跡の噂→稲荷）はイベント直後5ステップで平均 2.8 件の改宗を生むが、最終的にほぼ全員が離脱する。**H5: 整合**（早期改宗 mean 2.8 ≥ 2、定着率 0.118 ≤ 0.5）
- **H1: 不整合（事前宣言した基準による）** — famine の改宗 mean 1.80 が絶対下限 2 をわずかに下回った。方向は仮説どおり（baseline 0 に対して famine 1.8、改宗先は100%が救済+実利系）だが、宣言済みの閾値は動かさずそのまま報告する

### 不安は改宗の「引き金」ではなく「感度」だった（スイープC）

![不安デルタと救済+実利系改宗数](outputs/sweeps/figures/fig2_anxiety.png)

不安特性を ±0.20 動かしても、イベントのない baseline では**全条件で改宗ゼロ**（H1補助: 判定不能）。famine 側では 1.77 → 1.87 と微増にとどまる。これは設計段階の事前見積もりどおりで、本モデルでは**不安単独では改宗は起きず、危機イベントが作る「信念間の引力差」が駆動因子**であることを示す。不安はその引き金が引かれたときの感応度を変えるだけである。

### 実利欲求の効果は危機の下でだけ現れる（スイープD）

![実利欲求デルタと実利系改宗数](outputs/sweeps/figures/fig3_practical.png)

実利欲求デルタを上げると famine 側では実利系（稲荷・龍神）への改宗が 1.0 → 2.0 に単調増加する一方、baseline 側ではゼロのまま。**H2: 条件付き整合**（famine 側のみ単調増加。実利欲求も危機という文脈があって初めて改宗に転化する）。

### 寛容性は信仰地図を「安定」させない。むしろ流動化させる（スイープB・感度分析）

![寛容度デルタと改宗・習合・定着率](outputs/sweeps/figures/fig4_tolerance.png)

寛容度を上げると（famine 側）習合が 0 → 1.1 件に増えるだけでなく、**正面改宗も 1.83 → 2.57 に増え、定着率は 0.775 → 0.679 に低下**した。「寛容だから変わらない」のではなく「寛容だから動きやすい」。ただしこのスイープは習合の発生条件（寛容度 ≥ 0.65 の閾値ゲート）に直結したトートロジーを含むため**感度分析**であり、H6 の検証ではない。図中の n/8 は閾値を超えるエージェント数。

## 発見の要約

| 仮説 | 判定 | 根拠 |
|---|---|---|
| H1 危機→救済志向 | **不整合**（基準: mean ≥ 2 を 1.80 で下回り） | 方向は整合（baseline 0 vs famine 1.8、改宗先100%救済+実利） |
| H2 実利圧力→現世利益 | **条件付き整合** | famine 側のみ単調増加（1.0→2.0）。baseline 側はゼロ |
| H3 共同体→保存 | 判定不能 | 専用スイープ未実施 |
| H4 権威→制度信仰 | 判定不能 | 専用スイープ未実施 |
| H5 噂は速いが定着しない | **整合** | 早期改宗 2.8 件 / 定着率 11.8% |
| H6 寛容→習合 | 判定不能 | モデル仕様（閾値ゲート）によるトートロジー |

モデルから出た最も面白い創発的知見は、仮説リストになかったものだった：

1. **改宗の「入口」によって定着率がまったく違う**（危機経由 100% vs 噂経由 11.8%）
2. **個人特性（不安・実利欲求）は単独では改宗を起こせず、イベントとの掛け算でだけ効く**
3. **寛容性は安定装置ではなく流動化装置**

## 限界

- **エージェント8体の固定集団**。母集団からのサンプリングではなく、seed による乱数変動は「同じ村の並行世界」を意味する。統計量は記述統計（mean/std）であり検定はしていない
- **歴史の再現ではない**。モデル内実験であり、判定語の「整合」は「このモデルの挙動が仮説と矛盾しない」以上を意味しない
- **H6 はトートロジー**。習合の発生がエンジン内で寛容度の閾値に直結しているため、寛容度を動かして習合を観察しても定義の再現にしかならない。習合メカニズムの独立実装が次フェーズ課題
- **miracle_rumor シナリオには交絡がある**。step 20 の神社庇護・step 34 の寺スキャンダルが含まれ、揺り戻しは「噂の自然減衰」と「権威イベントの引き戻し」の複合。早期窓（step 5–10）の測定は庇護イベント前なので汚染されない
- **baseline の good_harvest（不安 -0.20）はスイープCのデルタと逆方向に働く**。ただし全条件に同一に作用するため条件間比較は成立する

## 再現方法

```bash
# 全スイープ（1,050 run、数秒〜数十秒）+ 宣言済み基準での仮説判定
.venv/bin/python experiments/run_sweep.py --sweep all --judge

# 図の再生成
.venv/bin/python experiments/plot_sweeps.py
```

- 出力は決定的：同じコードなら `outputs/sweeps/*/results.tsv` は何度実行しても byte 一致する
- run ごとの生ログは `outputs/sweeps/<sweep>/runs/<run_id>/`（git 管理対象外）、集計は `results.tsv` / `stats.json`（コミット済み）
- 判定基準の宣言と設計レビューの経緯は [tasks/todo.md](tasks/todo.md)、実験ログは [docs/experiment_log.md](docs/experiment_log.md)

## コンセプト

公開されている社会シミュレーションプロジェクトの2つのパターンを組み合わせています（[docs/references.md](docs/references.md)）。

- 実験ファーストのスクリプトとパラメータスイープ：`cygkichi/my-social-agents` を参考。
- 再利用可能なコア + 差し替え可能なドメインパック：`karesansui-u/hackathon-singulab` を参考。

最初のドメインは `japan_religion` です。

## セットアップ

```bash
cd religion-social-sim
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[test,analysis]"
```

## 単発実行

```bash
.venv/bin/python experiments/run_scenario.py \
  --domain domain_packs/japan_religion \
  --scenario famine.yaml \
  --output-dir outputs/runs/famine_run \
  --seed 42
```

シナリオは `baseline.yaml`（基準）、`famine.yaml`（飢饉）、`miracle_rumor.yaml`（奇跡の噂）の3つ。同じ seed なら結果は決定的（再現可能）。

### LLM ナラティブ生成（任意）

実行結果から「村で何が起きたか」の日本語の観察記録を LLM に書かせることができます。

```bash
# Claude Code CLI を使う場合
.venv/bin/python experiments/run_scenario.py \
  --scenario famine.yaml --output-dir outputs/runs/famine_narrated \
  --narrate claude --narrate-model haiku

# ローカル Ollama を使う場合
.venv/bin/python experiments/run_scenario.py \
  --scenario famine.yaml --output-dir outputs/runs/famine_narrated \
  --narrate ollama --narrate-model qwen2.5:7b
```

出力先に `narrative.md` が追加されます。LLM なし（デフォルト）でもシミュレーション自体は完全に動作します。

### ブラウザビューア

実行結果を村の地図として再生できるビューアを生成できます。

```bash
.venv/bin/python experiments/render_viewer.py --run outputs/runs/famine_run
open outputs/runs/famine_run/viewer.html
```

- 村人は自分の信仰に対応する場所（神社・寺・市場・田んぼなど）の周りに立ち、改宗すると移動する
- 色＝信仰、大きさ＝信仰の強さ、リング＝習合（副次信仰）
- 再生／停止・速度変更・ステップスライダー・村人クリックで詳細表示
- `viewer.html?step=30` のように URL で開始ステップを指定可能
- 単一 HTML ファイルなのでダブルクリックでそのまま開ける（サーバー不要）

## 出力ファイル

| ファイル | 内容 |
|---|---|
| `agent_turns.tsv` | ステップ × エージェントの生ログ（信仰・強度・不安・改宗圧力） |
| `belief_shares.tsv` | ステップごとの信仰別の信者数・平均強度 |
| `conversions.tsv` | 改宗・習合イベント（全件に理由トレース付き） |
| `events_log.tsv` | 発火したシナリオイベント |
| `summary.json` | 最終状態の集計（改宗数・定着率・最終分布） |
| `narrative.md` | `--narrate` 指定時のみ。LLM による日本語の観察記録 |
| `viewer.html` | `render_viewer.py` 実行時のみ。ブラウザで再生できる村マップ |
| `results.tsv` / `stats.json` | スイープ実行時。run ごとの集計と条件ごとの統計 |

## テスト

```bash
.venv/bin/python -m pytest
```

`validation/validation_plan.md` の5項目（baseline 安定／飢饉で実利・救済系が増加／噂で短期改宗圧力／改宗理由トレース必須／生ログと集計の分離）に加え、スイープ機能（特性デルタの適用とクランプ・既存挙動の不変・results.tsv の決定性・早期改宗定着率の計算）をテストとして固定しています（計18件）。

## 構成

```text
sim_core/
  ドメインに依存しないシミュレーションのコア。

domain_packs/japan_religion/
  日本の宗教データ、プロンプト、シナリオ、バリデーション、ビューア設定。

experiments/
  シナリオ実行（run_scenario.py）、スイープ（run_sweep.py）、
  図表生成（plot_sweeps.py）、ビューア生成（render_viewer.py）。

outputs/runs/
  単発実行の出力先。中身は git 管理対象外。

outputs/sweeps/
  スイープの集計（results.tsv / stats.json / figures はコミット、runs/ は対象外）。

docs/
  設計メモ、仮説、実験ログ、参考文献。

visualization/
  ブラウザビューアのテンプレート。
```

## 現在のスコープ（v0.4.0）

- ドメイン1つ：`japan_religion`
- 信念タイプ 7 種、初期エージェント 8 体
- シナリオ 3 つ：baseline（基準）、famine（飢饉）、miracle rumor（奇跡の噂）
- 決定的なステップ実行エンジン：イベント減衰、信念スコア（訴求×特性・共同体圧力・慣性）、改宗・習合判定、理由トレース、特性デルタ介入
- パラメータスイープ 4 本（1,050 run）と宣言済み基準による仮説判定
- LLM ナラティブ生成（claude CLI / Ollama、任意）

これはまだ歴史の再現ではありません。目標は、伝播メカニズムを観察できる「検証可能な装置」を作ることです。

## 次フェーズ候補

- 習合メカニズムの独立実装（H6 を検証可能にする）
- H3（共同体依存）・H4（権威）の専用スイープ
- エージェント数の拡大と母集団サンプリング
- エージェント単位の LLM「観測器」判断（hackathon-singulab の観測器プロンプト方式）
