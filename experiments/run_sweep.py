"""パラメータスイープランナー。

tasks/todo.md（設計 rev4）で宣言した4本のスイープを逐次実行し、
run ごとの集計行（results.tsv）と条件ごとの統計（stats.json)を出力する。

設計上の規律:
- rng は run_scenario() 内部の random.Random(seed) のみ。グローバル random は使わない。
- 並列実行しない（逐次）。
- run_id は決定的採番（uuid / timestamp 禁止）。
- results.tsv の行順は (scenario, trait, delta, seed) の昇順で固定（決定性検証のため）。

信念ファミリー分類の根拠（beliefs.tsv の appeal 列）:
- jodo_buddhism: salvation,grief,afterlife        → 救済系
- inari_belief:  practical_benefit,commerce,harvest → 実利系
- ryujin_belief: water,weather,agriculture          → 実利系
- それ以外（classical_shinto, ujigami_shinto, zen_buddhism, mountain_belief）→ その他
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim_core.domain_pack import read_tsv, read_yaml  # noqa: E402
from sim_core.engine import SYNCRETISM_TOLERANCE, run_scenario  # noqa: E402
from sim_core.population import generate_agents  # noqa: E402

DOMAIN = ROOT / "domain_packs" / "japan_religion"

# 母集団サンプリング用 rng の seed オフセット。値自体に意味はなく、
# シミュレーション rng の seed 空間（1–50）と重ならないことと、
# 定数として明示されていることだけが要件（設計 rev3）。
POPULATION_SEED_OFFSET = 10**6

# 仮説判定の絶対下限（実装前に設計で宣言済み。事後変更禁止）
# fixed8 (v0.4.0): H1=2, H5=2（8人村の per-capita 25%）
# sampled60 (v0.5.0): H1=15, H5=15（60 × 0.25。per-capita 完全パリティ）
ABS_FLOORS = {"fixed8": {"h1": 2, "h5": 2}, "sampled60": {"h1": 15, "h5": 15}}

SALVATION_BELIEFS = {"jodo_buddhism"}
PRACTICAL_BELIEFS = {"inari_belief", "ryujin_belief"}

# 早期改宗ウィンドウ: 各シナリオの最初の非 generation イベント発火 step を基点に +5。
# H5 の判定には miracle_rumor のみを使う（baseline / famine の値は参考値）。
EARLY_WINDOW = {
    "baseline": (10, 15),  # good_harvest @10
    "famine": (8, 13),  # famine @8
    "miracle_rumor": (5, 10),  # miracle_rumor @5
}

DELTAS = [-0.20, -0.10, 0.0, 0.10, 0.20]

SWEEPS: dict[str, dict] = {
    "scenario_seeds": {
        "scenarios": ["baseline", "famine", "miracle_rumor"],
        "trait": None,
        "deltas": [0.0],
        "seeds": list(range(1, 51)),
    },
    "tolerance": {
        "scenarios": ["baseline", "famine"],
        "trait": "tolerance",
        "deltas": DELTAS,
        "seeds": list(range(1, 31)),
    },
    "anxiety": {
        "scenarios": ["baseline", "famine"],
        "trait": "anxiety",
        "deltas": DELTAS,
        "seeds": list(range(1, 31)),
    },
    "practical_need": {
        "scenarios": ["baseline", "famine"],
        "trait": "practical_benefit_need",
        "deltas": DELTAS,
        "seeds": list(range(1, 31)),
    },
    # スイープ E（v0.6.0）: graded 習合メカニズムで H6 を検証する唯一のスイープ。
    # A–D は threshold のまま（2メカニズム併存の理由は README 参照）
    "tolerance_graded": {
        "scenarios": ["baseline", "famine"],
        "trait": "tolerance",
        "deltas": DELTAS,
        "seeds": list(range(1, 31)),
        "syncretism": "graded",
    },
}

# H6 の効果量下限（設計 rev3 で宣言。3 = 60 × 0.05、村の5%を最小の集合現象とする。
# H1/H5 の per-capita 25% パリティとは別基準＝H6 には引き継ぐ過去の宣言値が存在しない）
H6_SYNC_FLOOR = 3

RESULT_FIELDS = [
    "sweep",
    "scenario",
    "trait",
    "delta",
    "seed",
    "steps",
    "conversions",
    "syncretisms",
    "retention_rate",
    "conv_to_salvation",
    "conv_to_practical",
    "conv_to_other",
    "early_conversions",
    "early_convert_retention",
]


def _family_counts(conversion_rows: list[dict[str, str]]) -> tuple[int, int, int]:
    salv = sum(1 for c in conversion_rows if c["to_belief"] in SALVATION_BELIEFS)
    prac = sum(1 for c in conversion_rows if c["to_belief"] in PRACTICAL_BELIEFS)
    other = len(conversion_rows) - salv - prac
    return salv, prac, other


def compute_metrics(
    conversions: list[dict[str, str]],
    final_agents: list[dict],
    scenario: str,
) -> dict:
    """1 run 分の conversions.tsv 行と summary の final_agents から派生指標を計算する。

    early_convert_retention: 早期ウィンドウ内に改宗したエージェントのうち、
    最終ステップでその改宗先信仰を保持している割合。同一エージェントが
    ウィンドウ内で複数回改宗した場合は最後の改宗先を採用する。
    早期改宗ゼロの run は None（results.tsv では空欄 = N/A）。
    """
    conv_rows = [c for c in conversions if c["kind"] == "conversion"]
    salv, prac, other = _family_counts(conv_rows)

    lo, hi = EARLY_WINDOW[scenario]
    early = [c for c in conv_rows if lo <= int(c["step"]) <= hi]
    # step 順で上書きし、エージェントごとの「ウィンドウ内最後の改宗先」を取る
    early_target: dict[str, str] = {}
    for c in sorted(early, key=lambda c: int(c["step"])):
        early_target[c["agent_id"]] = c["to_belief"]

    final_belief = {a["id"]: a["belief"] for a in final_agents}
    if early_target:
        retained = sum(1 for aid, b in early_target.items() if final_belief.get(aid) == b)
        early_retention: float | None = retained / len(early_target)
    else:
        early_retention = None

    return {
        "conversions": len(conv_rows),
        "syncretisms": sum(1 for c in conversions if c["kind"] == "syncretism"),
        "conv_to_salvation": salv,
        "conv_to_practical": prac,
        "conv_to_other": other,
        "early_conversions": len(early),
        "early_convert_retention": early_retention,
    }


def _effective_trait_stats(trait: str, delta: float) -> dict:
    """agents.tsv に delta を適用した後の実効特性分布（seed 間で不変なので条件ごと1値）。"""
    rows = read_tsv(DOMAIN / "data" / "agents.tsv")
    raw = [float(r[trait]) for r in rows]
    eff = [max(0.0, min(1.0, v + delta)) for v in raw]
    clamped = sum(1 for v in raw if not (0.0 <= v + delta <= 1.0))
    out = {
        "min": round(min(eff), 4),
        "mean": round(sum(eff) / len(eff), 4),
        "max": round(max(eff), 4),
        "clamped_agents": clamped,
    }
    if trait == "tolerance":
        out["agents_at_or_above_syncretism_threshold"] = sum(
            1 for v in eff if v >= SYNCRETISM_TOLERANCE
        )
    return out


def _anxiety_saturation(run_dir: Path) -> float:
    """run 中に anxiety が 1.0 に張り付いた agent-step の比率。"""
    turns = read_tsv(run_dir / "agent_turns.tsv")
    if not turns:
        return 0.0
    return sum(1 for t in turns if float(t["anxiety"]) >= 1.0) / len(turns)


def run_sweep(
    name: str,
    out_root: Path,
    seeds: list[int] | None = None,
    population: str = "sampled60",
    syncretism: str | None = None,
) -> list[dict]:
    """1スイープを逐次実行する。

    population:
    - "sampled60": run の seed ごとに population.yaml から村を生成（母集団サンプリング）。
      村は random.Random(POPULATION_SEED_OFFSET + seed) で決定的に生成され、
      同じ seed なら scenario / delta が違っても同じ村になる（対応比較のため）。
    - "fixed8": 従来の agents.tsv（v0.4.0 の再現用。results.tsv / stats.json とも
      v0.4.0 と byte 一致することを完了基準2で要求）。
    """
    if population not in ("sampled60", "fixed8"):
        raise ValueError(f"unknown population mode: {population}")
    spec = SWEEPS[name]
    seeds = seeds if seeds is not None else spec["seeds"]
    trait = spec["trait"]
    # CLI/引数で明示されなければスイープ定義の既定値（A–D: threshold / E: graded）
    syncretism_mode = syncretism or spec.get("syncretism", "threshold")
    rows: list[dict] = []
    saturation_acc: dict[tuple, list[float]] = {}
    pop_acc: dict[tuple, list[dict]] = {}
    village_cache: dict[int, list[dict[str, str]]] = {}

    belief_rows = read_tsv(DOMAIN / "data" / "beliefs.tsv")
    pop_spec = (
        read_yaml(DOMAIN / "data" / "population.yaml") if population == "sampled60" else None
    )

    for scenario in spec["scenarios"]:
        for delta in spec["deltas"]:
            for seed in seeds:
                if trait is None:
                    run_id = f"{scenario}_s{seed:03d}"
                    adjustments = None
                else:
                    run_id = f"{scenario}_{trait}_d{delta:+.2f}_s{seed:03d}"
                    adjustments = {trait: delta}
                agents_rows = None
                if population == "sampled60":
                    if seed not in village_cache:
                        village_cache[seed] = generate_agents(
                            pop_spec, random.Random(POPULATION_SEED_OFFSET + seed), belief_rows
                        )
                    agents_rows = village_cache[seed]
                run_dir = out_root / name / "runs" / run_id
                summary = run_scenario(
                    DOMAIN,
                    f"{scenario}.yaml",
                    run_dir,
                    seed=seed,
                    trait_adjustments=adjustments,
                    agents_rows=agents_rows,
                    syncretism_mode=syncretism_mode,
                )
                if population == "sampled60":
                    _annotate_summary(run_dir, POPULATION_SEED_OFFSET + seed)
                    aux = _population_aux(agents_rows, trait, delta, belief_rows)
                    if syncretism_mode == "graded":
                        # H6 用補助値（graded スイープのみ。A–D の stats.json を変えない）
                        total_changes = summary["conversions"] + summary["syncretisms"]
                        aux["syncretism_share"] = (
                            summary["syncretisms"] / total_changes if total_changes else None
                        )
                        aux["final_secondary_holders"] = sum(
                            1 for a in summary["final_agents"] if a["secondary_belief"]
                        )
                    pop_acc.setdefault((scenario, delta), []).append(aux)
                conversions = read_tsv(run_dir / "conversions.tsv")
                metrics = compute_metrics(conversions, summary["final_agents"], scenario)
                rows.append(
                    {
                        "sweep": name,
                        "scenario": scenario,
                        "trait": trait or "none",
                        "delta": f"{delta:+.2f}",
                        "seed": seed,
                        "steps": summary["steps"],
                        "retention_rate": f"{summary['retention_rate']:.3f}",
                        **{
                            k: metrics[k]
                            for k in [
                                "conversions",
                                "syncretisms",
                                "conv_to_salvation",
                                "conv_to_practical",
                                "conv_to_other",
                                "early_conversions",
                            ]
                        },
                        "early_convert_retention": (
                            ""
                            if metrics["early_convert_retention"] is None
                            else f"{metrics['early_convert_retention']:.3f}"
                        ),
                    }
                )
                if name == "anxiety":
                    key = (scenario, delta)
                    saturation_acc.setdefault(key, []).append(_anxiety_saturation(run_dir))

    rows.sort(key=lambda r: (r["scenario"], r["trait"], float(r["delta"]), r["seed"]))

    sweep_dir = out_root / name
    sweep_dir.mkdir(parents=True, exist_ok=True)
    with (sweep_dir / "results.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    if population == "fixed8":
        # v0.4.0 実装をそのまま通す（stats.json の byte 一致を保つ）
        stats = _build_stats(name, spec, rows, saturation_acc)
    else:
        stats = _build_stats_sampled(name, spec, rows, saturation_acc, pop_acc)
    (sweep_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return rows


def _annotate_summary(run_dir: Path, population_seed: int) -> None:
    """summary.json に母集団情報を自己記述する（再現に必要な情報。codex MEDIUM-1）。"""
    path = run_dir / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["population_mode"] = "sampled60"
    summary["population_seed"] = population_seed
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _population_aux(
    agents_rows: list[dict[str, str]],
    trait: str | None,
    delta: float,
    belief_rows: list[dict[str, str]],
) -> dict:
    """stats 集計用の per-run 補助値。

    - initial_shares: その run の生成時点での信仰別エージェント数割合
      （= current_belief 列の構成比。条件内で平均して stats.json に記録する）
    - trait スイープでは、delta 適用後の実効特性の run 内 min/mean/max、
      クランプ発生数、（tolerance のみ）習合閾値以上の人数
    """
    n = len(agents_rows)
    shares = {b["id"]: 0 for b in belief_rows}
    for row in agents_rows:
        shares[row["current_belief"]] += 1
    aux: dict = {"initial_shares": {b: c / n for b, c in shares.items()}}
    if trait is not None:
        raw = [float(r[trait]) for r in agents_rows]
        eff = [max(0.0, min(1.0, v + delta)) for v in raw]
        aux["run_mean"] = sum(eff) / n
        aux["run_min"] = min(eff)
        aux["run_max"] = max(eff)
        aux["clamped_agents"] = sum(1 for v in raw if not (0.0 <= v + delta <= 1.0))
        if trait == "tolerance":
            aux["threshold_crossers"] = sum(1 for v in eff if v >= SYNCRETISM_TOLERANCE)
    return aux


def _build_stats_sampled(
    name: str, spec: dict, rows: list[dict], saturation_acc: dict, pop_acc: dict
) -> dict:
    """sampled60 用の stats。母集団が run ごとに変わるため、
    実効 trait 分布・クランプ数・閾値跨ぎ人数は全て run 間の mean±std で記録する
    （v0.4.0 の「条件ごと1値」はエージェント固定の帰結。設計 rev3 MEDIUM-7 対応）。
    """
    trait = spec["trait"]
    conditions = []
    for scenario in spec["scenarios"]:
        for delta in spec["deltas"]:
            cond_rows = [
                r
                for r in rows
                if r["scenario"] == scenario and r["delta"] == f"{delta:+.2f}"
            ]
            if not cond_rows:
                continue
            cond: dict = {
                "scenario": scenario,
                "trait": trait or "none",
                "delta": f"{delta:+.2f}",
                "n_runs": len(cond_rows),
            }
            for metric in [
                "conversions",
                "syncretisms",
                "conv_to_salvation",
                "conv_to_practical",
                "conv_to_other",
                "early_conversions",
            ]:
                cond[metric] = _mean_std([float(r[metric]) for r in cond_rows])
            cond["retention_rate"] = _mean_std([float(r["retention_rate"]) for r in cond_rows])
            retentions = [
                float(r["early_convert_retention"])
                for r in cond_rows
                if r["early_convert_retention"] != ""
            ]
            cond["early_convert_retention"] = {
                **(_mean_std(retentions) if retentions else {"mean": None, "std": None}),
                "n_with_early_conversions": len(retentions),
                "n_na": len(cond_rows) - len(retentions),
            }
            aux_list = pop_acc.get((scenario, delta), [])
            if aux_list and "syncretism_share" in aux_list[0]:
                shares = [a["syncretism_share"] for a in aux_list if a["syncretism_share"] is not None]
                cond["syncretism_share"] = {
                    **(_mean_std(shares) if shares else {"mean": None, "std": None}),
                    "n_na": len(aux_list) - len(shares),
                }
                cond["final_secondary_holders"] = _mean_std(
                    [float(a["final_secondary_holders"]) for a in aux_list]
                )
            if aux_list:
                belief_ids = sorted(aux_list[0]["initial_shares"])
                cond["initial_shares_mean"] = {
                    b: round(
                        statistics.fmean(a["initial_shares"][b] for a in aux_list), 4
                    )
                    for b in belief_ids
                }
                if trait:
                    cond["effective_trait"] = {
                        "run_mean": _mean_std([a["run_mean"] for a in aux_list]),
                        "run_min": _mean_std([a["run_min"] for a in aux_list]),
                        "run_max": _mean_std([a["run_max"] for a in aux_list]),
                        "clamped_agents": _mean_std(
                            [float(a["clamped_agents"]) for a in aux_list]
                        ),
                    }
                    if trait == "tolerance":
                        cond["effective_trait"][
                            "agents_at_or_above_syncretism_threshold"
                        ] = _mean_std([float(a["threshold_crossers"]) for a in aux_list])
            if name == "anxiety":
                sat = saturation_acc.get((scenario, delta), [])
                cond["anxiety_saturation_rate"] = (
                    round(statistics.fmean(sat), 4) if sat else None
                )
            conditions.append(cond)
    return {"sweep": name, "population": "sampled60", "conditions": conditions}


def _mean_std(values: list[float]) -> dict:
    return {
        "mean": round(statistics.fmean(values), 4),
        # 母標準偏差（pstdev）。n が小さい条件でも定義可能で決定的。
        "std": round(statistics.pstdev(values), 4),
    }


def _build_stats(name: str, spec: dict, rows: list[dict], saturation_acc: dict) -> dict:
    trait = spec["trait"]
    conditions = []
    for scenario in spec["scenarios"]:
        for delta in spec["deltas"]:
            cond_rows = [
                r
                for r in rows
                if r["scenario"] == scenario and r["delta"] == f"{delta:+.2f}"
            ]
            if not cond_rows:
                continue
            cond: dict = {
                "scenario": scenario,
                "trait": trait or "none",
                "delta": f"{delta:+.2f}",
                "n_runs": len(cond_rows),
            }
            for metric in [
                "conversions",
                "syncretisms",
                "conv_to_salvation",
                "conv_to_practical",
                "conv_to_other",
                "early_conversions",
            ]:
                cond[metric] = _mean_std([float(r[metric]) for r in cond_rows])
            cond["retention_rate"] = _mean_std([float(r["retention_rate"]) for r in cond_rows])
            retentions = [
                float(r["early_convert_retention"])
                for r in cond_rows
                if r["early_convert_retention"] != ""
            ]
            cond["early_convert_retention"] = {
                **(_mean_std(retentions) if retentions else {"mean": None, "std": None}),
                "n_with_early_conversions": len(retentions),
                "n_na": len(cond_rows) - len(retentions),
            }
            if trait:
                cond["effective_trait"] = _effective_trait_stats(trait, delta)
            if name == "anxiety":
                sat = saturation_acc.get((scenario, delta), [])
                cond["anxiety_saturation_rate"] = (
                    round(statistics.fmean(sat), 4) if sat else None
                )
            conditions.append(cond)
    return {"sweep": name, "conditions": conditions}


def judge(out_root: Path, floors: dict[str, int]) -> dict:
    """設計で宣言した判定基準を機械的に適用する。

    判定語: consistent（整合）/ inconsistent（不整合）/ inconclusive（判定不能）。
    絶対下限 floors は ABS_FLOORS（fixed8: v0.4.0 設計 rev4 / sampled60: v0.5.0 設計 rev3
    の per-capita 完全パリティ 60×0.25=15）。実装前に宣言済み。ここで動かさないこと。
    """
    verdicts: dict[str, dict] = {}

    a = json.loads((out_root / "scenario_seeds" / "stats.json").read_text(encoding="utf-8"))
    by_scenario = {c["scenario"]: c for c in a["conditions"]}
    base = by_scenario["baseline"]
    fam = by_scenario["famine"]
    rumor = by_scenario["miracle_rumor"]

    # --- H1（主検証 = スイープA）---
    fam_mean = fam["conversions"]["mean"]
    threshold_rel = base["conversions"]["mean"] + base["conversions"]["std"]
    coping = fam["conv_to_salvation"]["mean"] + fam["conv_to_practical"]["mean"]
    coping_share = coping / fam_mean if fam_mean else 0.0
    h1_a = fam_mean >= floors["h1"] and fam_mean > threshold_rel and coping_share >= 0.60
    verdicts["H1"] = {
        "verdict": "consistent" if h1_a else "inconsistent",
        "evidence": {
            "famine_mean_conversions": fam_mean,
            "absolute_floor": floors["h1"],
            "baseline_mean_plus_1std": round(threshold_rel, 4),
            "coping_share_of_famine_conversions": round(coping_share, 4),
            "required_coping_share": 0.60,
        },
    }

    # --- H1 補助（スイープC、baseline 側）。全条件ゼロ改宗なら判定不能 ---
    c = json.loads((out_root / "anxiety" / "stats.json").read_text(encoding="utf-8"))
    c_base = [cond for cond in c["conditions"] if cond["scenario"] == "baseline"]
    c_base.sort(key=lambda cond: float(cond["delta"]))
    series = [cond["conv_to_salvation"]["mean"] + cond["conv_to_practical"]["mean"] for cond in c_base]
    if all(v == 0 for v in series):
        verdicts["H1_aux_anxiety"] = {
            "verdict": "inconclusive",
            "evidence": {
                "baseline_coping_conversions_by_delta": series,
                "note": "全条件ゼロ改宗。設計時の事前見積もり通り。"
                "本モデルでは不安は改宗の駆動因子ではなく変調因子（イベント由来の gap 形成が駆動）。",
            },
        }
    else:
        decreases = sum(1 for i in range(len(series) - 1) if series[i + 1] < series[i])
        verdicts["H1_aux_anxiety"] = {
            "verdict": "consistent" if decreases <= 1 else "inconsistent",
            "evidence": {
                "baseline_coping_conversions_by_delta": series,
                "adjacent_decreases": decreases,
                "max_allowed_decreases": 1,
            },
        }

    # --- H2（スイープD）---
    d = json.loads((out_root / "practical_need" / "stats.json").read_text(encoding="utf-8"))
    h2: dict = {"evidence": {}}
    statuses = []
    for scenario in ["baseline", "famine"]:
        conds = [cond for cond in d["conditions"] if cond["scenario"] == scenario]
        conds.sort(key=lambda cond: float(cond["delta"]))
        series = [cond["conv_to_practical"]["mean"] for cond in conds]
        if all(v == 0 for v in series):
            statuses.append("inconclusive")
        else:
            decreases = sum(1 for i in range(len(series) - 1) if series[i + 1] < series[i])
            statuses.append("consistent" if decreases <= 1 else "inconsistent")
        h2["evidence"][scenario] = {"practical_conversions_by_delta": series}
    if statuses == ["consistent", "consistent"]:
        h2["verdict"] = "consistent"
    elif "consistent" in statuses:
        h2["verdict"] = "conditionally_consistent"
        h2["evidence"]["note"] = "片方のシナリオのみ単調増加（設計基準により条件付き整合）"
    elif set(statuses) == {"inconclusive"}:
        h2["verdict"] = "inconclusive"
    else:
        h2["verdict"] = "inconsistent"
    h2["evidence"]["per_scenario_status"] = dict(zip(["baseline", "famine"], statuses))
    verdicts["H2"] = h2

    # --- H5（スイープA、miracle_rumor のみ）---
    early_mean = rumor["early_conversions"]["mean"]
    retention = rumor["early_convert_retention"]["mean"]
    if retention is None:
        verdicts["H5"] = {
            "verdict": "inconclusive",
            "evidence": {"note": "早期改宗が発生した run がない"},
        }
    else:
        h5 = early_mean >= floors["h5"] and retention <= 0.5
        verdicts["H5"] = {
            "verdict": "consistent" if h5 else "inconsistent",
            "evidence": {
                "miracle_rumor_early_conversions_mean": early_mean,
                "required_min": floors["h5"],
                "early_convert_retention_mean": retention,
                "required_max": 0.5,
                "confound_note": "miracle_rumor シナリオには step20 shrine_patronage / "
                "step34 temple_corruption が含まれる。揺り戻しは噂の自然減衰と権威イベントの複合",
            },
        }

    # --- H3 / H4: 設計上スイープなし ---
    verdicts["H3"] = {"verdict": "inconclusive", "evidence": {"note": "専用スイープなし（未検証）"}}
    verdicts["H4"] = {"verdict": "inconclusive", "evidence": {"note": "専用スイープなし（未検証）"}}

    # --- H6（v0.6.0、スイープ E = graded 習合メカニズム）---
    e_stats_path = out_root / "tolerance_graded" / "stats.json"
    if e_stats_path.exists():
        verdicts["H6"] = _judge_h6(json.loads(e_stats_path.read_text(encoding="utf-8")))
    else:
        verdicts["H6"] = {
            "verdict": "inconclusive",
            "evidence": {
                "note": "graded 習合メカニズムのスイープ（tolerance_graded）が未実行。"
                "threshold メカニズムでは tolerance >= 0.65 の二値ゲートが習合を直接決める"
                "トートロジーのため検証不能"
            },
        }
    return verdicts


def _judge_h6(stats: dict) -> dict:
    """H6 判定（設計 rev3 で宣言した (a)(b)(c) 基準。famine 側が判定対象）。

    (a) syncretisms の条件平均が tolerance デルタに対し単調増加（隣接減少1箇所以下）
    (b) syncretism_share も単調増加（習合が改宗を置き換えていること）
    (c) 効果量下限: syncretisms の最大条件平均 >= H6_SYNC_FLOOR（=3、村の5%）
    """
    conds = [c for c in stats["conditions"] if c["scenario"] == "famine"]
    conds.sort(key=lambda c: float(c["delta"]))
    sync_series = [c["syncretisms"]["mean"] for c in conds]
    conv_series = [c["conversions"]["mean"] for c in conds]
    share_series = [c["syncretism_share"]["mean"] for c in conds]

    if all((s or 0) + c < 1 for s, c in zip(sync_series, conv_series)):
        return {
            "verdict": "inconclusive",
            "evidence": {"note": "belief-change イベントがほぼゼロ", "syncretisms": sync_series},
        }

    def monotonic(series: list) -> bool:
        vals = [v if v is not None else 0.0 for v in series]
        return sum(1 for i in range(len(vals) - 1) if vals[i + 1] < vals[i]) <= 1

    a = monotonic(sync_series)
    b = monotonic(share_series)
    c = max(sync_series) >= H6_SYNC_FLOOR
    passed = sum([a, b, c])
    verdict = "consistent" if passed == 3 else ("inconsistent" if passed == 0 else "conditionally_consistent")
    return {
        "verdict": verdict,
        "evidence": {
            "criteria": {"a_syncretisms_monotonic": a, "b_share_monotonic": b, "c_effect_floor": c},
            "famine_syncretisms_by_delta": sync_series,
            "famine_conversions_by_delta": conv_series,
            "famine_syncretism_share_by_delta": share_series,
            "effect_floor": H6_SYNC_FLOOR,
            "note": "判定対象はマクロな置換パターン。ミクロルールに tolerance が入っている事実は判定根拠にしない",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sweep",
        default="all",
        choices=["all", *SWEEPS.keys()],
    )
    parser.add_argument(
        "--population",
        default="sampled60",
        choices=["sampled60", "fixed8"],
        help="sampled60: seedごとに60人の村を生成（v0.5.0）/ fixed8: 従来のagents.tsv（v0.4.0再現）",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="省略時は sampled60 → outputs/sweeps、fixed8 → outputs/sweeps_fixed8",
    )
    parser.add_argument(
        "--syncretism",
        default=None,
        choices=["threshold", "graded"],
        help="習合メカニズムの上書き。省略時はスイープ定義の既定値（A–D: threshold / E: graded）",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="実行後に設計宣言済みの基準で仮説判定を出力する（要: 全スイープの stats.json）",
    )
    args = parser.parse_args()

    if args.output_dir:
        out_root = Path(args.output_dir)
    else:
        subdir = "sweeps" if args.population == "sampled60" else "sweeps_fixed8"
        out_root = ROOT / "outputs" / subdir
    names = list(SWEEPS.keys()) if args.sweep == "all" else [args.sweep]
    for name in names:
        rows = run_sweep(name, out_root, population=args.population, syncretism=args.syncretism)
        print(f"sweep {name}: {len(rows)} runs ({args.population}) -> {out_root / name / 'results.tsv'}")

    if args.judge:
        verdicts = judge(out_root, ABS_FLOORS[args.population])
        print(json.dumps(verdicts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
