"""実行結果からスタンドアロンのブラウザビューア（viewer.html）を生成する。

使い方:
    .venv/bin/python experiments/render_viewer.py \
        --run outputs/runs/famine_dev \
        --domain domain_packs/japan_religion

生成された viewer.html はダブルクリック（file://）でそのまま開ける。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim_core.domain_pack import load_domain_pack, read_tsv

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "visualization" / "viewer_template.html"


def build_data(run_dir: Path, domain_dir: Path) -> dict:
    pack = load_domain_pack(domain_dir)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    beliefs = {
        row["id"]: {"label_ja": row.get("label_ja") or row["label"]}
        for row in read_tsv(pack.data_path("beliefs.tsv"))
    }
    agents = {
        row["id"]: {"label_ja": row.get("label_ja") or row["label"], "role": row["role"]}
        for row in read_tsv(pack.data_path("agents.tsv"))
    }
    places = [
        {
            "id": row["id"],
            "label_ja": row.get("label_ja") or row["label"],
            "type": row["type"],
            "x": float(row["x"]),
            "y": float(row["y"]),
            "affinity": row["affinity"],
        }
        for row in read_tsv(pack.data_path("places.tsv"))
    ]
    event_labels = {
        row["id"]: row.get("label_ja") or row["label"]
        for row in read_tsv(pack.data_path("events.tsv"))
    }

    agent_turns = [
        {
            "step": int(r["step"]),
            "agent_id": r["agent_id"],
            "belief": r["belief"],
            "secondary_belief": r["secondary_belief"] or None,
            "strength": float(r["strength"]),
            "anxiety": float(r["anxiety"]),
            "openness": float(r["openness"]),
            "top_pull": r["top_pull"],
            "gap": float(r["gap"]),
        }
        for r in read_tsv(run_dir / "agent_turns.tsv")
    ]
    belief_shares = [
        {"step": int(r["step"]), "belief_id": r["belief_id"], "adherents": int(r["adherents"])}
        for r in read_tsv(run_dir / "belief_shares.tsv")
    ]
    conversions = [
        {
            "step": int(r["step"]),
            "agent_id": r["agent_id"],
            "kind": r["kind"],
            "from_belief": r["from_belief"],
            "to_belief": r["to_belief"],
        }
        for r in read_tsv(run_dir / "conversions.tsv")
    ]
    events_log = [
        {
            "step": int(r["step"]),
            "event_id": r["event_id"],
            "type": r["type"],
            "label_ja": event_labels.get(r["event_id"], r["event_id"]),
        }
        for r in read_tsv(run_dir / "events_log.tsv")
    ]

    scenario_labels = {"baseline": "平時の村", "famine": "飢饉の村", "miracle_rumor": "奇跡の噂"}
    return {
        "title": "日本の宗教伝播シミュレーション",
        "scenario": summary["scenario"],
        "scenario_label": scenario_labels.get(summary["scenario"], summary["scenario"]),
        "seed": summary["seed"],
        "steps": summary["steps"],
        "n_conversions": summary["conversions"],
        "retention_rate": summary["retention_rate"],
        "beliefs": beliefs,
        "agents": agents,
        "places": places,
        "agent_turns": agent_turns,
        "belief_shares": belief_shares,
        "conversions": conversions,
        "events_log": events_log,
    }


def render(run_dir: str | Path, domain_dir: str | Path) -> Path:
    run = Path(run_dir)
    data = build_data(run, Path(domain_dir))
    template = TEMPLATE.read_text(encoding="utf-8")
    html = template.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    out = run / "viewer.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="実行結果ディレクトリ（summary.json があること）")
    parser.add_argument("--domain", default="domain_packs/japan_religion")
    args = parser.parse_args()
    out = render(args.run, args.domain)
    print(f"viewer: {out}")


if __name__ == "__main__":
    main()
