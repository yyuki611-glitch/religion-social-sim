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

from sim_core.domain_pack import load_domain_pack, read_tsv, read_yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "visualization" / "viewer_template.html"


def build_data(run_dir: Path, domain_dir: Path) -> dict:
    pack = load_domain_pack(domain_dir)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    beliefs = {
        row["id"]: {"label_ja": row.get("label_ja") or row["label"]}
        for row in read_tsv(pack.data_path("beliefs.tsv"))
    }
    tsv_agents = {
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

    turn_rows = read_tsv(run_dir / "agent_turns.tsv")
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
        for r in turn_rows
    ]

    # agents 辞書は「run に実際に登場する村人」だけで作る。
    # 母集団サンプリング run（v0.5.0+）の村人 ID は agents.tsv（8人）に存在せず、
    # 逆に agents.tsv の8人を混ぜると、テンプレートの描画ループが turns を持たない
    # 村人で落ちて地図が真っ暗になる（v1.0.0 で実害）。
    # 名前は agents.tsv に居ればそれを使い、居なければ agent_turns の label から補完。
    # population.yaml のロール label → label_ja で日本語化する（例: Farmer 01 → 農民01）。
    run_labels: dict[str, str] = {}
    for r in turn_rows:
        if r["agent_id"] not in run_labels:
            run_labels[r["agent_id"]] = r["label"]
    role_ja = {}
    pop_path = pack.data_path("population.yaml")
    if Path(pop_path).exists():
        spec = read_yaml(pop_path)
        role_ja = {role["label"]: role["label_ja"] for role in spec["roles"]}
    agents = {}
    for aid, label in run_labels.items():
        if aid in tsv_agents:
            agents[aid] = tsv_agents[aid]
            continue
        label_ja = label
        for en, ja in role_ja.items():
            if label.startswith(en + " "):
                label_ja = ja + label[len(en) + 1 :]
                break
        agents[aid] = {"label_ja": label_ja, "role": ""}
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
