"""スイープ結果（results.tsv / stats.json）から README 用の図4枚を生成する。

ラベルは英語表記（CIや他環境での日本語フォント問題を避けるため）。
日本語の説明は README 側に書く。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read_results(sweep_dir: Path) -> list[dict]:
    with (sweep_dir / "results.tsv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _read_stats(sweep_dir: Path) -> dict:
    return json.loads((sweep_dir / "stats.json").read_text(encoding="utf-8"))


def _conditions(stats: dict, scenario: str) -> list[dict]:
    conds = [c for c in stats["conditions"] if c["scenario"] == scenario]
    conds.sort(key=lambda c: float(c["delta"]))
    return conds


def fig1_scenarios(out_root: Path, fig_dir: Path) -> None:
    rows = _read_results(out_root / "scenario_seeds")
    scenarios = ["baseline", "famine", "miracle_rumor"]
    data = [
        [int(r["conversions"]) for r in rows if r["scenario"] == s] for s in scenarios
    ]
    retention = []
    for s in scenarios:
        vals = [
            float(r["early_convert_retention"])
            for r in rows
            if r["scenario"] == s and r["early_convert_retention"] != ""
        ]
        retention.append(sum(vals) / len(vals) if vals else float("nan"))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.boxplot(data, tick_labels=scenarios)
    ax1.set_ylabel("conversions per run")
    ax1.set_title("Conversions by scenario (50 seeds)")
    ax1.grid(axis="y", alpha=0.3)

    ax2.bar(scenarios, retention, color=["#999", "#999", "#c0392b"])
    ax2.set_ylabel("early-convert retention (mean)")
    ax2.set_ylim(0, 1)
    ax2.set_title("Do early converts keep the new belief?")
    ax2.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig1_scenarios.png", dpi=150)
    plt.close(fig)


def _line_by_delta(ax, stats: dict, scenario: str, metric_fn, label: str, color: str) -> None:
    conds = _conditions(stats, scenario)
    xs = [float(c["delta"]) for c in conds]
    ys = [metric_fn(c) for c in conds]
    errs = [metric_fn(c, "std") for c in conds]
    ax.errorbar(xs, ys, yerr=errs, marker="o", capsize=3, label=label, color=color)


def fig2_anxiety(out_root: Path, fig_dir: Path) -> None:
    stats = _read_stats(out_root / "anxiety")

    def coping(c, key="mean"):
        return c["conv_to_salvation"][key] + c["conv_to_practical"][key]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    _line_by_delta(ax, stats, "baseline", coping, "baseline", "#2980b9")
    _line_by_delta(ax, stats, "famine", coping, "famine (saturation caveat)", "#c0392b")
    sat = {
        c["delta"]: c.get("anxiety_saturation_rate")
        for c in stats["conditions"]
        if c["scenario"] == "famine"
    }
    ax.set_xlabel("anxiety delta (additive, clamped to [0,1])")
    ax.set_ylabel("salvation+practical conversions (mean)")
    ax.set_title(
        "Anxiety sweep: salvation+practical conversions by delta\n"
        f"(famine anxiety-saturation rate by delta: "
        f"{', '.join(f'{k}:{v:.0%}' for k, v in sorted(sat.items()))})",
        fontsize=9,
    )
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig2_anxiety.png", dpi=150)
    plt.close(fig)


def fig3_practical(out_root: Path, fig_dir: Path) -> None:
    stats = _read_stats(out_root / "practical_need")

    def practical(c, key="mean"):
        return c["conv_to_practical"][key]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    _line_by_delta(ax, stats, "baseline", practical, "baseline", "#2980b9")
    _line_by_delta(ax, stats, "famine", practical, "famine", "#c0392b")
    ax.set_xlabel("practical_benefit_need delta (additive, clamped to [0,1])")
    ax.set_ylabel("conversions to practical beliefs (mean)")
    ax.set_title("Practical-need sweep: conversions to practical beliefs by delta")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig3_practical.png", dpi=150)
    plt.close(fig)


def fig4_tolerance(out_root: Path, fig_dir: Path) -> None:
    stats = _read_stats(out_root / "tolerance")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, scenario in zip(axes, ["baseline", "famine"]):
        conds = _conditions(stats, scenario)
        xs = [float(c["delta"]) for c in conds]
        ax.errorbar(
            xs,
            [c["conversions"]["mean"] for c in conds],
            yerr=[c["conversions"]["std"] for c in conds],
            marker="o",
            capsize=3,
            label="conversions",
            color="#c0392b",
        )
        ax.errorbar(
            xs,
            [c["syncretisms"]["mean"] for c in conds],
            yerr=[c["syncretisms"]["std"] for c in conds],
            marker="s",
            capsize=3,
            label="syncretisms",
            color="#27ae60",
        )
        ax2 = ax.twinx()
        ax2.plot(
            xs,
            [c["retention_rate"]["mean"] for c in conds],
            marker="^",
            linestyle="--",
            color="#7f8c8d",
            label="retention rate (right)",
        )
        ax2.set_ylim(0, 1.05)
        if scenario == "famine":
            ax2.set_ylabel("retention rate")
        # 閾値跨ぎ人数の注釈。sampled60 では村が seed ごとに変わるため mean±std、
        # fixed8（v0.4.0 スキーマ）では条件ごとの1値
        total_agents = 60 if stats.get("population") == "sampled60" else 8
        labels = []
        for c in conds:
            cross = c["effective_trait"]["agents_at_or_above_syncretism_threshold"]
            if isinstance(cross, dict):
                labels.append(f"{cross['mean']:.1f}±{cross['std']:.1f}")
            else:
                labels.append(str(cross))
        for x, text in zip(xs, labels):
            ax.annotate(
                f"{text}/{total_agents}", (x, ax.get_ylim()[1] * 0.92), ha="center", fontsize=7
            )
        ax.set_xlabel("tolerance delta")
        ax.set_title(
            f"{scenario} (n/{total_agents} = agents over syncretism threshold 0.65)", fontsize=9
        )
        ax.grid(alpha=0.3)
        if scenario == "baseline":
            ax.set_ylabel("events per run (mean)")
            handles1, labels1 = ax.get_legend_handles_labels()
            handles2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(handles1 + handles2, labels1 + labels2, fontsize=8)
    fig.suptitle("Tolerance sweep (sensitivity analysis — threshold-gated by design)", fontsize=10)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig4_tolerance.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweeps-dir", default=str(ROOT / "outputs" / "sweeps"))
    args = parser.parse_args()
    out_root = Path(args.sweeps_dir)
    fig_dir = out_root / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig1_scenarios(out_root, fig_dir)
    fig2_anxiety(out_root, fig_dir)
    fig3_practical(out_root, fig_dir)
    fig4_tolerance(out_root, fig_dir)
    for p in sorted(fig_dir.glob("*.png")):
        print(p)


if __name__ == "__main__":
    main()
