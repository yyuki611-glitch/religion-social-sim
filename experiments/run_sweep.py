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
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim_core.domain_pack import read_tsv  # noqa: E402
from sim_core.engine import SYNCRETISM_TOLERANCE, run_scenario  # noqa: E402

DOMAIN = ROOT / "domain_packs" / "japan_religion"

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
}

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


def run_sweep(name: str, out_root: Path, seeds: list[int] | None = None) -> list[dict]:
    spec = SWEEPS[name]
    seeds = seeds if seeds is not None else spec["seeds"]
    trait = spec["trait"]
    rows: list[dict] = []
    saturation_acc: dict[tuple, list[float]] = {}

    for scenario in spec["scenarios"]:
        for delta in spec["deltas"]:
            for seed in seeds:
                if trait is None:
                    run_id = f"{scenario}_s{seed:03d}"
                    adjustments = None
                else:
                    run_id = f"{scenario}_{trait}_d{delta:+.2f}_s{seed:03d}"
                    adjustments = {trait: delta}
                run_dir = out_root / name / "runs" / run_id
                summary = run_scenario(
                    DOMAIN,
                    f"{scenario}.yaml",
                    run_dir,
                    seed=seed,
                    trait_adjustments=adjustments,
                )
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

    stats = _build_stats(name, spec, rows, saturation_acc)
    (sweep_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return rows


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


def judge(out_root: Path) -> dict:
    """tasks/todo.md（rev4）で宣言した判定基準を機械的に適用する。

    判定語: consistent（整合）/ inconsistent（不整合）/ inconclusive（判定不能）。
    閾値は実装前に設計で宣言済み。ここで動かさないこと。
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
    h1_a = fam_mean >= 2 and fam_mean > threshold_rel and coping_share >= 0.60
    verdicts["H1"] = {
        "verdict": "consistent" if h1_a else "inconsistent",
        "evidence": {
            "famine_mean_conversions": fam_mean,
            "absolute_floor": 2,
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
        h5 = early_mean >= 2 and retention <= 0.5
        verdicts["H5"] = {
            "verdict": "consistent" if h5 else "inconsistent",
            "evidence": {
                "miracle_rumor_early_conversions_mean": early_mean,
                "required_min": 2,
                "early_convert_retention_mean": retention,
                "required_max": 0.5,
                "confound_note": "miracle_rumor シナリオには step20 shrine_patronage / "
                "step34 temple_corruption が含まれる。揺り戻しは噂の自然減衰と権威イベントの複合",
            },
        }

    # --- H3 / H4 / H6: 設計上スイープなし or トートロジー ---
    verdicts["H3"] = {"verdict": "inconclusive", "evidence": {"note": "専用スイープなし（未検証）"}}
    verdicts["H4"] = {"verdict": "inconclusive", "evidence": {"note": "専用スイープなし（未検証）"}}
    verdicts["H6"] = {
        "verdict": "inconclusive",
        "evidence": {
            "note": "エンジンが tolerance >= 0.65 で習合を直接ゲートしており、"
            "tolerance を上げると習合が増えるのはモデル定義の再現（トートロジー）。"
            "スイープ tolerance は感度分析として報告"
        },
    }
    return verdicts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sweep",
        default="all",
        choices=["all", *SWEEPS.keys()],
    )
    parser.add_argument("--output-dir", default=str(ROOT / "outputs" / "sweeps"))
    parser.add_argument(
        "--judge",
        action="store_true",
        help="実行後に設計宣言済みの基準で仮説判定を出力する（要: 全スイープの stats.json）",
    )
    args = parser.parse_args()

    out_root = Path(args.output_dir)
    names = list(SWEEPS.keys()) if args.sweep == "all" else [args.sweep]
    for name in names:
        rows = run_sweep(name, out_root)
        print(f"sweep {name}: {len(rows)} runs -> {out_root / name / 'results.tsv'}")

    if args.judge:
        verdicts = judge(out_root)
        print(json.dumps(verdicts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
