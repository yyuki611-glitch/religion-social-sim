# 習合メカニズムの独立実装（H6 を検証可能にする）v0.6.0

2026-06-06 設計 rev3（rev2: evaluator HIGH4・MEDIUM6・LOW1 反映 / rev3: MEDIUM2・LOW1 反映、APPROVE 済み）。
v0.4.0 から3回のレビューで指摘され続けた宿題の本丸:
「エンジンが `tolerance >= 0.65` の二値閾値で習合を直接ゲートしているため、
tolerance を動かして習合を観察するのはトートロジー（定義の再現）であり、
H6『高い寛容性は改宗ではなく習合を生む』は検証不能」を解消する。

## 現状の問題（engine.py 実測）

習合は2箇所とも `agent.traits["tolerance"] >= SYNCRETISM_TOLERANCE(0.65)` で直接ゲート:
1. 改宗時に旧信仰を副次として保持するか（`keep_old_as_secondary`）
2. 改宗に至らない圧力（threshold*0.5 < gap <= threshold が3ステップ）での副次取り込み

→ 「tolerance が高い人だけが習合する」がコードの定義そのもの。検証ではない。

## 新メカニズム: 段階的な「保持コスト」モデル

二値ゲートを廃止し、**改宗トリガー時の「旧信仰を捨てるか保持するか」を、
競合する複数要因の連続スコアで決める**:

```
keep_score = W_KEEP_TOLERANCE × tolerance        # 寛容: 併存への抵抗の低さ
           + W_KEEP_STRENGTH  × old_strength     # 旧信仰への愛着
           + W_KEEP_TRADITION × tradition_orientation  # 伝統: 捨てることへの抵抗
drop_score = min(1.0, gap / GAP_REF)             # 新信仰の引力（観測分布で正規化）
           + W_DROP_NOVELTY × novelty_openness   # 新奇志向: 過去を引きずらない
保持（習合的改宗）⇔ 完全改宗 の分岐: keep_score > drop_score（同値は drop = 完全改宗）
```

重みの宣言値と較正根拠（← evaluator HIGH-1）:
- W_KEEP_TOLERANCE = 0.50 / W_KEEP_STRENGTH = 0.30 / W_KEEP_TRADITION = 0.20（keep 合計 1.00）
- GAP_REF = 0.30 / W_DROP_NOVELTY = 0.35（drop 最大 1.35）
- **較正データ（threshold 実験の実測。スイープ E のデータは見ていない）**: sampled60 famine 20 run・
  改宗450件の改宗時 gap 分布は min 0.07 / 中央値 0.18 / 平均 0.19 / p90 0.29 / max 0.44。
  GAP_REF=0.30 は p90 相当（= 「観測された強い引力」で drop 項が 1.0 に達する正規化）
- 較正の出所（← evaluator MEDIUM-B）: v0.5.0 マージ後（コミット 7d6e591 = タグ v0.5.0）の
  `outputs/sweeps/scenario_seeds/runs/famine_s001〜s020/conversions.tsv` の reason 列から
  `gap=([\d.]+)` を正規表現抽出して集計（2026-06-06、設計 rev2 作成時にインラインスクリプトで実行。
  再現コマンドは同パターンの grep + statistics.median/fmean）
- **典型値での勝敗例示**（tolerance 0.55 / old_strength 0.40 / tradition 0.78 / novelty 0.30 の農民型。
  old_strength=0.40 の根拠（← evaluator LOW）: 改宗トリガーは gap>threshold が3ステップ持続した後に
  発火し、その間エンジンは strength を毎ステップ 0.02+0.04×gap 減衰させるため、改宗時点の strength は
  初期値（0.50–0.80）より侵食されている。0.40 は侵食後の保守的な代表値であり、初期値 0.75 を使うと
  keep=0.660 でさらに keep 寄りになる＝例示は厳しい側に立っている）:

| 改宗時 gap | keep | drop | 勝者 |
|---|---|---|---|
| 0.10 | 0.551 | 0.438 | keep（習合的改宗） |
| 0.18（中央値） | 0.551 | 0.705 | drop（完全改宗） |
| 0.29（p90） | 0.551 | 1.072 | drop（完全改宗） |

  → 中央値 gap で drop が勝ち、低 gap で keep が勝つ**拮抗した綱引き**になっている。
  tolerance デルタ ±0.20 は keep を ±0.10 動かし境界をずらすが、危機の強い引力（高 gap）は
  寛容でも完全改宗に倒す。**仮説が落ちる余地が構造的にある**
- **非対称性の明示**: keep 合計 1.00 / drop 最大 1.35 は意図的（強い危機は古い愛着を押し流す、
  という drop 優位の設計判断）。スケールが揃っていないことを README 限界にも記載する
- **重みの固定規律（← evaluator HIGH-3）**: 重みは「実装後・スイープ E 実行前」に固定する。
  較正に使ってよいのは threshold 実験（既存 A–D / v0.4.0 / v0.5.0）の観測値のみ。
  **スイープ E を一度でも実行した後の重み変更は理由を問わず禁止**（実行前なら境界バグ修正は可、
  ただし修正内容と理由を本書に追記する）

副次取り込み（改宗なしの習合）も同様に二値ゲートを外す:
- 持続的な複数信仰からの引力（threshold*0.5 < gap <= threshold が3ステップ）が条件（既存のまま）
- 取り込み判定を `rng.random() < syncretism_openness` に変更。
  `syncretism_openness = 0.25 × tolerance + 0.15 × novelty_openness + 0.10 × anxiety`
  （確率的・段階的。**最大 0.50 で意図的に頭打ち**: 改宗なしの副次取り込みは改宗より稀な現象として
  設計する ← evaluator MEDIUM-1 の明示要求）

**なぜこれで H6 が検証可能になるか**:
- tolerance はミクロルールに**段階的な一要因**として入る（重み 0.50/合計1.0、および確率の一項）。
  二値スイッチではないので「閾値を跨ぐ人数の観察」には還元されない
- 旧信仰の強度・伝統・新奇・gap という**競合要因**があるため、tolerance を上げても
  マクロな習合数が単調増加する保証はない（gap の大きい危機下では drop が勝ちうる。
  共同体フィードバックで二次効果も入る）。**仮説が落ちる余地が構造的にある**
- 判定対象は「ミクロルールに tolerance が入っているか」（自明）ではなく
  「**マクロな置換パターン**: tolerance ↑ で belief-change イベントに占める習合の割合が増え、
  完全改宗を置き換えるか」（創発）であることを README / experiment_log に明記する

## 後方互換の方針（重要）

エンジンの意味論が変わるため、無条件に差し替えると v0.4.0 / v0.5.0 の公表済み結果が
再現不能になる。**メカニズムをフラグで版管理する**:

- `run_scenario(..., syncretism_mode="threshold" | "graded")`。**デフォルト "threshold"（既存挙動と byte 同一）**
- `run_sweep.py --syncretism graded|threshold`（デフォルト threshold）
- 完了基準で「デフォルトで v0.5.0 sampled60 / v0.4.0 fixed8 の結果と byte 一致」を要求
- graded が研究的に妥当と確認できたら、全スイープの graded 移行は次フェーズで行う（今回はやらない）

## 新スイープ E `tolerance_graded`（H6 検証）

- {baseline, famine} × tolerance デルタ {-0.20, -0.10, 0, +0.10, +0.20} × seed 1–30（300 run）、sampled60 + graded
- results.tsv スキーマは既存と同一 + **新列なし**（習合数 syncretisms は既存列にある）
- 判定指標: `syncretism_share = syncretisms / (conversions + syncretisms)`（belief-change イベントに占める習合の割合）。stats.json に条件ごとの mean±std を追加

## H6 判定基準（実装前に宣言・事後変更禁止）

- **H6 整合**: famine 側で (a) tolerance デルタと syncretisms の条件平均が単調増加（隣接減少1箇所以下）、
  (b) **かつ** syncretism_share = syncretisms / (conversions + syncretisms) も単調増加
  （習合が「増えただけ」でなく改宗を**置き換えている**こと）、
  (c) **かつ** 効果量下限: syncretisms の最大条件平均 ≥ **3（= 60 × 0.05）**
- (c) の根拠（← evaluator HIGH-2）: 「村の5%」を集合現象として観察できる最小規模とする。
  H1/H5 の per-capita 25% パリティとは**別基準**である——あれは「v0.4.0 で宣言済みの同一指標の
  下限を N 間で引き継ぐ」パリティであり、H6 には引き継ぐべき過去の宣言値が存在しない
  （これまで検証不能だったため）。新規宣言の最小効果量であり、5% は v0.5.0 不安スイープで
  顕在化した「平坦系列を整合と誤判定する欠陥」を塞ぐための下限
- **置き換え/共増加の区別（← evaluator MEDIUM-3）**: (a)(b) が両立しても conversions が単に
  減っただけの可能性があるため、experiment_log には conversions / syncretisms / syncretism_share の
  **3系列を必ず併記**し、「置き換え」（conversions 横ばい以下で share 増）か「共増加」
  （両方増えて share も増）かを判定文に明記する
- baseline 側は参考系列（v0.5.0 の baseline は belief-change 自体が少ないため）
- (a)(b)(c) の一部のみ成立は「条件付き整合」、全滅は「不整合」、belief-change がほぼゼロなら「判定不能」
- 判定語は従来どおり 整合/不整合/判定不能。「ミクロに tolerance が入っている」ことは判定根拠にしない
- 補助指標: 最終ステップで副次信仰を持つエージェント数（summary の final_agents の
  secondary_belief 非null数から算出）を stats.json に記録（村がどれだけ習合的になったかの
  マクロ状態。判定には使わず参考）。**stats.json のキー名を宣言（← evaluator MEDIUM-A）**:
  条件ごとに `syncretism_share: {"mean":…, "std":…}` と `final_secondary_holders: {"mean":…, "std":…}`

## スコープ

1. **エンジン**: syncretism_mode パラメータ追加（デフォルト "threshold"）。
   **rng 規律（← evaluator HIGH の強調要求）: threshold パスのコードは1行も変更しない。
   graded で増える rng.random() 消費は graded 分岐の内側でのみ発生させる。
   これにより threshold モードの rng 消費列は完全不変 = v0.4.0 / v0.5.0 byte 互換**。
   既存テスト31件はデフォルト引数追加のみのため影響なし（← evaluator MEDIUM-5）
2. **run_sweep.py**: `--syncretism` フラグ、スイープ E 定義、syncretism_share の stats 追加、
   H6 judge 実装（宣言基準）。E の出力は `outputs/sweeps/tolerance_graded/`（コミット対象）
3. **図**: fig5（tolerance デルタ × 習合数 / syncretism_share / 完全改宗数、famine 主・baseline 参考）
4. **テスト**: (a) デフォルト threshold で既存31件パス + v0.5.0 既知結果のピン留め維持、
   (b) graded の決定性（**副次取り込みの確率分岐を含む** ← evaluator LOW）、
   (c) keep/drop スコアの単体テスト——**境界例を事前宣言**（← evaluator MEDIUM-6）:
   keep_score == drop_score の同値 → drop（完全改宗）/ tolerance=0 でも strength+tradition で
   keep が勝ちうる / gap が GAP_REF 以上で drop 項が 1.0 で頭打ち、
   (d) スイープEの縮小版決定性
5. **ドキュメント**: README（H6 の節を「検証不能」から結果に差し替え。**2メカニズム併存の説明文を
   必ず入れる**（← evaluator MEDIUM-4）:「H1/H2/H5 は threshold メカニズムで検証済み。H6 のみ
   graded メカニズムで検証する。全スイープの graded 移行と両メカニズムの挙動比較は次フェーズ」。
   ミクロ自明 vs マクロ創発の区別と keep/drop スケール非対称も限界に明記）、
   experiment_log、hypotheses、CHANGELOG 0.6.0、pyproject

## 完了基準

1. デフォルト（threshold）で: pytest 全件パス、`--population fixed8` が v0.4.0 タグと byte 一致、
   sampled60 の results.tsv が v0.5.0 タグと byte 一致（**対象は A–D の4本のみ。E は graded のため
   byte 一致の対象外** ← evaluator MEDIUM-7 の明確化）
2. スイープ E（300 run）が完走し、results.tsv + stats.json + fig5 が生成される。2回実行 byte 一致。
   **stats.json に条件ごとの syncretism_share の mean±std と最終副次信仰保持者数の mean±std が
   含まれること**（← evaluator HIGH-4。judge が読むキーの存在を基準化）
3. H6 判定が宣言基準 (a)(b)(c) で行われ、conversions / syncretisms / syncretism_share の3系列と
   「置き換え/共増加」の区別を含む数値根拠付きで experiment_log に記録される
4. 新規テスト全パス（graded 決定性・スコア単体（宣言済み境界例）・E縮小版・副次取り込み確率分岐の決定性）
5. 静的チェック: README 図パス整合、`git status --porcelain` に runs/ が現れない
6. GitHub 目視確認は push 後に 作者 依頼

## やらないこと

- スイープ A–D の graded 移行（次フェーズ。今回は E のみ graded）
- 副次信仰の減衰・棄教メカニズム（次フェーズ候補として記録）
- H3/H4 スイープ（このタスクの次にやる）
- 統計的検定

## 進め方

1. 設計レビュー: evaluator モード1 のみ（codex は一時使用停止中）。APPROVE まで実装しない
2. 実装 → 検証 → evaluator モード2
3. PR → merge（公開リポ既承認・進行承認済み）
