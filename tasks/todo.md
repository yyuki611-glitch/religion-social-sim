# H3・H4 専用スイープ（6仮説完全制覇）v0.7.0

2026-06-07 設計 rev3。
- rev2: evaluator モード1指摘（HIGH4・MEDIUM4）反映
- rev3: codex-reviewer 指摘（HIGH2・CRITICAL1・MEDIUM2・LOW3）反映。ただし指摘3の
  「community_pressure が改宗確率に1:1で効く」は belief.py 実測で誤り（係数0.15）と確認、
  指摘5の「下限3件は理論上限」も v0.4.0 実績（8人村で庇護後4件）と矛盾するため棄却。
  即時/遅延の構造非対称・解釈ルール事前宣言・診断キー・スキーマ防御テストは採用
v0.4.0 から「判定不能（未検証）」のまま残っていた最後の2仮説に専用スイープで判定を出し、
「3つの問い・6つの仮説を立てて、全部に答えて、限界も明示した」という完結の形を作る。

- **H3**: 強い共同体依存は、地域の神社や家の信仰（氏神信仰・古典神道）を保存する
- **H4**: 権威による庇護は、制度と結びついた信念を加速させる

## 配線の開示（設計段階で宣言）

v0.6.0 の批判レビューで確立した規律に従い、先に配線を開示する:
- H3: community_dependence は信念スコアの共同体項（多数派信仰への引力 ×0.35）と
  openness の community_pressure 項に直接入っている。「共同体依存が同調を生む」はミクロ配線
- H4: shrine_patronage イベントは `target_belief=classical_shinto`・`authority_signal=0.60`・
  **`community_signal=0.25`** と定義されており、「庇護が古典神道に向かう」方向は配線そのもの。
  さらに community_signal 経由の引力も混ざるため、「権威」単独の測定純度は完全ではない
  （← evaluator MEDIUM-2。authority_trust デルタが動かすのは authority_signal 項と openness の
  authority 項であり、デルタへの応答は権威チャネルに帰属できるが、改宗数の水準には
  community 寄与が含まれる）
- よって判定対象は方向性ではなく**定量応答**（デルタへの単調性・効果量）に限る。
  README の「主張できること・できないこと」にも追記する

## 仮説が落ちる余地（事前見積もり）

- **H3 は本当に落ちうる**: community_dependence は2つの**逆方向チャネル**を持つ。
  (i) 多数派信仰への引力（信念スコアの community 項 ×0.35。**閾値型・遅延**: gap>threshold が
  3ステップ続いて初めて改宗が起きる）、
  (ii) openness の community_pressure = dep × (1 − 自信仰のシェア)（**即時・線形**だが係数は
  belief.py 実測で **0.15**（最大寄与 +0.15）。codex 指摘の「1:1で効く」は誤り）。
  さらに famine イベント自体が community_signal=0.20 を持ち、dep が高いほど稲荷への
  イベント引力も強まる（dep×0.20×1.6）。危機で地元信仰のシェアが下がった村では
  (ii)+イベント項が (i) を上回り、高 dep がむしろ保存を**壊す**方向に働きうる
- **逆転時の解釈ルールを事前宣言**（← codex HIGH-1）: famine 側で local_retention が dep に
  対し**単調減少**した場合、それは測定の失敗ではなく「このモデルでは共同体依存は危機下で
  保存ではなく雪崩を加速する」という**正当な不整合（仮説の棄却）**として記録する。
  谷型（非単調）は「条件付き判定不能」とし、チャネル帰属の診断を experiment_log に書く。
  baseline 側は belief-change が少なく効果量下限を満たさない可能性が高い（参考系列）
- **H4 の効果規模の事前見積もり**: shrine_patronage の信念スコア寄与は
  1.6 × 0.60 × auth_trust = **0.96 × auth_trust**（auth_trust=0.5 の代表的エージェントで ≈0.48。
  改宗時 gap の典型値 0.18 を大きく超える）で、
  v0.4.0 実績では8人村で庇護後に**4件**の古典神道改宗が観測された（per-capita 50%）。
  60人村で下限3件（5%）は十分到達可能（← codex MEDIUM-5 の「理論上限に近い」は実績と矛盾
  するため棄却）。一方 authority_trust **デルタ ±0.20** が動かすのは openness の権威項
  （係数0.1 → 最大±0.02）とイベント項（±0.20×0.96 ≈ ±0.19 のスコア差）で、デルタ応答が
  フラット＝判定不能になる可能性は受け入れる（v0.5.0 不安スイープと同じ扱い）

## スイープ定義

| スイープ | 軸 | 対象 |
|---|---|---|
| F `community` | {baseline, famine} × community_dependence デルタ {-0.20, -0.10, 0, +0.10, +0.20} × seed 1–30（300 run） | H3 |
| G `authority` | {baseline, miracle_rumor} × authority_trust デルタ 同5段階 × seed 1–30（300 run） | H4（miracle_rumor は step 20 に shrine_patronage（唯一の権威庇護イベント）を含むため対象シナリオに採用。baseline は権威イベントなしの対照） |

- メカニズムは **threshold**（H1/H2/H5 と同一系。習合ゲートは H3/H4 の対象外なので
  graded を持ち出さず、A–D との比較可能性を保つ）
- population は sampled60（v0.5.0 と同一）。rng 規律・run_id 形式・決定性要件は既存スイープと同一
- **results.tsv のスキーマは変更しない**（全スイープ共通スキーマの byte 互換を守る）。
  H3/H4 固有の指標は graded 方式と同じく **aux → stats.json** に記録する

## クランプ飽和の事前開示

- community_dependence の center は farmer 0.82 / authority 0.88 / elder 0.80（村の約半数が高位）。
  デルタ +0.20 で大量に 1.0 クランプが発生し、上端で条件差が圧縮される。
  実効分布とクランプ数は stats.json に記録（既存の仕組み）し、単調性判定は圧縮を含む
  全5条件で行う（フラット化で落ちるならそれも結果）
- **クランプの非対称性（← evaluator MEDIUM-3）**: クランプは +側条件のみで発生し、−側の
  条件差は正常に伸びる。「単調性は低 dep 側で確認しやすく、高 dep 側は圧縮される」という
  読み方の注意を experiment_log に記録する
- authority_trust は村役 0.85 のみ高位（3人）で飽和の影響は小さい

## 判定指標（stats.json のキー名を宣言）

- **`local_retention`** {"mean","std"}（スイープF）: run ごとに「初期信仰が地域信仰だった
  エージェントのうち、最終ステップでも同じ信仰を保持している割合」
  - **地域信仰の定義と根拠（← evaluator MEDIUM-1）**: `ujigami_shinto`（appeal: community,
    ancestor, local_protection = 地域の神社）+ `classical_shinto`（appeal: kinship, land,
    ritual_continuity = 家・土地の信仰）。H3 の文言「地域の神社**や家の**信仰」の両半分に
    appeal タグで対応する2信念を採用する
  - **分母は run 開始時の地域信仰保持者数で固定**（← evaluator HIGH-2。途中で改宗しても
    分母は変わらない。population.yaml 上の期待値は村の約45%＝約27人）。分母ゼロの run は
    N/A（n_na 記録）
  - **計算元（← evaluator HIGH-1）**: `summary["final_agents"]` には初期信仰が含まれない
    （id/label/belief/secondary/strength のみ。エンジン実装確認済み）。**`agents_rows` の
    `current_belief`（初期信仰）と `final_agents` の `belief`（最終信仰）を id で突き合わせて
    計算する**。実装は `_population_aux` に summary を渡すか、ループ内で id→初期信仰マップを
    作る
- **`conv_to_classical_post_patronage`** {"mean","std"}（スイープG）: run ごとに
  「step 20–25（shrine_patronage 発火後5ステップ）の古典神道への改宗数」を conversions.tsv
  から計算。baseline では同じ step 窓で計測（イベントなしの対照値）
  - **窓の交絡を事前開示（← evaluator HIGH-4）**: EVENT_DECAY=0.92 のため step 5 の
    miracle_rumor（稲荷向け）は step 20 で重み 0.92^15 ≈ 0.29、step 25 で ≈ 0.19 と**まだ有効**。
    この窓の測定は shrine_patronage 単独ではなく「噂の残存 + 庇護」の複合場での古典神道改宗
    である。ただし噂は稲荷向け（競合方向）なので、庇護効果を**過大評価する方向には働かない**。
    experiment_log の限界に追記する（完了基準に含める）
- どちらも aux 経由で stats.json に集計（graded の syncretism_share と同じ実装パターン）

## 判定基準（実装前に宣言・事後変更禁止）

効果量下限は v0.5.0 不安スイープの教訓（平坦系列を整合と誤判定しない）に従い必須とする。

- **H3 整合**（F・famine 側が主判定。baseline は参考）:
  (a) community デルタと local_retention の条件平均が単調増加（隣接減少1箇所以下）
  (b) **かつ** 効果量下限: 条件平均の max − min ≥ **0.05**（= 5パーセントポイント。
  地元信仰保持者約27人に対し1.4人分の差。H6 と同じ「村の5%」系の最小効果量）
  - 単調**減少** + 効果量下限成立 → **不整合（正当な棄却）**。谷型 → 条件付き判定不能
    （前掲の事前宣言ルール）
  - **N/A 無効化閾値**（← codex LOW-6a）: 分母ゼロ run が条件あたり **5件超**（30 runs の
    1/6）なら H3 判定自体を判定不能とする
  - **診断キー**（← codex LOW-6b。判定には使わない）: stats.json に `local_retention_ujigami`
    と `local_retention_classical` を分解記録（異質な2母集団——氏神は農民・家内に広く、
    古典神道は村役・古老に集中——の合算が判定を曖昧にしないかの検査用）
- **H4 整合**（G・miracle_rumor 側が主判定。baseline は対照）:
  (a) authority デルタと conv_to_classical_post_patronage の条件平均が単調増加（同上）
  (b) **かつ** 効果量下限: 最大条件平均 ≥ **3**（= 60 × 0.05、H6 と同一の新規最小効果量）
  - **(c) は整合条件ではなく測定の妥当性チェック**（← evaluator HIGH-3）: baseline 側の
    同窓改宗 mean が miracle_rumor 側の 1/2 以下であること＝「測った改宗が庇護イベント由来」
    の確認。**(c) が失敗した場合は (a)(b) の成否にかかわらず判定を「判定不能（測定の妥当性
    不成立）」とし、交絡注記を experiment_log に記録する**。(c) 成立時のみ (a)(b) で
    整合/条件付き/不整合を判定する
  - (c) の限界の明示（← codex HIGH-2）: (c) は「イベントの構造分離」の確認であって
    **authority_trust デルタには感応しない**（全デルタ条件で同じ判定になる）。権威*感度*の
    判定はあくまで (a)(b) が担う。この役割分担を experiment_log にも書く
  - 噂残存の定量（← codex の補強）: step 20 時点の噂残存はスコア寄与 ≈ 0.046×novelty
    （庇護の権威項 0.96×auth_trust の 1/70 以下）でスコア面の交絡は小さい。実質的な交絡は
    「step 5–10 に稲荷へ流れた人口が窓の時点で競合構造を変えている」という**状態面**にあり、
    これは rev2 で宣言済みの複合場の注記でカバーする
- 部分成立（(a)(b) の片方のみ）は「条件付き整合」、両方不成立は「不整合」、
  対象イベント反応がほぼゼロは「判定不能」
- 判定語は従来どおり。方向性の配線は判定根拠にしない

## スコープ

1. **run_sweep.py**: SWEEPS に F/G を追加、aux に local_retention / post-patronage 改宗数を追加、
   _build_stats_sampled に2キーの集計を追加（**graded キーと同様、該当スイープのみに出力**。
   A–E の stats.json は不変 = byte 互換維持）、judge() に H3/H4 の宣言基準を実装
   （stats.json が無ければ従来どおり判定不能）
2. **plot_sweeps.py**: fig6（F: community デルタ × local_retention、2シナリオ）、
   fig7（G: authority デルタ × 庇護後改宗数、miracle_rumor 主・baseline 対照）
3. **エンジン変更なし**（trait_adjustments と既存イベントで完結）
4. **テスト**: F/G の縮小版決定性、local_retention 計算の単体テスト（合成データ）、
   post-patronage 窓の計算単体テスト、A–E の stats.json に新キーが混入しないテスト、
   **RESULT_FIELDS が宣言済みリストと完全一致するスキーマ防御テスト**（← codex LOW-6c。
   F/G 実装時の誤った列追加で完了基準4の byte 一致が壊れるのを防ぐ）
5. **ドキュメント**: README（結果2節・発見の要約 6/6 完成・配線開示追記・図2枚）、
   experiment_log、hypotheses、CHANGELOG 0.7.0、pyproject

## 完了基準

1. スイープ F/G（計600 run）が完走し、results.tsv ×2 + stats.json ×2 + 図2枚が生成。2回実行 byte 一致
2. stats.json に宣言キー（local_retention / conv_to_classical_post_patronage）の mean±std が存在
3. H3/H4 の判定が宣言基準で行われ、数値根拠付きで experiment_log に記録（6仮説すべてに判定が揃う）
4. 既存テスト42件パス維持 + 新規テスト全パス。既存スイープ A–E の results.tsv / stats.json が
   再実行で byte 不変（**比較参照は v0.6.0 タグ** ← evaluator MEDIUM-4。共通スキーマ・aux 分岐の互換確認）
5. 静的チェック: README 図パス整合（7枚）、git status に runs/ なし
6. GitHub 目視確認は push 後に 作者確認

## やらないこと

- 新イベント・新シナリオの追加（既存 shrine_patronage を使う。「権威イベントの種類を増やした
  検証」は次フェーズ）
- graded メカニズムでの H3/H4（threshold で統一）
- 統計的検定・不偏分散移行（次フェーズ宣言済み）
- README 冒頭の「発見ファースト」再構成（v1.0 で実施）

## 進め方

1. 設計レビュー: codex-reviewer（恒久対処済みで復帰）+ evaluator モード1 並行。APPROVE まで実装しない
2. 実装 → 検証 → evaluator モード2
3. PR → merge（既承認の運用に従う）
